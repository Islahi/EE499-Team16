# Term 2 Technical Design Baseline

**Status:** Finalized high-level design reference  
**Purpose:** Preserve the project/Term 1 technical baseline and map it to the detailed software design and current implementation tasks.  
**Detailed software contracts:** `TERM2_SOFTWARE_DESIGN_SPEC.md`  
**Schedule source of truth:** live Task Register / Gantt

## 1. Design hierarchy

The project now uses three levels:

```text
Official project requirements + Term 1 baseline
                    ↓
        This technical design baseline
                    ↓
      TERM2_SOFTWARE_DESIGN_SPEC.md
                    ↓
         Current Gantt implementation tasks
                    ↓
        Coding + testing + debugging
                    ↓
      Chapter 4 evidence / Chapter 5 validation
```

This file defines the **technical baseline**. `TERM2_SOFTWARE_DESIGN_SPEC.md` defines exact software architecture, module responsibilities, data structures, file formats, interfaces, units and required outputs so implementation owners do not design incompatible local solutions.

### Design vs implementation rule

**Design work includes:** mathematical model, architecture, interfaces, data flow, algorithms, data structures, file formats, units, sign conventions, numerical configuration and validation plan.

**Implementation work includes:** coding the defined design, running it, debugging, unit/integration testing, collecting results and validating behavior.

If implementation reveals that a design choice must change, update the design documentation and record the reason before allowing different modules to diverge.

---

# SD-1 — Product Scope

## Existing baseline

The Term 2 product is a **software-based decision-support tool for BESS planning in renewable-integrated radial distribution networks**.

The final program should support:

1. loading/defining a radial network,
2. loading time-series load data,
3. loading PV generation / solar-resource data,
4. baseline simulation without BESS,
5. simulation with BESS,
6. manual comparison of BESS locations/sizes,
7. automatic BESS planning using decision vector `[B,P,E]`,
8. evaluation under uncertain load/PV conditions,
9. baseline-vs-BESS comparison,
10. technical/economic result display/export.

Where:

- `B` = installation bus,
- `P` = BESS power rating,
- `E` = BESS energy capacity.

## Network scope

- use a small **5-bus radial system** for development/debugging,
- later run the same framework on the **IEEE 33-bus radial distribution system**,
- the 5-bus system is not the final product limit.

## Renewable source

Solar PV is the implemented renewable source for the case study.

## Initial scope limits

Unless later required/approved:

- one BESS installation at a time,
- stationary BESS,
- radial distribution systems,
- grid-connected operation,
- no real-time physical grid control,
- no detailed thermal/electrochemical battery model,
- no detailed degradation model initially,
- no transmission-system optimization.

### Implementation mapping

- Tasks 51–57 integrate the decision-support software.
- Task 60 demonstrates scalability on IEEE 33-bus.

---

# SD-2 — User Workflow and Software Requirements

## Baseline workflow

```text
Start
  ↓
Load/create network
  ↓
Load load profile
  ↓
Load PV profile
  ↓
Validate inputs
  ↓
Run baseline simulation
  ↓
Inspect network results
  ↓
Configure BESS planning bounds
  ↓
Run deterministic optimization
  ↓
Run uncertainty-aware optimization
  ↓
View recommended BESS
  ↓
Compare baseline vs BESS
  ↓
Save/export results
```

## Required input families

- network topology/equipment/base values,
- time-series load and PV,
- BESS planning bounds,
- economic coefficients used by the retained objective.

## Required output families

- bus voltage,
- branch current/loading,
- losses,
- source/grid power,
- power balance,
- BESS SOC and power,
- selected `[B,P,E]`,
- cost,
- curtailment,
- load shedding,
- voltage violations,
- improvements relative to baseline,
- computation/convergence information where useful.

The exact software objects, fields, file formats and units are defined in `TERM2_SOFTWARE_DESIGN_SPEC.md`.

### Implementation mapping

- Task 10 creates the predefined module skeleton.
- Task 11 implements the predefined I/O structures/sample fixtures.
- Tasks 51–57 integrate the final workflow/UI.
- Task 62 checks common software failure cases.

---

# SD-3 — Software Architecture

## Architecture decision

The detailed architecture is now defined **before implementation** in `TERM2_SOFTWARE_DESIGN_SPEC.md`.

Main modules:

- `network_model.py` — static network representation and validation,
- `data_loader.py` — standardized load/PV import,
- `fbs.py` — one-step radial Forward/Backward Sweep,
- `bess.py` — BESS configuration/state/limits,
- `simulation.py` — orchestration layer,
- `metrics.py` — performance/economic metrics,
- `uncertainty.py` — future ARIMA/Monte Carlo scenario interface,
- `optimizer.py` — future GWO/WSM optimization interface,
- `results.py` — result tables/plots/export,
- `ui.py` — final user interface.

## Independence rule

Each module should be independently testable and should interact through documented public data objects/functions rather than shared mutable globals.

