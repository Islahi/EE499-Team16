@echo off
setlocal
cd /d "%~dp0"
set QT_QPA_PLATFORM=offscreen
if not defined OPENBLAS_NUM_THREADS set OPENBLAS_NUM_THREADS=1
if not defined MKL_NUM_THREADS set MKL_NUM_THREADS=1
if not defined OMP_NUM_THREADS set OMP_NUM_THREADS=1
where py >nul 2>&1
if not errorlevel 1 (
    py -3.14 -c "import sys" >nul 2>&1
    if not errorlevel 1 goto python314
)
python -m pytest -ra tests %*
exit /b %errorlevel%
:python314
py -3.14 -m pytest -ra tests %*
exit /b %errorlevel%
