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

## How to read this guide

For each task:
- **Start / Deadline** = internal working dates.
- **What to do** = actual work.
- **Done when** = what must exist before marking it complete.

---

# Completed early preparation

## Task 1 — Define the data we need
**Start:** 20 Sep 2026  
**Deadline:** 21 Sep 2026  
**Status:** Done  
**What to do:** List the required load, PV/weather, network and BESS/economic data.  
**Done when:** One clear data checklist exists.

## Task 2 — Get load data
**Start:** 20 Sep 2026  
**Deadline:** 23 Sep 2026  
**Status:** Done  
**What to do:** Find a usable historical load profile and record source, unit, time step and date range.  
**Done when:** Load dataset is ready.

## Task 3 — Get PV / weather data
**Start:** 20 Sep 2026  
**Deadline:** 23 Sep 2026  
**Status:** Done  
**What to do:** Find irradiance/weather/PV data that can be aligned with the load data.  
**Done when:** PV/weather dataset is ready.

## Task 4 — Get network data
**Start:** 21 Sep 2026  
**Deadline:** 23 Sep 2026  
**Status:** Done  
**What to do:** Prepare the small 5-bus development case and IEEE 33-bus data.  
**Done when:** Both network datasets are ready.

## Task 5 — Check the selected data
**Start:** 23 Sep 2026  
**Deadline:** 24 Sep 2026  
**Status:** Done  
**What to do:** Check sources, units, timestamps, missing values and compatibility.  
**Done when:** Short data-quality note exists.

## Task 6 — Clean and align the data
**Start:** 24 Sep 2026  
**Deadline:** 25 Sep 2026  
**Status:** Done  
**What to do:** Fix missing values where needed and align load/PV data to common time steps and units.  
**Done when:** Simulation-ready profiles exist.

## Task 7 — Finalize simulation-ready data package
**Start:** 25 Sep 2026  
**Deadline:** 25 Sep 2026  
**Status:** Done  
**What to do:** Store the cleaned load, PV/weather and network data with source and unit notes. No advisor presentation is required.  
**Done when:** Final simulation-ready data package is stored.

## Task 9 — Finalize implementation baseline
**Start:** 24 Sep 2026  
**Deadline:** 25 Sep 2026  
**Status:** Done  
**What to do:** Confirm the Term 1 implementation choices and the minimum module/interface definitions needed to start coding.  
**Done when:** Implementation baseline is finalized.

---

# Parallel ethics task

## Task 8 — Prepare individual ethical analysis + final-report ethics material
**Start:** 26 Sep 2026  
**Internal draft target:** 7 Oct 2026  
**Priority:** Medium  
**What to do:** Each member prepares the required individual 3–5 page ethical analysis using the SCE Engineer Charter 2025. Cover project context, stakeholders, two ethical issues, alternatives/decision-making, safety/risk/compliance, data/privacy/security, broader impacts, professional integrity, IP/attribution, mitigation and reflection.  
**Done when:** Each member has a usable individual draft/outline and the team has material reusable in Chapter 6.2 and Appendix D.  
**Important:** This task runs in parallel with Tasks 10 onward and should not stop implementation.

---

# Setup

## Task 10 — Set up the code structure
**Start:** 26 Sep 2026  
**Deadline:** 29 Sep 2026  
**What to do:** Create simple folders/modules for data, network, BESS, optimization, uncertainty and results.  
**Done when:** Runnable project structure exists.

## Task 11 — Define basic input / output formats
**Start:** 27 Sep 2026  
**Deadline:** 30 Sep 2026  
**What to do:** Decide how network data, time-series data, BESS settings and simulation results move between modules.  
**Done when:** Simple interface/data-format note exists.

---

# V1 — Network simulator

## Task 12 — Prepare the 5-bus test case
**Start:** 28 Sep 2026  
**Deadline:** 1 Oct 2026  
**What to do:** Create one small radial network that is easy to understand and debug.  
**Done when:** 5-bus case is ready for power flow.

## Task 13 — Implement FBS for one time step
**Start:** 1 Oct 2026  
**Deadline:** 6 Oct 2026  
**What to do:** Implement the Term 1 Forward-Backward Sweep method for one static network condition.  
**Done when:** FBS runs on the 5-bus case.

## Task 14 — Verify the FBS result
**Start:** 5 Oct 2026  
**Deadline:** 8 Oct 2026  
**What to do:** Compare voltages, power balance and losses with a trusted/reference result or simple manual checks.  
**Done when:** FBS result is verified for the small case.

