@echo off
cd /d "%~dp0"
python -m pip install -r requirements_extra.txt
if errorlevel 1 (echo Some packages may not support this Python version. Check the output.)
pause
