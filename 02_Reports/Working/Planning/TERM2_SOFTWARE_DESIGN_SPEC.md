# Term 2 Software Design Specification

**Status:** Design specification for implementation handoff  
**Purpose:** Move software architecture, interfaces, data structures, file formats, and module I/O decisions out of implementation tasks and into one design reference.  
**Related baseline:** `TERM2_SHADOW_DESIGN.md`  
**Scheduling source of truth:** live Task Register / Gantt

## 1. How to read this specification

This document distinguishes between two kinds of statements:

- **Existing baseline requirement** — already supported by the Term 1 baseline, current project requirements, or current working context. Implementation should preserve it unless evidence/advisor guidance justifies a change.
- **Proposed design decision** — an implementation-level software design choice that was not fixed by the existing requirements. It is specified here so implementation tasks do not need to redesign the software independently. These choices should be reviewed by the team; if the team changes one, update this specification before or with the implementation change.

This file is **not implementation code**. It defines what the code must expose and how modules exchange data.

### Design vs implementation rule

**DESIGN includes:** architecture, module responsibilities, data structures, interfaces, algorithms, file formats, units, sign conventions, and required/optional outputs.

**IMPLEMENTATION includes:** writing the Python code that follows this specification, unit/integration testing, debugging, performance checks, and validation.

An implementation task should not invent a new architecture or data contract unless the design is first updated and the reason is recorded.

---

# 2. Overall software architecture

## 2.1 Existing baseline requirements

The software must support the staged workflow already defined for the project:

```text
Network + load/PV data
        ↓
Baseline radial power flow (FBS)
        ↓
BESS model
        ↓
Performance evaluation
        ↓
Optimization
        ↓
Uncertainty/scenarios
        ↓
Decision-support results/UI
```

The current technical baseline preserves:

- radial distribution networks,
- FBS power flow,
- solar PV,
- BESS decision vector `[B, P, E]`,
- hourly operation initially,
- later uncertainty/scenario analysis,
- later GWO/WSM optimization,
- 5-bus development case and IEEE 33-bus larger case.

## 2.2 Proposed module structure

**Proposed design decision:** use small Python modules with explicit data objects passed between them. No module should depend on UI state or global mutable variables.

```text
                         ui.py  [future]
                           │
                           ▼
                     simulation.py
                    /      │       \
                   /       │        \
          data_loader.py  bess.py   network_model.py
                   \       │        /
                    \      │       /
                           ▼
                         fbs.py
                           │
                           ▼
                       metrics.py
                           │
               ┌───────────┴───────────┐
               ▼                       ▼
        uncertainty.py [future]   optimizer.py [future]
               │                       │
               └───────────┬───────────┘
                           ▼
                       results.py
```

### Module responsibilities

| Module | Responsibility | Must not do |
|---|---|---|
| `network_model.py` | Represent static network topology/equipment and validate it | Run time-series simulation or optimization |
| `data_loader.py` | Read/validate profile files and produce standardized profile objects | Solve power flow |
| `fbs.py` | Solve one radial-network power-flow time step | Read CSV files, optimize BESS, or manage UI |
| `bess.py` | Represent BESS parameters/state and apply one charge/discharge step | Solve network power flow |
| `simulation.py` | Orchestrate network + profiles + BESS + FBS over one or many time steps | Contain optimizer search logic |
| `metrics.py` | Calculate technical/economic metrics from simulation results | Modify network/BESS state |
| `uncertainty.py` | Future scenario/forecast interface | Reimplement network physics |
| `optimizer.py` | Future search over `[B,P,E]` using simulator/evaluator | Duplicate FBS/BESS equations |
| `results.py` | Standardized result/export helpers | Change simulation state |
| `ui.py` | Future user interaction | Contain engineering calculations |

## 2.3 Module interaction rule

**Proposed design decision:** modules interact through typed data objects/interfaces, not by importing and modifying each other's internal variables.

Examples:

- `data_loader.py` returns `ProfileData`.
- `network_model.py` returns/contains `NetworkModel`.
- `simulation.py` combines `NetworkModel`, `ProfileData`, and optional `BESSConfig/BESSState` into an `OperatingPoint`.
- `fbs.py` consumes `NetworkModel + OperatingPoint + FBSConfig` and returns `PowerFlowResult`.
- `metrics.py` consumes results and returns metric values.
- future `optimizer.py` calls the public simulation/evaluation interface only.

