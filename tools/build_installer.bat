@echo off
title Build Standalone ESP32 Installer
echo Building standalone executable with PyInstaller...
cd /d "%~dp0\.."
python -m PyInstaller --onefile --clean --name "ESP32-FileTransfer-Installer" --distpath "dist" --add-data "app;app" --add-data "www;www" --add-data "main.py;." --add-data "boot.py;." --add-data "config.example.json;." tools\deploy.py
echo.
echo Build finished! Executable is ready at: dist\ESP32-FileTransfer-Installer.exe
pause
