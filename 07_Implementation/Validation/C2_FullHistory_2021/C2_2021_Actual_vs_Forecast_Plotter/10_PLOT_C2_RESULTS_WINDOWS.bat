@echo off
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
    py -3 c2_plotter_gui.py %*
) else (
    python c2_plotter_gui.py %*
)
if errorlevel 1 (
    echo.
    echo The C2 plotter needs Python with numpy, pandas, matplotlib, and Tkinter.
    echo Try: python -m pip install numpy pandas matplotlib
    pause
)
