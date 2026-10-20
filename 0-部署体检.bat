@echo off
REM Read-only health check. Chinese output is produced by scripts\check.ps1 (UTF-8 BOM).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\check.ps1"
pause
