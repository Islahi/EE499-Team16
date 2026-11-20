@echo off
cd /d "%~dp0"
python cohort_cases.py --cohort cohort_output --pv "Input\nasa_pv_043d26N_002d94W.csv"
pause
