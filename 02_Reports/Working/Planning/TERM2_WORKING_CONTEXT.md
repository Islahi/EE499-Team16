# Term 2 Working Context — Discussion Summary

**Last updated:** 2026-09-21

This file preserves the main Term 2 project discussion so future AI assistants and team members do not need prior chat history to understand the current working direction.

> **Important:** This is a working-context document, not a confirmed technical-decision record. Major technical choices become binding only when explicitly confirmed by the team/advisors and recorded in `DECISIONS.md`.

## 1. Current project direction

The team is moving away from treating Term 2 as only a research/simulation exercise.

The current working direction is to develop a **working BESS planning / decision-support software tool** that integrates the project's simulation and optimization work.

A reasonable target workflow discussed is:

1. user defines or loads a distribution network,
2. user provides load and renewable profiles,
3. the program runs a baseline power-flow/time-series simulation,
4. renewable/load uncertainty is represented through scenarios,
5. BESS location, power rating, and energy capacity are optimized,
6. the optimized system is simulated/verified,
7. the program presents before/after technical and economic results.

The tool should start from a small, understandable system (approximately a **5-bus radial network**) and later demonstrate scalability/validation using the **IEEE 33-bus system**.

This direction is a **working project/product direction**, not yet a confirmed entry in `DECISIONS.md`.

## 2. Why the direction changed

The main lesson drawn from Term 1 feedback is that the team did not lack technical topics or algorithms. Instead, the project had many separate research components without a sufficiently complete engineering design tying them together.

Term 1 already considered or researched:

- IEEE 33-bus radial distribution system,
- solar PV integration,
- load/renewable time series,
- ARIMA forecasting,
- Monte Carlo scenario generation,
- Grey Wolf Optimization (GWO),
- Forward-Backward Sweep power flow,
- BESS location, power, and energy-capacity variables,
- SOC and voltage constraints,
- weighted objectives involving cost, curtailment, and load shedding,
- baseline-vs-optimized comparison concepts.

The final Term 1 feedback is especially important: the project was described as largely conceptual, with no complete design presented and unclear relationships/interfaces between modules.

Therefore, Term 2 needs to turn the researched pieces into a **defined, implemented, testable, and validated engineering system**.

## 3. General Guidance interpretation

The classroom General Guidance distinguishes the project as both **software** and **simulation**.

### Software engineering design should include

- architecture,
- algorithms,
- interfaces,
- data flow,
- control logic.

### Simulation engineering design should include

- mathematical model,
- assumptions,
- parameters,
- numerical method,
- validation plan.

### Implementation then includes

- coding,
- debugging,
- testing,
- integration,
- running simulations,
- collecting outputs,
- checking behavior.

The team's main current weakness is not the absence of algorithms; it is the missing design and implementation structure connecting them.

## 4. Main design/implementation gaps identified

The discussion identified the following major gaps that should be repaired during Term 2:

- exact product definition and user workflow,
- software architecture,
- module interfaces,
- data flow between modules,
- control/error-handling logic,
- finalized network/power-flow assumptions,
- finalized mathematical BESS model,
- finalized optimization variables/objective/constraints,
- defensible uncertainty/scenario methodology,
- deterministic baseline implementation,
- integrated BESS sizing/placement optimization,
- validation strategy,
- software testing,
- decision-support/user interface,
- reproducibility,
- larger-network validation.

This list is consistent with `KNOWN_GAPS.md`, but adds the working software-product interpretation developed during the Term 2 discussion.

## 5. Recommended implementation sequence

The current recommended sequence is:

```text
Data acquisition
    ↓
Product definition / requirements
    ↓
Software architecture + interfaces
    ↓
Simulation / mathematical design
    ↓
Minimal deterministic 5-bus system
    ↓
Baseline power flow
    ↓
BESS model + dispatch
    ↓
Deterministic BESS sizing/placement
    ↓
Uncertainty / scenario modelling
    ↓
Uncertainty-aware BESS optimization
    ↓
Decision-support UI integration
    ↓
Validation + sensitivity testing
    ↓
IEEE 33-bus benchmark
    ↓
Final documentation + demonstration
```

A key recommendation is **not to begin Term 2 by directly coding GWO**. The backend model, interfaces, deterministic baseline, and validation reference should be established first.

## 6. Small-system validation strategy

A small ~5-bus radial system was discussed as a useful minimum implementation because it is:

- easy to understand,
- easy to debug,
- fast to simulate,
- suitable for demonstrating the software workflow,
- small enough to validate optimization results by exhaustive/brute-force search.

A useful optimizer-validation method is:

