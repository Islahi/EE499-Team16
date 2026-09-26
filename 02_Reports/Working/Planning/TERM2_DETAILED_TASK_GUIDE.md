# Term 2 Detailed Task Guide

**Last aligned:** 26 Sep 2026  
**Progress Update:** 22 Oct 2026  
**Final report:** 30 Nov 2026  
**Final presentation:** 6–10 Dec 2026

## Current status

- Tasks 1–7 are **Done**. Data acquisition and processing finished last week.
- Task 9 is **Done**. The implementation baseline is finalized.
- There is **no separate advisor data-presentation task**.
- Task 8 Ethics runs **in parallel** and does not block implementation.
- Main implementation starts now with Task 10.

## Design handoff rule

Before coding, use:

- `TERM2_SHADOW_DESIGN.md` for the high-level technical baseline.
- `TERM2_SOFTWARE_DESIGN_SPEC.md` for exact software architecture, module responsibilities, data structures, file formats, interfaces, units/sign conventions and required/optional outputs.

Implementation tasks should focus on **coding, testing, debugging and integration**. Do not independently redesign module boundaries, profile formats, sign conventions or public interfaces inside an implementation task.

Where `TERM2_SOFTWARE_DESIGN_SPEC.md` labels a choice as a **proposed design decision**, it is an explicit proposal rather than a new project requirement. If the team changes it, update the design specification before implementations diverge.

Two later design gates remain open:

- confirm WSM normalization before Task 33,
- confirm the best/worst scenario ranking metric before Task 45.

## How to read this guide

For each task:
- **Start / Deadline** = internal working dates.
- **What to do** = implementation/work activity.
- **Done when** = required artifact/result.

---

# Completed early preparation

## Task 1 — Define the data we need
**Start:** 20 Sep 2026  
**Deadline:** 21 Sep 2026  
**Status:** Done  
**What to do:** List required load, PV/weather, network and BESS/economic data.  
**Done when:** One clear data checklist exists.

## Task 2 — Get load data
**Start:** 20 Sep 2026  
**Deadline:** 23 Sep 2026  
**Status:** Done  
**Done when:** Load dataset is ready with source/unit/time-step notes.

## Task 3 — Get PV / weather data
**Start:** 20 Sep 2026  
**Deadline:** 23 Sep 2026  
**Status:** Done  
**Done when:** PV/weather dataset is ready.

## Task 4 — Get network data
**Start:** 21 Sep 2026  
**Deadline:** 23 Sep 2026  
**Status:** Done  
**Done when:** Development 5-bus and IEEE 33-bus network data are ready.

## Task 5 — Check the selected data
**Start:** 23 Sep 2026  
**Deadline:** 24 Sep 2026  
**Status:** Done  
**Done when:** Sources, units, timestamps, missing values and compatibility are checked.

## Task 6 — Clean and align the data
**Start:** 24 Sep 2026  
**Deadline:** 25 Sep 2026  
**Status:** Done  
**Done when:** Simulation-ready load/PV profiles exist.

## Task 7 — Finalize simulation-ready data package
**Start / Deadline:** 25 Sep 2026  
**Status:** Done  
**Done when:** Cleaned load, PV/weather and network data are stored with source/unit notes.

## Task 9 — Finalize implementation baseline
**Start:** 24 Sep 2026  
**Deadline:** 25 Sep 2026  
**Status:** Done  
**Done when:** High-level implementation baseline is finalized.

---

# Parallel ethics task

## Task 8 — Prepare individual ethical analysis + final-report ethics material
**Start:** 26 Sep 2026  
**Internal draft target:** 7 Oct 2026  
**Priority:** Medium  
**What to do:** Each member prepares the required individual 3–5 page ethical analysis using the SCE Engineer Charter 2025, including two distinct ethical issues and the required stakeholder/safety/privacy/impact/integrity/IP/mitigation/reflection content.  
**Done when:** Each member has a usable draft/outline and the team has material reusable in Chapter 6.2 and Appendix D.  
**Important:** Runs in parallel with Tasks 10 onward.

---

# Setup — implement the predefined design

