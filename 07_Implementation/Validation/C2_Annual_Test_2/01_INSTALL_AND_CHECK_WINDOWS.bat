@echo off
cd /d "%~dp0"
echo === Install C2 benchmark packages ===
python --version
python -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo === Run offline data and math checks ===
python test_c2_model_benchmark.py
if errorlevel 1 goto failed
echo.
echo Setup and offline checks complete.
pause
exit /b 0
:failed
echo.
echo FAILED. Read the error above; make sure Python 3.11 or 3.12 is installed.
pause
exit /b 1
