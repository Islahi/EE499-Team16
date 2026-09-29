# Term 2 Software Design Specification

**Status:** Design specification for implementation handoff  
**Purpose:** Move software architecture, interfaces, data structures, file formats, numerical contracts and module I/O decisions out of implementation tasks so implementation owners can code against a common specification.  
**Related high-level baseline:** `TERM2_SHADOW_DESIGN.md`  
**Schedule source of truth:** live Task Register / Gantt  

## 1. Design authority and labels

This document is a **DESIGN artifact**, not implementation code.

Two labels are used throughout:

- **Existing baseline requirement** — already supported by the official/project material, Term 1 baseline, or current working context. Implementation should preserve it unless evidence/advisor guidance justifies a change.
- **Proposed design decision** — a software/numerical design choice not fixed by the existing requirements. It is specified here so individual implementers do not invent incompatible local solutions. It is **not a new customer requirement** and is not automatically a confirmed team decision in `DECISIONS.md`.

### Design vs implementation rule

**DESIGN owns:**

- software architecture,
- module responsibilities,
- public interfaces,
- data structures,
- algorithms/numerical contracts,
- file formats,
- units and sign conventions,
- required vs optional outputs,
- configuration meanings,
- future-module integration boundaries.

**IMPLEMENTATION owns:**

- writing the Python code that follows this specification,
- unit/integration testing,
- debugging,
- verification against references,
- performance checks,
- running experiments and validation.

If implementation reveals a required design change, update this document first (or in the same change) and record the engineering reason. Do not allow modules to diverge silently.

---

# 2. Overall software architecture

## 2.1 Existing baseline requirements

The software must support the staged project workflow:

```text
Network + load/PV data
        ↓
Radial power flow (FBS)
        ↓
BESS model
        ↓
Performance metrics
        ↓
Optimization
        ↓
Uncertainty/scenarios
        ↓
Decision-support results/UI
```

The current baseline preserves:

- radial distribution networks,
- Forward/Backward Sweep (FBS),
- solar PV,
- BESS planning vector `[B, P, E]`,
- hourly operation initially,
- later ARIMA/Monte Carlo uncertainty,
- later GWO/WSM optimization,
- a 5-bus development case,
- later IEEE 33-bus use without rewriting the core solver.

## 2.2 Proposed implementation package layout

**Proposed design decision:** use the following module split under `07_Implementation/`. The exact Python package name may be chosen during repository setup, but these file responsibilities are fixed by this specification.

```text
07_Implementation/
├─ src/
│  ├─ network_model.py
│  ├─ network_cases.py
│  ├─ data_loader.py
│  ├─ fbs.py
│  ├─ bess.py
│  ├─ simulation.py
│  ├─ metrics.py
│  ├─ uncertainty.py      # placeholder until V5
│  ├─ optimizer.py        # placeholder until V4
│  ├─ results.py
│  └─ ui.py               # later V6
└─ tests/
   ├─ test_network_model.py
   ├─ test_data_loader.py
   ├─ test_fbs.py
   ├─ test_bess.py
   └─ test_simulation.py
```

`network_cases.py` is proposed so the 5-bus/IEEE-33 case data does not become mixed with the reusable network data model.

## 2.3 Module responsibilities

| Module | Responsibility | Must not do |
|---|---|---|
| `network_model.py` | Define static network entities, topology, validation and radial ordering | Run power flow, read time-series CSV, update SOC, optimize |
| `network_cases.py` | Construct named network cases using `NetworkModel` objects | Contain FBS equations |
| `data_loader.py` | Read/validate prepared load/PV profiles and return standardized profile objects | Solve power flow or choose optimization decisions |
| `fbs.py` | Solve one radial-network power-flow time step | Read CSV, update BESS SOC, optimize, manage UI |
| `bess.py` | Define BESS parameters/state and apply one physically feasible charge/discharge step | Solve network power flow |
| `simulation.py` | Orchestrate profiles, BESS injection and FBS for one/many time steps | Contain GWO search logic |
| `metrics.py` | Calculate technical/economic performance from simulation results | Modify network/BESS state |
| `uncertainty.py` | Later forecasting/scenario generation/selection interface | Reimplement network/BESS physics |
| `optimizer.py` | Later search over `[B,P,E]` using the public simulator/evaluator | Duplicate FBS/SOC equations |
| `results.py` | Result formatting/export helpers | Change engineering state |
| `ui.py` | Later user interaction and display | Contain engineering calculations |

