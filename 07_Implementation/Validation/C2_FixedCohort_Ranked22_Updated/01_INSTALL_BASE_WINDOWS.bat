@echo off
cd /d "%~dp0"
python -m pip install -r requirements_base.txt
if errorlevel 1 (echo Package installation failed. See the error above.)
pause