This keeps modules independently testable.

---

# 3. `network_model.py` design specification

## 3.1 Responsibility

`network_model.py` defines the **static electrical network model**. It stores topology, base quantities, buses, branches, fixed/base loads, PV units, and validation helpers.

It does not run FBS, update SOC, load time-series files, or perform optimization.

## 3.2 Data structure choice

**Proposed design decision:** use Python `dataclass` objects for electrical entities and one `NetworkModel` dataclass/container.

Reason for proposing dataclasses:

- clearer field names/units than nested anonymous dictionaries,
- lightweight compared with a deep class hierarchy,
- easy to construct for 5-bus and IEEE 33-bus cases,
- straightforward unit testing,
- easy conversion to/from dictionaries/CSV later.

Do not use free-form dictionaries as the primary internal network representation. Dictionaries may still be used temporarily for lookup tables inside functions.

## 3.3 Required data objects

### `Bus`

| Field | Type | Unit | Required | Meaning |
|---|---|---:|---|---|
| `bus_id` | `int` | — | yes | Unique bus identifier |
| `name` | `str` | — | yes | Human-readable label |
| `base_kv` | `float` | kV line-line | yes | Nominal bus voltage |
| `is_slack` | `bool` | — | yes | True only for source/slack bus |
| `v_set_pu` | `float` | p.u. | yes | Slack/reference voltage setpoint; default 1.0 where applicable |

### `Line`

| Field | Type | Unit | Required | Meaning |
|---|---|---:|---|---|
| `line_id` | `str` | — | yes | Unique branch identifier |
| `from_bus` | `int` | — | yes | One endpoint |
| `to_bus` | `int` | — | yes | Other endpoint |
| `r_ohm` | `float` | ohm/phase | yes | Series resistance |
| `x_ohm` | `float` | ohm/phase | yes | Series reactance |
| `ampacity_a` | `float | None` | A | optional | Thermal/current limit when available |

**Proposed design decision:** line rows do not need to be entered in source-to-load order. `NetworkModel` derives parent/child orientation from the slack bus before FBS.

### `Load`

| Field | Type | Unit | Required | Meaning |
|---|---|---:|---|---|
| `load_id` | `str` | — | yes | Unique load identifier |
| `bus_id` | `int` | — | yes | Connected bus |
| `p_base_kw` | `float` | kW | yes | Base active demand |
| `q_base_kvar` | `float` | kVAR | yes | Base reactive demand |

Positive load values mean **consumption**.

### `PVUnit`

| Field | Type | Unit | Required | Meaning |
|---|---|---:|---|---|
| `pv_id` | `str` | — | yes | Unique PV identifier |
| `bus_id` | `int` | — | yes | Connected bus |
| `p_rated_kw` | `float` | kW | yes | Installed active-power rating |
| `q_capability_kvar` | `float | None` | kVAR | optional | Reserved for future reactive-power capability |

The static object stores installed/rated data. Time-varying PV output comes from `ProfileData`/`OperatingPoint`, not by repeatedly mutating `PVUnit`.

### `NetworkModel`

| Field | Type | Unit | Required |
|---|---|---:|---|
| `buses` | `list[Bus]` | — | yes |
| `lines` | `list[Line]` | — | yes |
| `loads` | `list[Load]` | — | yes |
| `pv_units` | `list[PVUnit]` | — | yes, may be empty |
| `base_power_kva` | `float` | kVA, 3-phase base | yes |
| `frequency_hz` | `float` | Hz | yes |

## 3.4 Required validation behavior

`NetworkModel.validate()` must check at minimum:

1. bus IDs are unique,
2. exactly one slack bus exists,
3. every line endpoint exists,
4. no line connects a bus to itself,
5. loads/PV reference existing buses,
6. the graph is connected,
7. the graph is radial for the FBS solver (`number_of_lines = number_of_buses - 1` after connectivity is confirmed),
8. base quantities and line impedances are physically valid/nonnegative where appropriate.

A validation failure must raise/return a clear error before FBS starts.

## 3.5 Base-value convention

