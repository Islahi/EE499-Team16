# Network model and FBS code guide

This folder contains the documentation for Tasks **10, 12 and 13**. The Python
source code is one folder above (`src_accelerated/`), while all READMEs live here.
This separation keeps the application folder focused on executable modules.

Project-level records are available in
[the dated development explanation](DEVELOPMENT_CHRONOLOGY.md) and
[the detailed script reference](SCRIPT_REFERENCE.md).

The fastest Windows launch is to double-click
[`../app.pyw`](../app.pyw). It starts the Designer-based desktop application
without opening a console. For troubleshooting, use the terminal launcher:

```powershell
cd 07_Implementation
python .\examples\run_accelerated_ui.py
```

This guide documents the module structure,
five-bus network model, and one-time-step Forward/Backward Sweep (FBS) solver.
The solver calculates bus voltages, branch currents, power flows and losses
for a balanced radial distribution network.

For the hourly integration module, see the dedicated
[`simulation.py` README](README_simulation.md), including its execution flow,
inputs/outputs, configurable defaults and future parameter changes.
For performance evaluation, see the dedicated
[`metrics.py` README](README_metrics.md).
For GWO search, raw WSM and the exhaustive reference, see the dedicated
[`optimizer.py` README](README_optimizer.md).
For ARIMA, Monte Carlo scenarios, selection and scenario-based GWO, see
[`uncertainty.py` README](README_uncertainty.md).
For summaries, CSV exports and baseline comparisons, see
[`results.py` README](README_results.md).
For static Excel network import and the IEEE 33-bus source workbook, see
[`network_loader.py` README](README_network_loader.md).
For irradiance conversion and synthetic demand, see
[`pv_model.py` README](README_pv_model.md) and
[`load_generator.py` README](README_load_generator.md).
For the desktop, its editable forms, input variables and test instructions, see
[`ui.py` README](README_ui.md).

The accelerated desktop also stores accepted studies in timestamped session
folders. The **Scenarios** window generates or imports an inspectable saved
scenario package before uncertainty optimization, while completed runs are
automatically exported inside the same session.

## 1. Start here

Use **Python 3.10 or newer**. Open a terminal in the repository root and run:

```bash
cd 07_Implementation
python -m pip install -r requirements-accelerated.txt
python .\examples\run_accelerated_ui.py
```

Run the command from `07_Implementation`, the folder containing
`src_accelerated`. Windows users can alternatively double-click `app.pyw`.

## 2. What each file does

| File | Responsibility | Current status |
|---|---|---|
| `network_model.py` | Stores buses, lines, loads and PV; validates topology and builds sweep order | Implemented |
| `network_loader.py` | Imports supported Excel network data without editing the workbook | Implemented |
| `fbs.py` | Solves one operating point using Python, NumPy, optional Numba or experimental CuPy | Implemented |
| `data_loader.py` | Existing team code for reading load/PV CSV profiles | Existing implementation; not connected to the demo |
| `pv_model.py` | Prepares PV power from irradiance CSVs | Implemented; see README_pv_model.md |
| `load_generator.py` | Prepares literature-based synthetic hourly load | Implemented; see README_load_generator.md |
| `bess.py` | Existing BESS configuration, state and energy-update function | Existing implementation preserved |
| `simulation.py` | Contains the net-load-target dispatch policy; combines profiles/BESS/FBS, applies controls and checks feasibility | Implemented; see the simulation test guide |
| `metrics.py` | Summarizes simulation energy/voltage/reserve performance and simple investment cost | Implemented; see README_metrics.md |
| `optimizer.py` | Searches allowed BESS bus/power/energy catalogs with GWO and a public evaluator | Implemented; see README_optimizer.md |
| `uncertainty.py` | Generates/selects ARIMA/Monte Carlo scenarios and evaluates common candidates | Implemented; see README_uncertainty.md |
| `results.py` | Formats summaries and exports existing results | Implemented; see README_results.md |
| `ui.py` | Designer-backed PySide6 windows, timestamp selection and worker jobs | Implemented; see README_ui.md |
| `ui_workflow.py` | Qt-free preparation/run orchestration and sizing catalogs | Implemented |
| `study_session.py` | Creates reproducible input snapshots, logs and numbered run folders | Implemented |
| `scenario_store.py` | Writes and reloads scenario CSV packages and their validation/ranking manifest | Implemented |
| `network_layout.py` | Longest-spine radial layout, feeder-wide branch balancing and layer-aware spacing | Implemented |
| `network_diagram.py` | Single-line symbols, toolbar icons, rotation, selectable buses and independent Properties/Results layers | Implemented |
| `__init__.py` | Makes `src_accelerated` a Python package | Present |

