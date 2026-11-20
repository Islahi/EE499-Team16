@echo off
cd /d "%~dp0"
python -u run_c2.py --datasets Distributed_15Bus_Load Bilbao_Modelled_PV
pause
