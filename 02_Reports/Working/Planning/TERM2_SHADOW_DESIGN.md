# Term 2 Technical Design Baseline

**Status:** Finalized high-level design reference  
**Purpose:** Preserve the project/Term 1 technical baseline, identify proposed design decisions where the baseline was incomplete, and map the design to the detailed software implementation-handoff specification.  
**Detailed software contracts:** `TERM2_SOFTWARE_DESIGN_SPEC.md`  
**Schedule source of truth:** live Task Register / Gantt

## 1. Design hierarchy

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

This file owns the **high-level technical design**. `TERM2_SOFTWARE_DESIGN_SPEC.md` owns the exact software architecture, module responsibilities, data structures, file formats, public interfaces, units, sign conventions and numerical contracts.

### Design vs implementation rule

**DESIGN work includes:**

- mathematical/physical assumptions,
- architecture and module boundaries,
- algorithms/numerical contracts,
- interfaces and data flow,
- data structures/file formats,
- units/sign conventions,
- validation strategy.

**IMPLEMENTATION work includes:**

- coding the documented design,
- unit/integration testing,
- debugging,
- verification against known/reference cases,
- running trials/experiments,
- collecting evidence/results.

An implementation owner should not make a new architecture/interface/file-format choice locally. If a design gap is discovered, update the design documentation first or in the same reviewed change.

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
- later use the same framework on the **IEEE 33-bus radial distribution system**,
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

---

# SD-2 — User Workflow and Software Requirements

## Baseline workflow

```text
Load/create network
      ↓
Load load/PV profiles
      ↓
Validate inputs
      ↓
Run baseline FBS simulation
      ↓
Add/configure BESS
      ↓
Manual/automatic BESS evaluation
      ↓
Uncertainty-aware evaluation
      ↓
Compare baseline vs BESS
      ↓
Display/export results
```

## Required input families

- network topology/equipment/base values,
- time-series load and PV,
- BESS planning bounds/parameters,
- economic coefficients used by the retained objective.

## Required output families

- bus voltage,
- branch current/loading,
- losses,
- source/grid power,
- power balance,
- BESS SOC/power,
- selected `[B,P,E]`,
- cost,
- curtailment,
- load shedding,
- voltage violations,
- improvements relative to baseline,
- convergence/computation information where useful.

Exact objects/fields/units are defined in `TERM2_SOFTWARE_DESIGN_SPEC.md`.

---

# SD-3 — Software Architecture

The software architecture is a **design decision**, not an implementation-task decision.

Main modules are defined before coding:

- `network_model.py` — static network entities/topology/validation,
- `network_cases.py` — named 5-bus/IEEE-33 case construction,
- `data_loader.py` — standardized load/PV import,
- `fbs.py` — one-step radial Forward/Backward Sweep,
- `bess.py` — BESS configuration/state/limits,
- `simulation.py` — orchestration layer,
- `metrics.py` — technical/economic metrics,
- `uncertainty.py` — later ARIMA/Monte Carlo scenario interface,
- `optimizer.py` — later GWO/WSM interface,
- `results.py` — result tables/plots/export,
- `ui.py` — final user interface.

### Independence rule

- modules exchange documented public data objects/functions,
- no shared mutable global engineering state,
- FBS does not read CSV files,
- BESS logic does not solve network power flow,
- optimizer does not duplicate FBS/BESS physics,
- UI does not contain engineering calculations.

The exact dependency direction and object ownership are defined in `TERM2_SOFTWARE_DESIGN_SPEC.md` Section 2.

---

# SD-4 — Interfaces, Data Flow and Units

## Deterministic data flow

