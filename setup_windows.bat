@echo off
setlocal

echo === MafiaMatrix Bot - Windows Setup ===
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Install Python 3.11+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause & exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo Python %PYVER% found.
echo.

:: Create venv if needed
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 ( echo ERROR: Failed to create venv. & pause & exit /b 1 )
)

call venv\Scripts\activate.bat

:: Install Python dependencies
echo Installing dependencies...
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
if errorlevel 1 ( echo ERROR: pip install failed. & pause & exit /b 1 )
echo Dependencies installed.
echo.

:: Install Chrome via patchright
echo Installing Chrome browser (this may take a few minutes)...
patchright install chrome
if errorlevel 1 ( echo ERROR: patchright install failed. & pause & exit /b 1 )
echo Chrome installed.
echo.

:: Create .env if missing
if not exist ".env" (
    echo Creating .env file...
    (
        echo MM_EMAIL=your@email.com
        echo MM_PASSWORD=yourpassword
    ) > .env
    echo.
    echo IMPORTANT: Edit .env and enter your MafiaMatrix login credentials before starting the bot.
    echo   File location: %CD%\.env
) else (
    echo .env file already exists.
)

echo.
echo === Setup complete ===
echo Run bot_launcher.bat to start the bot.
echo.
pause
