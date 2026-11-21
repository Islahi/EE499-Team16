@echo off
setlocal
cd /d "%~dp0"

set QT_QPA_PLATFORM=offscreen
python -m pytest -q -ra tests
set test_exit=%errorlevel%
if not "%test_exit%"=="0" pause

endlocal & exit /b %test_exit%
