@echo off
cd /d "%~dp0"
python run_benchmark.py --scope categories --suite selected --models Naive YearAgoCalendarNaive SeasonalNaive FourierOLS CalendarRidge --max-jobs 12
pause
