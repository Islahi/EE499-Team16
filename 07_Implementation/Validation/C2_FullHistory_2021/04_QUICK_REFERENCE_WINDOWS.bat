@echo off
cd /d "%~dp0"
python run_c2.py --models SeasonalNaive --seasons daily weekly yearly_365d
pause
