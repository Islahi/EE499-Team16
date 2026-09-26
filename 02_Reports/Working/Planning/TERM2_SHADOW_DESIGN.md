# Term 2 Technical Implementation Baseline

**Status:** Finalized reference  
**Purpose:** Preserve the agreed Term 1 implementation baseline and show how the **current Gantt tasks** implement it.  
**Important:** This document does **not** revise submitted Chapters 1–3. It is a technical reference for implementation. The live Task Register / Gantt remains the source of truth for task numbers, dates, status and dependencies.

## 1. How to use this document

The earlier version of this file used old task numbers such as “Task 9–17”. Those numbers no longer match the current Gantt and have therefore been removed.

This file now uses stable technical section IDs:

- **SD-1** Product Scope
- **SD-2** User Workflow and Software Requirements
- **SD-3** Software Architecture
- **SD-4** Interfaces and Data Flow
- **SD-5** Network and FBS Baseline
- **SD-6** BESS Baseline
- **SD-7** Objective and Optimization Baseline
- **SD-8** Uncertainty Baseline
- **SD-9** Verification and Validation Baseline

The relationship is:

```text
Term 1 baseline
      ↓
Technical baseline in this file
      ↓
Current Gantt tasks implement it
      ↓
Implementation trials / verification
      ↓
Formal validation against Term 1 specifications
      ↓
Document justified changes in Chapter 4
```

The implementation stages remain:

1. **V1 — Network simulator**
2. **V2 — Fixed BESS**
3. **V3 — Manual sizing/placement comparison**
4. **V4 — Automatic optimization**
5. **V5 — Uncertainty-aware optimization**
6. **V6 — Final decision-support software**

---

# SD-1 — Product Scope

## Product definition

The Term 2 product is a **software-based decision-support tool for BESS planning in renewable-integrated radial distribution networks**.

The final program should allow the user to:

1. define or load a radial distribution network,
2. load time-series electrical demand,
3. load PV generation / solar-resource data,
4. simulate the network without BESS,
5. add and simulate a BESS,
6. evaluate different BESS locations and sizes,
7. automatically determine a BESS decision vector
   \(x=[B,P,E]\),
8. evaluate the recommended BESS under uncertain load/PV conditions,
9. compare the system before and after BESS installation,
10. display technical and economic results.

Where:

- \(B\) = BESS installation bus,
- \(P\) = BESS power rating,
- \(E\) = BESS energy capacity.

## Network scope

- Use a small **5-bus radial test system** for development and debugging.
- Test the same framework later on the **IEEE 33-bus radial distribution system**.
- The 5-bus system is an implementation case, not the final product limit.

## Renewable source

- Solar PV is the implemented renewable source.
- Other renewable profiles may be supported later, but are not required for the current case study.

## Initial scope limits

Unless later required:

- one BESS installation at a time,
- stationary BESS,
- radial distribution networks,
- grid-connected operation,
- no real-time physical grid control,
- no detailed thermal/electrochemical BESS model,
- no detailed degradation model initially,
- no transmission-system optimization.

### Current Gantt implementation

- **Task 9** finalized the implementation baseline.
- **Tasks 51–57** integrate the complete decision-support software.
- **Task 60** demonstrates scalability on IEEE 33-bus.

---

# SD-2 — User Workflow and Software Requirements

## User workflow

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
Run uncertainty-aware optimization
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
- PV profile / solar-resource data.

### BESS planning bounds

- allowed candidate buses,
- \(P_{min},P_{max}\),
- \(E_{min},E_{max}\).

### Economic inputs

As required by the retained cost model:

- BESS energy cost,
- power-conversion cost,
- grid-energy price,
- fixed O&M,
- load-shedding penalty,
- curtailment penalty where justified.

## Required outputs

### Network

- bus voltage,
- line loading/current,
- losses,
- source/grid power,
- power balance.

### BESS

- SOC,
- charging/discharging power.

