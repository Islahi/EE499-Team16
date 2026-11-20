@echo off
setlocal
cd /d "%~dp0"
call "%~dp0PYTHON_CONFIG.bat"
echo Installing optional solvers into Python %EE499_PY_SELECTOR% user site packages.
py -%EE499_PY_SELECTOR% -m pip install --user -r "requirements-optional.txt"
if errorlevel 1 (echo Some optional native solver libraries could not be installed. & pause & exit /b 1)
echo For MATLAB R2026b run 03_INSTALL_MATLAB_ENGINE.bat and install MATPOWER separately.
pause
