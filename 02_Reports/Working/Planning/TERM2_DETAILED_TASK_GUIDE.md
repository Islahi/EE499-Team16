# Term 2 Detailed Task Guide

**Schedule:** 20 September 2026 → 31 December 2026  
**Main rule:** Start from the Term 1 design. Implement it first, test it, and only change it when there is a clear reason.

This file explains the tasks in more detail than the Gantt sheet. The Google Sheet is still the main place to update **Owner, Status, Progress, Start/End dates, and dependencies**.

## How to read each task

For every task:

- **Start** = when we should begin.
- **Deadline** = internal date we want it finished.
- **What to do** = the actual work.
- **Done when / Deliverable** = what must exist before we mark it Done.
- **Depends on** = task(s) that should already be completed or stable.
- **Report connection** = where the result is likely to be used later.
- **Important note** = simple warning or guidance so we do not overcomplicate the task.

---

# Data

## Task 1 — Define the data we need

**Start:** 9/20/2026  
**Deadline:** 9/21/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** None

### What to do

Write a short list of the data needed for load, PV/weather, network and BESS/economic values.

### Done when / Deliverable

One clear data checklist.

### Report connection

Working project data/support material. Results may be referenced later in Chapter 4 or Chapter 5.

### Important note

Keep this simple. We only need to know exactly what files/fields we are looking for before searching.

---

## Task 2 — Get load data

**Start:** 9/20/2026  
**Deadline:** 9/24/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 1

### What to do

Find one usable historical load profile and record the source, unit, time step and date range.

### Done when / Deliverable

Load dataset ready.

### Report connection

Working project data/support material. Results may be referenced later in Chapter 4 or Chapter 5.

### Important note

Prefer data that has enough history and a clear time step. Record the source immediately so we do not lose it later.

---

## Task 3 — Get PV / weather data

**Start:** 9/20/2026  
**Deadline:** 9/24/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 1

### What to do

Find irradiance, weather or PV generation data that can be matched with the load data.

### Done when / Deliverable

PV/weather dataset ready.

### Report connection

Working project data/support material. Results may be referenced later in Chapter 4 or Chapter 5.

### Important note

Make sure the PV/weather data can be converted into the same time base as the load data.

---

## Task 4 — Get network data

**Start:** 9/22/2026  
**Deadline:** 9/24/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 1

### What to do

Prepare a small 5-bus test case and the IEEE 33-bus data for later use.

### Done when / Deliverable

5-bus + IEEE 33-bus data ready.

### Report connection

Working project data/support material. Results may be referenced later in Chapter 4 or Chapter 5.

### Important note

The 5-bus case is only for learning/debugging. IEEE 33-bus remains the main larger benchmark.

---

## Task 5 — Check the selected data

**Start:** 9/23/2026  
**Deadline:** 9/25/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 2,3,4

### What to do

Check source, units, timestamps, missing values and whether the data can be used together.

### Done when / Deliverable

Short data quality note.

### Report connection

Working project data/support material. Results may be referenced later in Chapter 4 or Chapter 5.

### Important note

This is a quick sanity check, not a research paper. The goal is to avoid using bad or incompatible data.

---

## Task 6 — Clean and align the data

**Start:** 9/24/2026  
**Deadline:** 9/26/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 2,3

### What to do

Fix missing values where needed and put load/PV data on the same time step and units.

### Done when / Deliverable

Simulation-ready load/PV files.

### Report connection

Working project data/support material. Results may be referenced later in Chapter 4 or Chapter 5.

### Important note

Do not change the original raw files. Keep a cleaned copy so we can reproduce the process.

---

## Task 7 — Prepare data for advisor

**Start:** 9/25/2026  
**Deadline:** 9/27/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 5,6

### What to do

Prepare source links, sample plots, data summary and questions for the advisor.

### Done when / Deliverable

Advisor data package.

### Report connection

Working project data/support material. Results may be referenced later in Chapter 4 or Chapter 5.

### Important note

Bring evidence, not only links: plots, file samples, units, coverage and questions.

---

# Ethics

## Task 8 — Write ethics / responsibility notes

**Start:** 9/27/2026  
**Deadline:** 10/3/2026  
**Priority:** Medium  
**Current owner:** Team  
**Depends on:** 5

