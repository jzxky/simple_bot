@echo off
setlocal enabledelayedexpansion

:: Check venv exists
if not exist "venv\Scripts\activate.bat" (
    echo Virtual environment not found. Run setup_windows.bat first.
    pause & exit /b 1
)

:: Check .env exists
if not exist ".env" (
    echo .env file not found. Run setup_windows.bat first.
    pause & exit /b 1
)

:: ── Version / update check ─────────────────────────────────────────────────

set "CURRENT_VERSION=unknown"
if exist "VERSION" (
    set /p CURRENT_VERSION=<VERSION
    set "CURRENT_VERSION=!CURRENT_VERSION: =!"
)

echo MafiaMatrix Bot v!CURRENT_VERSION!
echo.
echo Checking for updates...

:: Fetch latest version from GitHub using PowerShell
set "LATEST_VERSION="
for /f "delims=" %%v in ('powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/jzxky/simple_bot/main/VERSION' -UseBasicParsing -TimeoutSec 5).Content.Trim() } catch { '' }" 2^>nul') do (
    set "LATEST_VERSION=%%v"
)

if "!LATEST_VERSION!"=="" (
    echo Could not reach GitHub. Skipping update check.
    echo.
    goto :launch
)

if "!LATEST_VERSION!"=="!CURRENT_VERSION!" (
    echo You are on the latest version ^(!CURRENT_VERSION!^).
    echo.
    goto :launch
)

echo Update available: v!CURRENT_VERSION! ^-^> v!LATEST_VERSION!
echo.

:: Detect whether this is a git repo
set "IS_GIT=0"
if exist ".git\" set "IS_GIT=1"
git rev-parse --git-dir >nul 2>&1 && set "IS_GIT=1"

set /p "DO_UPDATE=Update now? [Y/N]: "
if /i not "!DO_UPDATE!"=="Y" goto :launch

if "!IS_GIT!"=="1" (
    echo.
    echo Pulling latest changes via git...
    git pull origin main
    if errorlevel 1 (
        echo.
        echo Git pull failed. You can update manually:
        echo   https://github.com/jzxky/simple_bot
    ) else (
        echo.
        echo Update complete. Re-run setup_windows.bat if dependencies changed.
    )
) else (
    echo.
    echo Download the latest version from:
    echo   https://github.com/jzxky/simple_bot/archive/refs/heads/main.zip
    echo.
    echo Opening download page...
    start https://github.com/jzxky/simple_bot/archive/refs/heads/main.zip
)

echo.
pause

:launch
set /p "LAUNCH_UI=Launch the UI in your browser? [Y/N]: "
echo.

call venv\Scripts\activate.bat

if /i "!LAUNCH_UI!"=="Y" (
    start http://localhost:5000
)

python main.py