### Optimization

- selected bus \(B^*\),
- selected power \(P^*\),
- selected energy \(E^*\).

### Performance

- cost,
- renewable curtailment,
- load shedding,
- voltage violations,
- losses,
- percentage improvements,
- computation time where useful.

## Error handling

The final application should handle or clearly report:

- missing/invalid data,
- inconsistent timestamps or units,
- invalid BESS bounds,
- disconnected networks,
- failed power flow,
- optimization non-convergence.

### Current Gantt implementation

- **Task 10** sets up the code structure.
- **Task 11** defines the basic input/output formats.
- **Tasks 51–57** implement the final UI/workflow.
- **Task 62** checks important software failure cases.

---

# SD-3 — Software Architecture

## Module structure

```text
                    User Interface
                         │
                    Data Manager
                         │
          ┌──────────────┴──────────────┐
          │                             │
    Network Model                 Uncertainty Module
      + FBS                             │
          └──────────────┬──────────────┘
                         │
                    BESS Model
                         │
                     Evaluator
              cost / technical metrics
                         │
                     Optimizer
                         │
                Results / Validation
```

## Main responsibilities

### Data Manager

- read simulation data,
- check timestamps/units,
- align profiles,
- provide clean inputs to the simulator.

### Network Model / FBS

- buses, lines, loads, PV and slack source,
- radial power flow,
- electrical network results.

### BESS Model

- P and E ratings,
- stored energy / SOC,
- charge/discharge limits,
- BESS network injection.

### Evaluator

Calculate:

- economic cost,
- losses,
- voltage violations,
- curtailment,
- load shedding,
- objective/fitness value.

### Optimizer

- choose \(B,P,E\),
- call the simulator/evaluator,
- search for the best/acceptable deployment.

The optimizer should not duplicate the electrical physics.

### Uncertainty Module

- ARIMA forecasting,
- Monte Carlo scenario generation,
- scenario selection,
- scenario evaluation.

### User Interface

- collect inputs,
- start simulation/optimization,
- show progress/errors,
- display and export results.

### Current Gantt implementation

- **Tasks 10–11** establish the module structure and interfaces.
- **Tasks 12–50** implement the backend modules incrementally.
- **Tasks 51–57** integrate the modules into the final software.

---

# SD-4 — Interfaces and Data Flow

## Deterministic flow

```text
Network data ─┐
Load data ────┼──> Prepared Inputs
PV data ──────┘
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

## Uncertainty flow

```text
Historical load/PV
        ↓
ARIMA / error model
        ↓
Monte Carlo scenarios
        ↓
Representative scenario set
        ↓
Simulation + Evaluator
        ↓