The optimizer must not duplicate FBS/BESS physics. The UI must not contain engineering calculations. FBS must not read CSV files directly.

### Implementation mapping

- Tasks 10–11 create the code/interface skeleton from the design.
- Tasks 12–50 implement backend modules.
- Tasks 51–57 integrate them.

---

# SD-4 — Interfaces, Data Flow and Units

Detailed public interfaces are defined in `TERM2_SOFTWARE_DESIGN_SPEC.md`.

## Deterministic data flow

```text
NetworkModel + ProfileData
          ↓
     OperatingPoint
          ↓
optional BESS step/injection
          ↓
        fbs.py
          ↓
   PowerFlowResult
          ↓
      metrics.py
          ↓
  evaluator / optimizer
```

## Uncertainty data flow

```text
Historical / prepared profiles
            ↓
      ARIMA / error model
            ↓
 Monte Carlo ScenarioSet
            ↓
      scenario selection
            ↓
 same simulation/evaluator path
            ↓
       optimizer / WSM
```

## Standard units at module boundaries

- active power: kW,
- reactive power: kVAR,
- energy: kWh,
- input/base voltage: kV line-line,
- solved voltage: p.u.,
- branch impedance: ohm/phase,
- current: A,
- SOC: fraction 0–1 internally,
- time step: hours.

## Standard power signs

- load = positive consumption,
- PV = positive generation,
- BESS `P > 0` = discharge/injection,
- BESS `P < 0` = charge/consumption.

### Implementation mapping

- Task 11 implements these data contracts.
- Task 16 implements the predefined profile loader.
- Tasks 20–23 implement the predefined BESS interface.
- Tasks 32–35 connect metrics/optimizer to the same public simulation interface.

---

# SD-5 — Network and FBS Baseline

## Existing network assumptions

- balanced radial distribution network,
- one grid/slack source,
- PQ loads,
- time-varying PV active-power injection,
- hourly resolution initially.

For IEEE 33-bus, bus 1 is the source/slack unless the benchmark data requires otherwise.

## Voltage criterion

`0.95 <= V_i <= 1.05 pu`

## Solver baseline

The **Forward-Backward Sweep (FBS)** method remains the initial radial power-flow solver.

A trusted external solver may be used as a verification reference but should not silently replace FBS.

## Software design contract

`TERM2_SOFTWARE_DESIGN_SPEC.md` now specifies before coding:

- `Bus`, `Line`, `Load`, `PVUnit`, `NetworkModel`,
- network validation/radial ordering,
- engineering-unit/base-value convention,
- `OperatingPoint`,
- `FBSConfig`,
- `PowerFlowResult`,
- FBS sign conventions,
- required/optional outputs,
- one-step public `run_fbs()` interface,
- proposed convergence tolerance/defaults.

These are no longer decisions left to Tasks 12–13.

### Implementation mapping

- Task 12 builds the 5-bus case using the documented `NetworkModel`.
- Task 13 implements `fbs.py` to the documented contract.
- Task 14 verifies it.
- Task 15 presents required outputs.
- Task 16 implements profile import.
- Task 17 adds the hourly orchestration loop.
- Task 18 verifies V1.
- Task 60 later applies the same design to IEEE 33-bus.

---

# SD-6 — BESS Baseline

## Existing BESS requirements/baseline

Planning variables remain distinct:

- `E_max` — energy capacity [kWh],
- `P_max` — power rating [kW],
- `B` — installation bus.

State of charge:

`SOC_t = E_t / E_max`

Charging:

`E_(t+1) = E_t + eta_c * P_ch,t * Delta_t`

Discharging:

`E_(t+1) = E_t - P_dis,t * Delta_t / eta_d`

Initial SOC constraint retained from Term 1:

`0.10 <= SOC_t <= 0.90`

Power constraints:

`0 <= P_ch,t <= P_max`

`0 <= P_dis,t <= P_max`

Other baseline assumptions:

- no simultaneous charging/discharging,
- fixed efficiency initially,
- Term 1 efficiency value is a starting assumption until verified/refined,
- initial SOC may start at 50% where no case-specific value is required,
- cyclic final SOC may be retained where the study requires it,
- detailed degradation is initially outside scope and must be stated as a limitation if omitted.

## Software design contract

`TERM2_SOFTWARE_DESIGN_SPEC.md` now defines before coding:

- `BESSConfig`,
- `BESSState`,
- `BESSStepResult`,
- common BESS/network sign convention,
- `step_bess()` interface,
- limit handling,
- separation between BESS state logic and FBS,
- BESS injection path through `simulation.py`.

### Implementation mapping

- Tasks 20–23 implement the documented BESS contract.
- Tasks 24–25 run/verify it over time.
- Tasks 27–30 compare BESS location and P/E choices manually.

---

# SD-7 — Objective and Optimization Baseline

## Existing baseline

