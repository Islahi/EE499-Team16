@echo off
setlocal
cd /d "%~dp0"
echo [1/2] Processing the same customer IDs from all three GoiEner archives...
python 01_build_common_cohort.py --manifests-zip "Input\Cleaned.zip" --pre "Input\imp-pre.tzst" --during "Input\imp-in.tzst" --post "Input\imp-post.tzst" --out cohort_output --max-gap-hours 168
if errorlevel 1 goto failed
echo.
echo [2/2] Exporting original GoiEner Cleaner format for your existing Load Distributor...
python 02_export_legacy_cleaner_format.py --source cohort_output --out "cohort_output\Distributor_Compatible" --wide-value average
if errorlevel 1 goto failed
echo.
echo SUCCESS: In your old distributor, select the following cleaned-data FOLDER:
echo %CD%\cohort_output\Distributor_Compatible
echo Then select Average, load and validate profiles, and distribute the loads.
goto done
:failed
echo.
echo ERROR: A step failed. Review the message above. Do not treat partial outputs as complete.
:done
pause
endlocal