## 2.4 Interaction and dependency rule

**Proposed design decision:** modules exchange explicit typed objects and function returns. No engineering module should depend on UI state or shared mutable globals.

Main dependency direction:

```text
network_cases.py ──> network_model.py
                           │
data_loader.py ────────────┤
                           ▼
                      simulation.py <── bess.py
                           │
                           ▼
                         fbs.py
                           │
                           ▼
                       metrics.py
                           │
                ┌──────────┴───────────┐
                ▼                      ▼
          optimizer.py           uncertainty.py
                └──────────┬───────────┘
                           ▼
                       results.py
                           ▲
                           │
                          ui.py
```

Implementation owners may create private helper functions, but public data contracts below must remain stable unless this design is updated.

## 2.5 Ownership of shared data objects

To avoid circular dependencies, each shared object has one owning module:

| Object | Owning module |
|---|---|
| `Bus`, `Line`, `Load`, `PVUnit`, `NetworkModel`, `RadialOrder` | `network_model.py` |
| `ProfileData`, `ProfileSlice` | `data_loader.py` |
| `OperatingPoint`, `FBSConfig`, `PowerFlowResult` | `fbs.py` |
| `BESSConfig`, `BESSState`, `BESSStepResult` | `bess.py` |
| `SimulationStepResult`, `TimeSeriesSimulationResult`, `SimulationConfig` | `simulation.py` |
| `PerformanceMetrics`, `EconomicConfig` | `metrics.py` |
| `Scenario`, `ScenarioSet` | `uncertainty.py` |
| `BESSCandidate`, `OptimizationResult`, optimizer config/bounds | `optimizer.py` |

Other modules import these public objects; they do not redefine them.

## 2.6 Independent testability

Each module must be testable without the full application:

- `network_model.py`: validate a tiny manually constructed network with no FBS call.
- `data_loader.py`: read small CSV fixtures with a test `NetworkModel` and no FBS call.
- `fbs.py`: run one fixed `OperatingPoint` with no CSV/BESS/optimizer.
- `bess.py`: run charge/discharge steps with no network solver.
- `simulation.py`: integration-test network + profiles + optional BESS using the public functions.
- later `optimizer.py`: use a stub evaluator or the public simulation/evaluation path, never solver internals.

---

# 3. `network_model.py` design specification

## 3.1 Responsibility

`network_model.py` represents the **static balanced radial distribution network** used by the solver. It stores network topology/equipment and base/reference data, validates the network, and derives radial branch ordering.

It does not contain time-varying profile values, FBS iteration state, BESS SOC, optimization state, or UI state.

## 3.2 Data structure choice

**Proposed design decision:** use Python `dataclass` objects for network entities and one `NetworkModel` dataclass/container.

Why:

- field names and units are explicit,
- easier to test than nested free-form dictionaries,
- lightweight enough for both 5-bus and IEEE 33-bus cases,
- easy to convert from files/dictionaries later.

Free-form dictionaries are allowed only as internal lookup helpers, not as the primary public network representation.

## 3.3 Required network entities

### `Bus`

| Field | Type | Unit | Required | Meaning |
|---|---|---:|---|---|
| `bus_id` | `int` | — | yes | Unique bus identifier |
| `name` | `str` | — | yes | Human-readable label |
| `base_kv` | `float` | kV line-line | yes | Nominal/base voltage |
| `is_slack` | `bool` | — | yes | Source/reference bus flag |
| `v_set_pu` | `float` | p.u. | yes | Slack/reference setpoint, normally 1.0 |

### `Line`

| Field | Type | Unit | Required | Meaning |
|---|---|---:|---|---|
| `line_id` | `str` | — | yes | Unique branch identifier |
| `from_bus` | `int` | — | yes | Source-file endpoint; orientation may be rederived |
| `to_bus` | `int` | — | yes | Source-file endpoint; orientation may be rederived |
| `r_ohm` | `float` | ohm/phase | yes | Series resistance |
| `x_ohm` | `float` | ohm/phase | yes | Series reactance |
| `ampacity_a` | `float | None` | A | optional | Current/thermal limit if known |

### `Load`