**Proposed design decision:** store network input values in engineering units (kV, kVA, ohm, kW, kVAR). `fbs.py` performs or calls a deterministic conversion to per-unit using the network base values.

For a balanced three-phase model:

```text
Z_base_ohm = V_base_kV^2 / S_base_MVA
```

with consistent line-line voltage and three-phase apparent-power base.

The conversion must be centralized; individual team members must not create their own unit conversions in separate modules.

## 3.6 Public interface

Required public operations conceptually:

```text
network.validate()
network.slack_bus_id()
network.radial_order()
network.loads_by_bus()
network.pv_by_bus()
```

`radial_order()` must provide the parent/child branch ordering needed by FBS.

### Input to `network_model.py`

- hard-coded/constructed 5-bus data initially, or standardized network-data reader later,
- bus/line/load/PV definitions,
- base values.

### Output from `network_model.py`

- validated `NetworkModel`,
- topology lookup/order helpers,
- no power-flow results.

---

# 4. `fbs.py` design specification

## 4.1 Responsibility

`fbs.py` performs a **single time-step Forward/Backward Sweep power-flow calculation** for a validated radial `NetworkModel` and one operating point.

Existing baseline requirement: FBS remains the initial power-flow method.

## 4.2 Information received from `network_model.py`

`fbs.py` receives the validated `NetworkModel` containing:

- bus IDs and slack bus,
- nominal/base voltage,
- branch endpoints and R/X,
- network base power,
- radial branch ordering/topology.

It must not read network CSV files directly.

## 4.3 Time-step operating input

**Proposed design decision:** use an `OperatingPoint` object for one time step.

Required fields:

```text
OperatingPoint
- p_load_kw:   mapping bus_id -> kW consumption
- q_load_kvar: mapping bus_id -> kVAR consumption
- p_pv_kw:     mapping bus_id -> kW generation
- q_pv_kvar:   mapping bus_id -> kVAR generation (default 0)
- p_bess_kw:   mapping bus_id -> kW injection (default 0)
- q_bess_kvar: mapping bus_id -> kVAR injection (default 0)
```

### Sign convention

- load values are positive consumption,
- PV values are positive generation,
- **BESS `p_bess_kw > 0` means discharging/injecting into the network**,
- **BESS `p_bess_kw < 0` means charging/absorbing from the network**.

The net complex demand at a bus is formed consistently as consumption minus generation/injection.

## 4.4 FBS configuration

**Proposed design decision:** define an `FBSConfig` object with:

| Field | Proposed default | Unit/meaning |
|---|---:|---|
| `max_iterations` | 100 | Maximum FBS iterations for one power-flow solution |
| `voltage_tolerance_pu` | `1e-6` | Maximum bus-voltage complex/magnitude change criterion |
| `slack_angle_deg` | 0.0 | Slack reference angle |
| `record_history` | `False` | Enable optional iteration-debug history |

These are software/numerical defaults, **not new customer requirements**. They may be changed by the team if verification shows a better justified choice.

## 4.5 Convergence criterion

**Proposed design decision:** after each backward+forward sweep, calculate the maximum change in bus voltage from the previous iteration:

```text
max_delta_v = max_i |V_i(new) - V_i(old)|
```

Converged when:

```text
max_delta_v <= voltage_tolerance_pu
```

or stop with `converged = False` after `max_iterations`.

This FBS iteration limit is separate from the GWO/optimization iteration limit.

## 4.6 Required FBS outputs

Use one `PowerFlowResult` object.

### Required outputs

| Output | Unit |
|---|---:|
| `voltage_complex_pu[bus_id]` | p.u. complex |
| `voltage_mag_pu[bus_id]` | p.u. |
| `voltage_angle_deg[bus_id]` | degree |
| `branch_current_a[line_id]` | A |
| `branch_p_kw[line_id]` | kW |
| `branch_q_kvar[line_id]` | kVAR |
| `line_loss_p_kw[line_id]` | kW |
| `line_loss_q_kvar[line_id]` | kVAR |
| `total_loss_p_kw` | kW |
| `total_loss_q_kvar` | kVAR |
| `slack_p_kw` | kW |
| `slack_q_kvar` | kVAR |
| `converged` | bool |
| `iterations` | count |
| `max_delta_v_pu` | p.u. |

