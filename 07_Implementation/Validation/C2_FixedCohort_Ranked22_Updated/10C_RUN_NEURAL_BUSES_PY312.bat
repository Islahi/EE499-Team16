@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv-neural\Scripts\python.exe" (echo Missing .venv-neural Python 3.12 & pause & exit /b 1)
echo C2 neural bus forecasts - excluding zero-load slack bus Bus_01.
".venv-neural\Scripts\python.exe" run_benchmark.py --scope buses --group neural --include-neural --exclude-cases Bus_01 --retry-failed --timeout-seconds 7200 --memory-gb 12
pause