| Field | Type | Unit | Required | Meaning |
|---|---|---:|---|---|
| `load_id` | `str` | — | yes | Unique load identifier |
| `bus_id` | `int` | — | yes | Connected bus |
| `p_base_kw` | `float` | kW | yes | Base active demand |
| `q_base_kvar` | `float` | kVAR | yes | Base reactive demand |

Positive load `P,Q` means consumption.

### `PVUnit`

| Field | Type | Unit | Required | Meaning |
|---|---|---:|---|---|
| `pv_id` | `str` | — | yes | Unique PV identifier |
| `bus_id` | `int` | — | yes | Connected bus |
| `p_rated_kw` | `float` | kW | yes | Installed active-power rating |
| `q_capability_kvar` | `float | None` | kVAR | optional | Reserved for later Q capability |

Static rated data stays in `PVUnit`; time-varying PV output comes from `ProfileData`.

### `NetworkModel`

| Field | Type | Unit | Required |
|---|---|---:|---|
| `buses` | `list[Bus]` | — | yes |
| `lines` | `list[Line]` | — | yes |
| `loads` | `list[Load]` | — | yes |
| `pv_units` | `list[PVUnit]` | — | yes; may be empty |
| `base_power_kva` | `float` | kVA, 3-phase base | yes |
| `frequency_hz` | `float` | Hz | yes |

## 3.4 `RadialOrder`

**Proposed design decision:** `NetworkModel.radial_order()` returns a deterministic `RadialOrder` object with:

- `slack_bus_id`,
- `parent_bus_by_bus`,
- `parent_line_by_bus`,
- `children_by_bus`,
- `forward_line_ids` ordered slack-to-leaves,
- `backward_line_ids` ordered leaves-to-slack.

Input line rows do **not** need to be stored in source-to-load order. The orientation used by FBS is derived from the slack bus.

## 3.5 Required validation behavior

`NetworkModel.validate()` must check at minimum:

1. unique bus IDs,
2. exactly one slack bus,
3. unique line IDs,
4. every line endpoint exists,
5. no self-connected line,
6. every load/PV references an existing bus,
7. connected graph,
8. radial graph (`n_lines = n_buses - 1` after connectivity check),
9. positive base power and bus base voltage,
10. physically valid line parameters (`r_ohm >= 0`, valid numeric `x_ohm`),
11. no negative base active/reactive load values unless a deliberate later model change is documented.

Validation failure must stop the solver before FBS starts and provide a clear error.

## 3.6 Network case construction

**Proposed design decision:** keep reusable entity definitions in `network_model.py`; keep actual study-case values in `network_cases.py`.

Required initial public builder:

```text
build_5_bus_case() -> NetworkModel
```

Later:

```text
build_ieee33_case(...) -> NetworkModel
```

The first implementation may encode the prepared 5-bus data directly in `network_cases.py`. `fbs.py` must not contain any 5-bus-specific constants or equations.

## 3.7 Units/base convention

**Proposed design decision:** module boundaries use engineering units; FBS converts deterministically to per-unit internally.

Balanced 3-phase base relations:

```text
S_base_MVA = base_power_kva / 1000
Z_base_ohm = V_base_kV^2 / S_base_MVA
I_base_A   = base_power_kva / (sqrt(3) * V_base_kV)
```

Initial feeder models are assumed to have the same nominal voltage level along the feeder because transformers are not part of the present network model. If transformer/multi-voltage modelling is later required, this design must be extended first.

## 3.8 Public interface

Required operations:

```text
network.validate() -> None / raises clear validation error
network.slack_bus_id() -> int
network.radial_order() -> RadialOrder
network.loads_by_bus() -> mapping
network.pv_by_bus() -> mapping
```

### Inputs

- bus definitions,
- line definitions,
- load definitions,
- PV definitions,
- base/reference parameters.

### Required outputs

- validated `NetworkModel`,
- deterministic topology/radial-order information.

### Optional/debug outputs

- validation summary,
- adjacency/lookup dictionaries.

No power-flow result belongs in this module.

---

# 4. `fbs.py` design specification

## 4.1 Responsibility

`fbs.py` performs **one single time-step Forward/Backward Sweep power-flow calculation** for a validated radial `NetworkModel` and one `OperatingPoint`.

**Existing baseline requirement:** FBS is the initial project power-flow method.

