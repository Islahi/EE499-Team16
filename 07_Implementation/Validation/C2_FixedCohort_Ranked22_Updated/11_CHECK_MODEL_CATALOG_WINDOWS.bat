@echo off
cd /d "%~dp0"
python tests\test_catalog.py
python tests\test_benchmark.py
pause
