@echo off
chcp 65001 >nul
title Ptu

cd /d "%~dp0"

echo ============================================
echo   Ptu - 一键启动
echo ============================================
echo.

:: 检查 Playwright 浏览器是否完整
python -c "from playwright.sync_api import sync_playwright; sync_playwright().__enter__().chromium.launch(headless=True).close()" 2>nul
if %errorlevel% neq 0 (
    echo [*] 首次使用，正在安装浏览器组件...
    python -m playwright install
    echo.
)

echo [*] 清理旧服务...
for /f "tokens=5" %%a in ('netstat -ano ^| find ":8000 " ^| find "LISTENING"') do taskkill /F /PID %%a 2>nul

echo [*] 启动中...
python run.py

pause
