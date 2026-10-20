@echo off
REM Start the seestar_alp backend (web UI :5432, Alpaca :5555, imaging :7556).
REM Run scripts\install.py first to create vendor\seestar_alp\.venv
cd /d "%~dp0vendor\seestar_alp"
echo ==========================================================
echo  Starting Seestar backend...
echo  Wait for "Startup Complete", then keep this window open.
echo  Web UI: http://localhost:5432/
echo ==========================================================
".venv\Scripts\python.exe" root_app.py
echo.
echo [backend exited] press any key to close.
pause
