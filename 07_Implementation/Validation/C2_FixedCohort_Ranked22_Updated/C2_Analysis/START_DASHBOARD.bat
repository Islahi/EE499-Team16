@echo off
setlocal
set "root=%~dp0"
set "entry=%root%00_Overview\C2_Forecast_Explorer.html"
if not exist "%entry%" (
  echo Dashboard file was not found.
  echo Extract the entire ZIP and keep this launcher beside the 00_Overview folder.
  pause
  exit /b 1
)
start "" "%entry%"
if errorlevel 1 (
  echo Windows could not open the dashboard. Open the HTML file with Microsoft Edge or Chrome.
  pause
  exit /b 1
)
exit /b 0
