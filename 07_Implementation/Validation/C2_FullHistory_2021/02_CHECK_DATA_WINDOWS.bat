@echo off
cd /d "%~dp0"
python c2_tests.py
python run_c2.py --prepare-only
pause
