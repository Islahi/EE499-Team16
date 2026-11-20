@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist "run_benchmark.py" (
  echo ERROR: This menu must be inside the EE499_C1_Benchmark folder next to run_benchmark.py.
  pause
  exit /b 1
)
rem Safely archive older unnumbered launchers; never delete old launchers or benchmark results.
set "backup_folder=%~dp0_old_launchers_before_numbering"
set "has_legacy="
if exist "%~dp0SETUP.bat" set "has_legacy=1"
if exist "%~dp0SETUP_OPTIONAL.bat" set "has_legacy=1"
if exist "%~dp0INSTALL_MATLAB_ENGINE.bat" set "has_legacy=1"
if exist "%~dp0VERIFY_MATLAB.bat" set "has_legacy=1"
if exist "%~dp0CHECK_SOLVERS.bat" set "has_legacy=1"
if exist "%~dp0RUN_QUICK_TEST.bat" set "has_legacy=1"
if exist "%~dp0RUN_ACCURACY.bat" set "has_legacy=1"
if exist "%~dp0RUN_SPEED.bat" set "has_legacy=1"
if exist "%~dp0RUN_FULL_BENCHMARK.bat" set "has_legacy=1"
if exist "%~dp0RUN_FAILED.bat" set "has_legacy=1"
if exist "%~dp0GENERATE_REPORTS.bat" set "has_legacy=1"
if exist "%~dp0OPEN_DASHBOARD.bat" set "has_legacy=1"
if exist "%~dp0PROFILE_QUICK.bat" set "has_legacy=1"
if defined has_legacy (
  if not exist "%backup_folder%" mkdir "%backup_folder%"
  if not exist "%backup_folder%" (echo ERROR: Cannot create backup directory. & pause & exit /b 1)
  if exist "%~dp0SETUP.bat" move /Y "%~dp0SETUP.bat" "%backup_folder%\SETUP.bat" >nul
  if exist "%~dp0SETUP_OPTIONAL.bat" move /Y "%~dp0SETUP_OPTIONAL.bat" "%backup_folder%\SETUP_OPTIONAL.bat" >nul
  if exist "%~dp0INSTALL_MATLAB_ENGINE.bat" move /Y "%~dp0INSTALL_MATLAB_ENGINE.bat" "%backup_folder%\INSTALL_MATLAB_ENGINE.bat" >nul
  if exist "%~dp0VERIFY_MATLAB.bat" move /Y "%~dp0VERIFY_MATLAB.bat" "%backup_folder%\VERIFY_MATLAB.bat" >nul
  if exist "%~dp0CHECK_SOLVERS.bat" move /Y "%~dp0CHECK_SOLVERS.bat" "%backup_folder%\CHECK_SOLVERS.bat" >nul
  if exist "%~dp0RUN_QUICK_TEST.bat" move /Y "%~dp0RUN_QUICK_TEST.bat" "%backup_folder%\RUN_QUICK_TEST.bat" >nul
  if exist "%~dp0RUN_ACCURACY.bat" move /Y "%~dp0RUN_ACCURACY.bat" "%backup_folder%\RUN_ACCURACY.bat" >nul
  if exist "%~dp0RUN_SPEED.bat" move /Y "%~dp0RUN_SPEED.bat" "%backup_folder%\RUN_SPEED.bat" >nul
  if exist "%~dp0RUN_FULL_BENCHMARK.bat" move /Y "%~dp0RUN_FULL_BENCHMARK.bat" "%backup_folder%\RUN_FULL_BENCHMARK.bat" >nul
  if exist "%~dp0RUN_FAILED.bat" move /Y "%~dp0RUN_FAILED.bat" "%backup_folder%\RUN_FAILED.bat" >nul
  if exist "%~dp0GENERATE_REPORTS.bat" move /Y "%~dp0GENERATE_REPORTS.bat" "%backup_folder%\GENERATE_REPORTS.bat" >nul
  if exist "%~dp0OPEN_DASHBOARD.bat" move /Y "%~dp0OPEN_DASHBOARD.bat" "%backup_folder%\OPEN_DASHBOARD.bat" >nul
  if exist "%~dp0PROFILE_QUICK.bat" move /Y "%~dp0PROFILE_QUICK.bat" "%backup_folder%\PROFILE_QUICK.bat" >nul
  echo Older launcher files were moved to: _old_launchers_before_numbering
  echo The benchmark source code and existing results were not changed.
  pause
)
:menu
cls
echo ==============================================================
echo   EE499 TEAM 16 - C1 POWER-FLOW BENCHMARK
 echo   Python 3.14 - MATLAB R2026b - No virtual environment
 echo ==============================================================
echo.
echo    1 - Install core Python libraries
echo    2 - Install optional solver libraries
echo    3 - Install MATLAB Engine for R2026b
echo    4 - Verify MATLAB and MATPOWER
echo    5 - Check solver availability
echo    6 - Run 15-bus quick test
echo    7 - Run accuracy benchmark
echo    8 - Run speed benchmark
echo    9 - Run full benchmark
echo   10 - Rerun failed / missing cases
echo   11 - Regenerate reports from saved data
echo   12 - Open offline dashboard
echo   13 - Run profiling diagnostic (not timed benchmark)
echo.
echo    0 - Exit
 echo.
set "choice="
set /p "choice=Choose an option [0-13]: "
if "%choice%"=="0" exit /b 0
set "selected="
if "%choice%"=="1" set "selected=01_SETUP.bat"
if "%choice%"=="2" set "selected=02_SETUP_OPTIONAL.bat"
if "%choice%"=="3" set "selected=03_INSTALL_MATLAB_ENGINE.bat"
if "%choice%"=="4" set "selected=04_VERIFY_MATLAB.bat"
if "%choice%"=="5" set "selected=05_CHECK_SOLVERS.bat"
if "%choice%"=="6" set "selected=06_RUN_QUICK_TEST.bat"
if "%choice%"=="7" set "selected=07_RUN_ACCURACY.bat"
if "%choice%"=="8" set "selected=08_RUN_SPEED.bat"
if "%choice%"=="9" set "selected=09_RUN_FULL_BENCHMARK.bat"
if "%choice%"=="10" set "selected=10_RUN_FAILED.bat"
if "%choice%"=="11" set "selected=11_GENERATE_REPORTS.bat"
if "%choice%"=="12" set "selected=12_OPEN_DASHBOARD.bat"
if "%choice%"=="13" set "selected=13_PROFILE_QUICK.bat"
if not defined selected (
 echo Invalid choice. Press any key to retry.
 pause >nul
 goto menu
)
call "%~dp0%selected%"
goto menu
