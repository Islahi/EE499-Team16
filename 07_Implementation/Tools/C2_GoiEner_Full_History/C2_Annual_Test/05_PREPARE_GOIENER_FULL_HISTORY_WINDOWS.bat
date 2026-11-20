@echo off
setlocal
cd /d "%~dp0"
echo [C2] Install dependencies, then prepare the downloaded GoiEner v7.1 annual data.
py -m pip install -r requirements.txt
if errorlevel 1 goto error
py -m pip install zstandard
if errorlevel 1 goto error
py prepare_goiener_v71.py
if errorlevel 1 goto error
echo Prepared. You can run 06_DOWNLOAD_NASA_FOR_MATCHING_YEARS_WINDOWS.bat next.
pause
exit /b 0
:error
echo Something failed. Inspect the messages above.
pause
exit /b 1
