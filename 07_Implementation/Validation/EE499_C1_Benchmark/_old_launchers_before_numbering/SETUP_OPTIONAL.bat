@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pip install -r "requirements-optional.txt"
if errorlevel 1 (echo Some optional native solver libraries could not be installed.)
echo For MATLAB Engine / MATPOWER setup, see README.md.
pause
