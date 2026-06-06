param(
    [string]$InstallDir = "",
    [switch]$StartApp,
    [int]$WaitSeconds = 45
)

$ErrorActionPreference = "Stop"

function Resolve-InstallDir {
    param([string]$Requested)

    if ($Requested) {
        return (Resolve-Path -LiteralPath $Requested).Path
    }

    $candidates = @()
    if ($env:ProgramFiles) {
        $candidates += (Join-Path $env:ProgramFiles "Ptu")
    }
    $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    if ($programFilesX86) {
        $candidates += (Join-Path $programFilesX86 "Ptu")
    }
    $candidates = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    if ($candidates.Count -gt 0) {
        return $candidates[0]
    }

    throw "Ptu install directory not found. Pass -InstallDir explicitly."
}

function Add-Check {
    param(
        [System.Collections.Generic.List[object]]$Results,
        [string]$Name,
        [bool]$Pass,
        [string]$Detail = "",
        [bool]$Critical = $true
    )

    $Results.Add([pscustomobject]@{
        Name = $Name
        Pass = $Pass
        Detail = $Detail
        Critical = $Critical
    }) | Out-Null
}

function Test-CommandExitZero {
    param([string]$ExePath)

    try {
        $p = Start-Process -FilePath $ExePath -ArgumentList "-version" -WindowStyle Hidden -PassThru -Wait
        return ($p.ExitCode -eq 0)
    } catch {
        return $false
    }
}

function Test-HttpReady {
    param(
        [int]$DeadlineSeconds
    )

    $deadline = (Get-Date).AddSeconds($DeadlineSeconds)
    $lastError = ""
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 700
        foreach ($port in 18080..18085) {
            try {
                $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec 2
                if ($resp.StatusCode -eq 200) {
                    return "http://127.0.0.1:$port/"
                }
            } catch {
                $lastError = $_.Exception.Message
            }
        }
    }
    if ($lastError) {
        Write-Host ("Last HTTP probe error: {0}" -f $lastError)
    }
    return ""
}

function Stop-PtuInstallProcesses {
    param([string]$ExePath)

    try {
        $target = (Resolve-Path -LiteralPath $ExePath).Path
    } catch {
        return
    }
    Get-Process Ptu -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $target } |
        Stop-Process -Force -ErrorAction SilentlyContinue
}

$results = [System.Collections.Generic.List[object]]::new()
$root = Resolve-InstallDir -Requested $InstallDir
$internal = Join-Path $root "_internal"
$ptuExe = Join-Path $root "Ptu.exe"
$ffmpeg = Join-Path $root "ffmpeg.exe"
$ffprobe = Join-Path $root "ffprobe.exe"
$thirdParty = Join-Path $root "THIRD_PARTY_NOTICES.md"
$chromium = Join-Path $internal "ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe"
$versionFile = Join-Path $internal "backend\app\version.py"
$envFile = Join-Path $internal "backend\.env"
$cookiesFile = Join-Path $internal "backend\cookies.yaml"
$logDir = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "Ptu\日志"

Write-Host "Ptu v1.5 installed smoke check"
Write-Host "InstallDir: $root"
Write-Host ""

Add-Check $results "Ptu.exe exists" (Test-Path -LiteralPath $ptuExe) $ptuExe
Add-Check $results "ffmpeg.exe exists beside Ptu.exe" (Test-Path -LiteralPath $ffmpeg) $ffmpeg
Add-Check $results "ffmpeg.exe runs" (Test-CommandExitZero -ExePath $ffmpeg) $ffmpeg
Add-Check $results "ffprobe.exe exists beside Ptu.exe" (Test-Path -LiteralPath $ffprobe) $ffprobe
Add-Check $results "ffprobe.exe runs" (Test-CommandExitZero -ExePath $ffprobe) $ffprobe
Add-Check $results "Chromium headless shell bundled" (Test-Path -LiteralPath $chromium) $chromium
Add-Check $results "THIRD_PARTY_NOTICES.md bundled" (Test-Path -LiteralPath $thirdParty) $thirdParty
Add-Check $results ".env not bundled" (-not (Test-Path -LiteralPath $envFile)) $envFile
Add-Check $results "cookies.yaml not bundled" (-not (Test-Path -LiteralPath $cookiesFile)) $cookiesFile

$versionOk = $false
if (Test-Path -LiteralPath $versionFile) {
    $versionText = Get-Content -LiteralPath $versionFile -Raw -Encoding UTF8
    $versionOk = ($versionText -match 'VERSION\s*=\s*"1\.5\.0"')
}
Add-Check $results "bundled backend version is 1.5.0" $versionOk $versionFile

if ($StartApp) {
    $process = $null
    $url = ""
    try {
        Stop-PtuInstallProcesses -ExePath $ptuExe
        Start-Sleep -Milliseconds 500
        $process = Start-Process -FilePath $ptuExe -PassThru
        $url = Test-HttpReady -DeadlineSeconds $WaitSeconds
    } finally {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 500
        }
        Stop-PtuInstallProcesses -ExePath $ptuExe
    }
    Add-Check $results "Ptu starts and serves local page" ($url -ne "") $url
}

$logExists = Test-Path -LiteralPath $logDir
Add-Check $results "runtime log folder exists after launch" $logExists $logDir $false

$failed = @($results | Where-Object { -not $_.Pass -and $_.Critical })
foreach ($item in $results) {
    if ($item.Pass) {
        $status = "[OK]"
    } elseif ($item.Critical) {
        $status = "[FAIL]"
    } else {
        $status = "[WARN]"
    }
    if ($item.Detail) {
        Write-Host ("{0} {1} - {2}" -f $status, $item.Name, $item.Detail)
    } else {
        Write-Host ("{0} {1}" -f $status, $item.Name)
    }
}

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host ("Smoke check failed: {0} item(s)" -f $failed.Count)
    exit 1
}

Write-Host "Smoke check passed."
exit 0
