# Term 2 Implementation

Tasks **10, 12 and 13** implemented on 6 Oct 2026 against
`02_Reports/Working/Planning/TERM2_SOFTWARE_DESIGN_SPEC.md`.

## Run

Python 3.10 or newer. From the repository root:

```bash
cd 07_Implementation
python -m pip install -r requirements.txt
python -m src.main
python -m unittest discover -s tests -v
```

Network/FBS and their unit tests use the Python standard library. Pandas is
needed to import/use the existing profile loader and hourly simulation.
NumPy and statsmodels are used by the ARIMA/Monte Carlo uncertainty module.
Openpyxl reads supported static network Excel files.
The demo uses the guide's five-bus verification case with 180 kW PV at bus 4.
It prints convergence, bus voltages, slack power and total losses.

## Code and status

Member 1's 10 Oct FBS submission is preserved separately with unchanged originals,
a portable reproduction driver, results, and a task assessment:
[`Contributions/Member_1/2026-10-10_FBS/README.md`](Contributions/Member_1/2026-10-10_FBS/README.md).
It supports small-case Tasks 14/15 and a Task 19 draft; Tasks 17/18 still need
profile/interface integration and failure handling. It does not replace the
production modules or supply Task 16.

| Module | Current scope |
|---|---|
| `src/network_model.py` | Bus/Line/Load/PVUnit dataclasses, network validation, radial ordering |
| `src/network_cases.py` | Prepared five-bus feeder and separate guide verification cases |
| `src/network_loader.py` | Read-only project-schema/IEEE33 Excel import into validated NetworkModel |
| `src/fbs.py` | OperatingPoint, FBSConfig, PowerFlowResult, one-step run_fbs |
| `src/main.py` | Runnable fixed-input demo and base operating-point fixture |
| `src/data_loader.py` | Existing team implementation, preserved unchanged |
| `src/pv_model.py` | Irradiance CSV preparation and piecewise bus-level PV power |
| `src/load_generator.py` | Seeded synthetic demand using published hourly normal statistics |
| `src/bess.py` | Existing team's BESS state/energy calculation, preserved unchanged |
| `src/simulation.py` | Hourly profiles/BESS/FBS integration, proportional curtailment/shedding, reserve and network-limit checks |
| `src/metrics.py` | Simulation energy/voltage/reserve summaries, simple BESS investment cost and percentage reduction |
| `src/optimizer.py` | Catalog-based GWO, raw WSM, simulation evaluator and exhaustive-search reference |
| `src/uncertainty.py` | ARIMA/Monte Carlo profiles, 100-to-45 stress selection and scenario evaluator |
| `src/results.py` | Readable summaries, simulation/optimization/scenario CSVs and baseline comparisons |
| `src/ui.py` | Designer-backed PySide6 desktop: loading/settings, jobs, network scene, text results/export |
| `src/ui_workflow.py` | Qt-free preparation/run orchestration and min/max/step sizing catalogs |
| `src/dispatch.py` | Explicit user-set net-load-target battery policy |
| `src/network_layout.py` | Deterministic radial schematic coordinates |

Software/application references are collected in
[`Software_GUI_and_Library_References.md`](../04_Research/Literature_Notes/Software_GUI_and_Library_References.md).
The VeraGrid section has focused links to revisit for uncertainty, investment
optimization, automatic network diagrams and results presentation. These are
references only; the current backend and dependencies are unchanged.

For desktop UI structure, read
[`Qt_Desktop_Implementation_Guide.md`](Qt_Desktop_Implementation_Guide.md).
It records the useful Designer/window/handler patterns from the user's PyQt5
password-manager project and the adaptations required for long simulations,
automatic feeder drawing, resource paths and our existing backend.

## Desktop application

The first desktop version loads your three `.ui` forms unchanged. See
[`README_ui.md`](src/README_ui.md) for all input variables, runtime-added sizing
steps/dispatch controls, workflow and manual checks. From the repository root:

```powershell
python -m pip install -r .\07_Implementation\requirements-ui.txt
python .\07_Implementation\examples\run_ui.py
```

Qt is optional for backend-only use. This implements the local desktop, not the
deferred website or Windows EXE. Actual supplier/cost inputs and real-study
validation remain outstanding.

