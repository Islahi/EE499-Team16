@echo off
setlocal
if not exist "%~dp0Dashboard.html" (
 echo Extract the complete ZIP and keep Dashboard.html beside this launcher.
 pause
 exit /b 1
)
start "" "%~dp0Dashboard.html"
