@echo off
setlocal
cd /d "%~dp0"

python -m pip install -r requirements-accelerated.txt
if errorlevel 1 (
    echo Dependency installation failed. Check Python and network access.
    pause
    exit /b 1
)

python -m src_accelerated.ui
if errorlevel 1 (
    echo Application exited with an error.
    pause
    exit /b 1
)

endlocal
