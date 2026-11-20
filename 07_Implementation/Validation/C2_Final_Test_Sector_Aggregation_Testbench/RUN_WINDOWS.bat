@echo off
setlocal
cd /d "%~dp0"
set OPENBLAS_NUM_THREADS=2
set OMP_NUM_THREADS=2
set MKL_NUM_THREADS=2
py -3 -m pip install -r requirements.txt
if errorlevel 1 (
 echo Dependency installation failed.
 pause
 exit /b 1
)
py -3 forecast_bench.py --recompute
if errorlevel 1 (
 echo Benchmark failed; examine the error above.
 pause
 exit /b 1
)
echo Benchmark completed. Open dashboard.html and EE499_Sector_Aggregation_Report.pdf.
pause
