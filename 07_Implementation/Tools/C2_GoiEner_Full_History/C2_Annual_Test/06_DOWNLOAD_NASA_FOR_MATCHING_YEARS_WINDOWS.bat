@echo off
setlocal
cd /d "%~dp0"
echo [C2] This downloads hourly NASA POWER data for 5 sites and all years to match GoiEner.
py download_nasa_full_history.py
if errorlevel 1 goto error
pause
exit /b 0
:error
echo Download or processing failed; retry the script to reuse already downloaded yearly responses.
pause
exit /b 1