### What to do

List the main issues: honest data use, assumptions, model limits, grid reliability and responsible use of recommendations.

### Done when / Deliverable

Working ethics note for Appendix D.

### Report connection

Appendix D / ethics notes; can also support Chapter 6.2.

### Important note

Keep the wording practical: what can go wrong, what assumption may mislead the user, and how we will communicate limits.

---

# Shadow Design

## Task 9 — Confirm the implementation baseline

**Start:** 9/27/2026  
**Deadline:** 9/29/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 7

### What to do

Use the Term 1 design as the starting point and review the shadow design before coding. Do not change Term 1 methods unless a real need appears.

### Done when / Deliverable

Shadow design accepted as starting baseline.

### Report connection

Internal shadow design / setup. This supports implementation but does not rewrite Chapters 1–3.

### Important note

This is mainly a review task. Read the Term 1 design and shadow design, confirm the starting methods, and note only obvious gaps needed for coding.

---

# Setup

## Task 10 — Set up the code structure

**Start:** 9/30/2026  
**Deadline:** 10/3/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 9

### What to do

Create simple folders/modules for data, network, BESS, optimization, uncertainty and results. Keep it easy to change later.

### Done when / Deliverable

Runnable project structure.

### Report connection

Internal shadow design / setup. This supports implementation but does not rewrite Chapters 1–3.

### Important note

Do not over-engineer folders/classes. We need a clean starting structure that can grow with V1–V6.

---

## Task 11 — Define basic input / output formats

**Start:** 10/1/2026  
**Deadline:** 10/4/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 9,10

### What to do

Decide how network data, time-series data, BESS settings and simulation results will be stored between modules.

### Done when / Deliverable

Simple data format/interface note.

### Report connection

Internal shadow design / setup. This supports implementation but does not rewrite Chapters 1–3.

### Important note

Focus on simple inputs/outputs between modules. Example: what goes into the network simulator and what results come out.

---

# V1 - Network

## Task 12 — Prepare the 5-bus test case

**Start:** 10/2/2026  
**Deadline:** 10/5/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 4,11

### What to do

Create one small radial network that is easy to understand and debug.

### Done when / Deliverable

5-bus case ready for power flow.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Use values that are easy to verify manually. The network should be small enough that we understand every bus and line.

---

## Task 13 — Implement FBS for one time step

**Start:** 10/4/2026  
**Deadline:** 10/10/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 12

### What to do

Implement the Forward-Backward Sweep method from Term 1 for one static network condition.

### Done when / Deliverable

FBS runs on the 5-bus case.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Start with one static operating point. Do not add time series, BESS or optimization yet.

---

## Task 14 — Check the FBS result

**Start:** 10/8/2026  
**Deadline:** 10/12/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 13

### What to do

Compare voltages, power balance and losses with a trusted/reference result or simple manual checks.

### Done when / Deliverable

Static power-flow check completed.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

If the result disagrees with the reference, stop and fix FBS before going further.

---

## Task 15 — Show basic network results

**Start:** 10/10/2026  
**Deadline:** 10/14/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 14

### What to do

Create simple tables/plots for bus voltage, line loading/current, losses and source power.

### Done when / Deliverable

Readable V1 result output.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Plots do not need to be fancy. They only need to make wrong voltages/losses/loading easy to notice.

---

## Task 16 — Import load and PV profiles

**Start:** 10/11/2026  
**Deadline:** 10/15/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 6,10

### What to do

Read the cleaned load/PV files and check timestamp, length, unit and scaling before simulation.

### Done when / Deliverable

Profiles load correctly.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Check units carefully. A correct file with the wrong kW/MW scale can ruin the whole simulation.

---

## Task 17 — Add the hourly simulation loop

**Start:** 10/14/2026  
**Deadline:** 10/18/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 15,16

### What to do

Run the network over the full time series instead of only one time step.

### Done when / Deliverable

Time-series 5-bus simulation works.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

The main goal is to repeat the same validated power flow for each hour using changing load/PV values.

---

## Task 18 — Validate V1

**Start:** 10/17/2026  
**Deadline:** 10/21/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 14,17

### What to do

Check the time-series power flow, outputs and power balance. Fix V1 before adding the battery.

