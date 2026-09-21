# Term 2 Shadow Design — Initial Implementation Baseline

**Status:** Working / provisional  
**Purpose:** Initial technical baseline for Tasks 9–17 and V1–V6 implementation  
**Important:** This document does **not** revise submitted Chapters 1–3. It starts from the **Term 1 baseline design** and fills missing implementation details such as software architecture, interfaces, control flow, and validation. Term 1 design choices remain the default implementation choices unless implementation, validation, unavailable data, or advisor feedback provides a clear reason to change them. Any implementation-driven change must be documented and justified in Chapter 4.

## 1. Why this document exists

Chapters 1–3 from Term 1 are treated as frozen. The team still needs enough technical definition to begin implementation without repeating a full design phase.

Therefore, Tasks 9–17 are treated as a **shadow design**:

- preserve the Term 1 baseline as the starting point,
- fill design details that were unclear or missing in Term 1,
- define the minimum technical information needed to start coding,
- implement the system incrementally,
- validate the Term 1 choices during implementation,
- change a baseline choice only when there is a clear technical/advisor reason,
- record and justify any important change in Chapter 4,
- validate the final implementation in Chapter 5.

## Baseline-preservation rule

The default sequence is:

```text
Term 1 baseline
    ↓
Implement as written
    ↓
Validate / test
    ↓
Keep it if it works
    ↓
Change only if evidence shows a need
```

The shadow design must not silently replace a Term 1 method simply because another method may appear better before implementation.

The implementation path is:

1. **V1 — Network simulator**
2. **V2 — Fixed BESS**
3. **V3 — Manual sizing/placement comparison**
4. **V4 — Automatic optimization**
5. **V5 — Uncertainty-aware optimization**
6. **V6 — Final decision-support software**

---

# Task 9 — Confirm Term 2 Product Scope and Minimum Capabilities

## Initial product definition

The Term 2 product is a **software-based decision-support tool for BESS planning in renewable-integrated radial distribution networks**.

The program should eventually allow a user to:

1. define or load a radial distribution network,
2. load time-series electrical demand,
3. load PV generation or solar-resource data,
4. simulate the network without BESS,
5. add and simulate a BESS,
6. evaluate different BESS locations and sizes,
7. automatically determine a suitable BESS:
   [
   x = [B, P, E]
   ]
8. evaluate the recommended BESS under uncertain load/PV conditions,
9. compare the system before and after BESS installation,
10. display technical and economic results.

Where:

- (B) = BESS bus/location,
- (P) = BESS power rating,
- (E) = BESS energy capacity.

## Initial network scope

- Start with an approximately **5-bus radial test system** for debugging and validation.
- Later test the same framework on the **IEEE 33-bus radial distribution system**.

The 5-bus system is an implementation and validation case, not the final product limit.

## Renewable source

- Implement **solar PV** as the renewable source for the Term 2 case study.
- The architecture may later support other generation profiles.
- Wind is not required unless explicitly requested by the advisors.

## Initial scope exclusions

Unless later required:

- one BESS installation at a time,
- stationary BESS,
- radial distribution systems,
- grid-connected operation,
- no real-time physical grid control,
- no detailed thermal/electrochemical battery model,
- no detailed battery degradation model initially,
- no transmission-system optimization.

---

# Task 10 — Define Software Requirements and User Workflow

## Initial user workflow

```text
Start
  ↓
Create/load network
  ↓
Load load profile
  ↓
Load PV profile
  ↓
Check input data
  ↓
Run baseline simulation
  ↓
Inspect network results
  ↓
Configure BESS planning bounds
  ↓
Run deterministic optimization
  ↓
Optional: run uncertainty-aware optimization
  ↓
View recommended BESS
  ↓
Compare baseline vs BESS
  ↓
Save/export results
```

## Required inputs

### Network

- buses,
- lines,
- line parameters,
- loads,
- slack/source bus,
- base values.

### Time series