## 4.2 `OperatingPoint`

**Proposed design decision:** `fbs.py` owns the one-time-step `OperatingPoint` dataclass.

```text
OperatingPoint
- p_load_kw:   mapping bus_id -> kW consumption
- q_load_kvar: mapping bus_id -> kVAR consumption
- p_pv_kw:     mapping bus_id -> kW generation
- q_pv_kvar:   mapping bus_id -> kVAR generation
- p_bess_kw:   mapping bus_id -> kW network injection
- q_bess_kvar: mapping bus_id -> kVAR network injection
```

Missing generation/BESS entries at buses are treated as zero **only after** the operating point has been assembled by `simulation.py`; FBS itself receives a complete bus-indexed operating state.

### Sign convention

- load `P,Q > 0` = consumption,
- PV `P,Q > 0` = generation/injection,
- BESS `P > 0` = discharge/injection,
- BESS `P < 0` = charge/consumption.

Net complex demand at bus `i`:

```text
S_net,i = (P_load,i - P_pv,i - P_bess,i)
        + j(Q_load,i - Q_pv,i - Q_bess,i)
```

## 4.3 Information received from `network_model.py`

FBS receives only the public network data needed for calculation:

- bus IDs,
- slack bus and setpoint,
- base voltage(s) and base power,
- branch endpoints and `R/X`,
- `RadialOrder` parent/child orientation.

It must not read network files directly.

## 4.4 FBS numerical algorithm contract

**Proposed design decision:** use the standard current-summation radial FBS sequence below.

1. Validate/obtain radial order.
2. Convert branch impedance and bus complex powers to consistent per-unit quantities.
3. Initialize all bus voltages to the slack/reference voltage (flat start); slack angle uses the configured reference angle.
4. **Backward sweep:** for every non-slack bus from leaves toward the slack:

```text
I_inj,i = conj(S_net,i / V_i)
I_branch(parent→i) = I_inj,i + sum(I_branch(i→child))
```

5. **Forward sweep:** from slack toward leaves:

```text
V_child = V_parent - Z_branch * I_branch(parent→child)
```

6. Evaluate the convergence criterion.
7. Repeat until converged or the configured maximum iterations is reached.
8. Calculate required branch flows, slack power and losses from the final iterate.

The implementation may split these steps into private helpers but may not change the public mathematical contract without updating this design.

## 4.5 FBS configuration

**Proposed design decision:** `FBSConfig` contains:

| Field | Proposed default | Meaning |
|---|---:|---|
| `max_iterations` | 100 | Max FBS sweeps for one power-flow solution |
| `voltage_tolerance_pu` | `1e-6` | Convergence tolerance |
| `slack_angle_deg` | `0.0` | Slack reference angle |
| `record_history` | `False` | Optional debug history |

These are numerical software defaults, not project performance requirements.

## 4.6 Convergence criterion

After each complete backward+forward sweep:

```text
max_delta_v = max_i |V_i(new) - V_i(old)|
```

Converged when:

```text
max_delta_v <= voltage_tolerance_pu
```

If the limit is reached first, return `converged = False`. The last iterate may be included for diagnosis, but downstream simulation/optimization must treat a non-converged result as infeasible/failed rather than as a valid solution.

The FBS iteration limit is separate from the later GWO iteration limit.

## 4.7 Branch orientation and result convention

All branch quantities returned by FBS are reported in the **derived parent→child radial direction**, regardless of the original `Line.from_bus/to_bus` storage order.

Required physical conversions use the centralized network base convention. In per-unit:

```text
S_branch_pu = V_parent_pu * conj(I_branch_pu)
Loss_branch_pu = |I_branch_pu|^2 * Z_branch_pu
```

Convert back using the network base for public kW/kVAR/A results.

## 4.8 `PowerFlowResult`

### Required outputs

| Field | Unit |
|---|---:|
| `voltage_complex_pu[bus_id]` | p.u. complex |
| `voltage_mag_pu[bus_id]` | p.u. |
| `voltage_angle_deg[bus_id]` | degree |
| `branch_current_a[line_id]` | A |
| `branch_p_kw[line_id]` | kW parent→child |
| `branch_q_kvar[line_id]` | kVAR parent→child |
| `line_loss_p_kw[line_id]` | kW |
| `line_loss_q_kvar[line_id]` | kVAR |
| `total_loss_p_kw` | kW |
| `total_loss_q_kvar` | kVAR |
| `slack_p_kw` | kW; positive when grid supplies network |
| `slack_q_kvar` | kVAR |
| `converged` | bool |
| `iterations` | count |
| `max_delta_v_pu` | p.u. |
| `message` | text status/diagnostic |

