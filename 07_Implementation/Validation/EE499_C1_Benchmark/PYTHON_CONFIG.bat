@echo off
rem Shared Python installation, no project-specific virtual environment.
rem MATLAB R2026b supports Python 3.14; align C1 with the forecasting interpreter.
rem Override temporarily with: set EE499_PYTHON_VERSION=3.13
set "EE499_PY_SELECTOR=3.14"
if defined EE499_PYTHON_VERSION set "EE499_PY_SELECTOR=%EE499_PYTHON_VERSION%"