To build the forms manually, follow
[`Qt_Designer_Build_Guide.md`](Qt_Designer_Build_Guide.md). It lists the three
form templates, widget hierarchy, exact object names/properties, all Settings
pages, Designer-only connections and later Python work.

## Irradiance and synthetic-load preparation

See [`README_pv_model.md`](src/README_pv_model.md) and
[`README_load_generator.md`](src/README_load_generator.md) for inputs, equations,
units, source attribution and limitations. From the repository root:

```powershell
python .\07_Implementation\examples\prepare_profiles.py --frequency-hz 60 --pv-bus 6 --pv-rating-kw 1000 --critical-irradiance 120 --hours 24 --simulate --output-dir .\07_Implementation\Results\prepared_check_01
```

Values are illustrative study inputs, not supplier specifications or recommended
PV/storage sizing. Omit `--hours 24` for three calendar months. Demand is
synthetic, weather is from the selected provider, and outputs include a provenance
manifest. Existing output directories and source files are never overwritten.
Measured load CSVs may be used instead of generating demand.

## Uncertainty workflow

See [`README_uncertainty.md`](src/README_uncertainty.md) for historical inputs,
PV ratings, forecast settings, ranking and scenario-evaluator assumptions.
From the repository root:

```powershell
python .\07_Implementation\examples\run_uncertainty.py
python .\07_Implementation\examples\run_uncertainty.py --forecast-hours 2160
python -m unittest discover -s .\07_Implementation\tests -p test_uncertainty.py -v
```

The synthetic demo generates 100 cases and selects 15 best/15 worst/15 random.
Add `--optimize --cost-per-kwh 2 --cost-per-kw 3` for the small GWO integration
check with illustrative prices. Selected cases use an equal-weight stress-set
mean, not a probability-corrected expected-performance estimate. Real-data
forecast quality and scenario realism remain to be validated.

## Network cases

See [`README_network_loader.md`](src/README_network_loader.md) for supported
Excel layouts, required units/frequency and input variables. From the repository root:

```powershell
python .\07_Implementation\examples\load_network.py --frequency-hz 60 --power-flow
python -m unittest discover -s .\07_Implementation\tests -p test_network_loader.py -v
```

This imports the existing IEEE 33-bus workbook without modifying it. The explicit
60 Hz is a study input, not supplied source data. The base-load snapshot converges
but has voltage below 0.95 pu; convergence is not feasibility. The looped PJM
five-bus workbook is incompatible and is rejected rather than altered.

- `build_5_bus_case(loads=None, pv_units=None)` represents the prepared **11 kV,
  10 MVA, 1→2→3→4→5** feeder. No arguments gives an unloaded topology because
  the published data contains no individual bus loads or PV ratings. Supply
  explicit `Load` and `PVUnit` lists for a loaded study. Default 60 Hz is a
  development configuration; frequency is not used by the supplied series R/X
  power-flow model. Grid-strength equivalents, transformers and shunts are not
  represented in the current design.
- `build_guide_3_bus_case()` and `build_guide_5_bus_case()` are fixtures from
  `Validation/FBS_Step_by_Step_Guide.pdf`. The latter is a **12.66 kV, 1 MVA,
  branched** feeder and is a distinct case from the prepared network.

## Public solver interface

```python
from src.network_cases import build_guide_5_bus_case
from src.main import base_operating_point
from src.fbs import FBSConfig, run_fbs

network = build_guide_5_bus_case()
point = base_operating_point(network)
result = run_fbs(network, point, FBSConfig())
if not result.converged:
    raise RuntimeError(result.message)
print(result.voltage_mag_pu)
print(result.total_loss_p_kw)
```

`base_operating_point()` is a demo fixture that uses rated PV output; the
simulation layer assembles actual profile values. All six OperatingPoint
mappings must include every bus, with explicit zeros. Load is positive demand,
PV positive generation, BESS positive discharge and negative charging.
Powers are three-phase kW/kvar, voltage bases line-to-line kV, line impedances
per-phase ohms and public current magnitudes A. Branch quantities follow the
derived slack-to-leaf direction even if input line endpoints are reversed.
`loads_by_bus()` and `pv_by_bus()` return bus-to-list mappings, including empty
lists, so multiple equipment objects at one bus can be aggregated.