### Optional/debug outputs

- per-unit branch currents,
- per-iteration voltage history,
- intermediate complex powers,
- radial order used.

Downstream modules must not depend on optional/debug fields.

## 4.9 Public interface

```text
run_fbs(
    network: NetworkModel,
    operating_point: OperatingPoint,
    config: FBSConfig
) -> PowerFlowResult
```

First implementation scope: **one time step only**. The time-series loop belongs in `simulation.py`.

---

# 5. Data/profile loading design specification

## 5.1 Responsibility

`data_loader.py` imports already-prepared load/PV simulation files, validates the schema/timestamps/bus references, and returns standardized profile objects.

It does not allocate system-level load to buses during simulation and does not solve power flow.

## 5.2 File format

**Proposed design decision:** use UTF-8 CSV in **long format** so the same schema works for 5 buses and IEEE 33 buses.

### `load_profile.csv`

Preferred/complete schema:

| Column | Type | Unit | Required | Meaning |
|---|---|---:|---|---|
| `timestamp` | ISO-8601 datetime | — | yes | Time index |
| `bus_id` | integer | — | yes | Load bus |
| `p_kw` | float | kW | yes | Active demand |
| `q_kvar` | float | kVAR | preferred | Reactive demand |

### Reactive-load fallback already defined by design baseline

If the prepared source file does not contain `q_kvar`, do **not** invent a rule during implementation. Apply the documented base-P/Q scaling rule from `TERM2_SHADOW_DESIGN.md` SD-4:

```text
m_i(t) = P_i(t) / P_base,i
Q_i(t) = m_i(t) * Q_base,i
```

The downstream `ProfileData` must always contain reactive load values.

### `pv_profile.csv`

| Column | Type | Unit | Required | Meaning |
|---|---|---:|---|---|
| `timestamp` | ISO-8601 datetime | — | yes | Time index |
| `bus_id` | integer | — | yes | PV bus |
| `p_kw` | float | kW | yes | PV active generation |
| `q_kvar` | float | kVAR | optional | PV reactive injection; default 0 for initial model |

**Proposed design decision:** initial PV is active-power-only unless a later approved design extends reactive capability.

## 5.3 Row-completeness rules

**Proposed design decision:**

- a bus with no `Load` object does not need a load-profile row and is treated as zero demand,
- every bus that has a configured `Load` must have exactly one load row per timestamp,
- a bus with no `PVUnit` does not need a PV-profile row and is treated as zero generation,
- every configured PV bus must have exactly one PV row per timestamp,
- duplicate `(timestamp, bus_id)` rows are errors,
- missing required numeric values are errors, not silently filled by the loader.

Any interpolation/filling belongs to earlier data preparation and must be documented there.

## 5.4 Timestamp/time-step contract

- timestamps must be parseable ISO-8601 values and sorted after import,
- load/PV profiles must align to the same timestamp set before simulation,
- the baseline time step is hourly,
- `dt_hours` is calculated/validated from consecutive timestamps,
- irregular time steps are rejected for the initial implementation rather than guessed.

Timezone conversion, if needed, belongs to data preparation; the simulation interface receives one consistent time basis.

## 5.5 Standardized in-memory data

**Proposed design decision:** pandas may be used internally by the loader, but downstream modules do not receive a DataFrame.

```text
ProfileData
- timestamps: ordered sequence[datetime]
- load_p_kw: dict[bus_id, array[float]]
- load_q_kvar: dict[bus_id, array[float]]
- pv_p_kw: dict[bus_id, array[float]]
- pv_q_kvar: dict[bus_id, array[float]]
- dt_hours: float
```

For one time index:

```text
ProfileSlice
- timestamp
- p_load_kw: dict[bus_id, float]
- q_load_kvar: dict[bus_id, float]
- p_pv_kw: dict[bus_id, float]
- q_pv_kvar: dict[bus_id, float]
```

`data_loader.py` owns `ProfileSlice`; `simulation.py` converts it into an FBS `OperatingPoint` after adding optional BESS injection.

