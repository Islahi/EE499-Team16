@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed. Check Python installation.
  pause
  exit /b 1
)
python goiener_distribution_gui.py
if errorlevel 1 pause
