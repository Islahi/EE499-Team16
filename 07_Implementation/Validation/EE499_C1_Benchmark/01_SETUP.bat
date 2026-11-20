@echo off
setlocal
cd /d "%~dp0"
call "%~dp0PYTHON_CONFIG.bat"
echo Using shared Python %EE499_PY_SELECTOR% (no virtual environment).
py -%EE499_PY_SELECTOR% --version
if errorlevel 1 (echo This Python version is not installed. Run: py --list & pause & exit /b 1)
py -%EE499_PY_SELECTOR% -m pip install --user -r "requirements.txt"
if errorlevel 1 (echo Dependency installation failed & pause & exit /b 1)
echo.
echo Core dependencies installed into Python %EE499_PY_SELECTOR% user site packages.
echo Optional libraries: run 02_SETUP_OPTIONAL.bat
echo For MATLAB R2026b, run 03_INSTALL_MATLAB_ENGINE.bat and configure MATPOWER.
pause
