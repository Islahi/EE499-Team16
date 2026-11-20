@echo off
setlocal
cd /d "%~dp0"
call "%~dp0PYTHON_CONFIG.bat"
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
py -%EE499_PY_SELECTOR% "run_benchmark.py" failed %*
pause