The accelerated desktop dependencies are in `../requirements-accelerated.txt`;
launch from the repo root with
`python .\07_Implementation\examples\run_accelerated_ui.py`.
See `../../Validation/Simulation_Test_Guide.md` for hourly examples and tests.

## 3. `network_model.py`: the static network

A **dataclass** is a Python class whose fields are declared directly. These
objects keep input values and their units clear:

| Class | Main fields | Meaning |
|---|---|---|
| `Bus` | `bus_id`, `name`, `base_kv`, `is_slack`, `v_set_pu` | A connection point; the slack bus has a fixed voltage |
| `Line` | `line_id`, `from_bus`, `to_bus`, `r_ohm`, `x_ohm`, optional `ampacity_a` | A branch with series impedance |
| `Load` | `load_id`, `bus_id`, `p_base_kw`, `q_base_kvar` | Static reference demand |
| `PVUnit` | `pv_id`, `bus_id`, `p_rated_kw`, optional `q_capability_kvar` | Static PV rating |
| `NetworkModel` | `buses`, `lines`, `loads`, `pv_units`, `base_power_kva`, `frequency_hz` | The whole feeder and its reference bases |
| `RadialOrder` | Parent/child lookups, forward/backward line lists | The directions and sequence used by FBS |

`network.validate()` checks IDs, bus references, finite physical parameters,
exactly one slack bus, connectivity and radial topology. Invalid input raises
`ValueError` before power-flow iteration begins.

`network.radial_order()` determines direction from the slack bus. Input line
rows can be reversed or shuffled; the solver still processes parents before
children in the forward sweep and children before parents in the backward sweep.

`network.loads_by_bus()` and `network.pv_by_bus()` return a list of equipment
objects for each bus. This permits multiple loads or PV units at one bus.

## 4. `fbs.py`: inputs and calculation

The public function is:

```python
result = run_fbs(network, operating_point, config)
```

It receives three objects:

1. `NetworkModel`: static equipment, topology and base values.
2. `OperatingPoint`: actual power values for **one time step**.
3. `FBSConfig`: convergence settings.

Every `OperatingPoint` mapping must contain **every network bus**, including
the slack bus. Use explicit zeros where there is no consumption or generation.

| OperatingPoint field | Unit | Sign convention |
|---|---|---|
| `p_load_kw` | kW | Positive active consumption |
| `q_load_kvar` | kvar | Positive reactive consumption |
| `p_pv_kw` | kW | Positive PV active injection |
| `q_pv_kvar` | kvar | Positive reactive injection; negative absorption |
| `p_bess_kw` | kW | Positive discharge; negative charging |
| `q_bess_kvar` | kvar | Positive reactive injection; negative absorption |

At each bus the solver calculates:

```text
P_net = P_load - P_PV - P_BESS
Q_net = Q_load - Q_PV - Q_BESS
S_net = P_net + jQ_net
```

It converts the input powers and impedances to per-unit, sets the initial
voltages to the slack voltage, then repeats:

1. **Backward sweep:** calculate load currents and add downstream currents,
   working from leaves toward the slack bus.
2. **Forward sweep:** calculate each child's voltage from its parent's voltage
   and the line voltage drop, working from the slack toward the leaves.
3. **Convergence check:** compare the new and previous complex bus voltages.

The equations and worked examples are in
[the supplied guide](../../Validation/FBS_Step_by_Step_Guide.pdf).

| FBSConfig field | Default | Purpose |
|---|---:|---|
| `max_iterations` | 100 | Maximum complete sweeps |
| `voltage_tolerance_pu` | 1e-6 | Maximum allowed complex-voltage change for convergence |
| `slack_angle_deg` | 0.0 | Slack voltage reference angle |
| `record_history` | False | Save the flat start and each completed voltage iterate |

Example configuration:

```python
from src.fbs import FBSConfig

config = FBSConfig(
    max_iterations=100,
    voltage_tolerance_pu=1e-8,
    slack_angle_deg=0.0,
    record_history=True,
)
```

The FBS iteration limit is separate from the future optimizer's iteration limit.

## 5. Outputs: `PowerFlowResult`

