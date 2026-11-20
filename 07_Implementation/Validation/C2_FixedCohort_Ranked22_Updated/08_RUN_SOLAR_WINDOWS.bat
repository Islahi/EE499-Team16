@echo off
cd /d "%~dp0"
python run_benchmark.py --scope pv --suite selected
pause
