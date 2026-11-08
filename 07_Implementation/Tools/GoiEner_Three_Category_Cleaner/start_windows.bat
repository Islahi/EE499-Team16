@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
python goiener_cleaner_gui.py
pause
