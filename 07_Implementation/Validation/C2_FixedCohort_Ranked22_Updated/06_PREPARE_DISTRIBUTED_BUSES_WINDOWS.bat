@echo off
cd /d "%~dp0"
echo IMPORTANT: Input\distributed_load_from_NEW_cohort.csv MUST be generated from cohort_output using the GoiEner Load Distributor.
python cohort_cases.py --cohort cohort_output --pv "Input\nasa_pv_043d26N_002d94W.csv" --distributed "Input\distributed_load_from_NEW_cohort.csv"
pause