## 5.6 Public interface

```text
load_profiles(
    load_csv_path,
    pv_csv_path,
    network: NetworkModel
) -> ProfileData

profile_at(
    profiles: ProfileData,
    index: int
) -> ProfileSlice
```

This prevents `data_loader.py` from importing/depending on FBS internals.

---

# 6. BESS model design specification

## 6.1 Existing baseline requirements

Preserve:

- installation bus/location `B`,
- energy capacity `E` [kWh],
- power rating `P` [kW],
- SOC state,
- SOC limits initially 10%–90%,
- charge/discharge efficiency,
- no simultaneous charge/discharge,
- hourly operation initially.

Power and energy capacity remain distinct.

## 6.2 Proposed data structures

### `BESSConfig`

| Field | Unit | Required | Meaning |
|---|---:|---|---|
| `bus_id` | — | yes | Connection bus |
| `energy_capacity_kwh` | kWh | yes | Nominal energy capacity |
| `power_rating_kw` | kW | yes | Nominal bidirectional power rating |
| `soc_min` | fraction | yes | Minimum SOC |
| `soc_max` | fraction | yes | Maximum SOC |
| `soc_initial` | fraction | yes | Starting SOC |
| `eta_charge` | fraction | yes | Charging efficiency |
| `eta_discharge` | fraction | yes | Discharging efficiency |
| `max_charge_kw` | kW | optional | Default = `power_rating_kw` |
| `max_discharge_kw` | kW | optional | Default = `power_rating_kw` |

### Efficiency design gate

The existing baseline mentions approximately 85% efficiency but does not unambiguously establish whether it is directional or round-trip. Therefore:

- the software structure uses separate `eta_charge` and `eta_discharge`,
- the implementer must **not** silently assign 0.85 to both directions,
- numeric values must come from an explicitly documented case configuration/team decision/source.

This preserves the requirement without inventing an unsupported interpretation.

### `BESSState`

| Field | Unit |
|---|---:|
| `energy_kwh` | kWh |
| `soc` | fraction |

Invariant:

```text
energy_kwh = soc * energy_capacity_kwh
```

### `BESSStepResult`

| Field | Unit |
|---|---:|
| `actual_power_kw` | kW |
| `energy_before_kwh` | kWh |
| `energy_after_kwh` | kWh |
| `soc_before` | fraction |
| `soc_after` | fraction |
| `limited` | bool |
| `limit_reason` | enum/string |

## 6.3 Power sign convention

Same convention everywhere:

- `requested_power_kw > 0` = discharge/injection to network,
- `requested_power_kw < 0` = charge/absorption from network.

**Proposed design decision:** initial BESS is active-power-only (`q_bess_kvar = 0`) unless a later approved design extends it.

## 6.4 One-step algorithm/limit contract

Public call:

```text
step_bess(
    config: BESSConfig,
    state: BESSState,
    requested_power_kw: float,
    dt_hours: float
) -> BESSStepResult
```

The implementation must first validate the configuration/state, then clip the requested action to physical power/SOC limits.

### Discharge request (`requested_power_kw > 0`)

Let:

```text
E_min = soc_min * energy_capacity_kwh
P_soc_limit = max(0, (E_before - E_min) * eta_discharge / dt_hours)
```

Then:

```text
P_dis = min(requested_power_kw, max_discharge_kw, power_rating_kw, P_soc_limit)
E_after = E_before - P_dis * dt_hours / eta_discharge
actual_power_kw = +P_dis
```

### Charge request (`requested_power_kw < 0`)

Let `P_charge_request = abs(requested_power_kw)` and:

```text
E_max_allowed = soc_max * energy_capacity_kwh
P_soc_limit = max(0, (E_max_allowed - E_before) / (eta_charge * dt_hours))
```

Then:

```text
P_ch = min(P_charge_request, max_charge_kw, power_rating_kw, P_soc_limit)
E_after = E_before + eta_charge * P_ch * dt_hours
actual_power_kw = -P_ch
```

Zero request leaves the state unchanged.

The result reports whether/why clipping occurred. Numerical guard logic may be used for floating-point tolerance, but it must not intentionally violate SOC limits.

## 6.5 BESS-network interaction

`bess.py` never edits voltage/current directly.

