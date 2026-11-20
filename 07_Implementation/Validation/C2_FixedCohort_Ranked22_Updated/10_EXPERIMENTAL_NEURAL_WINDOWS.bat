@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv-neural\Scripts\python.exe" (
  echo ERROR: Python 3.12 neural venv is missing.
  echo Run: py -3.12 -m venv .venv-neural
  pause
  exit /b 1
)
echo C2 Neural Pilot - AutoNHITS / first category job / Python 3.12 only.
echo This will keep previously completed Python 3.14 results.
".venv-neural\Scripts\python.exe" run_benchmark.py --scope categories --group neural --include-neural --models AutoNHITS --retry-failed --max-jobs 1 --timeout-seconds 7200 --memory-gb 12
pause
