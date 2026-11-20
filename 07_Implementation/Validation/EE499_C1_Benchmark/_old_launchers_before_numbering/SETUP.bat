@echo off
setlocal
cd /d "%~dp0"
py -3.12 -m venv ".venv"
if errorlevel 1 (echo Python 3.12 required; install and retry.& pause & exit /b 1)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r "requirements.txt"
if errorlevel 1 (echo Dependency installation failed & pause & exit /b 1)
echo.
echo Optional solvers: .venv\Scripts\python.exe -m pip install -r requirements-optional.txt
echo OpenDSS/MATPOWER adapters also require separate configuration; see README.md.
pause