- timestamp,
- load profile,
- PV profile or source data used to calculate PV generation.

### BESS planning bounds

Eventually define:

- allowed candidate buses,
- (P_{min}, P_{max}),
- (E_{min}, E_{max}).

### Economic inputs

Eventually include, if retained by the final objective:

- battery energy cost,
- battery power-conversion cost,
- grid-energy price,
- fixed O&M,
- load-shedding penalty,
- curtailment penalty.

## Required outputs

### Baseline/network outputs

- bus voltage,
- line loading/current,
- system losses,
- grid import/export,
- power balance.

### BESS outputs

- SOC,
- charging/discharging power.

### Optimization outputs

- selected bus (B^*),
- selected power (P^*),
- selected energy (E^*).

### Performance outputs

- cost,
- renewable curtailment,
- load shedding,
- voltage violations,
- losses,
- percentage improvement relative to baseline,
- computation time where useful.

## Initial software error handling

The application should eventually handle:

- missing data,
- invalid files,
- inconsistent timestamps,
- invalid units,
- impossible BESS bounds,
- disconnected networks,
- failed power flow,
- optimization non-convergence.

---

# Task 11 — Design Initial Software Architecture and Module Boundaries

## Shadow architecture

```text
                      ┌────────────────┐
                      │ User Interface │
                      └───────┬────────┘
                              │
                     ┌────────▼────────┐
                     │  Data Manager   │
                     └────────┬────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
      ┌───────▼────────┐             ┌────────▼─────────┐
      │ Network Model  │             │ Uncertainty      │
      │ + Power Flow   │             │ Module           │
      └───────┬────────┘             └────────┬─────────┘
              │                               │
              └───────────────┬───────────────┘
                              │
                     ┌────────▼────────┐
                     │   BESS Model    │
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │   Evaluator     │
                     │ cost/technical  │
                     │ metrics         │
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │   Optimizer     │
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │ Results /       │
                     │ Validation      │
                     └─────────────────┘
```

The exact code structure may change during implementation.

## Initial responsibilities

### Data Manager

- read files,
- check timestamps,
- convert/check units,
- resample and align profiles,
- provide clean data to the simulation.

### Network Model / Power Flow

- represent buses, lines, loads, PV and grid source,
- run power flow,
- return electrical network results.

### BESS Model

- represent power and energy ratings,
- track SOC/stored energy,
- enforce charge/discharge and efficiency limits,
- inject/absorb power at the selected bus.

### Evaluator

Calculate:

- cost,
- losses,
- voltage violations,
- curtailment,
- load shedding,
- objective/fitness value.

### Optimizer

- choose (B,P,E),
- request candidate evaluations from the simulation/evaluator,
- search for an acceptable/best design.

The optimizer should not duplicate the electrical physics.

### Uncertainty Module

- forecasting or error modelling,
- Monte Carlo scenario generation,
- scenario selection/reduction,
- scenario probabilities if used.

### User Interface

- collect user inputs,
- start simulation/optimization,
- show errors/progress,
- display results.

### Results / Validation

- plots,
- tables,
- baseline-vs-BESS comparisons,
- validation/benchmark outputs,
- exportable results.

---

# Task 12 — Define Initial Module Interfaces and Data Flow

## Main deterministic data flow

```text
Network data ─┐
              │
Load data ────┼──> Data Manager
              │
PV data ──────┘
                    ↓
              Prepared Inputs
                    ↓
             Network Simulator
                    ↓
               + BESS Model
                    ↓
             Technical Results
                    ↓
                Evaluator
                    ↓
               Fitness/Metrics
                    ↓
                Optimizer
                    ↓
             Recommended BESS
```

## Uncertainty data flow

```text
Historical load/PV
        ↓
Forecast / Error Model
        ↓
Scenario Generator
        ↓
Representative Scenario Set
        ↓
Simulation + Evaluator
        ↓
Uncertainty-aware Optimizer
```

