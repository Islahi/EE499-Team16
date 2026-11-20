@echo off
setlocal
cd /d "%~dp0"
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
set NUMEXPR_NUM_THREADS=1
".venv\Scripts\python.exe" "run_benchmark.py" reports %*
if errorlevel 1 (echo Benchmark command failed: check messages above)
pause