1. restrict the candidate locations/sizes to a manageable set,
2. enumerate all valid combinations,
3. determine the known/best result,
4. compare GWO or another optimizer against that reference.

This provides direct evidence that the optimization implementation works.

The IEEE 33-bus system can then be used later to demonstrate scalability and benchmark behavior.

## 7. BESS planning variables

The main planning variables discussed remain conceptually:

[
x = [B, P_{BESS}, E_{BESS}]
]

where:

- (B) = battery bus/location,
- (P_{BESS}) = battery power rating,
- (E_{BESS}) = battery energy capacity.

The distinction between power and energy capacity must remain clear.

Operational dispatch/SOC behavior occurs inside the evaluation of a candidate planning solution.

## 8. Optimization approach

GWO was used in the Term 1 baseline, but it is **not automatically a permanent Term 2 decision**.

The discussion emphasized that:

- the optimization method should be chosen because it is appropriate and verifiable,
- a mixed discrete/continuous problem must be handled carefully because bus location is discrete while power/energy ratings are continuous,
- for 5–33 candidate buses, exhaustive location evaluation combined with a continuous sizing optimizer may be clearer than forcing all variables directly into GWO,
- whatever optimizer is used should be checked against a small known/reference search.

Potential methods discussed as alternatives or benchmarks include GWO, PSO, exhaustive/grid search, and mathematical optimization approaches when appropriate.

## 9. Uncertainty as the main project differentiator

BESS optimization by itself is not novel; commercial/research tools already perform storage sizing, dispatch, planning, or placement in various forms.

The strongest potential project contribution is therefore the **integration of uncertainty directly into the distribution-system BESS planning workflow**.

The uncertainty pipeline discussed is:

```text
Historical data
    ↓
Forecast / expected profile
    ↓
Forecast errors or probabilistic model
    ↓
Monte Carlo scenarios
    ↓
Representative-scenario reduction
    ↓
BESS planning optimization
    ↓
Power-flow verification over scenarios
```

The design is only genuinely uncertainty-aware if the scenarios affect the optimization objective and/or constraints, not if scenarios are generated only after the battery has already been selected.

A practical first uncertainty level is scenario/expected-value optimization, potentially combined with reliability/constraint-violation metrics.

## 10. Deterministic vs uncertainty-aware validation

A particularly strong Term 2 validation experiment discussed is:

1. design a BESS using the deterministic/nominal forecast,
2. design another BESS using uncertainty-aware optimization,
3. test both on a common set of **unseen/out-of-sample scenarios**,
4. compare their performance.

Possible comparison metrics include:

- expected/total operating cost,
- renewable curtailment,
- load shedding,
- voltage violations,
- worst-case voltage behavior,
- reliability/constraint pass rate.

This experiment can demonstrate the value of uncertainty-aware planning without requiring the team to invent a novel optimization algorithm.

## 11. Scenario-generation issue from Term 1

The Term 1 approach of generating 100 scenarios and retaining:

- 15 best,
- 15 worst,
- 15 random

was identified as weakly justified.

The discussion recommends using a more defensible representative-scenario method, such as:

- clustering (for example k-means or k-medoids),
- quantile/representative scenarios,
- probability-distance/forward selection methods.

K-medoids may be attractive because selected representatives are actual generated trajectories rather than synthetic centroids.

No replacement method has yet been confirmed as a team decision.

## 12. Existing tools and project positioning

Existing software/frameworks discussed include:

- pandapower,
- OpenDSS,
- BambooGrid,
- Sandia QuESt / QuESt-SSIM,
- HOMER,
- REopt.

Important conclusion:

> The project should **not** claim that existing tools do not perform optimization or that BESS sizing/placement itself is novel.

Instead, the working contribution should be framed more narrowly around an integrated educational/engineering planning workflow such as:

> configurable distribution network → load/renewable profiles → uncertainty scenarios → BESS sizing/location optimization → power-flow verification → baseline/optimized/robustness comparison.

The team may use an existing trusted power-flow engine rather than rewriting a power-flow solver purely for novelty.

## 13. Immediate advisor-driven priority: data

The current advisors asked the team to **obtain project data before the next meeting**, whose date is currently TBA.

This is the immediate priority.

The data work is represented as Tasks 1–7 in the Term 2 planning spreadsheet.

### Data categories required

The current data search should cover:

- historical load-demand time series,
- solar/PV/weather/irradiance data,
- distribution-network data,
- later BESS technical/economic parameters.

### What counts as an acceptable dataset

The team discussed that a dataset should not be considered "found" merely because a link exists.