### Optional/debug outputs

- per-unit branch currents,
- iteration voltage history,
- parent/child sweep order,
- intermediate complex bus powers.

Debug outputs must not be required by downstream modules.

## 4.7 Public interface

Conceptual function:

```text
run_fbs(
    network: NetworkModel,
    operating_point: OperatingPoint,
    config: FBSConfig
) -> PowerFlowResult
```

Implementation may use helper functions internally, but this public contract should remain stable unless the design document is updated.

---

# 5. Data/profile loading design specification

## 5.1 Responsibility

`data_loader.py` imports already-prepared simulation data, validates required fields/units/timestamps, and returns a standardized in-memory profile object.

The loader does not decide bus allocations during simulation and does not solve power flow.

## 5.2 File format

**Proposed design decision:** use UTF-8 CSV files in **long format** because the same format scales from 5 buses to IEEE 33-bus without creating bus-specific column names.

### Load profile file: `load_profile.csv`

Required columns:

| Column | Type | Unit | Meaning |
|---|---|---:|---|
| `timestamp` | ISO-8601 datetime | — | Time index |
| `bus_id` | integer | — | Load bus |
| `p_kw` | float | kW | Active demand |
| `q_kvar` | float | kVAR | Reactive demand |

Each timestamp may contain multiple rows, one per load bus.

### PV profile file: `pv_profile.csv`

Required columns:

| Column | Type | Unit | Meaning |
|---|---|---:|---|
| `timestamp` | ISO-8601 datetime | — | Time index |
| `bus_id` | integer | — | PV bus |
| `p_kw` | float | kW | Available/used PV active generation for the base simulation |

Optional column:

| Column | Unit | Meaning |
|---|---:|---|
| `q_kvar` | kVAR | PV reactive injection if later modeled; default 0 |

### Why absolute bus-level values are proposed

Using `p_kw/q_kvar` by bus avoids hidden assumptions inside the simulator. If the source dataset is system-level only, allocation/scaling must be performed once in data preparation and documented before the file is passed to the simulator.

That allocation is a data/design-preparation decision, not something `fbs.py` should infer.

## 5.3 Standardized in-memory structure

**Proposed design decision:** `data_loader.py` may use pandas internally, but downstream modules receive a `ProfileData` object rather than a DataFrame dependency.

```text
ProfileData
- timestamps: ordered sequence of datetime
- load_p_kw: dict[bus_id, array[float]]
- load_q_kvar: dict[bus_id, array[float]]
- pv_p_kw: dict[bus_id, array[float]]
- pv_q_kvar: dict[bus_id, array[float]]   # optional/default zero
- dt_hours: float
```

## 5.4 Loader validation

Required checks:

- required columns exist,
- timestamps parse correctly and are sorted,
- no duplicate `(timestamp, bus_id)` rows within the same profile file,
- load and PV timestamps can be aligned,
- bus IDs exist in `NetworkModel`,
- units are the required engineering units,
- no missing/non-numeric required power values remain,
- time step is consistent with the intended simulation resolution.

## 5.5 Public interface

Conceptually:

```text
load_profiles(
    load_csv_path,
    pv_csv_path,
    network: NetworkModel
) -> ProfileData
```

and:

```text
profile_data.operating_point(index, bess_injection=None) -> OperatingPoint
```

`simulation.py` uses this interface; FBS never reads CSV directly.

---

# 6. BESS model design specification

## 6.1 Existing baseline requirements

Preserve:

- location/bus `B`,
- energy capacity `E` in kWh,
- power rating `P` in kW,
- SOC state,
- SOC limits initially 10%–90%,
- charge/discharge efficiency,
- no simultaneous charge and discharge,
- hourly time step initially,
- initial SOC may use the current baseline assumption when no case-specific value is supplied.

## 6.2 Proposed BESS data structures

Use two dataclasses so immutable/configuration data is separated from changing state.

### `BESSConfig`

| Field | Unit | Required |
|---|---:|---|
| `bus_id` | — | yes |
| `energy_capacity_kwh` | kWh | yes |
| `power_rating_kw` | kW | yes |
| `soc_min` | fraction | yes |
| `soc_max` | fraction | yes |
| `soc_initial` | fraction | yes |
| `eta_charge` | fraction | yes |
| `eta_discharge` | fraction | yes |
| `max_charge_kw` | kW | optional; default = power rating |
| `max_discharge_kw` | kW | optional; default = power rating |

