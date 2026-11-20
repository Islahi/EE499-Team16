@echo off
cd /d "%~dp0"
echo === Test all 9 StatsForecast model APIs on SHORT synthetic training data ===
set "C2_MODEL_API_TEST=1"
python test_c2_model_benchmark.py
if errorlevel 1 goto failed
set "C2_MODEL_API_TEST="
echo.
echo === One measured 8,784-hour SeasonalNaive forecast ===
python run_c2_model_benchmark.py --models SeasonalNaive --seasonalities daily --datasets A_GoiEner_Total_Load --max-jobs 1
if errorlevel 1 goto failed
echo.
echo Smoke test completed; see C2_model_benchmark_results folder.
pause
exit /b 0
:failed
set "C2_MODEL_API_TEST="
echo.
echo FAILED. See the model API error above.
pause
exit /b 1
