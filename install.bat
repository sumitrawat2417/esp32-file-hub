@echo off
title ESP32 File Hub Installer
cd /d "%~dp0"
python tools\deploy.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo [!] Deployment exited with code %ERRORLEVEL%.
    pause
)
