@echo off
chcp 936 >nul
echo ====================================
echo    PML - PhiraMural
echo    Starting...
echo ====================================
echo.

cd /d "%~dp0"

if exist "PML_PhiraMural.exe" (
    start "" "PML_PhiraMural.exe"
    exit
)

echo [INFO] PML_PhiraMural.exe not found, trying Python...
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found
    echo.
    echo Please install Python 3.12+:
    echo https://www.python.org/downloads/
    echo.
    echo Check "Add Python to PATH" during install
    echo.
    pause
    exit /b 1
)

python phira_video_bg_plugin.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to run
    echo.
    pause
)