FBS uses constant complex-power demand and flat initialization. Convergence
is `max(abs(V_new - V_old)) <= tolerance`, default 1e-6 pu, maximum 100 sweeps.
Optional history contains the initial flat start followed by each completed
sweep. `iterations` counts completed sweeps. Failed/non-converged results are
for diagnosis and must not be accepted by downstream simulation/optimization.
Simulation checks voltage, optional import/export caps and reserve feasibility.
Proportional PV/load controls produce actual curtailed/shed energy records.
Convergence alone does not certify feasibility, and electrical feasibility does
not mean all demand was served. Thermal limits are excluded from the initial scope.

## Hourly simulation

See the dedicated [`simulation.py` README](src/README_simulation.md) for a
walkthrough of the code, settings, reserve logic and returned results.

Run this block from the repository root (`EE499-Team16`):

```powershell
python .\07_Implementation\examples\run_simulation.py
python .\07_Implementation\examples\run_simulation.py --hours 2160
python -m unittest discover -s .\07_Implementation\tests -p test_simulation.py -v
```

The example uses synthetic load/PV curves on the guide feeder and a simple
demonstration dispatch policy. Both 24-hour and three-month runs are supported.
Real study validation remains pending. The desktop now exposes the confirmed
user-set net-load-target starting policy; this example retains its demo policy.
See [the simulation test guide](Validation/Simulation_Test_Guide.md) for expected
behavior, CSV usage, reserve settings and result fields.

## Performance metrics

See the dedicated [`metrics.py` README](src/README_metrics.md) for cost inputs,
returned fields and example calls. Cost coefficients are unset until supplied.
Curtailment and shedding are read automatically from new simulation records.
Only legacy results without those records need explicit external records.

Run this block from the repository root (`EE499-Team16`). For a variable-by-
variable input guide, see [which variables to fill or change](src/README_metrics.md#which-variables-to-fill-or-change).

```powershell
python -m unittest discover -s .\07_Implementation\tests -p test_metrics.py -v
python .\07_Implementation\examples\run_simulation.py --cost-per-kwh 2 --cost-per-kw 3
python .\07_Implementation\examples\run_simulation.py --pv-rating-kw 1200 --grid-import-limit-kw 400 --grid-export-limit-kw 0
```

The cost values are arithmetic examples, not sourced prices. The last command
uses illustrative PV/supply/export settings to exercise both curtailment and
shedding. Grid caps default to None (unlimited); voltage controls are enabled
by default. See `SimulationConfig` for controls that can be disabled or changed.

## GWO optimization

The dedicated [`optimizer.py` README](src/README_optimizer.md) explains search
catalogs, dispatch, weights, required prices and result fields. Run this small
synthetic example from the repository root:

```powershell
python .\07_Implementation\examples\run_optimization.py --cost-per-kwh 2 --cost-per-kw 3 --compare-exhaustive
python -m unittest discover -s .\07_Implementation\tests -p test_optimizer.py -v
```

The coefficients are illustrative, not sourced project prices. This compares
GWO with all eight catalog choices and prints the no-BESS baseline separately.
With these inputs the baseline has the lower raw score; the best battery is
not automatically preferable to installing none. Real-data optimization still
needs project inputs, an operating policy and validated bounds.

## Save results

See [`README_results.md`](src/README_results.md) for the export files, missing/
failure values and required run context. From the repository root:

```powershell
python .\07_Implementation\examples\run_simulation.py --output-dir .\07_Implementation\Results\simulation_run_01
python -m unittest discover -s .\07_Implementation\tests -p test_results.py -v
```

`--output-dir` must be a new directory; existing runs are never overwritten.
The optimization and scenario-GWO examples accept the same option. Exports use
existing outputs only: CSV generation does not rerun the engineering model.

## Verification

The suite now contains 193 assertion-based tests: the previous 162 backend tests
plus 13 Qt-free UI workflow tests and 18 offscreen Qt tests (the latter skip
without the optional desktop dependency). See `Validation/FBS_Verification_Notes.md`
for the FBS verification boundary and `src/README_ui.md` for UI checks.
The network/FBS tests cover manual
first-sweep values, guide outputs, an analytic two-bus solution, power balance,
input validation, reversed lines, slack demand, injection signs and failures.
For the additional independent nodal-equation check:

```bash
python -m pip install -r Validation/requirements.txt
python -m Validation.verify_nodal_reference
```

This checks the implementation; it does not complete formal Chapter 5
validation or mark other scheduled tasks complete.
