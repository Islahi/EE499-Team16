@echo off
cd /d "%~dp0"
echo Re-attempting failed runs with the same settings. Use only if you have changed constraints.
python -u run_c2.py --retry-failed
pause