```text
requested BESS power
       ↓
    bess.py
       ↓
actual feasible p_bess_kw + new BESSState
       ↓
  simulation.py adds injection at BESS bus
       ↓
   OperatingPoint
       ↓
      fbs.py
```

This allows BESS logic to be tested without FBS.

---

# 7. `simulation.py` orchestration contract

**Proposed design decision:** one orchestration layer owns the sequence between profiles, BESS and FBS. UI/optimizer code must not call private FBS/BESS helpers directly.

## 7.1 Single-step interface

```text
simulate_step(
    network: NetworkModel,
    profile_slice: ProfileSlice,
    fbs_config: FBSConfig,
    bess_config: BESSConfig | None = None,
    bess_state: BESSState | None = None,
    bess_request_kw: float = 0.0
) -> SimulationStepResult
```

Required sequence:

1. convert `ProfileSlice` into bus-indexed load/PV values,
2. if BESS exists, call `step_bess()`,
3. insert actual BESS injection at `BESSConfig.bus_id`,
4. create one `OperatingPoint`,
5. call `run_fbs()`,
6. return both power-flow and BESS-state results.

## 7.2 Time-series interface

```text
simulate_timeseries(
    network: NetworkModel,
    profiles: ProfileData,
    simulation_config: SimulationConfig,
    bess_config: BESSConfig | None = None,
    dispatch_policy = None
) -> TimeSeriesSimulationResult
```

The first FBS task does **not** implement this loop; Task 17 later adds it using the same one-step contracts.

---

# 8. Metrics and future modules

## 8.1 `metrics.py`

Public concept:

```text
evaluate_results(
    simulation_result,
    economic_config: EconomicConfig
) -> PerformanceMetrics
```

Existing metric families remain:

- cost,
- renewable curtailment,
- load shedding,
- voltage/technical violations,
- losses,
- percentage improvement.

Economic coefficients remain inputs; do not hard-code unverified cost values in the public interface.

## 8.2 `uncertainty.py` placeholder — do not implement before V5

Existing baseline: ARIMA + Monte Carlo, 100 generated scenarios, 45 retained scenarios.

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

Scenarios reuse `ProfileData`; they do not introduce a second simulation format.

The exact 15-best/15-worst/15-random ranking rule is documented at the high-level design layer (`TERM2_SHADOW_DESIGN.md` SD-8) and must be fixed there before selection code diverges.

## 8.3 `optimizer.py` placeholder — do not implement before V4

Existing baseline: decision vector `[B,P,E]`, starting GWO/WSM approach.

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

The optimizer evaluates candidates through the public simulation/evaluator interface. It must not contain its own copy of FBS or BESS equations.

## 8.4 `results.py` / `ui.py`

`results.py` may format/export standardized results. `ui.py` may collect user choices and call public backend interfaces. Neither module owns engineering equations.

---

# 9. Module input/output specification

## 9.1 Main I/O matrix

| Module | Required inputs | Required outputs | Optional/debug outputs |
|---|---|---|---|
| `network_model.py` | buses, lines, loads, PV units, base values | validated `NetworkModel`, `RadialOrder`/lookups | validation diagnostics |
| `network_cases.py` | named case parameters/data | constructed `NetworkModel` | source/case metadata |
| `data_loader.py` | load CSV, PV CSV, `NetworkModel` | `ProfileData`, `ProfileSlice` | import-quality summary |
| `bess.py` | config, state, requested kW, `dt_hours` | `BESSStepResult` | clipping diagnostics |
| `fbs.py` | `NetworkModel`, `OperatingPoint`, `FBSConfig` | `PowerFlowResult` | iteration history/intermediates |
| `simulation.py` | network, profile slice/data, configs, optional BESS | step/time-series result | per-step diagnostics |
| `metrics.py` | simulation result + economic inputs | `PerformanceMetrics` | metric component breakdown |
| `uncertainty.py` | historical/prepared profiles + config | `ScenarioSet` | scenario statistics |
| `optimizer.py` | network, profiles/scenarios, bounds/config, evaluator | `OptimizationResult` | population/convergence details |
| `results.py` | standardized results | tables/plots/export files | extra diagnostics |
| `ui.py` | user files/settings/selections | calls backend + displays results | UI logs |

## 9.2 Shared units

