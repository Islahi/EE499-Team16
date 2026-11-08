@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Python package installation failed.
  pause
  exit /b 1
)
python gui.py
if errorlevel 1 pause
