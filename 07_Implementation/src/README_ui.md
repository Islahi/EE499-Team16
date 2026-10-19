# Desktop UI — `ui.py`

The first desktop version connects your three editable Designer forms to the
existing program. It uses PySide6/Qt Widgets, not a web page. The compact network
toolbar is editable in `assets/main_window.ui`; Python binds its controls and
draws the icons. This update preserves the user's narrower sidebar and relocated
log checkbox. `bess.py`, `data_loader.py` and source workbooks are unchanged.

## Install and run

From the repository root (`EE499-Team16`) in PowerShell:

```powershell
python -m pip install -r .\07_Implementation\requirements-ui.txt
python .\07_Implementation\examples\run_ui.py
```

Alternatively, from `07_Implementation`, run `python -m src.ui`.
Do not run `python src/ui.py` directly: package-relative imports need the module
launcher. The optional Qt requirements are separate; backend scripts/tests do
not require Qt. The desktop dependency range currently targets Python 3.10–3.14.

## 1. Load Data

1. Choose a supported `.xlsx` network. For the existing data, choose
   `04_Research/Working_Data/Network_Data/IEEE_33Bus_Network_Data.xlsx`.
   Use **Auto** or **IEEE33** format. Supply frequency **60 Hz** as an explicit
   study input; this workbook does not provide it. Project-schema workbooks
   may supply their own frequency. The looped PJM case is not supported.
   `PJM_5Bus_Network_Data.xlsx` is not our radial five-bus example: it has five
   buses, six branches, generator voltage controls and transmission-line
   charging. It is deliberately rejected, not repaired by deleting lines.
   In that workbook, **PV bus** means specified active power/voltage magnitude,
   not photovoltaic panels. The existing radial five-bus Python fixtures are
   separate from this file; they are not currently a built-in UI data-source
   choice. Use IEEE33 or a supported project-format radial workbook in the UI.
2. Click **Load Network** to inspect buses/base demand and prefill existing PV
   installations. This is a preview, not a simulation or a data commit.
3. Choose PV input mode (table below). For irradiance or prepared PV power, the
   PV table is the **complete installed rating per bus** for this study, not
   additional equipment. Enter one integer bus ID and total rated kW per row.
   Loading another network replaces this table with that workbook's PV units.
4. Choose synthetic demand or a prepared load-power CSV. Synthetic demand uses
   the published hourly normal statistics, scaled by workbook base P/Q. Its
   seed makes repeated preparation reproducible; it is not measured demand.
5. Set study start and calendar months. The submitted date-only widget starts
   at midnight. For the local 2024 weather, try **2024-01-01**, **1 month** first,
   then **3 months**. January–March 2024 contains **2,184 hourly steps**, not
   2,160. Sources must cover the entire selected period; no hours are invented.
6. Press **OK** to prepare/check data in the background. Errors leave the dialog
   open. Only successful preparation commits data to the main window; Cancel
   does not replace the previously loaded study. Dialog fields are retained
   during this application session, including unapplied edits after Cancel.

| PV mode | What to supply |
|---|---|
| Open-Meteo irradiance CSV | Existing `OpenMeteo_Jeddah_2024_Hourly.csv`, explicit PV ratings, critical/standard irradiance |
| NASA POWER irradiance CSV | Existing NASA CSV; source clock is preserved, not automatically converted from LST to civil time |
| Prepared irradiance CSV | Hourly `timestamp,irradiance_w_m2` CSV; see the PV README |
| Prepared PV power CSV | Long-format power CSV plus explicit installed ratings; no irradiance conversion |
| No PV | Clears PV devices for this study and creates zero PV; ignores the disabled PV table |

Irradiance thresholds have units **W/m²**, not kW. Standard irradiance defaults
to 1,000 W/m²; critical irradiance must be supplied. For a software check only,
bus 6 / 1,000 kW / critical 120 W/m² are illustrative inputs, not recommended
design values or supplier specifications. This is the existing simple GHI-based
model, without a temperature, tilt or inverter-loss calculation.

Prepared load and PV power CSVs use:

```csv
timestamp,bus_id,p_kw,q_kvar
2024-01-01T00:00:00,2,100,50
2024-01-01T01:00:00,2,105,52.5
```

Include every study hour for every included bus, with no duplicate timestamp/bus
rows. Load CSVs must cover configured load buses; PV CSVs must cover configured
PV buses. IDs must belong to the network. Values must be finite; load P/Q and PV
P cannot be negative. PV P cannot exceed the explicit installed rating at its
bus. Rows outside the study interval can be present, but malformed source rows
are still rejected. Keep both sources on the same timezone-naive hourly clock.

