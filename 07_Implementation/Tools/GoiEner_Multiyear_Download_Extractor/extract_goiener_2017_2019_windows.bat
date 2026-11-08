@echo off
cd /d "%~dp0"
python goiener_tool.py extract --start 2017-01-01 --end 2019-12-31 --max-per-sector 5
pause
