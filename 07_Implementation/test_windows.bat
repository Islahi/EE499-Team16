@echo off
setlocal
cd /d "%~dp0"

python -m pytest -q tests
set test_exit=%errorlevel%
if not "%test_exit%"=="0" pause

endlocal & exit /b %test_exit%
