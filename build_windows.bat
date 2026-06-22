@echo off
setlocal

echo === MafiaMatrix Bot - Windows Build ===
echo.

:: Check Python 3.11+
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ from https://www.python.org/downloads/
    pause & exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
for /f "tokens=1,2 delims=." %%a in ("%PY_VER%") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
if %PY_MAJOR% LSS 3 (
    echo ERROR: Python 3.11 or newer is required. Found %PY_VER%.
    pause & exit /b 1
)
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 11 (
    echo ERROR: Python 3.11 or newer is required. Found %PY_VER%.
    pause & exit /b 1
)
echo Python %PY_VER% OK.

:: Create / reuse virtual environment
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat

:: Upgrade pip silently
python -m pip install --quiet --upgrade pip

:: Install / refresh dependencies
echo Installing dependencies...
pip install --quiet --upgrade -r requirements.txt
pip install --quiet --upgrade pyinstaller

:: Clean previous build artefacts
echo Cleaning previous build...
if exist "build\" rmdir /s /q build
if exist "dist\MafiaMatrixBot.exe" del /q "dist\MafiaMatrixBot.exe"

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
echo 1. Copy MafiaMatrixBot.exe to any folder on the target machine.
echo 2. In that same folder, create a .env file:
echo      MM_EMAIL=your@email.com
echo      MM_PASSWORD=yourpassword
echo 3. Run: MafiaMatrixBot.exe --install   (downloads Chrome, one time only)
echo 4. Run: MafiaMatrixBot.exe
echo.
echo Note: The first launch will take ~10-20s to unpack. Subsequent launches are fast.
echo.
pause