## Task 10 — Set up the code structure from the design spec
**Start:** 26 Sep 2026  
**Deadline:** 29 Sep 2026  
**Design reference:** `TERM2_SOFTWARE_DESIGN_SPEC.md` §2  
**What to do:** Create the predefined module/file skeleton for network, data loading, FBS, BESS, simulation, metrics, future uncertainty/optimizer, results and UI. Do not redesign module responsibilities here.  
**Done when:** Runnable module skeleton matches the design specification.

## Task 11 — Implement the agreed I/O structures and sample fixtures
**Start:** 27 Sep 2026  
**Deadline:** 30 Sep 2026  
**Design reference:** `TERM2_SOFTWARE_DESIGN_SPEC.md` §§3–8  
**What to do:** Create the specified dataclasses/data objects, interface skeletons and small sample fixtures. Do not choose new data formats in this task.  
**Done when:** I/O structures and sample fixtures match the design specification.

---

# V1 — Network simulator

## Task 12 — Build the 5-bus NetworkModel case
**Start:** 28 Sep 2026  
**Deadline:** 1 Oct 2026  
**Design reference:** `TERM2_SOFTWARE_DESIGN_SPEC.md` §§3, 9  
**What to do:** Represent the prepared 5-bus radial case with the specified `Bus`, `Line`, `Load`, `PVUnit` and `NetworkModel` structures.  
**Done when:** Validated 5-bus `NetworkModel` is ready for FBS.

## Task 13 — Implement `fbs.py` for one time step
**Start:** 1 Oct 2026  
**Deadline:** 6 Oct 2026  
**Design reference:** `TERM2_SOFTWARE_DESIGN_SPEC.md` §4  
**What to do:** Implement the documented `NetworkModel + OperatingPoint + FBSConfig -> PowerFlowResult` contract. No CSV loading or BESS/optimizer logic belongs in `fbs.py`.  
**Done when:** One-step FBS runs on the 5-bus case and returns all required outputs/convergence fields.

## Task 14 — Verify the FBS result
**Start:** 5 Oct 2026  
**Deadline:** 8 Oct 2026  
**What to do:** Compare voltage, power balance and losses with trusted/manual reference checks; test convergence behavior.  
**Done when:** FBS result is verified for the small case.

## Task 15 — Show basic network results
**Start:** 7 Oct 2026  
**Deadline:** 10 Oct 2026  
**What to do:** Present required `PowerFlowResult` outputs such as bus voltage, branch current/power, losses and source power.  
**Done when:** V1 output is readable and traceable to the documented result contract.

## Task 16 — Implement load and PV profile import
**Start:** 30 Sep 2026  
**Deadline:** 3 Oct 2026  
**Design reference:** `TERM2_SOFTWARE_DESIGN_SPEC.md` §5  
**What to do:** Implement `data_loader.py` using the predefined long-format load/PV CSV fields and `ProfileData`. Validate timestamps, units, bus IDs and missing/duplicate rows.  
**Done when:** Prepared files load into valid `ProfileData` without redefining the format.

## Task 17 — Add the hourly simulation loop
**Start:** 9 Oct 2026  
**Deadline:** 13 Oct 2026  
**Design reference:** `TERM2_SOFTWARE_DESIGN_SPEC.md` §7  
**What to do:** Use the orchestration interface to build an `OperatingPoint` for each timestamp and call the same one-step FBS contract repeatedly.  
**Done when:** Time-series 5-bus simulation works without changing `fbs.py`'s public interface.

## Task 18 — Verify V1 network implementation
**Start:** 12 Oct 2026  
**Deadline:** 15 Oct 2026  
**What to do:** Check time-series outputs, power balance, data-interface behavior and error handling; fix implementation problems.  
**Done when:** V1 is stable enough for BESS integration.

## Task 19 — Write Chapter 4: V1 network implementation
**Start:** 14 Oct 2026  
**Deadline:** 17 Oct 2026  
**Done when:** Chapter 4 V1 draft documents the implemented design, trials/problems and verification evidence.

---

# V2 — Fixed BESS

## Task 20 — Implement the BESS configuration/state structures
**Start:** 3 Oct 2026  
**Deadline:** 5 Oct 2026  
**Design reference:** `TERM2_SOFTWARE_DESIGN_SPEC.md` §6  
**What to do:** Implement the specified `BESSConfig` and `BESSState` structures using the retained BESS baseline.  
**Done when:** Configuration/state objects match the design contract.