## 2. Settings: what to change

**Simulation:** voltage limits default to 0.95–1.05 pu. Curtailment and shedding
can be enabled separately. Optional import/export groups unchecked mean **no
limit** (`None`); checked with value zero means a real **zero** limit. Reserve
is a fraction of horizon peak demand held as battery power and energy for the
configured duration, not a second generator. Thermal constraints are excluded.

**Battery:** for an individual battery run, enable Manual BESS and enter its
bus, positive power kW and energy kWh. Fill efficiencies explicitly, and check
minimum/initial/maximum SOC. The UI uses percentages, then divides by 100 for
the backend. A power rating is not an energy capacity.

**Dispatch:** choose **Net-load target**, then enter target kW. The request is
`original load − available PV − target`: discharge above target, charge below.
A positive target may charge from the grid. Zero is a valid explicit target,
not a guessed recommended value. SOC, reserve, rating and network constraints
may prevent tracking. Idle is diagnostic only. Without Manual BESS, Run
Simulation is a no-BESS baseline and does not apply the configured dispatch.

**Optimization:** select allowed buses and enter positive min/max/step values
for both power and energy. Example arithmetic only: min 100, max 250, step 100
creates `[100, 200, 250]`. Both endpoints are included; the last gap may be
shorter. Equal min/max creates one size, but still supply a positive step.
Each axis is limited to 10,000 entries as a software guard, not a supplier limit.
Small steps/many buses/iterations can make the search expensive. This is a
generic study grid; battery product data is not required.

Run Optimization searches these catalogs through the existing GWO, using the
same SOC/efficiency/dispatch inputs. It does **not** use the Manual BESS size or
installation bus. It requires target dispatch, allowed buses, valid battery
parameters and both explicit cost coefficients. For a quick wiring check use
a small population (at least 3), one iteration and a narrow size range before
attempting a three-month scenario search. GWO is not a global-optimality proof.

**Economics:** enable the group only when both `cost_per_kwh` and `cost_per_kw`
are intentional inputs. Cost = energy × cost/kWh + power × cost/kW. Unchecked
means unavailable, not free. Checked zeros explicitly mean zero-cost terms.
No supplier prices are invented; illustrative values are not design evidence.
WSM remains the existing raw, unnormalized 0.50/0.25/0.25 objective.

**Uncertainty:** enabling this group affects optimization, not an ordinary
simulation. It fits ARIMA to loaded history, generates Monte Carlo futures,
selects the requested best/worst/random cases and evaluates common candidates.
Defaults retain 100 generated and 15/15/15 selected cases. Forecast hours start
**after the last loaded historical hour**; they are not additional historical
weather rows. The selected cases are an equal-weight stress portfolio, not a
probability-preserving expected-value calculation. ARIMA fit/coverage failures
remain errors; the UI does not silently substitute another forecasting method.

**Apply** commits settings without closing. **OK** validates/applies/closes.
**Cancel** discards only edits since the last Apply/OK. New data or applied
settings clear earlier results so they cannot be exported as a new run.

## 3. Network, results and export

- Network is an automatically arranged **schematic**, not a geographical map or
  network editor. Lines and buses are vector graphics, not PNG fragments.
  Use Zoom In/Out, the mouse wheel over the diagram, and Fit. The wheel zooms
  in/out toward the cursor; dragging empty space pans the view. Select a bus,
  conductor or line ID for details. Long feeders may still need zooming after
  Fit. Moving/zooming the view does not alter electrical data.
- The single-line-style symbols are busbars, hollow triangular arrows for connected
  loads, rectangular solar PV symbols, a battery for BESS and a
  grid box at the slack bus. Each bus and its attached symbols form one clickable
  selection area. Equipment presence, not instantaneous demand/PV output, drives
  these symbols; PV stays visible at night. One load arrow represents aggregate
  load devices at that bus, not one arrow per customer. Arrows do **not** show
  computed feeder-flow direction. Bus labels show existing ID numbers only, not
  a repeated "Bus" prefix or new numbering. Repeated "Load" captions are removed;
  short PV/BESS/Grid labels and unique line IDs remain where useful. Tooltips
  retain full descriptions. There is no in-diagram legend. No formal IEC/IEEE
  symbol compliance is claimed. No icon download is needed. Compact spacing no
  longer reserves a caption beside every load, so conductor runs are shorter;
  annotated modes still reserve enough room for the displayed values.
