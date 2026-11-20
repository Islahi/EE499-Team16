@echo off
setlocal
cd /d "%~dp0"
echo Export ONLY - use when fixed-cohort processing (02) has already finished.
echo No .tzst files will be reprocessed.
python 02_export_legacy_cleaner_format.py --source cohort_output --out "cohort_output\Distributor_Compatible" --wide-value average
if errorlevel 1 goto failed
echo.
echo SUCCESS: Select this folder in your old GoiEner Load Distributor:
echo %CD%\cohort_output\Distributor_Compatible
goto done
:failed
echo.
echo ERROR: Check the cohort_output source files and the message above.
:done
pause
endlocal