## Initial conceptual data structures

### NetworkData

- buses,
- lines,
- loads,
- slack/source,
- PV locations.

### TimeSeriesData

- timestamp,
- load,
- PV.

### BESSConfig

- bus,
- power rating,
- energy capacity,
- initial SOC,
- efficiency,
- SOC minimum,
- SOC maximum.

### SimulationResult

- bus voltages,
- line loading,
- losses,
- grid power,
- BESS power,
- BESS SOC,
- curtailment,
- load shedding.

## Initial evaluation interface

Conceptually:

[
evaluate(B,P,E,scenario)
]

returns metrics such as:

[
[J, C, E_{curt}, E_{shed}, V_{viol}, Loss]
]

The final Python function signatures and classes can change during implementation.

---

# Task 13 — Initial Network and Power-Flow Assumptions

## Network

- balanced radial distribution network,
- one grid/slack source,
- IEEE 33-bus bus 1 used as the source/slack unless the benchmark implementation requires otherwise.

## Loads

- initial representation: PQ loads,
- active/reactive demand may vary with time-series profiles.

## PV

- time-varying active-power injection,
- reactive-power operation can initially be simplified unless later required.

## Voltage criterion

Initial operating limit:

[
0.95 leq V_i leq 1.05 	ext{pu}
]

## Solver

The **Forward-Backward Sweep (FBS)** method selected in the Term 1 baseline remains the initial power-flow method to implement.

Implementation should therefore begin by reproducing the Term 1 FBS-based radial power-flow approach.

A trusted external solver such as pandapower may still be used as a **validation/reference tool** to compare results, but it should not replace FBS by default.

If FBS later creates a verified technical problem, cannot support a required feature, or the advisors request a different solver, the change should be documented and justified in Chapter 4.

## Time step

Initial common resolution:

[
Delta t = 1 	ext{hour}
]

This is provisional and may be revised based on the selected datasets.

## Infeasible cases

If a candidate causes:

- power-flow non-convergence,
- invalid/disconnected operation,
- unacceptable technical violations,

it should be marked infeasible and handled through constraints or penalties during optimization.

Exact penalty handling will be finalized during V4.

---

# Task 14 — Initial BESS Mathematical Model

## Planning variables

- (E_{max}): energy capacity [kWh],
- (P_{max}): power rating [kW],
- (B): installation bus.

Power and energy capacity must remain distinct.

## State variable

Use stored energy (E_t) and/or:

[
SOC_t = rac{E_t}{E_{max}}
]

## Initial energy update

Charging:

[
E_{t+1}=E_t+eta_c P_{ch,t}Delta t
]

Discharging:

[
E_{t+1}=E_t-rac{P_{dis,t}Delta t}{eta_d}
]

## Initial SOC constraint

Retain the Term 1 baseline initially:

[
0.10 leq SOC_t leq 0.90
]

The exact range can later be replaced by a selected BESS/datasheet requirement.

## Power constraints

[
0 leq P_{ch,t} leq P_{max}
]

[
0 leq P_{dis,t} leq P_{max}
]

## Operating assumptions

- charging and discharging cannot occur simultaneously,
- use a fixed BESS efficiency initially,
- the Term 1 value of approximately 85% is a starting assumption, not a final immutable value,
- initial SOC can start at 50% unless the case study requires another value,
- retain a cyclic end condition initially:
  [
  E(0)=E(T)
  ]
  where appropriate.

## Degradation

Detailed degradation is initially **out of scope** unless required by the advisors.

If omitted, this must be listed as a model limitation rather than implied to be included.

---

# Task 15 — Initial Objective Function, Constraints, and Metrics

## Decision vector

[
x=[B,P,E]
]

with:

- (B) restricted to allowed candidate buses,
- (P) restricted to selected bounds,
- (E) restricted to selected bounds.

## Initial objective components

Retain the three main Term 1 concerns:

- economic cost,
- renewable curtailment,
- load shedding.