### Done when / Deliverable

V1 accepted as stable baseline.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

V1 is complete only when we trust the network engine enough to build the battery on top of it.

---

# V2 - BESS

## Task 19 — Set the starting BESS parameters

**Start:** 10/18/2026  
**Deadline:** 10/20/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 9

### What to do

Use the Term 1 BESS model as the baseline: P, E, SOC limits, efficiency and initial/final SOC rules.

### Done when / Deliverable

BESS settings written in code/config.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Use the Term 1 BESS values/rules first. Do not redesign the battery model here.

---

## Task 20 — Implement SOC update

**Start:** 10/19/2026  
**Deadline:** 10/23/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 19

### What to do

Code the battery energy/SOC update for charging and discharging.

### Done when / Deliverable

SOC changes correctly for simple tests.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Test charging and discharging separately using simple numbers that can be checked by hand.

---

## Task 21 — Add charge / discharge limits

**Start:** 10/21/2026  
**Deadline:** 10/25/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 20

### What to do

Enforce SOC, power, efficiency and no simultaneous charge/discharge rules.

### Done when / Deliverable

Battery limits enforced.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Try boundary cases such as full battery, empty battery and command above the power limit.

---

## Task 22 — Connect a fixed BESS to the network

**Start:** 10/23/2026  
**Deadline:** 10/27/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 15,21

### What to do

Place one fixed BESS at a chosen bus and make its charging/discharging affect the power flow.

### Done when / Deliverable

Fixed BESS changes network injection.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

The battery power must change the bus injection seen by the power-flow model.

---

## Task 23 — Run fixed-BESS time series

**Start:** 10/26/2026  
**Deadline:** 10/30/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 17,22

### What to do

Run the 5-bus time series with one fixed BESS and save SOC/network results.

### Done when / Deliverable

Full V2 simulation completed.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Save SOC and network outputs for every hour so problems can be traced later.

---

## Task 24 — Validate V2

**Start:** 10/29/2026  
**Deadline:** 11/2/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 23

### What to do

Check SOC by hand for simple steps and test SOC/power limits and network interaction.

### Done when / Deliverable

V2 battery model validated.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

If SOC or power limits fail, do not continue to optimization yet.

---

# V3 - Manual Compare

## Task 25 — Choose manual test cases

**Start:** 11/1/2026  
**Deadline:** 11/2/2026  
**Priority:** Medium  
**Current owner:** Team  
**Depends on:** 24

### What to do

Pick a small set of buses, power ratings and energy capacities to compare before using GWO.

### Done when / Deliverable

Manual comparison table planned.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Keep the set small. The purpose is understanding, not finding the final optimum manually.

---

## Task 26 — Compare BESS locations

**Start:** 11/2/2026  
**Deadline:** 11/5/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 25

### What to do

Keep P and E fixed and move the battery between selected buses. Compare the results.

### Done when / Deliverable

Location comparison results.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Only change bus location here so we can see the effect of location clearly.

---

## Task 27 — Compare BESS P and E sizes

**Start:** 11/4/2026  
**Deadline:** 11/7/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 25

### What to do

Keep location controlled and compare different battery power and energy sizes.

### Done when / Deliverable

Size comparison results.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Separate power P from energy E. They are different decisions and should not be treated as the same value.

---

## Task 28 — Summarize what changes the result

**Start:** 11/6/2026  
**Deadline:** 11/9/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 26,27

### What to do

Write a short note showing how location, power and energy affect voltage, cost, curtailment or shedding.

### Done when / Deliverable

V3 reference results ready.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

This becomes our expectation/reference before GWO. If GWO later gives a strange result, compare it with these cases.

---

# V4 - Optimization

## Task 29 — Implement cost / curtailment / shedding metrics

**Start:** 11/7/2026  
**Deadline:** 11/11/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 28

### What to do

Code the same main performance terms used in the Term 1 objective and make sure each one can be calculated separately.

### Done when / Deliverable

Evaluator returns all main metrics.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Calculate every metric separately first. Do not immediately hide everything inside one fitness number.

---

## Task 30 — Implement the Term 1 WSM objective

**Start:** 11/9/2026  
**Deadline:** 11/12/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 29

### What to do

