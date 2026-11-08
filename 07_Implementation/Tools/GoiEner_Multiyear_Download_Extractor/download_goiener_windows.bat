@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Could not install Python dependencies. Try: python -m pip install -r requirements.txt
  pause
  exit /b 1
)
python goiener_tool.py download --with-pre
if errorlevel 1 (
  echo If Zenodo download is blocked, use the official Zenodo record and manually save metadata.csv and imp-pre.tzst to goiener_original.
)
pause