```text
NetworkModel + ProfileData
          ↓
      ProfileSlice
          ↓
optional BESS step/injection
          ↓
     OperatingPoint
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
Historical/prepared profiles
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
- base/nominal voltage: kV line-line,
- solved voltage: p.u.,
- branch impedance: ohm/phase,
- current: A,
- SOC: fraction 0–1 internally,
- time step: hours.

## Standard signs

- load = positive consumption,
- PV = positive generation,
- BESS `P > 0` = discharge/injection,
- BESS `P < 0` = charge/absorption,
- slack `P > 0` = grid supplies the modeled network.

## Proposed design decision — reactive load when Q is absent

If the prepared load profile contains only active power, the implementation owner must not invent a Q model. Use the bus base-load P/Q ratio:

```text
m_i(t) = P_i(t) / P_base,i
Q_i(t) = m_i(t) * Q_base,i
```

If measured/defined `q_kvar` exists, use it instead.

This is a **proposed design decision**, not a new project requirement.

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

Forward/Backward Sweep remains the initial radial power-flow solver. A trusted external solver may be used only as an independent verification reference unless evidence justifies a documented method change.

## Detailed design already fixed before coding

`TERM2_SOFTWARE_DESIGN_SPEC.md` Sections 3–4 define:

- `Bus`, `Line`, `Load`, `PVUnit`, `NetworkModel`, `RadialOrder`,
- 5-bus case construction boundary,
- network validation/radial ordering,
- engineering-unit/per-unit conversion rules,
- `OperatingPoint`,
- exact FBS backward/forward sequence,
- `FBSConfig`, convergence and failure behavior,
- `PowerFlowResult`,
- required/optional outputs,
- one-step public `run_fbs()` interface.

These are DESIGN decisions and are not left to Tasks 12–13.

---

# SD-6 — BESS Baseline

## Existing baseline

Planning variables remain distinct:

- `E` — energy capacity [kWh],
- `P` — power rating [kW],
- `B` — installation bus.

State:

`SOC_t = E_t / E_max`

Charging:

`E_(t+1) = E_t + eta_c * P_ch,t * Delta_t`

Discharging:

`E_(t+1) = E_t - P_dis,t * Delta_t / eta_d`

Initial SOC constraint:

`0.10 <= SOC_t <= 0.90`

Other retained assumptions:

- no simultaneous charging/discharging,
- fixed efficiency initially,
- initial SOC may use 50% where no case-specific value is required,
- cyclic end SOC may be retained where the study requires it,
- detailed degradation is initially outside scope and must be stated as a limitation if omitted.

## Detailed design already fixed before coding

`TERM2_SOFTWARE_DESIGN_SPEC.md` Section 6 defines:

- `BESSConfig`, `BESSState`, `BESSStepResult`,
- common BESS/network sign convention,
- exact one-step charge/discharge clipping equations,
- `step_bess()` public interface,
- separation between BESS state logic and FBS,
- injection path through `simulation.py`.

## Efficiency design gate

The approximately 85% value in the baseline is ambiguous. The software uses separate `eta_charge` and `eta_discharge`; an implementer must not silently assign 0.85 to both directions. Numeric values require a documented interpretation/source/team decision.

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

Main constraints include voltage/SOC/BESS bounds/allowed buses/network feasibility.

GWO remains the starting optimizer. Limited exhaustive search on the small case is an independent verification reference.

## Proposed design decision — WSM normalization

Term 1 does not fully define a common numerical scale. The current proposed default remains fixed no-BESS baseline-relative normalization:

```text
C_norm    = C_candidate     / max(|C_baseline|, eps)
Curt_norm = Ecurt_candidate / max(|Ecurt_baseline|, eps)
Shed_norm = Eshed_candidate / max(|Eshed_baseline|, eps)

J = 0.50*C_norm + 0.25*Curt_norm + 0.25*Shed_norm
```

This is proposed, not a new customer requirement. If changed, update the design before Task 33 implementation.

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

## Interface rule

Future `Scenario`/`ScenarioSet` reuse the exact same `ProfileData`/simulation path; uncertainty code does not create a second network model or solver.

## Proposed design decision — best/worst ranking

Until replaced by a team/advisor-approved rule, the proposed scenario stress score is:

```text
Stress_s = sum_t max(P_load,total,s(t) - P_PV,total,s(t), 0) * Delta_t
```

Selection:

1. 15 highest stress = worst,
2. 15 lowest stress = best,
3. 15 random from remaining 70,
4. fixed recorded seed (proposed default 42) for reproducibility.

This is a proposed design decision, not a new Term 1 requirement.

---

# SD-9 — Verification and Validation Baseline

## A. Implementation verification / trials

Question: **Did we implement the documented design correctly?**

Examples:

- network validation,
- FBS reference comparison,
- power-balance checks,
- SOC hand calculations/limit tests,
- manual BESS location/size trials,
- GWO vs exhaustive search,
- GWO population/iteration tests,
- ARIMA RMSE/MAPE,
- scenario realism,
- software input/failure tests.

This evidence primarily supports Chapter 4.

## B. Formal validation experiments

Question: **Does the implemented product satisfy the Term 1 design specifications?**

Each Chapter 5 experiment should include objective, background, detailed steps, tools, organized data/figures/tables, and analysis/conclusion.

Requirement evidence is summarized as:

`Requirement -> Target -> Experiment/direct check -> Measured result -> Evidence -> Status`

with status `Met`, `Partially Met`, or `Not Met`.

Do not alter a requirement to make it pass.

---

# Current Gantt implementation mapping

| Design section | Main current implementation tasks |
|---|---|
| SD-1 Product scope | 51–57, 60 |
| SD-2 Workflow/requirements | 10–11, 51–57, 62 |
| SD-3 Architecture | 10–11, then all backend/UI modules |
| SD-4 Interfaces/data flow | 11, 16–17, 20–23, 32–35, 42–45, 52–54 |
| SD-5 Network/FBS | 12–19, 60 |
| SD-6 BESS | 20–31 |
| SD-7 Objective/GWO | 32–40 |
| SD-8 ARIMA/MC/scenarios | 42–50 |
| SD-9 Verification/validation | verification tasks throughout + 41, 58–61 |

Task numbers/dates/status live in the Task Register/Gantt. Design contracts live here and in `TERM2_SOFTWARE_DESIGN_SPEC.md`.

---

# Change-control rule

```text
Existing baseline
      ↓
Document detailed design
      ↓
Implement documented design
      ↓
Test / verify
      ↓
If change is needed, show evidence
      ↓
Update design documentation
      ↓
Implement the revised contract consistently
      ↓
Document implementation change in Chapter 4
```

The intent is simple: **team members should implement an agreed specification, not independently design their module while coding it.**
