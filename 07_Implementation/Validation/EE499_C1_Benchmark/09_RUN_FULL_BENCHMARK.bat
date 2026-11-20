@echo off
setlocal
cd /d "%~dp0"
call "%~dp0PYTHON_CONFIG.bat"
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
set NUMEXPR_NUM_THREADS=1
py -%EE499_PY_SELECTOR% "run_benchmark.py" full %*
if errorlevel 1 (echo Benchmark command failed: check messages above)
pause
