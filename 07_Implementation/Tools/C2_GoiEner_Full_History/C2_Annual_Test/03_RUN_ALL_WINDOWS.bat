@echo off
cd /d "%~dp0"
echo === Full 9-model / multiple seasonality / 7-dataset benchmark ===
echo May take a VERY long time for 720-hour or 8760-hour seasonal models.
echo Model results saved individually; rerun this BAT to resume completed jobs.
echo.
python -u run_c2_model_benchmark.py %*
if errorlevel 1 (
    echo Benchmark exited with an error. Check output above.
) else (
    echo Benchmark finished; see C2_model_benchmark_results\.
)
pause