Uncertainty-aware optimization
```

## Conceptual data structures

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
- SOC minimum/maximum.

### SimulationResult

- bus voltages,
- line loading,
- losses,
- grid power,
- BESS power,
- BESS SOC,
- curtailment,
- load shedding.

Conceptually, the optimization layer should be able to request:

```text
evaluate(B, P, E, scenario)
```

and receive objective/performance metrics.

### Current Gantt implementation

- **Task 11** defines the software I/O formats.
- **Task 16** connects the prepared load/PV profiles.
- **Tasks 32–39** connect the evaluator/optimizer to the simulation.
- **Tasks 52–57** expose the same workflow through the UI.

---

# SD-5 — Network and FBS Baseline

## Network assumptions

- balanced radial distribution network,
- one grid/slack source,
- PQ loads,
- time-varying PV active-power injection,
- hourly time step initially.

For IEEE 33-bus, bus 1 is the source/slack unless the benchmark data requires otherwise.

## Voltage criterion

\[
0.95 \leq V_i \leq 1.05\;pu
\]

## Power-flow solver

The **Forward-Backward Sweep (FBS)** method selected in Term 1 remains the initial solver.

A trusted external solver may be used only as a reference to verify the implementation. It should not silently replace FBS.

If FBS later creates a demonstrated technical problem or cannot support a required feature, the change must be documented and justified in Chapter 4.

## Infeasible cases

Cases with failed power flow, invalid/disconnected operation or unacceptable technical violations should be marked infeasible and handled using constraints/penalties during optimization.

### Current Gantt implementation

- **Task 12** prepares the 5-bus case.
- **Task 13** implements one-step FBS.
- **Task 14** verifies FBS.
- **Task 15** produces basic network outputs.
- **Task 16** imports load/PV profiles.
- **Task 17** adds the hourly loop.
- **Task 18** verifies V1.
- **Task 19** documents V1 in Chapter 4.
- **Task 60** tests the framework on IEEE 33-bus.

---

# SD-6 — BESS Baseline

## Planning variables

- \(E_{max}\): energy capacity,
- \(P_{max}\): power rating,
- \(B\): installation bus.

Power and energy capacity must remain distinct.

## State of charge

\[
SOC_t=\frac{E_t}{E_{max}}
\]

Charging:

\[
E_{t+1}=E_t+\eta_c P_{ch,t}\Delta t
\]

Discharging:

\[
E_{t+1}=E_t-\frac{P_{dis,t}\Delta t}{\eta_d}
\]

## Initial SOC constraint

Retain the Term 1 baseline initially:

\[
0.10 \leq SOC_t \leq 0.90
\]

## Power constraints

\[
0 \leq P_{ch,t} \leq P_{max}
\]

\[
0 \leq P_{dis,t} \leq P_{max}
\]

## Operating assumptions

- no simultaneous charge/discharge,
- fixed efficiency initially,
- approximately 85% Term 1 efficiency remains the starting value until verified/refined,
- initial SOC may begin at 50% if no case-specific value is required,
- retain a cyclic end condition where appropriate.

Detailed degradation is initially outside scope unless later required; if omitted, state it as a limitation.

### Current Gantt implementation

- **Tasks 20–25** implement and verify the fixed BESS model.
- **Task 26** documents V2.
- **Tasks 27–30** manually compare location and P/E sizing.
- **Task 31** documents the V3 trials.

---

# SD-7 — Objective and Optimization Baseline

## Decision vector

\[
x=[B,P,E]
\]

## Objective components

Retain the Term 1 concerns:

- economic cost,
- renewable curtailment,
- load shedding.

The starting Weighted Sum Method follows the Term 1 priority:

\[
J=0.50\,C+0.25\,E_{curt}+0.25\,E_{shed}
\]

The implementation must define how the criteria are normalized/made comparable before weighting.

## Main constraints

- voltage limits,
- SOC limits,
- BESS P/E bounds,
- allowed installation buses,
- network feasibility.

## Optimizer

GWO is the initial optimizer selected in Term 1.

It should search over \(B,P,E\) while calling the same network/BESS evaluator used by manual simulations.

Use a limited exhaustive search on the small system as an independent reference for optimizer verification.

### Current Gantt implementation

- **Task 32** implements cost/curtailment/shedding metrics.
- **Task 33** implements the Term 1 WSM objective.
- **Tasks 34–36** implement and run GWO.
- **Task 37** builds the exhaustive-search reference.
- **Task 38** compares GWO with exhaustive search.
- **Task 39** tests population/iteration settings.
- **Task 40** documents V4.

---

# SD-8 — Uncertainty Baseline

## Uncertain quantities

- load demand,
- PV generation.

## Term 1 workflow to implement first

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

The Term 1 workflow remains the starting implementation. Do not replace it simply because another stochastic approach may appear theoretically better.

ARIMA should be checked with forecast-error metrics such as RMSE/MAPE. Generated scenarios should be checked against historical behavior and physical limits.

If implementation shows that the Term 1 scenario-by-scenario workflow cannot produce a defensible single physical BESS deployment, record the evidence first and then justify any refinement in Chapter 4.

### Current Gantt implementation

- **Task 42** implements ARIMA.
- **Task 43** verifies forecast accuracy.
- **Task 44** generates 100 Monte Carlo scenarios.
- **Task 45** selects the 45 Term 1 scenarios.
- **Task 46** checks scenario realism.
- **Tasks 47–49** run and verify the uncertainty workflow.
- **Task 50** documents V5.

---

# SD-9 — Verification and Validation Baseline

Use two levels of evidence.

## A. Implementation trials / verification

These answer: **Did we implement each part correctly and reach a satisfactory implementation?**

Examples:

- FBS vs trusted/manual reference,
- power-balance checks,
- SOC hand calculations,
- battery-limit tests,
- manual BESS placement/sizing trials,
- GWO vs exhaustive search,
- population/iteration trials,
- ARIMA RMSE/MAPE,
- scenario realism checks,
- software failure-case testing.

This evidence primarily supports **Chapter 4 — Implementation**.

## B. Formal validation experiments

These answer: **Does the finished product satisfy the Term 1 design specifications?**

The official final-report template requires each formal experiment to include:

1. objective,
2. relevant background,
3. detailed work plan / steps,
4. tools,
5. organized figures/tables/data,
6. analysis and conclusion.

The current formal experiments are:

- technical/economic performance,
- optimizer/uncertainty requirements,
- IEEE 33-bus/network scalability,
- final requirement-evidence summary.

For each Term 1 requirement, report:

```text
Requirement → Target → Experiment/direct check → Measured result → Evidence → Status
```

Status should be one of:

- **Met**,
- **Partially Met**,
- **Not Met**.

Do not change a requirement simply to make it pass.

### Current Gantt implementation

Implementation verification is spread across:

- **Tasks 14, 18, 25, 28–30, 38–39, 43, 46, 49 and 62**.

Formal validation is planned/performed in:

- **Task 41** — design the Chapter 5 experiments,
- **Task 58** — technical/economic performance experiment,
- **Task 59** — optimizer/uncertainty experiment,
- **Task 60** — IEEE 33-bus scalability experiment,
- **Task 61** — final requirement-evidence summary.

---

# Current Gantt Mapping Summary

| Technical baseline section | Current Gantt tasks |
|---|---|
| SD-1 Product Scope | 9, 51–57, 60 |
| SD-2 Workflow / Requirements | 10–11, 51–57, 62 |
| SD-3 Architecture | 10–11, 12–50, 51–57 |
| SD-4 Interfaces / Data Flow | 11, 16, 32–39, 52–57 |
| SD-5 Network / FBS | 12–19, 60 |
| SD-6 BESS | 20–31 |
| SD-7 Objective / GWO | 32–40 |
| SD-8 ARIMA / MC / Scenarios | 42–50 |
| SD-9 Verification / Validation | 14, 18, 25, 28–30, 38–39, 41, 43, 46, 49, 58–62 |

## Report-writing tasks

The implementation evidence is written progressively:

- **Task 19** — Chapter 4 V1,
- **Task 26** — Chapter 4 V2,
- **Task 31** — Chapter 4 V3,
- **Task 40** — Chapter 4 V4,
- **Task 50** — Chapter 4 V5,
- **Task 57** — Chapter 4 V6 / final integration,
- **Task 64** — merge and polish Chapter 4,
- **Task 65** — finish Chapter 5, Chapter 6 and Appendix D.

---

# Change-control rule

The baseline-preservation sequence remains:

```text
Term 1 baseline
    ↓
Implement it
    ↓
Test / verify it
    ↓
Keep it if it works
    ↓
Change only with evidence or advisor reason
    ↓
Document the change in Chapter 4
```

This document is now a **finished technical reference**. It should only be updated when the implementation produces a real technical decision/change that needs to be recorded. Task numbering and dates should be maintained only in the live Task Register/Gantt, not duplicated as section identities here.