### `BESSState`

| Field | Unit |
|---|---:|
| `energy_kwh` | kWh |
| `soc` | fraction |

`energy_kwh = soc * energy_capacity_kwh` must remain consistent.

## 6.3 Step interface

The BESS model receives a requested active-power action and returns the physically feasible action/state.

```text
step_bess(
    config: BESSConfig,
    state: BESSState,
    requested_power_kw: float,
    dt_hours: float
) -> BESSStepResult
```

### Sign convention

Use the same convention as FBS:

- requested/actual `power_kw > 0` = discharge to network,
- requested/actual `power_kw < 0` = charge from network.

### Required `BESSStepResult`

| Output | Unit |
|---|---:|
| `actual_power_kw` | kW |
| `energy_before_kwh` | kWh |
| `energy_after_kwh` | kWh |
| `soc_before` | fraction |
| `soc_after` | fraction |
| `limited` | bool |
| `limit_reason` | string/enum |

## 6.4 BESS-network interaction

`bess.py` does not directly edit bus voltages or line flows.

The interaction is:

```text
requested BESS action
        ↓
     bess.py
        ↓
actual feasible p_bess_kw + updated SOC
        ↓
simulation.py inserts p_bess_kw at BESS bus
        ↓
OperatingPoint
        ↓
      fbs.py
```

This separation allows BESS logic to be unit-tested without a power-flow solver.

---

# 7. Simulation/orchestration and future-module interfaces

## 7.1 `simulation.py`

**Proposed design decision:** add an orchestration layer rather than letting UI/optimizer call FBS and BESS internals directly.

### Single-step simulation interface

```text
simulate_step(
    network: NetworkModel,
    operating_point: OperatingPoint,
    fbs_config: FBSConfig,
    bess_config: BESSConfig | None = None,
    bess_state: BESSState | None = None,
    bess_request_kw: float = 0
) -> SimulationStepResult
```

### Time-series interface

```text
simulate_timeseries(
    network,
    profiles,
    simulation_config,
    bess_config=None,
    dispatch_policy=None
) -> TimeSeriesSimulationResult
```

The first FBS implementation only needs `run_fbs()` for one time step. The hourly loop can be added later without changing the FBS contract.

## 7.2 `metrics.py`

Placeholder/public concept:

```text
evaluate_results(simulation_result, economic_config) -> PerformanceMetrics
```

Required metric families remain those already in the baseline: cost, curtailment, load shedding, voltage/technical limits, losses, and improvement measures.

Detailed economic coefficients remain inputs; do not hard-code unverified values in module interfaces.

## 7.3 `uncertainty.py` future interface

Existing baseline: ARIMA + Monte Carlo, 100 generated scenarios, 45 retained scenarios.

Do not implement now unless the schedule reaches V5.

**Proposed interface placeholder:**

```text
Scenario
- scenario_id
- profiles: ProfileData
- probability: float | None
- metadata: mapping

ScenarioSet
- scenarios: list[Scenario]

generate_scenarios(history/profiles, config) -> ScenarioSet
select_scenarios(scenario_set, selection_config) -> ScenarioSet
```

This allows future scenarios to reuse the exact same `ProfileData` and simulation interfaces.

## 7.4 `optimizer.py` future interface

Existing baseline: optimizer decision vector is `[B,P,E]`; GWO/WSM is the starting baseline.

Do not implement now unless the schedule reaches V4.

**Proposed interface placeholder:**

```text
BESSCandidate
- bus_id
- power_rating_kw
- energy_capacity_kwh

OptimizationResult
- best_candidate
- best_objective
- metrics
- convergence_history
- iterations
- metadata

optimize(
    network,
    profiles_or_scenarios,
    bounds,
    evaluator,
    optimizer_config
) -> OptimizationResult
```

The optimizer must call the simulation/evaluator public interfaces. It must not contain its own copy of FBS or SOC equations.

---

# 8. Module input/output specification

## 8.1 Summary table

