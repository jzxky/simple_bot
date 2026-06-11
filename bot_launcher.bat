@echo off
setlocal

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

call venv\Scripts\activate.bat
python main.py