Use:

[
min J(x)
]

where (J) aggregates appropriately normalized/weighted versions of:

[
C(x),quad E_{curt}(x),quad E_{shed}(x)
]

The initial weighting follows the Term 1 baseline:

[
J = 0.50,C + 0.25,E_{curt} + 0.25,E_{shed}
]

or the equivalent Term 1 Weighted Sum Method implementation.

These weights are the **starting implementation values**. Task 32 sensitivity testing will later check how strongly the result depends on them. They should only be changed if sensitivity results, normalization requirements, implementation evidence, or advisor feedback shows a need.

Because the three criteria have different units/scales, implementation must clearly define how the Weighted Sum Method makes them comparable. If the Term 1 report did not fully specify normalization, this is an implementation detail that must be clarified without changing the intended 0.50/0.25/0.25 priority unless necessary.

## Initial technical constraints

[
0.95 leq V_i(t) leq 1.05
]

[
SOC_{min} leq SOC(t) leq SOC_{max}
]

[
0 leq P_{ch/dis}(t) leq P_{max}
]

[
0 leq E(t) leq E_{max}
]

[
Binmathcal{B}_{allowed}
]

## Initial economic components

Potentially include:

- BESS CAPEX,
- BESS fixed O&M,
- grid electricity purchase,
- load-shedding penalty / Value of Lost Load,
- curtailment penalty if retained and justified.

Exact values remain an input/data task.

## Metrics to report

Even if not every metric is optimized directly, report:

- selected bus,
- power rating,
- energy capacity,
- total/annualized cost,
- curtailed energy,
- unserved/load-shed energy,
- network losses,
- minimum/maximum bus voltage,
- voltage violations,
- computation time.

---

# Task 16 — Initial Uncertainty and Scenario Methodology

This task follows the Term 1 uncertainty baseline first. Validation in V5 determines whether refinement is necessary.

## Uncertain variables

Initial:

- load demand,
- PV generation.

## Initial uncertainty concept

Represent historical behavior as:

[
	ext{expected / forecast profile} + 	ext{forecast error / uncertainty}
]

Use an error/statistical model to generate possible trajectories.

## Initial pipeline

```text
Historical data
      ↓
Expected / Forecast Profile
      ↓
Forecast Residual / Error Model
      ↓
Monte Carlo Sampling
      ↓
Large Scenario Set
      ↓
Representative Scenario Selection
      ↓
Uncertainty-aware BESS Optimization
```

## ARIMA status

ARIMA remains a candidate because it was used in Term 1, but it is **not automatically mandatory**.

Retain it only if it is appropriate for the selected data and can be validated.

## Scenario count

Do not treat 45 scenarios as a final scientific requirement.

Initial approach:

1. generate a larger candidate scenario set,
2. validate statistical/physical realism,
3. reduce the set if computationally necessary,
4. perform sensitivity to the retained scenario count.

The final scenario count should be justified experimentally.

## Scenario reduction

Do not automatically retain the Term 1 “15 best + 15 worst + 15 random” method.

Candidate approaches include:

- k-medoids or another clustering method,
- representative quantile selection,
- probability-distance/forward selection.

The final method will be selected during V5.

## Scenario probabilities

Equal scenario probabilities are acceptable for an initial implementation if no better probabilistic weighting is justified.

## How uncertainty enters planning

Use a common planning decision:

[
x=[B,P,E]
]

across scenarios (s=1,ldots,N_s).

A simple initial expected-performance formulation is:

[
J(x)=sum_{s=1}^{N_s} p_s J_s(x)
]

with technical/SOC constraints checked across the scenario evaluations.

This is preferred over independently optimizing a different BESS for every scenario and selecting one afterward.

---

# Task 17 — Initial Validation and Software Test Plan

Validation should be developed alongside implementation, but the following baseline tests are defined now.

## V1 — Network simulator

### Test objectives

Check:

