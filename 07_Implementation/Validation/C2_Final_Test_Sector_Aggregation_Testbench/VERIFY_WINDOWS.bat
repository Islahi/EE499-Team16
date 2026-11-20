@echo off
setlocal
cd /d "%~dp0"
py -3 forecast_bench.py --verify-only
pause
