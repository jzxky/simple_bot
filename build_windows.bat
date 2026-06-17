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

:: Build — single portable EXE
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
echo Output: dist\MafiaMatrixBot.exe
echo.
echo === First-time setup for end users ===
echo 1. Copy MafiaMatrixBot.exe to any folder on the target machine
echo 2. Run:  MafiaMatrixBot.exe --install    (downloads Chrome, one time only)
echo 3. Create a .env file in the SAME folder as MafiaMatrixBot.exe:
echo      MM_EMAIL=your@email.com
echo      MM_PASSWORD=yourpassword
echo 4. Run:  MafiaMatrixBot.exe
echo.
echo Note: On first launch the EXE will take ~10-20s to unpack itself.
echo       Subsequent launches are just as fast.
echo.
pause
