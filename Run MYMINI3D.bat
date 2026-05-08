@echo off
cd /d "%~dp0"
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Could not start MYMINI3D Laser Studio.
    echo Make sure Python is installed and run:
    echo   pip install -r requirements.txt
    pause
)