For each candidate dataset, record:

- source/provenance,
- system/location represented,
- variables/columns,
- units,
- sampling interval,
- period covered,
- missing/outlier data,
- usage/license considerations,
- compatibility with the other project datasets.

### Evidence expected from each team member

A useful dataset handoff for the team/advisor meeting should include:

- original source/reference,
- downloaded file or representative sample,
- short column/variable description,
- units,
- time interval and total duration,
- missing-data/quality notes,
- at least one simple plot,
- unresolved concerns/questions.

The working rule discussed is:

> A dataset is not considered ready merely because a source was found; the team should be able to show its structure, quality, provenance, and representative behavior.

## 14. Time resolution

The discussion suggested **hourly data as the initial common resolution** because it is practical for:

- load/PV alignment,
- SOC updates,
- Monte Carlo scenarios,
- time-series power flow,
- debugging,
- manageable computational effort.

This is a recommendation/working assumption, **not yet a confirmed team decision**.

Higher-resolution data (for example 15- or 30-minute) can still be retained and later evaluated if useful.

## 15. Ethics and professional responsibility

Ethics/professional responsibility was added as an early critical task instead of leaving it until final-report writing.

Topics to consider include:

- truthful use and presentation of data,
- data provenance and integrity,
- transparent modelling assumptions,
- clearly stated model limitations,
- reliability and grid-safety implications,
- environmental/economic trade-offs,
- responsible interpretation of optimization results,
- avoiding presentation of model output as a guaranteed real-world operating/planning decision.

This is currently treated as prudent engineering/report work. A repository text search did not independently establish a specifically named mandatory "Ethics" section in the official material.

## 16. Current semester planning system

The working Term 2 plan is maintained in a Google Sheet:

https://docs.google.com/spreadsheets/d/1HE7RNvaZ-VkVMlozWfkfPbe23hywnEdOzuaI1CfAEcY/edit

Repository planning files:

- `02_Reports/Working/Planning/README.md`
- `02_Reports/Working/Planning/EE499_Team16_Term2_Task_Register.csv`

The plan currently contains 38 tasks spanning:

- data,
- ethics,
- product design,
- software design,
- simulation design,
- validation design,
- core implementation,
- BESS implementation,
- optimization,
- uncertainty,
- software product/UI,
- validation,
- software testing,
- documentation/finalization.

The Google Sheet is the primary collaborative planning surface; the CSV is a version-controlled snapshot.

### Dynamic Gantt behavior

The `Task Register` is the main editable tab.

The `Semester Gantt` automatically reads:

- task,
- phase,
- Start/End dates,
- priority,
- status,
- progress.

Changing dates in the Task Register moves the weekly Gantt bars automatically.

Status colors:

- Not Started — gray,
- In Progress — blue,
- Blocked — red,
- Done — green,
- TBA — yellow.

## 17. Immediate weekly-team-meeting focus

The discussion proposed the following focus for the current weekly meeting:

1. align the team on the Term 2 working direction: working BESS planning software rather than disconnected research components,
2. acknowledge the main Term 1 weakness: many methods existed, but the engineering design/integration remained incomplete,
3. prioritize the advisor-requested data acquisition,
4. agree on minimum dataset-quality requirements,
5. discuss hourly resolution as the initial common time step,
6. assign responsibility for load, renewable/weather, and network data,
7. require real dataset evidence rather than links alone,
8. begin ethics/professional-responsibility work in parallel,
9. after the data gate, confirm the minimum software/product scope.

Useful meeting outcomes include assigning owners for:

- load data,
- PV/weather data,
- network data,

and agreeing what each person must bring before the next advisor meeting.

## 18. Important open decisions

Future AI assistants should **not silently assume** the following have been confirmed:

- final software/product scope,
- final power-flow engine,
- final network-input method/UI,
- final BESS mathematical model,
- final objective function and weights/normalization,
- final uncertainty model,
- final scenario-reduction method,
- final optimizer,
- whether hourly time resolution is mandatory,
- whether load uncertainty is included alongside renewable uncertainty,
- final validation metrics,
- exact alignment with or departure from the original official project brief.

These should be discussed with the team/advisors and recorded in `DECISIONS.md` only when explicitly confirmed.

## 19. Overall current interpretation

The project should not be treated as starting from zero.

The team has a substantial research and conceptual foundation from Term 1. The main Term 2 challenge is to transform that foundation into:

> **a complete engineering design → a working integrated application → a validated result.**

The most immediate practical work is **data acquisition and evaluation**, followed by freezing the minimum product architecture/design needed to begin the deterministic 5-bus implementation.
