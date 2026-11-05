@echo off
title Build Standalone ESP32 Installer
echo Building standalone executable with PyInstaller...
cd /d "%~dp0\.."

python -m PyInstaller --onefile --clean --name "ESP32-FileTransfer-Installer" --distpath "dist" --workpath "tools\build" --specpath "tools\build" --add-data "app;app" --add-data "www;www" --add-data "main.py;." --add-data "boot.py;." --add-data "config.example.json;." tools\deploy.py

:: Automatically clean up temporary build cache
rd /s /q "tools\build" 2>nul

echo.
echo Build finished! Executable is ready at: dist\ESP32-FileTransfer-Installer.exe
pause