- Before simulation, details show base load and installed PV rating. After
  simulation, details initially show the **last attempted hour**, then follow
  the selected timestamp, its voltage and operating point;
  failed-hour voltages are explicitly diagnostic. Green/red indicate calculated
  in/out-of-limit voltages when the Results layer is enabled. BESS is identified
  by its own symbol, not by overriding voltage colour. Optimization retains summary metrics, so its diagram does
  not invent optimized hourly voltages; run a manual battery simulation to
  inspect that design's time series.
- **Properties** and **Results** are independent checkboxes; both start off.
  Properties shows nominal bus kV, base P/Q demand, installed PV and BESS ratings
  (when configured), and line R/X in ohms. These are inputs, not calculated flow.
  Enabling Results opens a small timestamp window listing only retained simulation
  hours on the original source clock. OK applies the selected hour; Cancel while
  enabling leaves Results off. **Choose timestamp…** changes the hour later;
  cancelling that window preserves the current hour. A status line above the
  diagram identifies the hour only while Results is enabled. Bus details use
  this same selection, never another hour.
  Result labels show voltage pu, served P/Q load, actual PV/BESS kW, bus shedding/
  curtailment, and line sending-end P/Q, current A and active loss kW. BESS positive
  means discharge; line P/Q is referenced from the source-rooted parent toward the
  child, regardless of workbook endpoint order or drawing rotation. Missing control
  data is N/A, not an invented zero. Non-converged hours are listed explicitly;
  calculated diagram labels/voltage colours are suppressed for those hours.
  The selected-bus detail panel may still show clearly labelled diagnostic values.
  Optimization-only summaries cannot enable hourly Results. Applying settings,
  loading another study or starting a new run invalidates the old result selection.
- Arrangement is automatic, without Auto Arrange or branch-position controls.
  The longest downstream chain forms the spine. Subtree depth, parallel leaf
  count, downstream bus count and installed equipment estimate branch space.
  All lateral branches across the whole feeder share one balancing pass: larger
  branches are considered first, then assigned to the less occupied side, alternating
  on equal scores. A new junction does not restart at Above. IDs only break equal
  topology ties. Envelopes and side corridors avoid overlaps; this is a layout heuristic,
  not a guaranteed globally optimal routing algorithm for every possible feeder.
  Each lateral has its own offset busbar take-off and straight lead before a bend.
  Loads move to the opposite bar side; with branches on both sides, load equipment
  uses the other side of the bar. Bus numbers, impedance, voltages and hourly power
  do not decide physical positions. Loading a study chooses an initial horizontal/
  vertical view using the viewport aspect. Resizing changes the camera fit, not
  topology, branch order, branch sides or the user's rotation.
- Each busbar extends only far enough to cover its actual incoming/outgoing and
  installed load/PV/BESS connection ports, plus a small end margin. A plain/load-only
  bus does not reserve three equipment slots. Visible property/result annotations
  reserve separate space; they do not lengthen busbars. Turning layers off compacts
  spacing while preserving branch order, side assignments and chosen rotation.
- Fit, Zoom Out and Zoom In are compact vector-icon buttons with accessible names
  and tooltips. **90°** rotates clockwise without changing connectivity, sending-end
  definitions, data or selected hour; labels stay upright. Above/below become left/
  right after rotation. Fit shows the whole schematic; zoom in to read long feeders.
- **Selection details** expands/collapses the shared bus/line detail panel, which
  starts collapsed. Selected values still update while the panel is hidden. The relocated
  log checkbox retains its existing behaviour; hiding the log gives the diagram
  more height. Both panel and log changes refit the view without rerouting branches.
- Click a conductor or its line ID to select it; the conductor highlights orange
  (selection, not an overload warning). A 14-screen-pixel-wide hit corridor makes
  thin lines easier to pick at different zoom levels; visible bus equipment takes
  precedence at connection points. Line details show source-rooted endpoints, R/X,
  and retained-hour sending-end P/Q, current and active/reactive losses. The selected
  line and its detail values survive rotation, layer changes and timestamp changes.
  Missing hourly data remains "Not calculated"; non-converged hours suppress line
  results. Diagram Properties/Results toggles affect canvas labels, not the selected
  element's inspector. Clearing results removes old calculated inspector values.
