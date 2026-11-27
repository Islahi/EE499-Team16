@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "REPORT_DIR=%~dp0Results\Diagnostics"
if not exist "%REPORT_DIR%\" mkdir "%REPORT_DIR%"
if not exist "%REPORT_DIR%\" exit /b 1
set "REPORT=%REPORT_DIR%\windows_gui_check.txt"
rem Run one interpreter only, so a failed integration check is not obscured.
where py >nul 2>&1
if not errorlevel 1 (
  py -3.14 -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    py -3.14 "%~dp0src\app.pyw" --check-runtime "%REPORT%"
    set "CHECK_RC=!errorlevel!"
    goto finished
  )
)
python "%~dp0src\app.pyw" --check-runtime "%REPORT%"
set "CHECK_RC=!errorlevel!"
:finished
if exist "%REPORT%" (
  type "%REPORT%"
) else (
  echo Runtime check did not produce a report. Review src\app_startup_error.txt.
)
echo Runtime check exit code: %CHECK_RC%
if /i not "%~1"=="--no-pause" pause
exit /b %CHECK_RC%