## Task 21 — Implement the BESS SOC/energy step
**Start:** 4 Oct 2026  
**Deadline:** 7 Oct 2026  
**What to do:** Implement the documented `step_bess()` energy/SOC update and sign convention.  
**Done when:** `BESSStepResult` is correct for simple charge/discharge checks.

## Task 22 — Implement BESS operating limits
**Start:** 6 Oct 2026  
**Deadline:** 8 Oct 2026  
**What to do:** Enforce SOC/power/efficiency/no-simultaneous-charge-discharge behavior through the documented interface and report clipping/limit reason.  
**Done when:** BESS limits are enforced without hidden state changes.

## Task 23 — Connect the fixed BESS through `simulation.py`
**Start:** 9 Oct 2026  
**Deadline:** 11 Oct 2026  
**Design reference:** `TERM2_SOFTWARE_DESIGN_SPEC.md` §§6–7  
**What to do:** Follow the defined flow: requested action → feasible BESS injection/state → `OperatingPoint` → `fbs.py`.  
**Done when:** BESS changes network injection through the public simulation interface.

## Task 24 — Run fixed-BESS time series
**Start:** 11 Oct 2026  
**Deadline:** 13 Oct 2026  
**Done when:** Full V2 time-series simulation completes with SOC and network results.

## Task 25 — Verify V2 BESS implementation
**Start:** 13 Oct 2026  
**Deadline:** 15 Oct 2026  
**Done when:** Hand SOC/energy checks, operating-limit tests and network interaction checks pass.

## Task 26 — Write Chapter 4: V2 BESS implementation
**Start:** 15 Oct 2026  
**Deadline:** 17 Oct 2026  
**Done when:** Chapter 4 V2 draft documents the implemented BESS contract, trials and fixes.

---

# V3 — Manual BESS trials

## Task 27 — Choose manual test cases
**Start / Deadline:** 16 Oct 2026  
**What to do:** Pick a small test set within the already-defined candidate/bounds rules.  
**Done when:** Manual comparison table is planned.

## Task 28 — Compare BESS locations
**Start:** 16 Oct 2026  
**Deadline:** 18 Oct 2026  
**Done when:** Location-comparison results exist using the same public simulator/evaluator.

## Task 29 — Compare BESS P and E sizes
**Start:** 16 Oct 2026  
**Deadline:** 18 Oct 2026  
**Done when:** Size-comparison results exist.

## Task 30 — Summarize what changes the result
**Start:** 18 Oct 2026  
**Deadline:** 20 Oct 2026  
**Done when:** V3 reference results explain the observed effects of B, P and E.

## Task 31 — Write Chapter 4 V3 + prepare Progress Update content
**Start:** 20 Oct 2026  
**Deadline:** 22 Oct 2026  
**Done when:** V3 Chapter 4 draft and Progress Update technical content are ready.

---

# V4 — Deterministic optimization

## Task 32 — Implement cost / curtailment / shedding metrics
**Start:** 22 Oct 2026  
**Deadline:** 25 Oct 2026  
**Design reference:** `TERM2_SOFTWARE_DESIGN_SPEC.md` §7  
**What to do:** Implement `metrics.py` against standardized simulation results; keep metric calculation separate from optimizer search logic.  
**Done when:** Evaluator returns all required main metrics through the documented interface.

## Task 33 — Implement the Term 1 WSM objective
**Start:** 24 Oct 2026  
**Deadline:** 27 Oct 2026  
**Design gate:** Confirm/document normalization before coding it.  
**What to do:** Apply the existing Term 1 weights through the evaluator using an explicit confirmed normalization method. Do not hide an arbitrary normalization rule in code.  
**Done when:** Working WSM fitness uses a documented normalization method.

## Task 34 — Implement GWO candidate variables
**Start:** 25 Oct 2026  
**Deadline:** 29 Oct 2026  
**Design reference:** `TERM2_SOFTWARE_DESIGN_SPEC.md` §7  
**What to do:** Use the predefined `BESSCandidate` / `[B,P,E]` interface; do not duplicate BESS/network equations.  
**Done when:** GWO creates valid candidates.

