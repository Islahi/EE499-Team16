# Term 2 Implementation

[V16](Release_Notes/V16/V16_CHANGES.md) is the current BESS
Planning Tool. Its source and desktop assets are in `src/`. The app supports
radial-network workbooks, hourly load and PV data, Numba Forward/Backward
Sweep, battery planning and dispatch, and saved HTML results dashboards.

## Run on Windows

From `07_Implementation`, using Python 3.14:

```bat
py -3.14 -m pip install -r requirements-accelerated.txt
start_windows.bat
```

The Information button shows effective settings, equations, and model
assumptions. For setup, simulation, optimization, and saved reports, use the
[V15.6 quick start](Release_Notes/V15_6/V15_6_CLEANUP_QUICKSTART.md).
New runs use `src/Results/`. Saved run folders can also be opened from the
desktop. See the [V15.6 release notes](Release_Notes/V15_6/V15_6_CHANGES.md)
for the session export fix and recovery instructions.

V16 accepts compatible electrical edits made in Excel and archives both
workbook fingerprints with the result. The bus and line inspectors follow the
selected hour. **Plot bus** and **Plot line** open the matching report view.
Use **Study inputs** for archived load and PV curves, **Decisions** for the
control ledger, and **Compare runs** for separate saved reports. Set **GA stall
generations** in **Settings**. The default is 6.

## Verify and maintain

```bat
py -3.14 -m pip install -r requirements-test.txt
test_windows.bat -q
CHECK_WINDOWS_GUI.bat --no-pause
```

- Application code and technical notes are under [src](src/docs/README.md).
- Saved-run recovery and dashboard regeneration utilities are beside the launcher.
- The [validation index](Validation/README.md) lists each test kit, its inputs,
  and its entry point. Standalone data-preparation and plotting tools are under
  [Tools](Tools/README.md).
- The [results guide](Results/README.md) identifies the active run directory and
  where to recover archived demonstration outputs.
- [Earlier releases](Release_Notes/) document the evolution of the solver and UI.

The active suite covers V16 workbook compatibility, electrical diagnostics,
report integrity, GA stall behavior, and prior solver and dispatch regressions.
With Node.js installed, run `node --test tests/test_dashboard_blocks.cjs` for
the report's indexed data and plot export checks.
