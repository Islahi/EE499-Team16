@echo off
setlocal
cd /d "%~dp0"
call "%~dp0PYTHON_CONFIG.bat"
echo Starting MATLAB via shared Python %EE499_PY_SELECTOR%.
py -%EE499_PY_SELECTOR% -c "import matlab.engine; eng=matlab.engine.start_matlab(); release=eng.version('-release'); print('MATLAB release:', release); n=eng.exist('runpf','file'); print('MATPOWER runpf exists:', n); eng.quit(); assert str(release).lower() == '2026b', 'Expected MATLAB R2026b; check multi-version MATLAB installation'; assert n != 0, 'MATPOWER not on MATLAB search path'"
if errorlevel 1 (echo MATLAB/MATPOWER verification failed. Check installed release and MATPOWER path. & pause & exit /b 1)
echo MATLAB R2026b Engine and MATPOWER are callable.
pause
