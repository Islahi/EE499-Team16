# BESS Planning Tool · V15.6 cleanup

1. Double-click `start_windows.bat` in the application folder. Use **Open setup…** and **Save setup…** on the main window for saved configurations.
2. Load a radial-network workbook and a prepared case folder or hourly demand CSV/XLSX. A Bus Data / Branch Data workbook without a frequency requires the case's declared frequency in Hz. A standalone load file requires the columns `timestamp`, `bus_id`, `p_kw`, and `q_kvar`. When pairing it with solar data, add a JSON sidecar with the same base filename and its declared `clock`.
3. Use **Settings → Battery** for the optional manual installation used by **Simulation**. For **Optimize**, set the eligible buses, maximum fleet size, and stepped kW/kWh catalogs under **Optimization**. Population, maximum generations, and parallel workers are editable on that page. Select and apply a complete calendar year under **Study interval** before optimizing.
4. Confirm the tariffs in **Settings → Economics**. Daily MILP dispatch uses battery energy CAPEX in USD/kWh, inverter CAPEX in USD/kVA, real capital recovery and annual O&M.
5. Use the **Dashboard** menu to open or rebuild a saved run. **Compare runs** accepts saved dashboard HTML files. **Charts** shows the selected scenario and date window, including the hourly feeder when its trace is available.
6. Open **ⓘ Information** for read-only parameters, equations, and assumptions. Press **F1** inside Settings to review pending edits alongside the confirmed values. During a run, the dialog opens on the effective settings. Use **Open saved run** to view frozen settings from a saved run folder.
7. Expand **Model & Assumptions** in an offline HTML report to see its saved settings and equations. **Print / PDF** includes the section automatically. Use **Regenerate saved report** to add the section to an existing archive. Missing archived values appear as **Not recorded**.

## Windows commands

The package uses the existing Python installation. The tested interpreter was Python 3.14.7. If a required dependency is missing, install it in that installation before running the application.

```bat
py -3.14 -m pip install numpy pandas scipy numba openpyxl scikit-learn xgboost lightgbm PySide6 tzdata
py -3.14 -m pip install pytest
CHECK_WINDOWS_GUI.bat --no-pause
test_windows.bat -q
REGENERATE_SAVED_DASHBOARD.bat "C:\path\to\session\optimization\run_001"
```

A saved setup that used a different dispatch mode prompts a review of the economics before a new desktop run. Open archived sessions through **Study interval → Browse History**. Effective settings appear in the saved run metadata. The application log is at `src/Results/application.log`, and each study has a `session.log`.

See [the system validation report](docs/FULL_SYSTEM_TEST_REPORT.md) and [control audit](docs/UI_CONTROL_AUDIT.csv) for the verification and change details.
