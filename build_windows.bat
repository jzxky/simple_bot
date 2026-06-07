@echo off
setlocal

echo === MafiaMatrix Bot - Windows Build ===
echo.

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ from https://www.python.org/downloads/
    pause & exit /b 1
)

:: Create and activate a virtual environment
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat

:: Install dependencies
echo Installing dependencies...
pip install --quiet -r requirements.txt
pip install --quiet pyinstaller

:: Build
echo.
echo Building executable...
pyinstaller simple_bot.spec --noconfirm

if errorlevel 1 (
    echo.
    echo BUILD FAILED. See output above for details.
    pause & exit /b 1
)

echo.
echo BUILD COMPLETE.
echo Executable folder: dist\MafiaMatrixBot\
echo Run:              dist\MafiaMatrixBot\MafiaMatrixBot.exe
echo.
echo NOTE: On first run, create a .env file next to the exe:
echo   MM_EMAIL=your@email.com
echo   MM_PASSWORD=yourpassword
echo.
pause
