@echo off
REM Usuwa autostart i zatrzymuje TV Launcher. Pliki aplikacji i config.json zostają.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
pause
