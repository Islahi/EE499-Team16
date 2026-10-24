# Build our desktop UI in Qt Designer

This is a step-by-step manual build guide for the user, based on our discussion
and initial PowerPoint design. It specifies widgets, object names and useful
properties. **You build the forms; Python wiring comes afterward.** No `.ui`
files or application code were generated as part of writing this guide.

Read alongside [the desktop implementation guidance](Qt_Desktop_Implementation_Guide.md).
The coding-style reference contributes editable forms, explicit widget names
and named handlers, not the password manager's appearance or unrelated features.

## 1. What to build and save

Use **Qt Widgets Designer**, not Qt Design Studio's QML interface. Qt 6 Designer
is recommended for the planned Qt 6 application; PySide6 is still the proposed
Python binding, not a decision forced by these forms. If you already have Qt 5
Designer, these standard widgets are broadly similar, but the forms must later
be checked with the chosen binding/version. Do not mix Python bindings.

Create three forms with **File > New** and save them here (create the `assets`
folder in the project if it does not exist):

| File under `07_Implementation/src/assets/` | New Form template                    | Root `objectName` | `windowTitle`        | Suggested initial size |
| -------------------------------------------- | ------------------------------------ | ------------------- | ---------------------- | ---------------------- |
| `main_window.ui`                           | Main Window (`QMainWindow`)        | `MainWindow`      | `BESS Planning Tool` | 1200 x 800             |
| `load_data_dialog.ui`                      | Dialog without Buttons (`QDialog`) | `LoadDataDialog`  | `Load Data`          | 900 x 720              |
| `settings_dialog.ui`                       | Dialog without Buttons (`QDialog`) | `SettingsDialog`  | `Settings`           | 960 x 720              |

These dimensions are starting geometry, **not fixed sizes**. The sizes/ranges
in this guide are UI recommendations unless identified as existing backend
defaults. Keep the forms resizable. Use scroll areas for the larger input pages.
Build the main window first, preview it, then the two dialogs.

Useful shortcuts: F3 widget editing, F4 signals/slots, Ctrl+R preview, Ctrl+S
save. Designer menus may differ slightly by release. Use the **Object Inspector**
to select the exact container and the **Property Editor** to change properties.

The Widget Box may display a friendly name rather than the class name:
`Push Button` = `QPushButton`, `Double Spin Box` = `QDoubleSpinBox`,
`Plain Text Edit` = `QPlainTextEdit`, `Graphics View` = `QGraphicsView`.

Size shorthand used below: to set a "minimumWidth" or "minimumHeight", expand
**minimumSize** in Property Editor and edit its Width/Height child; likewise
use **maximumSize** for maximum width/height. These are not separate properties
in every Designer version. Leave unconstrained maximum dimensions at Qt's
default. `sizePolicy` also expands into horizontal/vertical policies.

## 2. Basics you will use repeatedly

### Widget name versus visible text

- `objectName` is the stable Python-facing identifier, e.g. `btn_load_data`.
- `text`, `title` and `windowTitle` are what a person sees, e.g. `Load Data`.
- Set both deliberately. Do not leave important inputs named `doubleSpinBox_7`.
- Names must be unique inside each form. The listed control names are the
  planned contract for later Python bindings; preserve them when editing.
- Static field labels can use `lbl_` plus the field's name. Do not use a label
  as an editable input or a clickable button.

### Use layouts, not fixed coordinates

1. Drag a container (`QWidget`, `QFrame`, group box or tab page) onto the form.
2. Drag its controls **inside** it. Check their parent in Object Inspector.
3. Select the intended child controls and use **Lay Out Horizontally**,
   **Vertically**, **in a Grid**, or **in a Form** as appropriate.
4. Give the container itself a top-level layout. Repeat for outer containers.
5. For `QMainWindow`, apply the outer content layout to **centralwidget**, not
   the `QMainWindow` itself. Dialogs can have a layout on the root dialog.

Use a form layout for label/input pairs, a horizontal layout for a file path
and Browse button, and a vertical layout for panels. A vertical spacer pushes
later buttons down. Set ordinary layout margins to approximately 12 px and
spacing to 8 px; these are visual choices, not engineering parameters.

