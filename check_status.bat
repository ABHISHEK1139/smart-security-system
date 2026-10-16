@echo off
echo =====================================
echo   CHECKING ACTIVITY MONITOR STATUS
echo =====================================
cd /d "%~dp0"
python stop_monitor.py status
echo.
echo Press any key to close this window.
pause > nul
