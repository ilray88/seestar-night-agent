@echo off
REM Night runner with watchdog. Chinese output comes from the .ps1 files (UTF-8 BOM).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\night_watchdog.ps1"
pause
