@echo off
chcp 65001 >nul
title Ptu - 安装必要组件

echo ============================================
echo   正在安装必要组件，请稍候...
echo ============================================
echo.

cd /d "%~dp0"

:: 1. 安装 Chromium（用于抓取抖音数据）
echo [1/2] 安装 Chromium 浏览器内核...
python -m playwright install chromium

:: 2. 检查 FFmpeg
echo [2/2] 检查 FFmpeg...
where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
    echo 未找到 FFmpeg，运行安装脚本...
    powershell -ExecutionPolicy Bypass -File install_ffmpeg.ps1
) else (
    echo FFmpeg 已安装 OK
)

echo.
echo ============================================
echo   安装完成！现在可以运行 一键启动.bat 了
echo ============================================
pause