| Module | Required inputs | Required outputs | Optional/debug outputs |
|---|---|---|---|
| `network_model.py` | buses, lines, loads, PV units, base values | validated `NetworkModel`, radial order/lookups | validation diagnostics |
| `data_loader.py` | load CSV, PV CSV, `NetworkModel` | `ProfileData` | import-quality summary |
| `bess.py` | `BESSConfig`, `BESSState`, requested kW, `dt_hours` | `BESSStepResult` | clipping/limit diagnostics |
| `fbs.py` | `NetworkModel`, `OperatingPoint`, `FBSConfig` | `PowerFlowResult` | iteration history/intermediates |
| `simulation.py` | network, profiles/operating point, configs, optional BESS | step/time-series simulation result | per-step debug details |
| `metrics.py` | simulation results, economic config | performance metrics | component breakdown |
| `uncertainty.py` | profiles/history + config | `ScenarioSet` | scenario statistics |
| `optimizer.py` | network, profiles/scenarios, bounds, evaluator/config | `OptimizationResult` | population/convergence details |
| `results.py` | standardized results | tables/plots/export files | extra diagnostics |
| `ui.py` | user selections/files/settings | calls public backend interfaces and displays results | UI logs |

## 8.2 Shared units and conventions

| Quantity | Standard unit |
|---|---:|
| Active power | kW |
| Reactive power | kVAR |
| Apparent/base power | kVA unless explicitly converted |
| Energy | kWh |
| Voltage input/base | kV line-line |
| Solved voltage | p.u. (required), kV may be derived |
| Line R/X | ohm/phase |
| Current | A |
| Time step | hours |
| SOC | fraction 0–1 internally; percentage only for display |
| Angle | degrees in public results |

### Power sign conventions

- load `P,Q`: positive consumption,
- PV `P,Q`: positive generation/injection,
- BESS `P > 0`: discharge/injection,
- BESS `P < 0`: charge/consumption,
- slack result positive when the grid supplies net power to the modeled network.

Every module must use these conventions.

## 8.3 Required vs optional output rule

Downstream code may depend only on outputs marked **required** in this specification. Optional/debug outputs can be added without changing downstream interfaces.

If a required output needs to be renamed/removed, update this design specification before changing multiple modules.

---

# 9. Initial 5-bus implementation contract

The first network/FBS implementation should be intentionally small, but it must use the same interfaces intended for larger systems.

Required characteristics:

- radial topology,
- exactly one slack bus,
- 5 buses represented using `Bus` objects,
- branches using `Line` objects,
- loads using `Load` objects,
- at least one PV unit where the selected 5-bus development case requires it,
- network base quantities defined once in `NetworkModel`,
- one operating point passed to `run_fbs()`,
- no 5-bus-specific equations hard-coded inside `fbs.py`.

The IEEE 33-bus case should later be constructible by supplying a larger `NetworkModel` without rewriting the FBS algorithm.

---

# 10. Design decisions still explicitly proposed

The following were not fixed by the existing project requirements and are therefore **proposed design decisions**, not new project requirements:

1. Python dataclasses as the primary internal network/BESS/config/result structures.
2. Long-format CSV for load/PV profile input.
3. Bus-level absolute kW/kVAR profile values at the simulator boundary.
4. `OperatingPoint` as the one-time-step power-flow input object.
5. BESS positive-power sign = discharge/injection.
6. Central `simulation.py` orchestration layer.
7. FBS default tolerance `1e-6 pu` and `max_iterations = 100`.
8. Standardized public result objects rather than returning anonymous tuples.
9. Future scenario objects reuse `ProfileData`.
10. Future optimizer uses only public simulation/evaluator interfaces.

These choices are intended to prevent each implementation owner from making incompatible local decisions. If the team rejects one, replace it with the team's chosen design here before implementation diverges.

---

# 11. Implementation handoff checklist

Before assigning an implementation task, the assignee should be able to answer from the design documents:

- What module am I implementing?
- What is the module responsible for?
- What must it not do?
- What input object/file does it receive?
- What fields and units are required?
- What output object/fields must it return?
- What sign conventions apply?
- What existing baseline requirement does it preserve?
- Which choices are only proposed design decisions?
- How will the module be tested independently?

If any of these cannot be answered, treat it as a design gap and update this specification before coding around it.