Combine the Term 1 criteria using the 0.50 / 0.25 / 0.25 baseline weights and clearly handle their scales/normalization.

### Done when / Deliverable

Working WSM fitness value.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Keep the Term 1 0.50/0.25/0.25 starting weights. Clearly document any normalization needed to combine different units.

---

## Task 31 — Implement GWO candidate variables

**Start:** 11/11/2026  
**Deadline:** 11/17/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 30

### What to do

Implement GWO using BESS location B, power P and energy E as the candidate solution.

### Done when / Deliverable

GWO can create valid B,P,E candidates.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Make sure invalid bus/P/E candidates are corrected or rejected consistently.

---

## Task 32 — Connect GWO to the simulator

**Start:** 11/15/2026  
**Deadline:** 11/20/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 31

### What to do

For every wolf, run the battery/network simulation and return the WSM fitness plus constraint handling.

### Done when / Deliverable

GWO evaluates real simulation results.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

This is the key integration point: GWO proposes a battery, the simulator tests it, and the evaluator gives the fitness back.

---

## Task 33 — Run deterministic GWO

**Start:** 11/19/2026  
**Deadline:** 11/22/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 32

### What to do

Run GWO using one deterministic load/PV profile and save convergence and best BESS result.

### Done when / Deliverable

First automatic BESS result.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Save the convergence history and final B, P and E. We need this later for validation and the report.

---

## Task 34 — Build exhaustive-search reference

**Start:** 11/20/2026  
**Deadline:** 11/24/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 28,30

### What to do

On the small 5-bus case, test a limited set of all allowed B,P,E combinations to find a known reference best result.

### Done when / Deliverable

Reference optimum for small case.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Keep the search space deliberately small so exhaustive search is possible.

---

## Task 35 — Compare GWO with exhaustive search

**Start:** 11/23/2026  
**Deadline:** 11/27/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 33,34

### What to do

Check whether GWO reaches the same or close result and record the difference and runtime.

### Done when / Deliverable

GWO validation result.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

We do not need GWO to match every decimal. We need evidence that it reaches the same/near-optimum solution reliably.

---

## Task 36 — Test GWO population and iterations

**Start:** 11/25/2026  
**Deadline:** 11/29/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 35

### What to do

Try a few population sizes and iteration limits to see their effect on result quality and runtime.

### Done when / Deliverable

GWO setting comparison.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

This directly answers the reviewer question about GWO population and iteration settings.

---

# V5 - Uncertainty

## Task 37 — Implement ARIMA

**Start:** 11/22/2026  
**Deadline:** 11/28/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 6

### What to do

Use the Term 1 ARIMA method on the selected historical data and generate forecasts.

### Done when / Deliverable

ARIMA forecast working.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Follow the Term 1 ARIMA baseline first. Do not replace it before testing it on the chosen data.

---

## Task 38 — Validate ARIMA

**Start:** 11/27/2026  
**Deadline:** 12/1/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 37

### What to do

Compare forecast and historical test data using RMSE, MAPE and simple plots.

### Done when / Deliverable

ARIMA validation results.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Use held-out data. A forecast that is only checked on the training data is not a useful validation.

---

## Task 39 — Generate 100 Monte Carlo scenarios

**Start:** 11/29/2026  
**Deadline:** 12/3/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 38

### What to do

Use the ARIMA/error behavior to generate the 100 scenarios described in the Term 1 design.

### Done when / Deliverable

100 load/PV scenarios generated.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Keep the generation method reproducible where possible, for example by saving random seeds/settings.

---

## Task 40 — Select the 45 Term 1 scenarios

**Start:** 12/2/2026  
**Deadline:** 12/5/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 39

### What to do

Select 15 best, 15 worst and 15 random scenarios using clear rules.

### Done when / Deliverable

45 baseline scenarios ready.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Use the same best/worst/random logic described in Term 1 and write the exact rule used in code.

---

## Task 41 — Check scenario realism

**Start:** 12/4/2026  
**Deadline:** 12/7/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 39,40

### What to do

Compare generated scenarios with historical data using range, mean, variation and profile shape. Check PV physical limits.

### Done when / Deliverable

Scenario quality check.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Generated scenarios should look like realistic load/PV profiles, not only pass a code check.

---

