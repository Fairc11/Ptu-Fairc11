@echo off
setlocal
chcp 65001 >nul
title Ptu build + installer

echo ============================================
echo   Ptu Windows build
echo   Internal: dist\Ptu\Ptu.exe + _internal\
echo   Release: installer\Ptu_Setup_vVERSION.exe
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ first.
    goto fail
)

for /f "tokens=2 delims== " %%V in ('findstr /R "^VERSION" backend\app\version.py') do set "APP_VERSION=%%~V"
if not defined APP_VERSION (
    echo [ERROR] Cannot read VERSION from backend\app\version.py
    goto fail
)

echo [INFO] Version: %APP_VERSION%
echo.

echo [INFO] Cleaning old processes and build folders...
taskkill /f /im Ptu.exe 2>nul
taskkill /f /im runw.exe 2>nul
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

echo [INFO] Running release checks...
python scripts\release_check.py
if errorlevel 1 (
    echo [ERROR] Release check failed.
    goto fail
)

echo [INFO] Running PyInstaller...
pyinstaller build.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    goto fail
)

echo.
echo [OK] PyInstaller output: dist\Ptu\Ptu.exe
echo.

set "ISCC="
where ISCC.exe >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%I in ('where ISCC.exe') do (
        if not defined ISCC set "ISCC=%%I"
    )
)
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if not defined ISCC (
    echo [ERROR] Inno Setup 6 compiler not found.
    echo [INFO] PyInstaller output still exists: dist\Ptu\
    echo [INFO] Install Inno Setup 6, then run this script again:
    echo        https://jrsoftware.org/isdl.php
    goto fail
)

echo [INFO] Running Inno Setup: %ISCC%
if exist installer rmdir /s /q installer
"%ISCC%" installer.iss
if errorlevel 1 (
    echo [ERROR] Inno Setup installer build failed.
    goto fail
)

echo.
echo [OK] Build complete.
echo [OK] Internal folder: dist\Ptu\
echo [OK] Release installer: installer\Ptu_Setup_v%APP_VERSION%.exe
echo.
echo Send only the installer EXE to users.
goto done

:fail
echo.
echo Build failed.
if "%PTU_NO_PAUSE%"=="" pause
exit /b 1

:done
if "%PTU_NO_PAUSE%"=="" pause
exit /b 0
