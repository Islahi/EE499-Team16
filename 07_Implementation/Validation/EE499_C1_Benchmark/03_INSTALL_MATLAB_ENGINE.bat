@echo off
setlocal
cd /d "%~dp0"
call "%~dp0PYTHON_CONFIG.bat"
echo Installing MATLAB R2026b Engine 26.2.5 into shared Python %EE499_PY_SELECTOR% (no venv).
py -%EE499_PY_SELECTOR% --version
if errorlevel 1 (echo Python %EE499_PY_SELECTOR% is missing. Run py --list. & pause & exit /b 1)
py -%EE499_PY_SELECTOR% -m pip install --user --upgrade "matlabengine==26.2.5"
if errorlevel 1 (echo Engine installation failed. Confirm MATLAB R2026b is installed and licensed. & pause & exit /b 1)
py -%EE499_PY_SELECTOR% -c "import matlab.engine; print('MATLAB Engine import succeeded')"
if errorlevel 1 (echo MATLAB Engine import failed & pause & exit /b 1)
echo Next install MATPOWER, then run 04_VERIFY_MATLAB.bat.
pause
