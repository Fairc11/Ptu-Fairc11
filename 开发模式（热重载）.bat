@echo off
chcp 65001 >nul
title Ptu 开发模式（热重载）
cd /d "%~dp0"
echo ============================================
echo   Ptu 开发模式 - 带热重载
echo   改了代码后刷新浏览器即可
echo   按 Ctrl+C 停止
echo ============================================
echo.
python run.py
pause
