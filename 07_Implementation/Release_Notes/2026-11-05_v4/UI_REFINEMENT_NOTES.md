# UI refinement — icon toolbar and compact settings

This release updates **BESS_Planning_Tool_UI_Refined_v1** (itself based on the standard GA two-offspring version).

## Changes to the graphical interface

- **Main window:** removed the left action sidebar. Six main functions appear as icon-only buttons in a native Qt top toolbar: Load Data, Forecasting, Run Simulation, Base-case FBS, Run Optimization, Settings. Settings is aligned on the right. The original button object names and connected handlers are preserved. Qt tooltips describe each action and its keyboard shortcut.
- **Network workspace:** retains its existing diagram controls, selection details, network/results tabs, progress, log and exports. Removing the sidebar increases available network width.
- **Status:** network size, hourly time steps, input sources, and session name are written to the Run Log when inputs load. The status bar stays one line tall.
- **Settings:** keeps Battery / Operation / Optimization / Economics pages, with shorter labels, tooltips for longer explanations, and GA-specific vs GWO-specific search controls displayed only for the selected algorithm. The obsolete Uncertainty page and raw WSM explanation have been removed from the Designer source. Numeric settings and internal object names are preserved.
- **Results:** default view now shows a compact summary. Select **Show full details** to display the original full report, including all simulation metrics and assumptions. Detailed CSV results and run logs are unchanged.
- **Load Data:** hides redundant introductory and synthetic-load descriptions. Existing file selection, input validation, and CSV-derived time range remain unchanged.
- **Visuals:** custom vector icons, neutral background, aligned fields and restrained hover styles. No additional GUI framework required.

## Keyboard shortcuts

| Shortcut | Function |
|---|---|
| Ctrl+L | Load data |
| Ctrl+F | Forecasting |
| Ctrl+R | Run simulation |
| Ctrl+B | Base-case FBS |
| Ctrl+O | Run optimization |
| Ctrl+, | Settings |

## What was not changed

No modifications were made to `optimizer.py`, `forecasting.py`, `fbs.py`, `simulation.py`, `metrics.py`, or `bess.py`. GA retains two-offspring single-point crossover; the StatsForecast AutoARIMA implementation and economic objective are unchanged. Existing Results/Sessions and bundled source input files are included.

## Run on Windows

1. Extract the ZIP to its own folder.
2. Double-click `start_windows.bat` (installs required packages) or run `py -m pip install -r requirements.txt` then `py -m src_accelerated.ui`.
3. To test: `py -m pytest -q tests`.

## Testing performed

- Full available non-GUI regression suite: **26 passed, 2 skipped** in the build environment.
- XML parsed for all Qt Designer forms and SVG files.
- Python files compiled successfully.
- Live PySide6/Windows GUI interaction has **not** been verified here because PySide6 was unavailable in this environment. Please validate toolbar hover, sizing and tab transitions on Windows before replacing your existing app.

## Design implementation note

Qt Designer's main form stores the original six buttons in a hidden compatibility holder. The application reparents those exact widgets to a native `QToolBar` at runtime. This avoids changing any existing click handlers or `set_busy()` logic, and deletes the hidden compatibility holder once its widgets have been moved. In Qt Designer the workspace is now full width.

## Compact toolbar and data-log revision

- Reduced primary icon toolbar height from a minimum of 49 px to a fixed 40 px, using 36 × 32 px buttons and 20 px icons.
- Removed the three-line study summary from the status bar and removed its obsolete Qt Designer label.
- On successful data load, writes bus count, hourly step count, load/PV sources, and session identifier to the Run Log (also saved in the session log).
- When a forecast is activated, logs its bus and forecast-step counts and session identifier.
- No electrical, optimizer, forecasting, settings, or file-export calculations were changed.