## Task 15 — Show basic network results
**Start:** 7 Oct 2026  
**Deadline:** 10 Oct 2026  
**What to do:** Create simple tables/plots for voltage, line loading/current, losses and source power.  
**Done when:** V1 result output is readable.

## Task 16 — Import load and PV profiles
**Start:** 30 Sep 2026  
**Deadline:** 3 Oct 2026  
**What to do:** Read the cleaned load/PV files and check timestamp, length, unit and scaling.  
**Done when:** Profiles load correctly.

## Task 17 — Add the hourly simulation loop
**Start:** 9 Oct 2026  
**Deadline:** 13 Oct 2026  
**What to do:** Run the network over the full time series.  
**Done when:** Time-series 5-bus simulation works.

## Task 18 — Verify V1 network implementation
**Start:** 12 Oct 2026  
**Deadline:** 15 Oct 2026  
**What to do:** Check time-series outputs and power balance and fix implementation problems.  
**Done when:** V1 is stable enough to build the battery on top of it.

## Task 19 — Write Chapter 4: V1 network implementation
**Start:** 14 Oct 2026  
**Deadline:** 17 Oct 2026  
**What to do:** Write the 5-bus setup, FBS implementation, time-series loop, outputs, trials/problems and checks.  
**Done when:** Chapter 4 V1 draft exists.

---

# V2 — Fixed BESS

## Task 20 — Set the starting BESS parameters
**Start:** 3 Oct 2026  
**Deadline:** 5 Oct 2026  
**What to do:** Use the Term 1 BESS baseline: P, E, SOC limits, efficiency and initial/final SOC rules.  
**Done when:** BESS settings are in code/config.

## Task 21 — Implement SOC update
**Start:** 4 Oct 2026  
**Deadline:** 7 Oct 2026  
**What to do:** Code battery energy/SOC update for charge and discharge.  
**Done when:** SOC changes correctly for simple checks.

## Task 22 — Add charge/discharge limits
**Start:** 6 Oct 2026  
**Deadline:** 8 Oct 2026  
**What to do:** Enforce SOC, power, efficiency and no simultaneous charge/discharge.  
**Done when:** Battery limits are enforced.

## Task 23 — Connect a fixed BESS to the network
**Start:** 9 Oct 2026  
**Deadline:** 11 Oct 2026  
**What to do:** Place one fixed BESS at a chosen bus and make its power affect network injection.  
**Done when:** BESS changes the network simulation correctly.

## Task 24 — Run fixed-BESS time series
**Start:** 11 Oct 2026  
**Deadline:** 13 Oct 2026  
**What to do:** Run the time series with one fixed BESS and save SOC/network results.  
**Done when:** Full V2 simulation completes.

## Task 25 — Verify V2 BESS implementation
**Start:** 13 Oct 2026  
**Deadline:** 15 Oct 2026  
**What to do:** Hand-check SOC and test SOC/power limits and network interaction.  
**Done when:** V2 BESS implementation is verified.

## Task 26 — Write Chapter 4: V2 BESS implementation
**Start:** 15 Oct 2026  
**Deadline:** 17 Oct 2026  
**What to do:** Write battery parameters, SOC update, limits, network connection, time-series behavior and fixes.  
**Done when:** Chapter 4 V2 draft exists.

---

# V3 — Manual BESS trials

## Task 27 — Choose manual test cases
**Start / Deadline:** 16 Oct 2026  
**What to do:** Pick a small set of buses, power ratings and energy capacities.  
**Done when:** Manual comparison table is planned.

## Task 28 — Compare BESS locations
**Start:** 16 Oct 2026  
**Deadline:** 18 Oct 2026  
**What to do:** Keep P and E fixed and move the BESS between selected buses.  
**Done when:** Location-comparison results exist.

## Task 29 — Compare BESS P and E sizes
**Start:** 16 Oct 2026  
**Deadline:** 18 Oct 2026  
**What to do:** Keep location controlled and compare different P/E values.  
**Done when:** Size-comparison results exist.

## Task 30 — Summarize what changes the result
**Start:** 18 Oct 2026  
**Deadline:** 20 Oct 2026  
**What to do:** Explain how location, power and energy affect voltage, cost, curtailment or shedding.  
**Done when:** V3 reference results are ready.

## Task 31 — Write Chapter 4 V3 + prepare Progress Update content
**Start:** 20 Oct 2026  
**Deadline:** 22 Oct 2026  
**What to do:** Document V3 trials and prepare current implementation status, working results, problems, next steps and figures for the Progress Update.  
**Done when:** Chapter 4 V3 draft + Progress Update content are ready.