- **Hide Diagram** is reversible and preserves inputs/results. **Clear Results**
  discards calculated output and timestamp selection, preserving loaded inputs and
  settings. **Clear Workspace** asks for confirmation before clearing loaded
  inputs, results, settings and layout overrides. Neither action deletes source
  workbooks, CSVs or exported folders; the run log remains as session history.
  These conflicting controls are disabled during a job; programmatic clear handlers
  also refuse to clear an active job.
- Results are text from `results.py`. Read completion, convergence, feasibility
  and curtailed/shed energy separately. A voltage-feasible result may still have
  substantial unserved demand. A successful search does not prove a battery
  beats no battery; compare separately under the same study settings.
- Progress reports stage-local work counts, not estimated remaining time or
  numerical convergence. GWO percentage is completed iterations/configured
  iterations. The stage label also shows candidate, scenario, simulation hour,
  control trial and FBS sweep counters as applicable. FBS sweeps are reported
  against their maximum; convergence can occur earlier (voltage delta is in
  the tooltip/log). One candidate can take much longer than another.
  Unknown-duration stages remain indeterminate. Snapshots are throttled to four
  per second, except stage/candidate/iteration boundaries. Detailed periodic
  logs are limited to one per ten seconds plus those boundaries.
- Every log entry has the device's local date/time and UTC offset. Source-data
  timestamps in simulation messages are separate. The live elapsed timer stops
  on success or failure; successful Results/exports include start, finish and
  measured duration. A 15-second silence warning means **no worker counter
  update**, not proof of a deadlock or proof the worker is still computing.
  The log is read-only, collapsible and keeps the most recent 5,000 lines.
- Current stage/candidate/scenario/hour/FBS text is written to the run log rather
  than occupying space beside the progress bar. The compact row retains only
  the percentage bar and elapsed timer.
- The Study Period uses calendar months. For smaller runs, use a shorter source
  dataset/study period and a smaller candidate catalog; there is no separate
  24-hour diagnostic control in the desktop.
- Export Results asks for a **new folder name**, not a filename/extension. The
  dialog uses a save-path picker because the folder must not already exist.
  Existing directories are refused. Export saves the retained result, source
  hashes and run settings without rerunning the calculation. Full serialized
  networks/profiles and uncertainty model diagnostics are not included.
- The Results tab opens with a concise summary. **Show full details** toggles the
  source hashes, settings, provenance and complete search catalogs in the same
  read-only panel. Exports always retain the full context.
- Conflicting actions and closing are blocked during an active job. There is
  no Cancel Run yet: wait for completion. A worker error restores controls and
  shows details in the log. Do not forcibly close the process to cancel a study.

## 4. Code and Designer ownership

| File | Responsibility |
|---|---|
| `ui.py` | Loads forms; explicit window/dialog handlers, timestamp picker and workers |
| `network_diagram.py` | Bus/line selection, wheel-zoom view, symbols, rotation and annotation layers |
| `network_icons.py` | Palette-aware Fit and Zoom vector icons, including disabled states |
| `ui_workflow.py` | Qt-free data preparation, run settings and public backend orchestration |
| `progress.py` | Qt-free counters, throttled nested snapshots and duration formatting |
| `dispatch.py` | User-configured net-load-target operating policy |
| `network_layout.py` | Qt-free global branch balancing, connection-driven bars and layer-aware spacing |
| `assets/*.ui` | Your editable Designer layouts; not generated Python |
| `../examples/run_ui.py` | Launcher independent of working directory |

The submitted sidebar is `frame_action` (singular), which is supported. The
study start is `QDateEdit`, which is supported as midnight. Python extends the
PV source choices and adds these settings without modifying the source forms:

| Runtime object name | Widget / location |
|---|---|
| `group_dispatch_policy` | QGroupBox / Battery page |
| `combo_dispatch_policy` | QComboBox: Idle first, Net-load target second |
| `spin_dispatch_target_kw` | QDoubleSpinBox / Dispatch group, kW |
| `spin_opt_power_step_kw` | QDoubleSpinBox / Optimization bounds, kW |
| `spin_opt_energy_step_kwh` | QDoubleSpinBox / Optimization bounds, kWh |