- power-flow convergence,
- bus voltages,
- power balance,
- losses.

### Reference

Compare against:

- trusted/reference solver results,
- benchmark data,
- hand calculations for simple cases where practical.

### Acceptance

No unexplained numerical mismatch beyond a defined tolerance.

The exact tolerance will be selected with the solver/reference.

---

## V2 — Fixed BESS

Validate:

- one-step SOC/energy calculations against manual calculations,
- charging efficiency,
- discharging efficiency,
- SOC minimum,
- SOC maximum,
- power limit,
- no simultaneous charge/discharge.

---

## V3 — Manual Sizing / Placement Comparison

Vary manually:

- BESS bus,
- power rating,
- energy capacity.

Check that model responses are physically and logically explainable.

Use these controlled cases as references for V4.

---

## V4 — Optimizer

Implement **Grey Wolf Optimization (GWO)** as selected in the Term 1 baseline.

Use a deliberately small 5-bus search case to independently enumerate every valid BESS option and establish a reference optimum.

Then compare GWO against the exhaustive-search reference.

Report:

- selected solution,
- objective difference,
- runtime,
- convergence behavior,
- repeatability across multiple GWO runs,
- effect of population size and iteration count where tested.

GWO remains the main optimizer unless this validation exposes a technical problem or the advisors approve a change.

---

## V5 — Forecast / Uncertainty Model

### Forecast or error model

Use held-out historical data and appropriate metrics such as:

[
RMSE
]

[
MAPE
]

where suitable.

### Scenario realism

Compare generated scenarios with historical data using:

- mean,
- standard deviation,
- percentiles,
- min/max,
- daily/temporal profile,
- distribution behavior.

For PV also check physical rules such as no unrealistic nighttime generation.

### Scenario-count sensitivity

Start from the Term 1 baseline of **45 retained scenarios**.

Then test additional scenario counts as a sensitivity study to determine whether the final recommendation/performance is stable. This test is evidence for whether the Term 1 choice should be retained or changed; it is not a reason to replace 45 before implementation.

---

## V5 — Uncertainty-aware Planning

First reproduce the Term 1 ARIMA → Monte Carlo → 45-scenario → GWO → WSM workflow.

After the baseline workflow works, evaluate its result against deterministic planning and on unseen/out-of-sample conditions where practical.

Compare:

- cost,
- voltage violations,
- load shedding,
- curtailment,
- constraint pass rate / robustness.

If this validation reveals that the Term 1 scenario-by-scenario/WSM workflow does not produce a technically defensible single BESS deployment, document that finding before changing the formulation.

---

## V6 — Software Testing

Test:

- valid workflow,
- invalid/missing files,
- bad units,
- empty time series,
- invalid BESS bounds,
- disconnected network,
- power-flow failure,
- optimizer non-convergence.

The software should handle expected user errors in a controlled way rather than simply crashing.

---

## IEEE 33-bus Scalability Test

After the small system is stable:

- run the same framework on the IEEE 33-bus network,
- verify no hard-coded 5-bus assumptions,
- compare benchmark behavior,
- document runtime/scalability issues.

---

# Shadow Design Change Rule

The **Term 1 baseline is the default implementation target**.

A baseline design choice should not be changed merely because another method appears more attractive before testing.

When implementation reveals that a Term 1 assumption or design choice is unsuitable:

1. implement/test the baseline far enough to identify the actual problem,
2. record the affected Term 1 design choice,
3. record the implementation/validation evidence,
4. discuss the change with the team/advisor when consequential,
5. update the shadow design,
6. implement the revised approach,
7. validate the revised behavior,
8. describe the important change and justification in Chapter 4.

The preferred engineering history is:

```text
Term 1 design
    ↓
Baseline implementation
    ↓
Validation evidence
    ↓
Retain OR justified revision
```

The shadow design mainly exists to **fill missing implementation detail and make the Term 1 design executable**, not to redesign the project in advance.
