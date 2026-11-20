@echo off
setlocal
cd /d "%~dp0"
call "%~dp0PYTHON_CONFIG.bat"
if not exist "results" mkdir "results"
py -%EE499_PY_SELECTOR% -m cProfile -s cumulative "run_benchmark.py" quick --case T04 --solver fbs_python,scipy_nr --out results_profile > "results\profile_quick.txt"
echo See results\profile_quick.txt and results_profile\. Do not compare timings with nonprofiled official runs.
pause