Layout shortcuts: Ctrl+1 horizontal, Ctrl+2 vertical, Ctrl+5 grid, Ctrl+6 form;
Ctrl+0 breaks a layout. **Ctrl+3/4 create horizontal/vertical splitters from
selected widgets**: Designer treats splitters as a layout operation, so you do
not need to find a draggable Splitter entry. [Qt layout instructions](https://doc.qt.io/qt-6/designer-layouts.html).

### Numeric input rules

Use `QSpinBox` for integers and `QDoubleSpinBox` for decimal values. For decimal
inputs set **decimals first, then minimum/maximum/value**, since changing the
precision can round the other properties. Set `keyboardTracking=false` and
`wrapping=false`. Read values in Python with `value()`, not by parsing the unit
suffix from `text()`. [Qt numeric widget reference](https://doc.qt.io/qt-6/qdoublespinbox.html).

In the tables below:

- **Power box**: `QDoubleSpinBox`, min 0, max 1000000000, decimals 2,
  singleStep 10, suffix ` kW`.
- **Energy box**: same, but suffix ` kWh`.
- **Required positive box**: value 0 and `specialValueText="Set value"` until
  supplied. Zero is a UI sentinel, NOT a valid positive engineering setting.
  Python must reject it when the relevant feature is enabled.
- **Percent box**: `QDoubleSpinBox`, min 0, max 100, decimals 2, singleStep 1,
  suffix ` %`.
- **Seed box**: `QSpinBox`, min 0, max 2147483647, value 42.

The large maxima above are editable UI ceilings, not approved study bounds or
supplier ratings. The arrow's `singleStep` is **not** the optimizer's search
resolution. Keep kW/kWh distinct. In Python divide percentages by 100 before
passing SOC, reserve or efficiencies to the backend.

## 3. Main window: `main_window.ui`

### 3.1 Create this object hierarchy

```text
MainWindow (QMainWindow)
  centralwidget (QWidget; vertical layout)
    splitter_main (QSplitter; Horizontal)
      frame_actions (QFrame; vertical layout)
        lbl_app_title
        btn_load_data
        btn_settings
        vertical spacer
        btn_run_simulation
        btn_run_optimization
        vertical spacer
        btn_export_results
        lbl_data_status
      panel_workspace (QWidget; vertical layout)
        tabs_workspace (QTabWidget)
          tab_network (QWidget; vertical layout)
            panel_network_tools (QWidget; horizontal layout)
              btn_zoom_in, btn_zoom_out, btn_fit_network
            network_view (QGraphicsView)
            group_bus_details (QGroupBox; form layout)
              lbl_bus_id, lbl_bus_voltage, lbl_bus_load, lbl_bus_pv
          tab_results (QWidget; vertical layout)
            results_text (QPlainTextEdit)
        panel_progress (QWidget; horizontal layout)
          lbl_stage, progress_run (QProgressBar)
    panel_log_header (QWidget; horizontal layout)
      chk_show_log (QCheckBox)
    run_log (QPlainTextEdit)
  statusbar (QStatusBar)
```

To make `splitter_main`, place `frame_actions` and `panel_workspace` side by
side, select both, then **Lay Out Horizontally in Splitter**. Rename the created
splitter. Lay out the central widget vertically with the splitter, log header
and log editor. Set its layout's `layoutStretch` / stretch setting to `1,0,0`
if exposed by your version (otherwise leave for Python): the workspace
gets extra height, not the log. Keep the default status bar; menus/toolbars are
not required for this first version (remove an unused menu bar if desired).

### 3.2 Main-window properties

| Widget / objectName                                    | Properties to set                                                                                                                                  |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `MainWindow`                                         | `minimumSize` about 900 x 600; leave maximum size unrestricted                                                                                   |
| `splitter_main`                                      | `orientation=Horizontal`; `childrenCollapsible=false`; `handleWidth=6`                                                                       |
| `frame_actions`                                      | `frameShape=NoFrame`; minimumWidth 200; maximumWidth 300; horizontal sizePolicy Preferred                                                        |
| `lbl_app_title`                                      | `text=BESS Planning`; `wordWrap=true`; font about 14 pt, bold                                                                                  |
| `btn_load_data`                                      | `text=Load Data`; minimumHeight 38                                                                                                               |
| `btn_settings`                                       | `text=Settings`; minimumHeight 38                                                                                                                |
| `btn_run_simulation`                                 | `text=Run Simulation`; `enabled=false`; minimumHeight 38                                                                                       |
| `btn_run_optimization`                               | `text=Run Optimization`; `enabled=false`; minimumHeight 38                                                                                     |
| `btn_export_results`                                 | `text=Export Results`; `enabled=false`; minimumHeight 38                                                                                       |
| `lbl_data_status`                                    | `text=No network or profiles loaded`; `wordWrap=true`                                                                                          |
| `tabs_workspace`                                     | `currentIndex=0`; `tabPosition=North`; `tabsClosable=false`; `movable=false`; sizePolicy Expanding/Expanding                               |
| `tab_network`, `tab_results`                       | Tab titles `Network`, `Results`; each page needs its own vertical layout                                                                       |
| `btn_zoom_in`, `btn_zoom_out`, `btn_fit_network` | Text `Zoom +`, `Zoom -`, `Fit`; start `enabled=false`                                                                                      |
| `network_view`                                       | sizePolicy Expanding/Expanding; `dragMode=ScrollHandDrag`; scrollBar policies AsNeeded; minimumSize about 400 x 280                              |
| `group_bus_details`                                  | `title=Selected Bus`; values below are labels, not editable fields                                                                               |
| `lbl_bus_id`                                         | `text=No bus selected` (next to static label `Bus`)                                                                                            |
| `lbl_bus_voltage`                                    | `text=Not calculated` (static label `Voltage (pu)`)                                                                                            |
| `lbl_bus_load`                                       | `text=Not available` (static label `Load (kW / kvar)`)                                                                                         |
| `lbl_bus_pv`                                         | `text=Not available` (static label `PV (kW)`)                                                                                                  |
| `results_text`                                       | `readOnly=true`; `undoRedoEnabled=false`; `placeholderText=Run a simulation or optimization to view results`; maximumBlockCount 0            |
| `lbl_stage`                                          | `text=Ready`; minimumWidth about 160                                                                                                             |
| `progress_run`                                       | `minimum=0`, `maximum=100`, `value=0`; `textVisible=true`; `format=%p%`                                                                  |
| `chk_show_log`                                       | `text=Show run log`; `checked=true`                                                                                                            |
| `run_log`                                            | `readOnly=true`; `undoRedoEnabled=false`; `maximumBlockCount=5000`; `lineWrapMode=NoWrap`; maximumHeight about 160; minimumHeight about 80 |

The network view is intentionally empty in Designer. Do NOT draw 33 buses or
import PNG line segments there. Python will create the `QGraphicsScene` and
perform automatic layout later. Likewise, selected-bus values will be populated
from the current loaded/run data; do not put pretend calculated values in them.

Use a **plain-text** results editor because the first output is a text summary.
It can show the existing Markdown summary literally; if rendered formatting is
wanted later, explicitly switch to a text browser/Markdown rendering in Python.
Do not limit the results block count as you do for the scrolling run log.

Python will switch progress to `minimum=maximum=0` for an indeterminate stage,
then restore a numeric range when a real total exists. Preview cannot demonstrate
backend progress. Turning off `chk_show_log` can hide the editor; a checkbox alone
does not collapse it without the connection in Section 11.

## 4. Load Data dialog: `load_data_dialog.ui`

Use a vertical layout on `LoadDataDialog` containing:

1. `lbl_load_help` (`QLabel`, wordWrap): `Load a radial network, then prepare or import matching hourly profiles.`
2. `tabs_data` (`QTabWidget`) with `tab_network_data`, `tab_pv_data`, `tab_load_data`.
3. `group_study_period` (`QGroupBox`, title `Study Period`, form layout).
4. `lbl_load_validation` (`QLabel`, wordWrap, text `Data has not been validated`).
5. `buttons_load_data` (`QDialogButtonBox`, standardButtons `Ok|Cancel`).

Three tabs keep the same Network/Irradiance/Load sections from your mockup,
without squeezing every input into three narrow columns. Give each tab a
vertical layout. For a long page, insert a `QScrollArea`, set
`widgetResizable=true`, and lay out its **scrollAreaWidgetContents**. Leave
`QScrollArea.frameShape=NoFrame`. Do not put controls beside its contents by
accident; inspect the parent hierarchy.

For every file row below: use a `QLineEdit` (readOnly true, clearButtonEnabled
false, placeholder `No file selected`) beside a `QPushButton` with text
`Browse...`. The Browse click opens a `QFileDialog` later in Python; a file dialog
is not a permanent widget placed on this form.

### 4.1 Network tab

Use a group box with a form layout and these controls:

| Type               | objectName               | Label / properties                                                                                      |
| ------------------ | ------------------------ | ------------------------------------------------------------------------------------------------------- |
| `QLineEdit`      | `edit_network_path`    | `Network workbook`; file-row rules above                                                              |
| `QPushButton`    | `btn_browse_network`   | `Browse...`; Python filter will be `*.xlsx`                                                         |
| `QComboBox`      | `combo_network_format` | `Workbook format`; items in order `Auto`, `Project`, `IEEE33`; currentIndex 0                   |
| `QDoubleSpinBox` | `spin_frequency_hz`    | `Frequency`; min 0, max 1000, decimals 2, value 0, specialValueText `Set frequency`, suffix ` Hz` |
| `QPushButton`    | `btn_load_network`     | `Load Network`; enabled false until path/frequency requirements are met in Python                     |
| `QLabel`         | `lbl_network_summary`  | wordWrap; `No network loaded`                                                                         |

Bus count is OUTPUT in `lbl_network_summary`, not an input. Python reads the
actual workbook topology. This loader cannot load the looped PJM workbook or
arbitrary Excel layouts; do not advertise those as supported.
For IEEE33, frequency is required. For a project-schema file, Python may read
the stored frequency; 0 in this widget means unspecified, never literal 0 Hz.
An explicit positive value may override it. Do not hard-code 60 as source data.

### 4.2 PV / Irradiance tab

| Type               | objectName                   | Label / properties                                                                                                                                                               |
| ------------------ | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `QComboBox`      | `combo_pv_source`          | `Input type`; items `Open-Meteo irradiance CSV`, `NASA POWER irradiance CSV`, `Prepared irradiance CSV`, `Prepared PV power CSV`, `No PV`; currentIndex 0            |
| `QLineEdit`      | `edit_pv_source_path`      | `Source CSV`; file-row rules                                                                                                                                                   |
| `QPushButton`    | `btn_browse_pv_source`     | `Browse...`                                                                                                                                                                    |
| `QGroupBox`      | `group_pv_conversion`      | `title=Irradiance Conversion`; vertical layout                                                                                                                                 |
| `QTableWidget`   | `table_pv_installations`   | Inside conversion group; columnCount 2; rowCount 1; headers `Bus ID`, `PV Rating (kW)`; selectionBehavior SelectRows; selectionMode SingleSelection; minimumHeight about 100 |
| `QPushButton`    | `btn_add_pv_row`           | `Add PV Row`; in horizontal row with Remove below                                                                                                                              |
| `QPushButton`    | `btn_remove_pv_row`        | `Remove Selected Row`                                                                                                                                                          |
| `QDoubleSpinBox` | `spin_critical_irradiance` | min 0, max 10000, decimals 2, value 0, specialValueText `Set critical irradiance`, suffix ` W/m²`                                                                           |
| `QDoubleSpinBox` | `spin_standard_irradiance` | min 0, max 10000, decimals 2, value 1000, suffix ` W/m²`                                                                                                                      |
| `QLabel`         | `lbl_pv_status`            | wordWrap; `PV input not validated`                                                                                                                                             |

The PV table is editable configuration, not a grid editor. Keep cells blank in
Designer: Python will supply bus-selection/numeric delegates or validate cell
text before constructing `PVUnit`s. Add/Remove rows require Python; do not put
unverified bus IDs or PV ratings into the saved form. If the workbook already
contains PV devices, Python must show/merge them explicitly, not add them twice.
`No PV` must also handle any existing installations explicitly, not leave hidden
active devices in the study model.

Python disables conversion controls for Prepared PV Power / No PV, since there
is no irradiance conversion in those modes. A prepared power file carries bus
IDs itself; its ratings/required equipment must be reconciled with the network.
Critical irradiance is required only when converting, with `0 < Rc < Rstd`.
1000 W/m² is the existing standard-irradiance model default, not an array size.

### 4.3 Load tab

| Type            | objectName               | Label / properties                                                                                     |
| --------------- | ------------------------ | ------------------------------------------------------------------------------------------------------ |
| `QComboBox`   | `combo_load_source`    | `Demand input`; items `Generate synthetic load`, `Import prepared load CSV`; currentIndex 0      |
| `QWidget`     | `panel_load_import`    | Horizontal layout with the next two file controls; initially enabled false                             |
| `QLineEdit`   | `edit_load_path`       | File-row rules; placeholder `Select prepared load CSV`                                               |
| `QPushButton` | `btn_browse_load`      | `Browse...`                                                                                          |
| `QGroupBox`   | `group_synthetic_load` | `title=Synthetic Demand`; form layout                                                                |
| `QLabel`      | `lbl_load_method`      | wordWrap; `Normal hourly statistics from Ali / Shaaban / Sindi (2022), scaled to network base loads` |
| `QSpinBox`    | `spin_load_seed`       | Seed-box settings; label `Synthetic-load seed`                                                       |
| `QLabel`      | `lbl_load_status`      | wordWrap; `Demand input not validated`                                                               |

Use a combo rather than two independent checkboxes: exactly one demand source
is active. Python switches the panels according to the combo. Do not add a
distribution-family selector yet: only the documented normal model is built.
The imported CSV needs hourly `timestamp,bus_id,p_kw,q_kvar`. Validation messages
must say WHICH times/buses mismatch rather than only `Match or not`.

### 4.4 Study period and dialog buttons

| Type              | objectName            | Label / properties                                                                                                           |
| ----------------- | --------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `QDateTimeEdit` | `date_study_start`  | `Start (source clock)`; displayFormat `yyyy-MM-dd HH:mm`; calendarPopup true; illustrative dateTime `2024-01-01 00:00` |
| `QSpinBox`      | `spin_study_months` | `Calendar months`; min 1, max 120, value 3                                                                                 |
| `QLabel`        | `lbl_study_period`  | wordWrap; `Hourly data; duration and coverage will be checked`                                                             |
| `QLabel`        | `lbl_source_clock`  | wordWrap; `Use one documented source clock; no automatic timezone mixing`                                                  |

Python sets an exact hourly start, calculates the exclusive end by adding
calendar months and checks complete source coverage/alignment. Do not assume
three months always means 2160 hours. These dates are only a visible starting
value for the supplied 2024 files, not a hidden program requirement.

`buttons_load_data`: OK means validate/prepare into temporary/new run storage
and commit the data selection only on success. Cancel discards staged changes.
**Do not connect `accepted()` straight to `accept()` in Designer**: Python must
validate first. Remove such a connection if a Designer template created it.
It is fine to connect `rejected()` to the dialog's `reject()`.

## 5. Settings dialog structure: `settings_dialog.ui`

Use the following hierarchy:

```text
SettingsDialog (QDialog; vertical layout)
  panel_settings_body (QWidget; horizontal layout)
    list_settings_pages (QListWidget)
    stack_settings_pages (QStackedWidget)
      page_battery
      page_operation
      page_optimization
      page_economics
      page_uncertainty
  lbl_settings_validation (QLabel)
  buttons_settings (QDialogButtonBox)
```

For `list_settings_pages`, double-click to edit items. Add these five items in
EXACTLY this order: `Battery`, `Operation`, `Optimization`, `Economics`,
`Uncertainty`. Set `currentRow=0`, selectionMode SingleSelection, minimumWidth
150, maximumWidth about 200, editTriggers NoEditTriggers.

For the stack, add/rename pages to match the order above and set currentIndex 0.
Each page needs a vertical layout. Use a `QScrollArea` inside long pages as in
Section 4, with a form-layout contents widget. Add a vertical spacer after the
fields if needed so they stay near the top. The stack's small Designer page
arrows DO NOT appear at runtime; connect list selection as in Section 11.

Set `lbl_settings_validation.text=Settings have not been applied` and wordWrap
true. Set `buttons_settings.standardButtons=Ok|Apply|Cancel`. Apply validates
and saves without closing; OK validates, saves and closes; Cancel discards
edits made since the last Apply/open. None of those actions should automatically
run a simulation. Apply needs Python button-click handling; it does not emit
`accepted()` like OK. Do not directly wire OK to `accept()` before validation.

## 6. Settings: Battery page

Create `group_manual_bess` (`QGroupBox`), title `Include manual BESS in simulation`,
checkable true, checked false, with a form layout. Put the first three controls
inside it. An unchecked checkable group box disables its child inputs without
custom toggle code. This option controls a FIXED simulation battery, not whether
the optimizer may search for one.

| Type               | objectName               | Label / properties                                                         |
| ------------------ | ------------------------ | -------------------------------------------------------------------------- |
| `QComboBox`      | `combo_bess_bus`       | `Installation bus`; editable false; leave items empty until network load |
| `QDoubleSpinBox` | `spin_bess_power_kw`   | `Power rating`; required-positive Power box                              |
| `QDoubleSpinBox` | `spin_bess_energy_kwh` | `Energy capacity`; required-positive Energy box                          |

Below it create `group_battery_parameters`, title `Battery Parameters`, with a
form layout. Keep it OUTSIDE the checkable manual group so optimization can use
these parameters even when manual simulation BESS is off.

| Type               | objectName                     | Label / properties                                                                                     |
| ------------------ | ------------------------------ | ------------------------------------------------------------------------------------------------------ |
| `QDoubleSpinBox` | `spin_soc_min_percent`       | `Minimum SOC`; Percent box; value 10                                                                 |
| `QDoubleSpinBox` | `spin_soc_max_percent`       | `Maximum SOC`; Percent box; value 90                                                                 |
| `QDoubleSpinBox` | `spin_soc_initial_percent`   | `Initial SOC`; Percent box; value 50                                                                 |
| `QDoubleSpinBox` | `spin_eta_charge_percent`    | `Charging efficiency`; Percent box; value 0; specialValueText `Set efficiency`                     |
| `QDoubleSpinBox` | `spin_eta_discharge_percent` | `Discharging efficiency`; same as above                                                              |
| `QLabel`         | `lbl_battery_note`           | wordWrap; `Generic battery; efficiencies must be supplied explicitly. No supplier catalog required.` |
| `QLabel`         | `lbl_dispatch_status`        | wordWrap; `Dispatch policy is not configured; default simulation leaves the battery idle.`           |

The SOC values above match existing defaults. Do not assume the historical
85% figure is both directional efficiencies. Zero efficiency is an unset
sentinel and must be rejected for BESS work. Python checks min SOC < max SOC,
initial within both, and efficiencies >0 and <=100%.

Do not add a battery-chemistry selector or + button for multiple BESS units.
The current model uses one generic BESS. The existing simulator has no automatic
dispatch if no policy is supplied; the optimizer requires a callable policy.
A later agreed/configurable policy must be wired before claiming useful battery
operation. Do not silently reuse the demo's fixed 600 kW dispatch target.

## 7. Settings: Operation page

Use `group_voltage` (form layout), then three checkable group boxes for reserve
and optional grid caps, then two checkboxes for operating controls.

| Type               | objectName                | Label / properties                                                                                                  |
| ------------------ | ------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `QDoubleSpinBox` | `spin_voltage_min_pu`   | `Minimum voltage`; min 0.1, max 2, decimals 3, singleStep 0.01, value 0.95, suffix ` pu`                        |
| `QDoubleSpinBox` | `spin_voltage_max_pu`   | `Maximum voltage`; same range/precision; value 1.05                                                               |
| `QGroupBox`      | `group_reserve`         | `title=Hold BESS Reserve`; checkable true; checked true; form layout                                              |
| `QDoubleSpinBox` | `spin_reserve_percent`  | Inside reserve group; `Peak demand reserve`; Percent box; value 10                                                |
| `QDoubleSpinBox` | `spin_reserve_hours`    | Inside reserve group; `Reserve duration`; min 0.01, max 8760, decimals 2, singleStep 0.25, value 1, suffix ` h` |
| `QGroupBox`      | `group_import_limit`    | `title=Limit Grid Import`; checkable true; checked false; form layout                                             |
| `QDoubleSpinBox` | `spin_import_limit_kw`  | Inside import group; Power box; value 0; no specialValueText                                                        |
| `QGroupBox`      | `group_export_limit`    | `title=Limit Grid Export`; checkable true; checked false; form layout                                             |
| `QDoubleSpinBox` | `spin_export_limit_kw`  | Inside export group; Power box; value 0; no specialValueText                                                        |
| `QCheckBox`      | `chk_allow_curtailment` | `text=Allow PV curtailment`; checked true                                                                         |
| `QCheckBox`      | `chk_allow_shedding`    | `text=Allow load shedding`; checked true                                                                          |
| `QLabel`         | `lbl_operation_note`    | wordWrap; `A feasible voltage result may still include unserved demand. Thermal constraints are not applied.`     |

Python converts unchecked import/export groups to **None (unlimited)**, NOT
zero. Checked with 0 means genuinely **no import** / **no export**. An unchecked
reserve group maps to reserve_fraction 0; use a valid positive duration even
when reserve is disabled. Reserve is based on ORIGINAL peak demand and is only
enforced for BESS runs, not an extra load injected into the feeder.

Keep voltage limits mandatory (no enable toggle). Do not add thermal/ampacity
limits, emissions or other unagreed constraints. Disallowing shedding can make
a run electrically infeasible; do not hide that outcome.

## 8. Settings: Optimization page

Use a vertical layout: allowed-bus list, a form for power/energy bounds and a
form for GWO settings. A scroll area is useful here.

| Type               | objectName                  | Label / properties                                                                                                                           |
| ------------------ | --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `QListWidget`    | `list_allowed_buses`      | `Allowed installation buses`; selectionMode MultiSelection; editTriggers NoEditTriggers; minimumHeight about 100; no Designer sample items |
| `QDoubleSpinBox` | `spin_opt_power_min_kw`   | `Minimum power`; required-positive Power box                                                                                               |
| `QDoubleSpinBox` | `spin_opt_power_max_kw`   | `Maximum power`; required-positive Power box                                                                                               |
| `QDoubleSpinBox` | `spin_opt_energy_min_kwh` | `Minimum energy`; required-positive Energy box                                                                                             |
| `QDoubleSpinBox` | `spin_opt_energy_max_kwh` | `Maximum energy`; required-positive Energy box                                                                                             |
| `QSpinBox`       | `spin_gwo_population`     | `GWO population`; min 3, max 100000, value 12                                                                                              |
| `QSpinBox`       | `spin_gwo_iterations`     | `GWO iterations`; min 1, max 1000000, value 20                                                                                             |
| `QSpinBox`       | `spin_gwo_seed`           | `GWO seed`; Seed-box settings                                                                                                              |
| `QLabel`         | `lbl_wsm_weights`         | wordWrap; `Raw WSM: cost 0.50; curtailment 0.25; shedding 0.25. No objective normalization.`                                               |
| `QLabel`         | `lbl_optimization_status` | wordWrap; `Min/max search integration is pending; current backend uses size lists.`                                                        |

The list is filled from actual bus IDs by Python. MultiSelection lets clicks
toggle several entries; never assume the row number equals the bus ID. Empty
selection is invalid, not automatic permission to search every bus.

Build min/max fields now, but the current `OptimizationBounds` still accepts
explicit catalogs. A tested min/max adaptation is REQUIRED before enabling that
workflow; do not pretend the widget's singleStep implements it. Bounds must be
positive and min <= max. They are generic design ranges, not manufacturer
product sizes. A supplier CSV/catalog is not needed for these fields.
Large population/iteration limits only avoid a restrictive UI; practical runs
should start small. Keep WSM weights visible as a fixed label initially, since
the user did not request another weighting interface.

## 9. Settings: Economics page

Create `group_economic_inputs` as a checkable `QGroupBox`, title `Cost coefficients supplied`,
checked false, with a form layout. Put the two cost boxes inside. Put currency
and explanatory notes below it.

| Type               | objectName            | Label / properties                                                                                       |
| ------------------ | --------------------- | -------------------------------------------------------------------------------------------------------- |
| `QDoubleSpinBox` | `spin_cost_per_kwh` | `Cost per kWh`; min 0, max 1000000000, decimals 2, singleStep 10, value 0; suffix ` /kWh`            |
| `QDoubleSpinBox` | `spin_cost_per_kw`  | `Cost per kW`; same; suffix ` /kW`                                                                   |
| `QLineEdit`      | `edit_currency`     | `Currency`; text `SAR`; `maxLength=16`                                                             |
| `QLabel`         | `lbl_cost_formula`  | wordWrap; `Investment cost = cost/kWh x battery kWh + cost/kW x battery kW`                            |
| `QLabel`         | `lbl_cost_note`     | wordWrap; `Unchecked means prices are unavailable, not free. Optimization requires both coefficients.` |

Unchecked maps to `None` for both costs. Checked means the user explicitly
provides both values, including a deliberate zero for a test if desired. Do not
invent supplier prices. A no-BESS simulation does not require these costs;
a BESS simulation can report cost unavailable; optimization currently cannot.
Do not add tariff, discount rate, O&M or degradation fields for the first model.

## 10. Settings: Uncertainty page

Create checkable `group_uncertainty`, title `Use uncertainty-aware optimization`,
checked false, with a form layout. Put the controls below inside it. Put the
limitations/status note outside, so it remains readable when disabled.

| Type         | objectName                | Label / properties                                                                                                                                  |
| ------------ | ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `QSpinBox` | `spin_forecast_hours`   | `Forecast horizon`; min 2, max 1000000, value 2160, suffix ` h`                                                                                 |
| `QSpinBox` | `spin_scenario_count`   | `Generated scenarios`; min 1, max 100000, value 100                                                                                               |
| `QSpinBox` | `spin_best_count`       | `Selected best cases`; min 0, max 100000, value 15                                                                                                |
| `QSpinBox` | `spin_worst_count`      | `Selected worst cases`; same; value 15                                                                                                            |
| `QSpinBox` | `spin_random_count`     | `Selected random cases`; same; value 15                                                                                                           |
| `QSpinBox` | `spin_uncertainty_seed` | `Scenario generation seed`; Seed-box settings                                                                                                     |
| `QSpinBox` | `spin_selection_seed`   | `Scenario selection seed`; Seed-box settings                                                                                                      |
| `QLabel`   | `lbl_uncertainty_note`  | wordWrap; `Selected cases are a stress portfolio, not probability-preserving reduction. Synthetic history does not validate real forecast skill.` |

2160 is an illustrative 90-day FORECAST horizon, not the calendar-month import
length in Section 4. Python must show actual forecast dates and allow an exact
calendar-based horizon later if desired; do not label 2160 as always three months.
The forecast starts AFTER the history. Historical simulation and future scenario
evaluation do not cover the same dates by default. Generated PV needs installed
ratings from the loaded network. Data adequacy and statistical validation still
matter; the library requires at least 48 training hours plus the 24-hour holdout.

For the initial screen, keep ARIMA `(1,0,0)` and holdout 24 hours as documented
defaults rather than adding advanced fields. Python validates selected totals:
best + worst + random must be >0 and <= generated count, without duplicates.
The two seeds map to `UncertaintyConfig.seed` and `SelectionConfig.seed`.

## 11. What to connect in Designer, and what to leave for Python

Open **Edit Signals/Slots** (F4) or the Signal/Slot Editor. These simple,
non-engineering connections may be saved in the forms:

| Sender                  | Signal                     | Receiver                 | Slot                     |
| ----------------------- | -------------------------- | ------------------------ | ------------------------ |
| `list_settings_pages` | `currentRowChanged(int)` | `stack_settings_pages` | `setCurrentIndex(int)` |
| `chk_show_log`        | `toggled(bool)`          | `run_log`              | `setVisible(bool)`     |
| `buttons_load_data`   | `rejected()`             | `LoadDataDialog`       | `reject()`             |
| `buttons_settings`    | `rejected()`             | `SettingsDialog`       | `reject()`             |

Select **Show signals and slots inherited from QWidget** if the expected slot
is hidden in the connection dialog. If your Designer cannot expose a property
or slot here, leave a note for Python instead of inventing a dynamic property
with the same name. [Qt connection editor](https://doc.qt.io/qt-6/designer-connection-mode.html).

Leave application actions unconnected for now. A button does not need a fake
slot in Designer to save the form. Later Python will connect named handlers:

| Controls                              | Later Python responsibility                                                              |
| ------------------------------------- | ---------------------------------------------------------------------------------------- |
| `btn_load_data`, `btn_settings`   | Open the matching dialog and retain its state                                            |
| Browse buttons / `btn_load_network` | File dialogs, source reading and network validation                                      |
| Source combos / PV row buttons        | Enable the proper panels; populate and validate bus/rating rows                          |
| Dialog OK / Apply                     | Validate staged values, convert units, commit; only then accept/close                    |
| Run buttons                           | Check readiness, snapshot inputs, start a worker; restore controls after success/failure |
| Zoom/Fit / selected bus               | Scene transforms and details; never modify electrical topology                           |
| `btn_export_results`                | Export retained results into a new directory, without rerunning calculations             |

Do not connect OK directly to `accept()` and later also connect validation:
the automatic connection could close the dialog before errors are handled.
Check Signal/Slot Editor for connections created automatically by templates.
Avoid also reconnecting Designer connections in Python, which can duplicate
actions. Set Settings's current row/index explicitly at startup as well.

For keyboard use, edit Tab Order (Edit menu) so navigation follows the visible
form order. Assign label buddies to inputs where useful. Do not make navigation
depend solely on small icons or colour.

## 12. Colour and appearance: do this last

First make the layout resize correctly with the normal system style. A plain
working form is more useful than a styled but clipped one. Suggested font is
the system font or Segoe UI, approximately 10-11 pt; use points, not fixed pixel
font sizes. Never set every widget to a fixed height/width.

If you want the mockup's teal sidebar, set only `frame_actions.styleSheet`:

```css
QFrame#frame_actions { background-color: #1B627D; }
QFrame#frame_actions QLabel { color: white; }
QFrame#frame_actions QPushButton {
    background-color: #237795;
    color: white;
    border: 1px solid #103F52;
    padding: 8px;
}
QFrame#frame_actions QPushButton:hover { background-color: #2A89AC; }
QFrame#frame_actions QPushButton:disabled { color: #A5B9C2; background-color: #355E6F; }
```

This is optional **Qt Style Sheet**, not a web/Streamlit implementation.
Keep keyboard focus visible; do not apply a broad `QWidget` colour/background
rule that accidentally recolours numeric inputs and graphics view content.
Icons are optional. Add assets/resources later with reliable paths; do not
copy the password manager's PNGs just to make the forms resemble it.

## 13. Preview checklist and handoff

Use Ctrl+R on each form, then resize it. Confirm:

- [ ] Main window has the five action buttons, Network/Results tabs and log toggle.
- [ ] Main content expands; actions/log do not consume all extra space.
- [ ] Network view is an empty graphics view, not a static feeder screenshot.
- [ ] Results/log are selectable but read-only; no fake engineering results.
- [ ] Each tab/stack page has a layout; long settings pages scroll.
- [ ] Settings navigation works in preview; all five categories are reachable.
- [ ] Checkable reserve/import/export/manual groups disable the intended children.
- [ ] All numeric units and names are correct; power != energy; percent != fraction.
- [ ] Currency/cost availability is separate from a numerical zero.
- [ ] OK is NOT directly connected to dialog acceptance before validation.
- [ ] Combo-driven mode changes/Browse buttons are expected to wait for Python.
- [ ] Form preview is usable on a smaller window and at Windows display scaling.
- [ ] All three files save as `.ui` XML; no handwritten Python overwritten.

When finished, share the three file paths. The next task is to inspect object
names/layouts and wire them to Python, not redesign the forms from scratch.
Keep the Designer forms as the source of truth even if generated Python is used.

### Backend work still required after you draw the forms

Designer does not implement data preparation orchestration, temporary/staged
state, file dialogs, network bus population, scene drawing, worker jobs, progress,
dispatch configuration, min/max optimizer adaptation or error handling. Some
backend functions already exist, but the UI connections do not. Keep Run/Export
disabled until their actual prerequisites are met; never present placeholders
as completed features. No GUI was launched/tested while writing this guide.
The listed key properties and connection slots were checked against installed
Qt 6.11.2 metadata without constructing a window; this is not a visual preview
test of forms you have not built yet.

## Implementation update — supplied forms (18 Oct 2026)

The forms are now connected in `src/ui.py` using PySide6 runtime loading. The
original form files are unchanged. Actual `frame_action` (singular) and the
date-only start widget are supported. See `src/README_ui.md` for operation,
input variables, tests and the distinction between implemented and pending work.

The user confirmed min/max sizing with explicit steps and a user-set net-load
target. Python adds `group_dispatch_policy`, `combo_dispatch_policy`,
`spin_dispatch_target_kw`, `spin_opt_power_step_kw` and
`spin_opt_energy_step_kwh` at runtime. The README specifies widget types and
locations if these are later moved into Designer. Do not confuse a spin box's
arrow increment with search resolution. Python also adds provider-specific
Open-Meteo/NASA choices to the PV source combo. Keep the documented names and
validation-first dialog button behavior when editing forms.

The formerly pending connections above are implemented: staged preparation,
settings, file dialogs, background jobs, vector network drawing, text results
and export. Reliable percentage progress, cooperative cancellation, EXE
packaging and real-study validation remain separate work.

## Sources and precedence

Object names, layouts and suggested UI ranges here are project-specific design
guidance, not values mandated by Qt or supplier specifications. Backend defaults
were checked against `simulation.py`, `optimizer.py`, `uncertainty.py`,
`metrics.py`, `pv_model.py` and `load_generator.py`. Engineering contracts and
confirmed user choices take precedence; update both docs/bindings if names change.

Qt documentation checked on 18 Oct 2026:
[widget properties/preview](https://doc.qt.io/qt-6/designer-widget-mode.html),
[layouts/splitters](https://doc.qt.io/qt-6/designer-layouts.html),
[containers/pages](https://doc.qt.io/qt-6/designer-using-containers.html),
[main windows](https://doc.qt.io/qt-6/designer-creating-mainwindows.html),
[dialog button roles](https://doc.qt.io/qt-6/qdialogbuttonbox.html),
[group-box toggles](https://doc.qt.io/qt-6/qgroupbox.html),
[numeric properties](https://doc.qt.io/qt-6/qdoublespinbox.html),
[special/unset numeric text](https://doc.qt.io/qt-6/qabstractspinbox.html),
[plain-text output/log](https://doc.qt.io/qt-6/qplaintextedit.html).
