@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
rem Avoid BLAS oversubscription across parallel GA candidate workers.
rem Each worker performs many small 32/64-bus linear solves, so one BLAS
rem thread per worker is typically faster and more predictable on 16 GB PCs.
if not defined OPENBLAS_NUM_THREADS set OPENBLAS_NUM_THREADS=1
if not defined MKL_NUM_THREADS set MKL_NUM_THREADS=1
if not defined OMP_NUM_THREADS set OMP_NUM_THREADS=1
if not defined NUMEXPR_NUM_THREADS set NUMEXPR_NUM_THREADS=1
rem Prefer the project's Python 3.14 installation. Do not relaunch a failed app
rem in a different Python environment; preserve the original error instead.
where py >nul 2>&1
if not errorlevel 1 (
  py -3.14 -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    py -3.14 "%~dp0src\app.pyw" %*
    exit /b !errorlevel!
  )
)
python "%~dp0src\app.pyw" %*
exit /b !errorlevel!