| Field | Meaning / unit |
|---|---|
| `voltage_complex_pu` | Complex voltage by bus, pu |
| `voltage_mag_pu` | Voltage magnitude by bus, pu |
| `voltage_angle_deg` | Voltage angle by bus, degrees |
| `branch_current_a` | Current magnitude by line, A |
| `branch_p_kw`, `branch_q_kvar` | Sending-end power by line, kW / kvar |
| `line_loss_p_kw`, `line_loss_q_kvar` | Losses by line, kW / kvar |
| `total_loss_p_kw`, `total_loss_q_kvar` | Sum of line losses, kW / kvar |
| `slack_p_kw`, `slack_q_kvar` | Grid supply, including any demand at the slack bus |
| `converged` | Whether the numerical tolerance was reached |
| `iterations` | Number of completed sweeps |
| `max_delta_v_pu` | Largest complex-voltage change in the last completed sweep |
| `message` | Convergence or failure explanation |
| `branch_current_pu` | Optional complex branch-current values for debugging |
| `voltage_history` | Optional voltage iterations when `record_history=True` |

Dictionary keys are bus IDs for bus quantities and line IDs for branch
quantities. Branch power uses the derived **parent→child** direction, regardless
of the input endpoint order. Negative active branch/slack power means export
against that direction. Current magnitude remains nonnegative.

Public powers are three-phase totals. Voltage bases are line-to-line kV,
line R/X are ohms per phase, and public current magnitudes are A.

## 6. Change loads, PV or BESS injection

This example loads a workbook and constructs one explicit operating point:

```python
from src_accelerated.fbs import FBSConfig, OperatingPoint, run_fbs
from src_accelerated.network_loader import load_network

network = load_network("path/to/network.xlsx", workbook_format="auto", frequency_hz=60)
bus_ids = [bus.bus_id for bus in network.buses]
loads = network.loads_by_bus()
pv_units = network.pv_by_bus()
zeros = {bus_id: 0.0 for bus_id in bus_ids}
point = OperatingPoint(
    {bus_id: sum(load.p_base_kw for load in loads[bus_id]) for bus_id in bus_ids},
    {bus_id: sum(load.q_base_kvar for load in loads[bus_id]) for bus_id in bus_ids},
    {bus_id: sum(unit.p_rated_kw for unit in pv_units[bus_id]) for bus_id in bus_ids},
    zeros.copy(), zeros.copy(), zeros.copy(),
)

# Override this time step's PV output rather than changing its installed rating.
point.p_pv_kw[4] = 90.0  # only if bus 4 exists in this workbook

# A prescribed injection only; use simulation.py for BESS SOC integration.
point.p_bess_kw[5] = 50.0  # discharge; use -50.0 for charging

result = run_fbs(network, point, FBSConfig())
if not result.converged:
    raise RuntimeError(result.message)
print(result.voltage_mag_pu)
print(result.slack_p_kw)
```

This construction adds all base loads at each bus, uses PV **rated** output,
and sets reactive PV and BESS injection to zero. Actual time-varying values
should be supplied through `OperatingPoint` by the simulation layer.

Changing `point.p_bess_kw` does not enforce battery capacity, efficiency or SOC
limits. Use `simulation.py` to call the existing BESS step and carry SOC.

## 7. Checks and current limits

From `07_Implementation`, run:

```bash
python -m unittest discover -s tests -v
```

The 12 network/FBS tests cover manual calculations, the guide's final answers, a two-bus
analytic solution, power balance, reversed lines, invalid inputs, injection
signs and failure handling. Twenty-five additional simulation integration tests
cover hourly BESS state, reserve, voltage, curtailment/shedding and failure handling, including a
synthetic three-month run. An optional independent nodal-equation check is:

```bash
python -m pip install -r Validation/requirements.txt
python -m Validation.verify_nodal_reference
```

See [verification notes](../../Validation/FBS_Verification_Notes.md) for numerical
comparisons and the guide's tolerance/iteration-count discrepancy.

Always check `result.converged` before accepting results. A failure result is
diagnostic. A converged solution can still violate voltage limits;
`simulation.py` evaluates voltage/reserve feasibility. Thermal constraints are
excluded from the first implementation scope.

Current scope is a balanced, single-voltage radial feeder with series lines
and constant-power injections. It does not model transformers, shunts,
unbalanced phases or optimization. Hourly SOC/profile integration is provided
by `simulation.py`, outside the solver. The same solver
can receive larger radial networks. `network_loader.py` now imports the supplied
IEEE 33-bus Excel workbook into that same model without rewriting the solver.

The software design authority remains
[`TERM2_SOFTWARE_DESIGN_SPEC.md`](../../../02_Reports/Working/Planning/TERM2_SOFTWARE_DESIGN_SPEC.md).
