@echo off
echo =====================================
echo   CHECKING ACTIVITY MONITOR STATUS
echo =====================================
cd /d "C:\security\script"
python stop_monitor.py status
echo.
echo Press any key to close this window.
pause > nul
