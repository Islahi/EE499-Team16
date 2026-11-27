@echo off
setlocal EnableDelayedExpansion
if "%~1"=="" (
  echo Usage: Drag a saved results folder, such as Sessions\...\optimization\run_001, onto this BAT.
  echo Or run: REGENERATE_SAVED_DASHBOARD.bat "C:\full\path\to\optimization\run_001"
  pause
  exit /b 2
)
set "RUN_FOLDER=%~f1"
cd /d "%~dp0..\.."
if not exist "%RUN_FOLDER%\summary.md" if not exist "%RUN_FOLDER%\hourly.csv" (
  echo ERROR: This does not look like an exported run folder: "%RUN_FOLDER%"
  pause
  exit /b 2
)
where py >nul 2>&1
if not errorlevel 1 (
  py -3.14 -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    py -3.14 -m src.dashboard "%RUN_FOLDER%"
    set "RC=!errorlevel!"
    goto complete
  )
)
python -m src.dashboard "%RUN_FOLDER%"
set "RC=!errorlevel!"
:complete
if "!RC!"=="0" (
  echo Dashboard regenerated successfully: "%RUN_FOLDER%\dashboard.html"
) else (
  echo Dashboard regeneration failed with exit code !RC!.
)
if /i not "%~2"=="--no-pause" pause
exit /b !RC!
