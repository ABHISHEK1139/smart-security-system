@echo off
echo ==================================
echo   STOPPING THE ACTIVITY MONITOR
echo ==================================
cd /d "%~dp0"
python stop_monitor.py
echo.
echo Press any key to close this window.
pause > nul
