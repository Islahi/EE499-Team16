@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv-neural\Scripts\python.exe" (echo Missing .venv-neural Python 3.12 & pause & exit /b 1)
echo C2 neural category forecasts - Python 3.12 isolated venv.
".venv-neural\Scripts\python.exe" run_benchmark.py --scope categories --group neural --include-neural --retry-failed --timeout-seconds 7200 --memory-gb 12
pause
