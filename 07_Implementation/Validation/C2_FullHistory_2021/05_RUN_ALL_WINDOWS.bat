@echo off
cd /d "%~dp0"
echo Full-history 2021 benchmark; each job has isolated memory/time guards.
python -u run_c2.py
pause
