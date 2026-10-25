@echo off
title Install Python Requirements
cd /d "%~dp0"

echo Installing Python dependencies...
echo.

python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ERROR: Failed to install requirements.
    pause
    exit /b 1
)

echo.
echo All requirements installed successfully!
pause