## Task 42 — Run GWO for the 45 scenarios

**Start:** 12/5/2026  
**Deadline:** 12/10/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 33,40

### What to do

Use the implemented GWO and simulation on the retained scenarios as described in Term 1.

### Done when / Deliverable

Scenario optimization results.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

This may be computationally heavy. Save each scenario result so a failed run does not force us to restart everything.

---

## Task 43 — Apply WSM to the scenario results

**Start:** 12/9/2026  
**Deadline:** 12/12/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 42

### What to do

Apply the Term 1 WSM process to the scenario outputs and produce the baseline uncertainty recommendation.

### Done when / Deliverable

Term 1 uncertainty workflow completed.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Reproduce the Term 1 WSM scenario comparison first before introducing a new uncertainty formulation.

---

## Task 44 — Validate the V5 result

**Start:** 12/11/2026  
**Deadline:** 12/14/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 41,43

### What to do

Check whether the uncertainty workflow gives one clear, usable BESS recommendation and identify any real problem before changing the method.

### Done when / Deliverable

V5 baseline accepted or issue documented.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

This is the decision gate: if V5 gives a clear usable result, keep it. If not, document the exact problem before changing anything.

---

# V6 - Software

## Task 45 — Sketch the simple UI

**Start:** 12/1/2026  
**Deadline:** 12/4/2026  
**Priority:** Medium  
**Current owner:** Team  
**Depends on:** 9

### What to do

Plan only the screens needed for network/data input, baseline run, optimization and results.

### Done when / Deliverable

Simple UI sketch/workflow.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Sketch first. We only need the minimum useful screens and buttons.

---

## Task 46 — Build network / data input UI

**Start:** 12/4/2026  
**Deadline:** 12/8/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 45,17

### What to do

Let the user load or enter the network and load/PV data without editing source code.

### Done when / Deliverable

Input screen working.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

The user should not need to edit Python files to change the main input data.

---

## Task 47 — Connect baseline simulation to UI

**Start:** 12/7/2026  
**Deadline:** 12/10/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 46,18

### What to do

Add a button/workflow to run V1 and show the main baseline results.

### Done when / Deliverable

Baseline run works from UI.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Get the baseline simulation working from the UI before adding optimization buttons.

---

## Task 48 — Connect optimization and results to UI

**Start:** 12/10/2026  
**Deadline:** 12/14/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 43,47

### What to do

Run the V4/V5 backend from the UI and show selected bus, P, E and main technical/economic results.

### Done when / Deliverable

Optimization works from UI.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Show at least selected bus B, power P, energy E and the main before/after metrics.

---

## Task 49 — Add progress, errors and save results

**Start:** 12/13/2026  
**Deadline:** 12/16/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 48

### What to do

Show useful error messages/progress and allow key results to be saved/exported.

### Done when / Deliverable

Basic software usability completed.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

Useful error messages are more important than visual polish.

---

## Task 50 — Run one full end-to-end test

**Start:** 12/15/2026  
**Deadline:** 12/18/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 49

### What to do

Start from input files and run the full workflow to the final BESS result without manual code edits.

### Done when / Deliverable

V6 full workflow works.

### Report connection

Mainly Chapter 4 — Implementation. Validation evidence from these tasks may also be reused in Chapter 5.

### Important note

This is the first proof that the program works as one product, not separate scripts.

---

# Validation

## Task 51 — Compare no BESS vs optimized BESS

**Start:** 12/17/2026  
**Deadline:** 12/20/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 44,50

### What to do

Use the same network/data and compare voltage, losses, cost, curtailment and shedding before and after BESS.

### Done when / Deliverable

Main before/after results.

### Report connection

Mainly Chapter 5 — Validation Experiments. Main conclusions also support Chapter 6.

### Important note

Use exactly the same data/case for before and after so the comparison is fair.

---

## Task 52 — Run sensitivity checks

**Start:** 12/18/2026  
**Deadline:** 12/22/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 36,44,51

### What to do

Test the items reviewers questioned: scenario count, GWO population/iterations and WSM weights. Change only if results show a real need.

### Done when / Deliverable

Sensitivity results and any justified change.

### Report connection

Mainly Chapter 5 — Validation Experiments. Main conclusions also support Chapter 6.

