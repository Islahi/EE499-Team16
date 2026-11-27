# Term 2 Implementation

[V17.0.2](Release_Notes/V17_0_2/CHANGELOG.md) is the current BESS
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

### Manual fleets and optimization

In **Settings → Battery / Manual Simulation**, enable the manual fleet and add
one row per battery. Enter its non-slack bus, power in kW, and energy in kWh.
The table shows each duration and the enabled fleet totals. All batteries share
the study SOC, efficiency, and duration limits. **Save settings** or **Apply**
commits the rows, including disabled rows. **Cancel** restores the last saved
values. **Simulation** dispatches the enabled batteries together. For a
No-BESS result, turn off the manual fleet and run a separate simulation.

Use **Corrective actions** in the same tab to choose **Enabled**, **Disabled**,
or **Compare both**. Enabled uses the current controller and the configured
voltage, line, and grid limits. It respects the load-shedding and PV-curtailment
permissions. Check feasibility and any remaining violations after the run.

Disabled runs FBS on the prescribed active and reactive demand and PV.
Installed batteries stay idle at their initial SOC. A converged result can
violate limits. Its demand and cost describe the modeled operating point.
Zero corrective shedding means that no automatic shedding was applied.
Unsolved hours retain their timestamps and prescribed inputs.

Compare both stores **Without corrective actions** and **With corrective
actions** in one report with shared inputs and distinct hourly exports. With
a battery installed, this compares idle operation with controlled dispatch.
Use the dashboard scenario selector to inspect either result. Base Case and
Optimize keep their existing behavior.

Standard **Optimize** searches up to the chosen limit of one, two, or three
batteries. Under **Advanced optimization**, explicitly enable experimental
optimization and choose a maximum from four up to the number of selected
non-slack buses. The default is four. The experiment uses coupled daily MILP
dispatch, and the optimizer may select a smaller fleet or No BESS.

### Dashboard charts

On a time-series plot, wheel to zoom around the pointer and drag horizontally
to pan. The Y scale stays fixed to the selected period. With the chart focused,
use Left/Right to pan, +/− to zoom, Shift+Left/Right to inspect a timestamp, or
Escape to reset the viewport to the selected period. Linked charts share the
viewport. Use **Edit → Link time** to give a chart its own time range.
**Save PNG** captures the visible chart. **Exact CSV** exports its visible
timestamps or buckets at retained precision.

In **Study Inputs** or **Power & Energy**, open **Show chart controls** and
choose **Group by** and a profile category or bus. Category presets can be
edited and pinned to **My Dashboard**. Categories come from archived bus
assignments and may represent scenario assumptions. Demand without an explicit
assignment is **Unclassified**. Incomplete category values appear as gaps.
Use **Compare Runs** to open a saved No-BESS or alternative fleet report.
Comparison charts align recorded timestamps and report coverage differences.

To build a custom category chart, choose **Show chart controls → Add chart**,
or **Edit** an existing chart. In **Add series**, set **Series scope** to
**Load profile category** and select a recorded quantity. Check the categories
you want and choose **Add selected series**. Each category can be edited,
reordered, or hidden independently. Switch the scope to **System total** or
**Individual bus** to add compatible series to the same chart.

**Summary** shows whole-study tables for energy, voltage, coverage, costs,
and battery installations. Select two saved scenarios for side-by-side values
and deltas. The CSV buttons export full-precision values. Chart zoom and
resolution leave whole-study totals unchanged.

**Load profile and electricity consumption** shows the full-period totals for
each archived category and demand bus. Switch scenarios in that section or
expand **Individual bus consumption** to filter, sort, or inspect a bus.
Estimated spending applies the recorded study grid-import tariff to served
energy. It is an illustrative estimate and is separate from system costs.
Missing full-period contributions are shown as N/A with coverage in the CSV.

Regenerate a dashboard from saved numerical files without solving again.

```bat
py -3.14 -m src.dashboard "path\to\run_folder"
```

## Verify and maintain

```bat
py -3.14 -m pip install -r requirements-test.txt
test_windows.bat -q
CHECK_WINDOWS_GUI.bat --no-pause
```

- Application code and technical notes are under [src](src/docs/README.md).
- Saved-run repair and dashboard regeneration are under [Tools/Recovery](Tools/Recovery/README.md).
- The [Qt design guides](References/Qt/Qt_Desktop_Implementation_Guide.md) document
  the editable forms and desktop integration.
- The [Windows packaging recipe](Packaging/BESS_Planning_Tool.spec) can be run from
  the repository root with `python -m PyInstaller 07_Implementation/Packaging/BESS_Planning_Tool.spec`.
- The [validation index](Validation/README.md) lists each test kit, its inputs,
  and its entry point. Standalone data-preparation and plotting tools are under
  [Tools](Tools/README.md).
- The [results guide](Results/README.md) identifies the active run directory and
  where to recover archived demonstration outputs.
- [Earlier releases](Release_Notes/) document the evolution of the solver and UI.

The active suite covers V16 workbook compatibility, electrical diagnostics,
report integrity, GA stall behavior, and prior solver and dispatch regressions.
With Node.js installed, run
`node --test tests/test_dashboard_blocks.cjs tests/test_dashboard_workspace.cjs tests/test_dashboard_categories.cjs`
for the report's indexed data, timeline, and export checks.

For a browser smoke check, open a saved `dashboard.html` directly from disk.
Wheel above the data and then over the page margin to check chart zoom and
normal page scrolling. Drag the plot, click a timestamp, and reset. Repeat
with two linked charts and an independent chart, then at 125% and 150%
browser zoom. Check the visible chart CSV against the chart's time labels.
