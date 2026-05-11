# FFmpeg Installer for Windows
# Downloads FFmpeg essentials build and adds to PATH

$ffmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
$zipPath = "$env:TEMP\ffmpeg.zip"
$extractPath = "$env:LOCALAPPDATA\ffmpeg"

Write-Host "Downloading FFmpeg..." -ForegroundColor Green
Invoke-WebRequest -Uri $ffmpegUrl -OutFile $zipPath -UseBasicParsing

Write-Host "Extracting..." -ForegroundColor Green
Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force

# Find the bin directory
$binDir = Get-ChildItem -Path $extractPath -Recurse -Directory -Filter "bin" | Select-Object -First 1
if (-not $binDir) {
    $ffmpegDir = Get-ChildItem -Path $extractPath -Directory | Select-Object -First 1
    $binDir = Join-Path $ffmpegDir.FullName "bin"
}

# Add to PATH
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$binDir*") {
    [Environment]::SetEnvironmentVariable("PATH", "$userPath;$binDir", "User")
    Write-Host "Added FFmpeg to user PATH" -ForegroundColor Green
}

Write-Host "FFmpeg installed successfully!" -ForegroundColor Green
Write-Host "FFmpeg path: $binDir" -ForegroundColor Green
Write-Host "Please restart your terminal for PATH changes to take effect." -ForegroundColor Yellow

# Clean up
Remove-Item $zipPath -Force