## Task 35 — Connect GWO to the simulator
**Start:** 28 Oct 2026  
**Deadline:** 1 Nov 2026  
**What to do:** Evaluate each candidate using the same public simulation/evaluator path used by manual trials.  
**Done when:** GWO scores real simulation results without duplicated physics.

## Task 36 — Run deterministic GWO
**Start:** 31 Oct 2026  
**Deadline:** 3 Nov 2026  
**Done when:** First automatic BESS result and convergence history exist.

## Task 37 — Build exhaustive-search reference
**Start:** 29 Oct 2026  
**Deadline:** 2 Nov 2026  
**Done when:** Small-case reference optimum exists.

## Task 38 — Compare GWO with exhaustive search
**Start:** 2 Nov 2026  
**Deadline:** 4 Nov 2026  
**Done when:** GWO result quality/runtime are compared with the reference.

## Task 39 — Test GWO population and iterations
**Start:** 3 Nov 2026  
**Deadline:** 5 Nov 2026  
**Done when:** GWO-setting comparison exists.

## Task 40 — Write Chapter 4: V4 GWO implementation
**Start:** 5 Nov 2026  
**Deadline:** 7 Nov 2026  
**Done when:** Chapter 4 V4 draft exists.

---

# Chapter 5 planning

## Task 41 — Design Chapter 5 validation experiments
**Start:** 5 Nov 2026  
**Deadline:** 7 Nov 2026  
**What to do:** Map every Term 1 requirement to a formal experiment/direct check and define objective, background, steps, tools, required figures/tables/data and analysis method.  
**Done when:** Experiment plan + requirement-to-evidence map exist.

---

# V5 — Uncertainty

## Task 42 — Implement ARIMA
**Start:** 27 Oct 2026  
**Deadline:** 1 Nov 2026  
**Design reference:** `TERM2_SOFTWARE_DESIGN_SPEC.md` §7  
**What to do:** Implement the retained ARIMA method behind the future uncertainty/scenario interface rather than coupling it directly to optimizer internals.  
**Done when:** Forecast is produced through the planned uncertainty interface.

## Task 43 — Verify ARIMA forecast accuracy
**Start:** 1 Nov 2026  
**Deadline:** 2 Nov 2026  
**Done when:** Held-out RMSE/MAPE and comparison plots exist.

## Task 44 — Generate 100 Monte Carlo scenarios
**Start:** 2 Nov 2026  
**Deadline:** 4 Nov 2026  
**Design reference:** `TERM2_SOFTWARE_DESIGN_SPEC.md` §7  
**What to do:** Generate the retained 100 scenarios and store them using `Scenario/ScenarioSet` so they reuse `ProfileData` and the normal simulation pipeline.  
**Done when:** 100 reproducible scenarios are in the standard scenario structure.

## Task 45 — Select the 45 Term 1 scenarios
**Start:** 4 Nov 2026  
**Deadline:** 5 Nov 2026  
**Design gate:** Confirm/document the best/worst ranking metric before coding the selector.  
**What to do:** Apply the retained 15 best + 15 worst + 15 random method to `ScenarioSet` using the confirmed explicit rule.  
**Done when:** 45 retained scenarios are available through the standard interface.

## Task 46 — Verify scenario realism
**Start:** 5 Nov 2026  
**Deadline:** 6 Nov 2026  
**Done when:** Scenario range/shape/variation/PV-limit checks are recorded.

## Task 47 — Run GWO for the 45 scenarios
**Start:** 5 Nov 2026  
**Deadline:** 9 Nov 2026  
**Done when:** Scenario optimization results exist through the same public optimizer/simulator contracts.

## Task 48 — Apply WSM to the scenario results
**Start:** 8 Nov 2026  
**Deadline:** 10 Nov 2026  
**Done when:** Term 1 uncertainty recommendation is produced.

## Task 49 — Verify V5 uncertainty workflow
**Start:** 10 Nov 2026  
**Deadline:** 11 Nov 2026  
**Done when:** Full ARIMA → MC → ScenarioSet selection → GWO/WSM workflow is verified or a real issue is documented.

## Task 50 — Write Chapter 4: V5 uncertainty implementation
**Start:** 11 Nov 2026  
**Deadline:** 13 Nov 2026  
**Done when:** Chapter 4 V5 draft exists.

---

# V6 — Software integration