---

# V4 — Deterministic optimization

## Task 32 — Implement cost / curtailment / shedding metrics
**Start:** 22 Oct 2026  
**Deadline:** 25 Oct 2026  
**Done when:** Evaluator returns all main metrics.

## Task 33 — Implement the Term 1 WSM objective
**Start:** 24 Oct 2026  
**Deadline:** 27 Oct 2026  
**Done when:** Working WSM fitness value exists using the Term 1 baseline weights.

## Task 34 — Implement GWO candidate variables
**Start:** 25 Oct 2026  
**Deadline:** 29 Oct 2026  
**Done when:** GWO creates valid B, P and E candidates.

## Task 35 — Connect GWO to the simulator
**Start:** 28 Oct 2026  
**Deadline:** 1 Nov 2026  
**Done when:** Each candidate can be simulated and scored.

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
**Done when:** GWO result quality and runtime are compared with the reference.

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
**Done when:** ARIMA forecast runs on the selected historical data.

## Task 43 — Verify ARIMA forecast accuracy
**Start:** 1 Nov 2026  
**Deadline:** 2 Nov 2026  
**Done when:** Held-out RMSE/MAPE and comparison plots exist.

## Task 44 — Generate 100 Monte Carlo scenarios
**Start:** 2 Nov 2026  
**Deadline:** 4 Nov 2026  
**Done when:** 100 scenarios are generated reproducibly.

## Task 45 — Select the 45 Term 1 scenarios
**Start:** 4 Nov 2026  
**Deadline:** 5 Nov 2026  
**Done when:** 15 best + 15 worst + 15 random scenarios are selected.

## Task 46 — Verify scenario realism
**Start:** 5 Nov 2026  
**Deadline:** 6 Nov 2026  
**Done when:** Generated scenarios are checked against historical range/shape/variation and PV limits.

## Task 47 — Run GWO for the 45 scenarios
**Start:** 5 Nov 2026  
**Deadline:** 9 Nov 2026  
**Done when:** Scenario optimization results exist.

## Task 48 — Apply WSM to the scenario results
**Start:** 8 Nov 2026  
**Deadline:** 10 Nov 2026  
**Done when:** Term 1 uncertainty recommendation is produced.

## Task 49 — Verify V5 uncertainty workflow
**Start:** 10 Nov 2026  
**Deadline:** 11 Nov 2026  
**Done when:** Full ARIMA → MC → 45 scenarios → GWO/WSM workflow is verified or a real issue is documented.

## Task 50 — Write Chapter 4: V5 uncertainty implementation
**Start:** 11 Nov 2026  
**Deadline:** 13 Nov 2026  
**Done when:** Chapter 4 V5 draft exists.

---

# V6 — Software integration

## Task 51 — Sketch the simple UI
**Start:** 5 Nov 2026  
**Deadline:** 7 Nov 2026  
**Done when:** Minimum screen/workflow sketch exists.

## Task 52 — Build network / data input UI
**Start:** 7 Nov 2026  
**Deadline:** 10 Nov 2026  
**Done when:** User can load/enter the main data without editing code.

## Task 53 — Connect baseline simulation to UI
**Start:** 9 Nov 2026  
**Deadline:** 11 Nov 2026  
**Done when:** Baseline simulation runs from the UI.

## Task 54 — Connect optimization and results to UI
**Start:** 11 Nov 2026  
**Deadline:** 14 Nov 2026  
**Done when:** UI runs optimization and shows selected B, P, E and main results.

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
**Done when:** IEEE 33-bus scalability experiment is complete.

## Task 61 — Complete Chapter 5 validation results
**Start:** 22 Nov 2026  
**Deadline:** 24 Nov 2026  
**Done when:** Formal experiments + requirement-evidence summary are complete.

---

# Final verification and report

## Task 62 — Test common software failure cases
**Start:** 15 Nov 2026  
**Deadline:** 18 Nov 2026  
**Done when:** Bad files, missing data, invalid bounds, disconnected network and failed optimization are handled/recorded.

## Task 63 — Freeze final cases and outputs
**Start:** 24 Nov 2026  
**Deadline:** 25 Nov 2026  
**Done when:** Exact inputs, settings, seeds, plots and tables used in the report are saved.

## Task 64 — Merge and polish Chapter 4 to template
**Start:** 18 Nov 2026  
**Deadline:** 26 Nov 2026  
**Done when:** Chapter 4 contains practical implementation details, trials, design calculations, justified changes and final screenshots/images.

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
