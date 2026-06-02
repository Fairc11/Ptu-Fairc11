param(
    [switch]$RestoreLatest
)

$ErrorActionPreference = "Stop"

$localAppData = [Environment]::GetFolderPath("LocalApplicationData")
$backupRoot = Join-Path $localAppData "PtuSmokeBackups"
$manifest = Join-Path $backupRoot "latest.json"

function Move-IfExists {
    param(
        [Parameter(Mandatory=$true)][string]$Source,
        [Parameter(Mandatory=$true)][string]$Destination
    )
    if (Test-Path -LiteralPath $Source) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
        Move-Item -LiteralPath $Source -Destination $Destination
        Write-Host "Moved: $Source -> $Destination"
        return $true
    }
    Write-Host "Not found: $Source"
    return $false
}

function Restore-IfExists {
    param(
        [Parameter(Mandatory=$true)][string]$Backup,
        [Parameter(Mandatory=$true)][string]$Target
    )
    if (-not (Test-Path -LiteralPath $Backup)) {
        Write-Host "Backup not found: $Backup"
        return
    }
    if (Test-Path -LiteralPath $Target) {
        $ts = Get-Date -Format "yyyyMMdd_HHmmss"
        $currentBackup = "$Target.current_$ts"
        Move-Item -LiteralPath $Target -Destination $currentBackup
        Write-Host "Current runtime moved aside: $Target -> $currentBackup"
    }
    Move-Item -LiteralPath $Backup -Destination $Target
    Write-Host "Restored: $Backup -> $Target"
}

if ($RestoreLatest) {
    if (-not (Test-Path -LiteralPath $manifest)) {
        Write-Error "No restore manifest found: $manifest"
    }
    $m = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    Restore-IfExists -Backup $m.ptuBackup -Target (Join-Path $localAppData "Ptu")
    Restore-IfExists -Backup $m.playwrightBackup -Target (Join-Path $localAppData "ms-playwright")
    Write-Host "Restore complete."
    exit 0
}

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$batchDir = Join-Path $backupRoot $ts
New-Item -ItemType Directory -Force -Path $batchDir | Out-Null

$ptu = Join-Path $localAppData "Ptu"
$playwright = Join-Path $localAppData "ms-playwright"
$ptuBackup = Join-Path $batchDir "Ptu"
$playwrightBackup = Join-Path $batchDir "ms-playwright"

Move-IfExists -Source $ptu -Destination $ptuBackup | Out-Null
Move-IfExists -Source $playwright -Destination $playwrightBackup | Out-Null

@{
    createdAt = (Get-Date).ToString("s")
    ptuBackup = $ptuBackup
    playwrightBackup = $playwrightBackup
} | ConvertTo-Json | Set-Content -LiteralPath $manifest -Encoding UTF8

Write-Host ""
Write-Host "Clean runtime is ready."
Write-Host "Run the installer/build now, then test first-start QR login and logs."
Write-Host "To restore latest backup:"
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\clean_runtime_for_smoke.ps1 -RestoreLatest"