## Task 51 — Sketch the simple UI
**Start:** 5 Nov 2026  
**Deadline:** 7 Nov 2026  
**Design reference:** `TERM2_SOFTWARE_DESIGN_SPEC.md` §2  
**What to do:** Create a UI wireframe that calls public backend interfaces only; no engineering calculations should be moved into UI code.  
**Done when:** Minimum UI workflow is consistent with backend architecture.

## Task 52 — Build network / data input UI
**Start:** 7 Nov 2026  
**Deadline:** 10 Nov 2026  
**What to do:** Build input controls around predefined `NetworkModel`/`ProfileData` loaders.  
**Done when:** UI supplies the documented backend inputs without source-code edits.

## Task 53 — Connect baseline simulation to UI
**Start:** 9 Nov 2026  
**Deadline:** 11 Nov 2026  
**What to do:** Call the public baseline simulation interface and display required result fields; do not call FBS internals directly.  
**Done when:** Baseline simulation runs from UI through the documented backend interface.

## Task 54 — Connect optimization and results to UI
**Start:** 11 Nov 2026  
**Deadline:** 14 Nov 2026  
**What to do:** Call the public optimizer/result interfaces and display B, P, E and main metrics.  
**Done when:** Optimization works from UI without embedding backend engineering logic.

## Task 55 — Add progress, errors and save results
**Start:** 14 Nov 2026  
**Deadline:** 15 Nov 2026  
**Done when:** Basic error/progress handling and save/export work.

## Task 56 — Run one full end-to-end test
**Start:** 15 Nov 2026  
**Deadline:** 16 Nov 2026  
**Done when:** Full workflow works without manual source-code edits.

## Task 57 — Write Chapter 4: V6 software integration
**Start:** 16 Nov 2026  
**Deadline:** 18 Nov 2026  
**Done when:** Final software-integration draft with screenshots exists.

---

# Validation experiments

## Task 58 — Experiment 1: Technical and economic performance
**Start:** 16 Nov 2026  
**Deadline:** 19 Nov 2026  
**Done when:** Formal experiment covers shedding, curtailment, cost, voltage and SOC/DoD requirements with figures/tables and conclusions.

## Task 59 — Experiment 2: Optimizer and uncertainty requirements
**Start:** 19 Nov 2026  
**Deadline:** 21 Nov 2026  
**Done when:** Scenario-count, GWO convergence/iteration and retained-scenario evidence is documented.

## Task 60 — Experiment 3: Network scalability
**Start:** 19 Nov 2026  
**Deadline:** 22 Nov 2026  
**Done when:** IEEE 33-bus scalability experiment is complete using the same generic `NetworkModel`/FBS interfaces.

## Task 61 — Complete Chapter 5 validation results
**Start:** 22 Nov 2026  
**Deadline:** 24 Nov 2026  
**Done when:** Formal experiments + requirement-evidence summary are complete.

---

# Final verification and report

## Task 62 — Test common software failure cases
**Start:** 15 Nov 2026  
**Deadline:** 18 Nov 2026  
**Done when:** Bad files, missing data, invalid bounds, disconnected network and failed optimization are handled/recorded through the documented module boundaries.

## Task 63 — Freeze final cases and outputs
**Start:** 24 Nov 2026  
**Deadline:** 25 Nov 2026  
**Done when:** Exact inputs, settings, seeds, plots and tables used in the report are saved.

## Task 64 — Merge and polish Chapter 4 to template
**Start:** 18 Nov 2026  
**Deadline:** 26 Nov 2026  
**Done when:** Chapter 4 contains practical implementation details, trials, design calculations, justified design changes and final screenshots/images.

## Task 65 — Finish Chapter 5, Chapter 6 and Appendix D
**Start:** 26 Nov 2026  
**Deadline:** 29 Nov 2026  
**Done when:** Chapters 5–6 + Appendix D match the official template and are ready for the 30 Nov report submission.

---

# Final presentation

## Task 66 — Prepare and deliver final presentation/demo
**Start:** 1 Dec 2026  
**Deadline/window:** 6–10 Dec 2026  
**What to do:** Prepare slides, select final figures, rehearse the software demo, run a clean reproducibility check and fix only critical demo issues.  
**Done when:** Final presentation/demo is ready and delivered.