The network controls now belong to `main_window.ui` inside `panel_network_tools`:
`btn_fit_network`, `btn_zoom_in`, `btn_zoom_out`, `btn_rotate_network`,
`chk_network_properties`, `chk_network_results`, `btn_result_timestamp`,
`chk_hide_diagram`, `chk_bus_details`, `btn_clear_results`, `btn_clear_workspace`
and `lbl_diagram_timestamp`. The detail inspector also contains `lbl_line_details`.
Keep these object names when editing in Designer; `chk_bus_details` now has the
visible caption "Selection details" but retains its existing object name.
Python supplies palette-aware icons and limits the three icon buttons to 36×32
logical pixels with 20×20 icons (Qt scales logical pixels for display DPI).
Auto Arrange, both branch combos and the runtime `panel_network_display` are gone.
The timestamp picker is a small Python-built `TimestampDialog`, not another `.ui`.
Keep `network_view` as a regular QGraphicsView in Designer: the form loader creates
the Python `NetworkView` subclass automatically for this object, adding wheel zoom
and forgiving line picking without a Designer plugin or generated form code.

You can later add the Battery/Optimization runtime settings objects in Designer using exactly their names; Python
checks for their presence instead of adding duplicates. Keep combo item order
and numeric ranges (0–1e9, two decimals); step zero means not supplied and is
rejected when starting optimization. Spin-box arrow increments do not define
search resolution. Do not add automatic OK→accept connections to either dialog:
Python must validate before it closes. Keep the existing rejected→reject and
settings-page/log connections. Do not mix PyQt5 and PySide6 objects.

The coding-style skill influenced the focused modules, explicit classes and
named handlers; numerical equations remain in the engineering modules.

## 5. What to test

From the repository root:

```powershell
python -m unittest discover -s .\07_Implementation\tests -p test_ui_workflow.py -v
python -m unittest discover -s .\07_Implementation\tests -p test_ui.py -v
python -m unittest discover -s .\07_Implementation\tests -v
```

The Qt tests run offscreen and skip when Qt is not installed. They exercise the
actual forms, validation, Apply/Cancel, preparation, real simulation/GWO, worker
success/error/cleanup, close guarding, selection, stale results and safe export.
Also test these interactively on your Windows display:

1. Load the IEEE33 workbook, No PV and synthetic load for one month. Confirm
   the diagram, zoom/fit, bus selection and missing-file/error messages.
2. Run without a battery; inspect shedding and voltage results. Then repeat
   using Open-Meteo with explicit PV ratings for Jan–Mar 2024.
3. Enable a manual battery and target dispatch; inspect changed output and SOC.
   Try invalid SOC/efficiency or unset sizes and verify useful errors.
4. Apply settings, edit them, then Cancel; confirm the applied values remain.
5. Run a small configured optimization; enable uncertainty only after that
   works. Confirm the Results forecast dates when uncertainty is enabled.
6. Export to a new folder, then try it again; the first export must remain
   untouched. Change inputs and confirm old results/export are cleared.
7. Resize at your usual Windows scaling, inspect all five Settings pages, and
   try closing during a run; it should stay open and explain why.
8. Enable Properties before running; check base kV, P/Q, PV and line R/X. Run a
   simulation, enable Results, select the first hour and compare a selected bus
   against that hour's labels. Change timestamp and cancel another selection.
   Toggle each layer independently; repeat after rotating through all four views.
9. Load IEEE33: branches should occupy both sides, not all Above. Reload the same
   study to check deterministic placement. Rotate through four views, resize the
   window, and toggle annotation layers: spacing may change but branch sides and
   order must not. Check load-only bars versus buses with PV/BESS or extra branches.
10. Hide/unhide the diagram and confirm results remain exportable. Clear Results
    and confirm the network stays loaded. Test No then Yes on Clear Workspace;
    confirm the workspace is empty but source files and previous exports remain.
11. Toggle Selection details and the relocated log checkbox; the diagram should gain
    height when panels are hidden. Check icon tooltips and readability at your
    normal Windows scaling. Open `main_window.ui` in Designer to edit the toolbar.
12. Check numbered buses and absent Load captions. Wheel forward/backward over the
    diagram; confirm zoom changes, then drag empty space to pan. Click a line or
    its ID and enable Selection details: R/X should be available before running.
    After simulation, compare that line's P/Q/current/losses with the selected hour.
    Rotate, change timestamp, then clear results: selection should persist without
    retaining stale calculated values. Clicking a bus should restore bus fields.

Still separate work: cooperative cancellation, Windows EXE
packaging, real-study validation, sourced battery/cost inputs, optional charts,
and the deferred web version. The desktop is an integrated prototype, not a
claim of validated optimal storage deployment.
