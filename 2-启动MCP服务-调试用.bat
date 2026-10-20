@echo off
REM Run the Seestar MCP server in stdio mode (debug only; an MCP client
REM normally launches it itself). Run scripts\install.py first.
cd /d "%~dp0vendor\seestar-mcp"
".venv\Scripts\python.exe" -m seestar_mcp.server
pause