| Quantity | Standard module-boundary unit |
|---|---:|
| Active power | kW |
| Reactive power | kVAR |
| Apparent/base power | kVA |
| Energy | kWh |
| Nominal/base voltage | kV line-line |
| Solved voltage | p.u. required; kV may be derived |
| Branch R/X | ohm/phase |
| Current | A |
| Time step | hours |
| SOC | fraction 0–1 internally |
| Public voltage angle | degrees |

## 9.3 Shared power signs

- load P/Q: positive consumption,
- PV P/Q: positive generation,
- BESS P: positive discharge/injection, negative charge/absorption,
- slack P: positive when grid supplies the modeled network.

## 9.4 Required vs optional rule

Downstream code may depend only on fields marked **required** in this specification. Debug/optional fields may be added without forcing downstream changes.

If a required field/interface must change, update the design specification before changing multiple implementations.

---

# 10. Initial 5-bus implementation contract

The 5-bus case is a development/verification case, not a different architecture.

It must:

- use the same `Bus/Line/Load/PVUnit/NetworkModel` structures,
- be built outside `fbs.py`, preferably by `network_cases.py`,
- have one slack bus,
- be radial,
- define base quantities once in `NetworkModel`,
- pass one `OperatingPoint` to `run_fbs()`,
- contain no 5-bus-specific equations inside the solver.

The later IEEE 33-bus case must be usable by supplying a larger `NetworkModel`, not by rewriting the FBS algorithm.

---

# 11. Proposed design decisions registry

The following are **proposed design decisions**, not added project requirements:

1. Python dataclasses for public entity/config/result objects.
2. `network_cases.py` separates case data from reusable network representation.
3. Long-format UTF-8 CSV for load/PV profiles.
4. Absolute bus-level kW/kVAR at the simulation boundary.
5. `ProfileSlice` owned by the loader; `OperatingPoint` owned by FBS; `simulation.py` converts between them.
6. BESS positive active power = discharge/injection.
7. Initial PV and BESS reactive injection = 0 unless later design extends it.
8. Engineering-unit public boundaries with centralized per-unit conversion in FBS.
9. FBS flat start at the slack setpoint.
10. FBS convergence by max complex bus-voltage change, default `1e-6 pu`, max 100 iterations.
11. Standardized result dataclasses instead of anonymous tuples.
12. Central `simulation.py` orchestration layer.
13. Future scenario objects reuse `ProfileData`.
14. Future optimizer calls only public simulation/evaluator interfaces.
15. Missing reactive-load profile values use the already documented base-P/Q scaling rule rather than an implementation-local assumption.

If the team rejects/replaces one of these choices, record the chosen replacement in the design documentation before implementation diverges.

---

# 12. Implementation task handoff map

The live Gantt remains the scheduling authority. Implementation owners should use this design mapping rather than redefining design decisions in task work.

| Current task area | Design to implement |
|---|---|
| Task 10 code structure | Sections 2.2–2.5 |
| Task 11 I/O structures/fixtures | Sections 2.5, 3, 4, 5, 6, 9 |
| Task 12 5-bus model | Sections 3 and 10 |
| Task 13 one-step FBS | Section 4 |
| Task 16 profile import | Section 5 + shadow-design SD-4 Q fallback |
| Task 17 time-series loop | Section 7 |
| Tasks 20–23 BESS | Section 6 + Section 7 interaction |
| Tasks 32–35 metrics/optimizer integration | Sections 8–9 + shadow-design SD-7 |
| Tasks 42–49 uncertainty | Section 8.2 + shadow-design SD-8 |
| Tasks 51–55 UI/results | Sections 2, 8.4 and 9 |

Implementation tasks should say **implement/test/debug the documented contract**, not “decide,” “define,” or “choose” architecture/file-format/interface behavior.

---

# 13. Implementation handoff checklist

Before an implementation owner begins a module, they should be able to answer from this design:

- What file/module owns this behavior?
- What is the module responsible for and explicitly not responsible for?
- Which data object/file does it receive?
- Which fields and units are required?
- What sign convention applies?
- What public function/interface must be exposed?
- What required output fields must be returned?
- Which outputs are debug-only?
- Which statements are existing baseline requirements versus proposed design decisions?
- How can the module be tested independently?

If any of these cannot be answered, treat it as a **design gap** and update the design before coding around it.
