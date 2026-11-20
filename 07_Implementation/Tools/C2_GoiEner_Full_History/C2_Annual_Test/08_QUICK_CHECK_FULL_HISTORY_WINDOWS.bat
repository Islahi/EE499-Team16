@echo off
setlocal
cd /d "%~dp0"
py run_c2_full_history.py --models SeasonalNaive --seasonalities weekly --categories load
pause
