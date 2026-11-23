# `network_loader.py` — static Excel network import

This module loads the network itself: buses, line connections/impedances, base
loads and any explicitly supplied PV ratings. It returns the existing
`NetworkModel`, validated for our balanced, single-voltage radial solver.
It does not load hourly profiles, run optimization or draw the network.

## Run and test

From the repository root, `EE499-Team16`:

```powershell
python -m pip install -r .\07_Implementation\requirements.txt
python .\07_Implementation\examples\load_network.py --frequency-hz 60
python .\07_Implementation\examples\load_network.py --frequency-hz 60 --power-flow
python -m unittest discover -s .\07_Implementation\tests -p test_network_loader.py -v
```

The example defaults to the existing workbook under
`04_Research/Working_Data/Network_Data/Working_RDS/IEEE_33Bus_Network_Data.xlsx`, resolving
that path from the script location rather than the current terminal directory.
The explicit 60 Hz is a **study input**, not a frequency claimed by the workbook.
Choose your intended study frequency; no frequency is silently guessed.

Expected import: 33 buses, 32 in-service lines, slack bus 1, 100,000 kVA base,
12.66 kV and 3,715 kW / 2,300 kvar base demand. No PV ratings are invented.
The optional base-load snapshot converges with approximately 202.678 kW active
losses and minimum voltage 0.91308 pu. That is below our 0.95 pu study limit:
convergence does not mean voltage feasibility. This is a source-data integration
check, not a complete hourly/BESS validation or a claim that constraints are met.

To inspect another supported workbook:

```powershell
python .\07_Implementation\examples\load_network.py "C:\path\my_network.xlsx" --format project
```

The example prints information only. It does not modify the workbook or save
results. `--power-flow` uses base loads and rated PV, not hourly PV availability.

## Public function

```python
from src.network_loader import load_network

network = load_network("path/to/network.xlsx", frequency_hz=60)
# Pass network to the existing simulator/FBS; it is an ordinary NetworkModel.
```

| Argument | Meaning |
|---|---|
| `path` | Existing `.xlsx` file; relative paths use the caller's working directory |
| `workbook_format` | `"auto"` by default, or explicitly `"project"` / `"reference"`; legacy `"ieee33"` keeps the old strict count check |
| `frequency_hz` | Optional positive numeric override. Required for a bus/branch reference workbook without a frequency field. A supplied value also overrides a valid project-template frequency. |

Format detection uses sheet names and validates columns; changing a filename
does not change its format. Workbooks are opened read-only and closed even on
validation failure. Formulas are never executed or evaluated by the importer.

## Supported format 1: IEEE33-style bus/branch workbook

The reference adapter expects `Overview`, `Bus Data` and `Branch Data` sheets,
with the documented IEEE33-style header labels and numbered rows. The bus and
branch counts may vary, but the active topology must still pass the same radial,
connected and single-voltage validation as the project schema. It is not a
generic importer for arbitrary spreadsheet column names.

- Read `Base MVA` and `Base voltage` from their labelled overview entries.
  Convert MVA to kVA; preserve line ohms and bus kW/kvar. Do not convert ohms a
  second time as though they were per-unit values. The first leading quantity
  is the active value; alternative values in explanatory text are not selected.
- Read slack/PQ bus types. Use the recorded slack voltage magnitude, requiring
  positive initial voltages and zero angles. Non-slack initial magnitudes do
  not replace the existing solver's flat initialization or become voltage limits.
- Base load comes from `Bus Data` once. Receiving-end loads in `Branch Data`
  must agree with that bus's values and are not added again.
- Skip explicit `TOTAL` and `Source:` footer rows without using their formulas.
  Formula cells in actual numeric input rows are rejected, even if Excel has a
  cached result. Rows after a footer cannot silently become network records.
- Buses with zero P and zero Q do not create artificial load devices. No PV
  equipment is created because the source has no installed-PV rating table.

The source workbook is preserved. Notes/citations in the workbook are not
imported as model properties; retain the source path in the later run context.
This adapter checks structure/electrical consistency, not every bibliographic
or descriptive claim written in the overview.

## Supported format 2: project Excel schema

Create an `.xlsx` with the sheets below. This README defines the schema; the
loader does not generate or rewrite a template file. Headers belong in row 1,
data starts in row 2, and numeric inputs must be actual Excel numbers, not text
or formulas. Required columns cannot be missing; headers may be reordered.
Sheet/column names are case-sensitive; header surrounding whitespace is trimmed.
Blank rows are ignored. Totals/subtitles should not be inserted into these tables.

Only the listed sheets/columns are supported. Unknown nonempty columns or extra
sheets are rejected rather than quietly discarding parameters such as transformer
taps, shunts or voltage-controlled generators. Optional `notes` columns are
ignored text, not electrical inputs.

### `Network` — required

Headers: `parameter,value`.

| parameter | Example value | Meaning |
|---|---:|---|
| `base_power_kva` | 1000 | Required positive three-phase power base, kVA |
| `frequency_hz` | 60 | Positive Hz; required unless supplied to `load_network()` |
| `name` | Example feeder | Optional descriptive text, not stored in NetworkModel |
| `notes` | Demonstration inputs | Optional descriptive text, not stored in NetworkModel |