### Important note

This is where we test the choices reviewers questioned. Do not change a baseline setting until the sensitivity result shows a reason.

---

## Task 53 — Run the IEEE 33-bus case

**Start:** 12/20/2026  
**Deadline:** 12/24/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 18,44

### What to do

Move the stable framework to the IEEE 33-bus system and run the baseline and optimized case.

### Done when / Deliverable

IEEE 33-bus final case results.

### Report connection

Mainly Chapter 5 — Validation Experiments. Main conclusions also support Chapter 6.

### Important note

Do not rewrite the program specifically for 33 buses. The same framework should scale to it.

---

# Software Testing

## Task 54 — Test common failure cases

**Start:** 12/21/2026  
**Deadline:** 12/25/2026  
**Priority:** High  
**Current owner:** Team  
**Depends on:** 50

### What to do

Try bad files, missing data, disconnected network, invalid BESS limits and failed optimization. Fix the important cases.

### Done when / Deliverable

Software failure test record.

### Report connection

Mainly Chapter 5 — Validation Experiments. Main conclusions also support Chapter 6.

### Important note

Test realistic mistakes a user may make. The program should fail clearly, not silently give nonsense results.

---

# Final Results

## Task 55 — Freeze final cases and outputs

**Start:** 12/24/2026  
**Deadline:** 12/26/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 51,52,53,54

### What to do

Stop changing the main setup. Save exact inputs, settings, seeds, plots and tables used in the final report.

### Done when / Deliverable

Reproducible final results package.

### Report connection

Mainly Chapter 5 — Validation Experiments. Main conclusions also support Chapter 6.

### Important note

After this task, treat the main results as frozen. Only fix critical errors.

---

# Documentation

## Task 56 — Write Chapter 4 implementation

**Start:** 12/18/2026  
**Deadline:** 12/27/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 50

### What to do

Write what was actually built, the V1–V6 path, trials, problems and any justified change from the Term 1 baseline.

### Done when / Deliverable

Chapter 4 updated from real implementation.

### Report connection

Chapter 4 — Implementation.

### Important note

Write from the real implementation, not from what we originally planned. Mention important trials and justified changes.

---

## Task 57 — Write Chapter 5 and final discussion

**Start:** 12/23/2026  
**Deadline:** 12/29/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 55,56

### What to do

Add validation experiments/results, update Chapter 6 discussion/conclusion, and finish ethics/professional responsibility material.

### Done when / Deliverable

Final validation/discussion sections ready.

### Report connection

Chapter 5 + Chapter 6 + Appendix D as needed.

### Important note

Chapter 5 should show evidence; Chapter 6 should explain what the evidence means and whether requirements were met.

---

# Finalization

## Task 58 — Prepare demo and final QA

**Start:** 12/27/2026  
**Deadline:** 12/31/2026  
**Priority:** Critical  
**Current owner:** Team  
**Depends on:** 55,56,57

### What to do

Prepare the presentation/demo, run one clean reproducibility check, fix final critical issues and make the submission package ready.

### Done when / Deliverable

Demo + submission-ready project.

### Report connection

Presentation/demo/submission package; final check against the full report and code.

### Important note

Prepare a backup demo path: saved screenshots/results in case the live run fails during presentation.

---

# Overall checkpoints

## End of September

We should have the main data ready and Task 9 reviewed. At this point we should be able to start coding without another long design phase.

## End of October

V1 should be stable and V2 should be nearly/fully working. We should trust the network power flow and understand the battery SOC model.

## End of November

V3 and V4 should be complete. We should have a deterministic BESS optimizer and evidence that GWO works reasonably compared with exhaustive search.

## Middle of December

V5 and V6 should be working. We should have the Term 1 uncertainty workflow implemented and a simple end-to-end software interface.

## End of December

Finish validation, IEEE 33-bus, final results, Chapters 4–6 updates, demo and final QA.

# Simple decision rule when a task is blocked

If a task cannot be completed:

1. Write the exact problem.
2. Check whether the problem comes from data, model, code, or a Term 1 design choice.
3. Try to fix the implementation first.
4. If the baseline design itself is the problem, record evidence.
5. Only then propose a design change.
6. Put important accepted changes in Chapter 4 and the project decision record when needed.
