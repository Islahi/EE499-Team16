@echo off
cd /d "%~dp0"
python run_benchmark.py --scope categories --group baselines
pause
