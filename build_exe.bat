@echo off
chcp 65001 >nul
title Ptu - 打包构建

echo ============================================
echo   Ptu - 打包为 Windows EXE
echo ============================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] 错误: 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

:: 检查依赖
echo [*] 检查依赖...
pip install pyinstaller pywebview 2>nul | findstr /i "successfully" >nul

:: 执行打包
echo [*] 开始打包，这可能需要几分钟...
pyinstaller build.spec

if %errorlevel% equ 0 (
    echo.
    echo [OK] 打包成功!
    echo.
    echo     输出文件: dist\Ptu.exe
    echo.
    echo     注意: 首次运行需要安装 Microsoft Edge WebView2
    echo     https://developer.microsoft.com/zh-cn/microsoft-edge/webview2/
    echo.
) else (
    echo.
    echo [!] 打包失败，请检查错误信息
    echo.
)

pause