Parameter names must be unique. The values above illustrate the format, not a
default network specification. If overriding frequency, malformed/nonpositive
frequency values already present in the sheet still raise an error.

### `Buses` — required

| Column | Required? | Meaning |
|---|---|---|
| `bus_id` | Yes | Unique integer; IDs need not be consecutive |
| `base_kv` | Yes | Positive line-to-line kV; identical across this single-voltage model |
| `is_slack` | Yes | Excel TRUE/FALSE or numeric 1/0; exactly one slack |
| `name` | No | Nonempty name; absent/blank becomes `Bus {id}` |
| `v_set_pu` | No | Positive pu magnitude; absent/blank defaults to 1.0. Used as the voltage reference at the slack, not a non-slack voltage-control device. |
| `notes` | No | Ignored text |

### `Lines` — required, even if only its header exists in a one-bus case

| Column | Required? | Meaning |
|---|---|---|
| `line_id` | Yes | Unique nonempty text, e.g. `L1` |
| `from_bus`, `to_bus` | Yes | Integer endpoints referring to existing buses |
| `r_ohm` | Yes | Nonnegative per-phase resistance, ohms |
| `x_ohm` | Yes | Finite per-phase reactance, ohms; signed values follow the existing model |
| `ampacity_a` | No | Positive A or blank. Stored only: thermal enforcement remains excluded. |
| `status` | No | Numeric 1/0 or TRUE/FALSE. If the column is absent, all lines are in service; if present, fill every row. Explicit 0 omits that open line from the returned operating topology. |
| `notes` | No | Ignored text |

Both orientations of a line are allowed; radial ordering determines the actual
slack-to-leaf calculation direction. Even open lines need valid IDs, endpoints
and parameters. Active lines must form one connected radial network. No line
is automatically removed to fix a loop, and the returned model does not retain
open ties for later reconfiguration. Keep the original workbook for that data.

### `Loads` — optional

Required columns if the sheet exists:
`load_id,bus_id,p_base_kw,q_base_kvar`. Optional column: `notes`.

Use unique nonempty text load IDs, existing integer bus IDs and nonnegative
three-phase kW/kvar. Multiple load devices at one bus are allowed. Omit the
sheet or leave only its header if the network has no base-load devices.

### `PV` — optional

Required columns if the sheet exists: `pv_id,bus_id,p_rated_kw`.
Optional columns: `q_capability_kvar,notes`.

Use unique nonempty text PV IDs, existing integer bus IDs and nonnegative
three-phase installed kW. Optional Q capability is nonnegative kvar or blank.
Multiple PV units at one bus are allowed. Ratings describe installed equipment,
not an hourly generation profile. Reactive capability is stored; the importer
does not implement inverter dispatch or additional enforcement.

## What you must supply separately

The static workbook does not provide hourly behaviour, economic coefficients,
battery parameters, dispatch rules or optimizer bounds. Continue to use the
existing profile loader and simulation/optimizer settings for those inputs.

Absolute hourly profile loads **replace** base-load values at the simulation
boundary; they are not added to them. If your source is a normalized load shape,
convert it to per-bus kW/kvar explicitly before passing it to `ProfileData`.
After selecting a different network, recheck profile bus IDs and search bounds.

With no installed PV, the unchanged profile loader still expects a PV CSV on
the same timeline: supply an explicit all-zero PV series at a valid bus. Do
not invent a PV rating just to satisfy a file interface. For an actual PV study,
add verified PV equipment/rating data and matching available-generation profiles.

## Rejected formats and current limits

- Loads currently require nonnegative active and reactive demand. Several test
  feeders use negative `Q_load` values to represent capacitor-bank or other
  reactive-power injection. Those files are rejected until shunt/reactive-source
  devices are represented explicitly; treating injection as an ordinary negative
  load would hide an important modeling distinction.
- A `NetworkModel` must contain exactly one slack bus and one connected radial
  tree. A two-substation workbook is therefore rejected as a disconnected forest.
  Import each feeder as a separate network, as done by the two working T18 files,
  until multi-root studies are implemented.
- The supplied PJM workbook is a meshed transmission/generator case, not this
  radial feeder model. It is rejected clearly; topology is never silently changed.
  Five buses does not imply the same network as the radial five-bus fixtures:
  the supplied PJM case has six branches and voltage-controlled generators.
  Its generator **PV bus** is a P/voltage classification, not solar PV equipment.
- `.xls`, `.xlsm`, CSV, JSON, MATPOWER `.m`/`.mat`, PDF and arbitrary spreadsheet
  layouts are not supported by this first network importer.
- No transformers, multi-voltage networks, shunts, unbalanced phases or
  voltage-controlled generation buses are introduced.
- No bus coordinates or drawing are built inside this loader. The desktop and
  `network_layout.py` now consume its returned `NetworkModel` for the diagram.
- Existing `data_loader.py`, `bess.py`, source workbooks and submitted files are
  unchanged. The new dependency is openpyxl, used for reading Excel only.

The test suite reads reference/PJM files without editing them, checks the
IEEE33 FBS snapshot and absolute-profile integration, and uses in-memory table
fixtures for project-schema/error cases. No replacement workbook is silently
generated by the tests.