Decision vector:

`x = [B,P,E]`

Objective components:

- economic cost,
- renewable curtailment,
- load shedding.

Starting Term 1 WSM priority:

`J = 0.50*C + 0.25*E_curt + 0.25*E_shed`

Main constraints:

- voltage limits,
- SOC limits,
- BESS P/E bounds,
- allowed buses,
- network feasibility.

GWO remains the starting optimizer. Limited exhaustive search on the small system is used as an independent verification reference.

## Predefined software interface

`TERM2_SOFTWARE_DESIGN_SPEC.md` reserves:

- `BESSCandidate`,
- `OptimizationResult`,
- optimizer public interface,
- rule that optimizer calls simulation/evaluator instead of duplicating network/BESS physics.

## Remaining design gate before V4

The Term 1 material does not fully determine every implementation detail of objective normalization. Therefore:

- Task 33 must **not silently invent a normalization rule in code**.
- Before/at the start of V4, the team must confirm the normalization method and update the design specification.

This is a design decision, not an implementation-owner choice.

### Implementation mapping

- Task 32 implements metrics using the defined interface.
- Task 33 implements the confirmed WSM formula/normalization.
- Tasks 34–35 implement the documented candidate/evaluator connection.
- Tasks 36–39 run and verify GWO.

---

# SD-8 — Uncertainty Baseline

## Existing Term 1 workflow

```text
Historical load/PV
      ↓
ARIMA
      ↓
Monte Carlo generation
      ↓
100 scenarios
      ↓
15 best + 15 worst + 15 random
      ↓
45 retained scenarios
      ↓
GWO / simulation
      ↓
WSM result
```

ARIMA should be checked with RMSE/MAPE. Generated scenarios should be checked against historical behavior and physical limits.

## Predefined software interface

`TERM2_SOFTWARE_DESIGN_SPEC.md` reserves `Scenario` and `ScenarioSet` so future scenarios reuse the same `ProfileData` and simulation pipeline.

## Remaining design gate before scenario selection

The baseline states **15 best + 15 worst + 15 random**, but the ranking/classification rule must be explicit before Task 45. If the Term 1 submission does not uniquely define the metric, the team must confirm one and record it in the design specification before implementation.

Task 45 should apply a documented rule, not invent one during coding.

### Implementation mapping

- Task 42 implements ARIMA behind the uncertainty interface.
- Task 43 verifies forecast accuracy.
- Task 44 generates `ScenarioSet`.
- Task 45 applies the confirmed selection rule.
- Task 46 verifies scenario realism.
- Tasks 47–49 connect scenarios to the normal optimization/simulation pipeline.

---

# SD-9 — Verification and Validation Baseline

Use two evidence levels.

## A. Implementation verification / trials

Question answered: **Did we implement the defined design correctly?**

Examples:

- network-model validation,
- FBS manual/trusted-reference comparison,
- power-balance checks,
- SOC hand calculations,
- BESS limit tests,
- manual BESS location/size trials,
- GWO vs exhaustive search,
- GWO population/iteration tests,
- ARIMA RMSE/MAPE,
- scenario realism,
- software input/failure tests.

This evidence primarily supports Chapter 4.

## B. Formal validation experiments

Question answered: **Does the implemented final product satisfy the Term 1 design specifications?**

Each formal Chapter 5 experiment should contain:

1. objective,
2. relevant background,
3. detailed work plan/steps,
4. tools,
5. organized data/figures/tables,
6. analysis/conclusion.

Final requirement evidence should be summarized as:

`Requirement -> Target -> Experiment/direct check -> Measured result -> Evidence -> Status`

with status:

- Met,
- Partially Met,
- Not Met.

Do not alter a requirement merely to make it pass.

---

# Current Gantt mapping summary

| Technical section | Main current tasks |
|---|---|
| SD-1 Product scope | 51–57, 60 |
| SD-2 Workflow/requirements | 10–11, 51–57, 62 |
| SD-3 Architecture | 10–11, 12–50, 51–57 |
| SD-4 Interfaces/data flow | 11, 16, 20–23, 32–35, 42–45, 52–54 |
| SD-5 Network/FBS | 12–19, 60 |
| SD-6 BESS | 20–31 |
| SD-7 Objective/GWO | 32–40 |
| SD-8 ARIMA/MC/scenarios | 42–50 |
| SD-9 Verification/validation | verification tasks throughout + 41, 58–61 |

---

# Change-control rule

The default sequence is:

```text
Existing baseline
      ↓
Document detailed design
      ↓
Implement the documented design
      ↓
Test / verify
      ↓
Keep it if it works
      ↓
Change only with evidence / team-advisor decision
      ↓
Update design documentation
      ↓
Document implementation change in Chapter 4
```

The detailed software contracts belong in `TERM2_SOFTWARE_DESIGN_SPEC.md`; task numbers/dates belong in the live Task Register/Gantt.
