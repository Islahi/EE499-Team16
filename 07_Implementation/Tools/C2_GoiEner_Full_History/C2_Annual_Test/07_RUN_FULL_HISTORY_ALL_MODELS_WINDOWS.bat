@echo off
setlocal
cd /d "%~dp0"
echo [C2] Run nine models against final complete calendar year of the new full-history data.
echo [C2] WARNING: this may require substantial memory and processing time.
py run_c2_full_history.py
if errorlevel 1 goto error
pause
exit /b 0
:error
echo Program exited with an error; inspect previous output.
pause
exit /b 1
