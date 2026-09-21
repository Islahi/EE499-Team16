# Term 2 Detailed Task Guide

**Internal finish:** 31 December 2026

## Official-template rule

This guide now follows **EE499_Final_Report_Template_v2025_Fall**.

- **Chapter 4 — Implementation:** practical implementation details, multiple trials, related design calculations, justified changes from the baseline design, and final-product assembly with multiple images.
- **Chapter 5 — Validation Experiments:** formal experiments on major parts and/or the final product to validate the design specifications.
- Every Chapter 5 experiment must contain: objective, relevant background, detailed work plan/steps, tools, organized figures/tables/data, and analysis/conclusion.
- **Chapter 6:** use the exact template headings: 6.1 Evaluation of Solution, 6.2 Impact of Solution, 6.3 Future Work, 6.4 Conclusion.
- **Appendix D:** code of ethics + project ethical issue + analysis using the code + informed decision.

The Term 1 requirements/specifications remain the main validation reference.

---

## Task 1 — Define the data we need

**Phase:** Data  
**Start:** 9/20/2026  
**Deadline:** 9/21/2026  
**Priority:** Critical  
**Depends on:** None

### What to do

Write a short list of the data needed for load, PV/weather, network and BESS/economic values.

### Done when

One clear data checklist.

### Report placement

Supporting material.

---

## Task 2 — Get load data

**Phase:** Data  
**Start:** 9/20/2026  
**Deadline:** 9/24/2026  
**Priority:** Critical  
**Depends on:** 1

### What to do

Find one usable historical load profile and record the source, unit, time step and date range.

### Done when

Load dataset ready.

### Report placement

Supporting material.

---

## Task 3 — Get PV / weather data

**Phase:** Data  
**Start:** 9/20/2026  
**Deadline:** 9/24/2026  
**Priority:** Critical  
**Depends on:** 1

### What to do

Find irradiance, weather or PV generation data that can be matched with the load data.

### Done when

PV/weather dataset ready.

### Report placement

Supporting material.

---

## Task 4 — Get network data

**Phase:** Data  
**Start:** 9/22/2026  
**Deadline:** 9/24/2026  
**Priority:** Critical  
**Depends on:** 1

### What to do

Prepare a small 5-bus test case and the IEEE 33-bus data for later use.

### Done when

5-bus + IEEE 33-bus data ready.

### Report placement

Supporting material.

---

## Task 5 — Check the selected data

**Phase:** Data  
**Start:** 9/23/2026  
**Deadline:** 9/25/2026  
**Priority:** High  
**Depends on:** 2,3,4

### What to do

Check source, units, timestamps, missing values and whether the data can be used together.

### Done when

Short data quality note.

### Report placement

Supporting material.

---

## Task 6 — Clean and align the data

**Phase:** Data  
**Start:** 9/24/2026  
**Deadline:** 9/26/2026  
**Priority:** Critical  
**Depends on:** 2,3

### What to do

Fix missing values where needed and put load/PV data on the same time step and units.

### Done when

Simulation-ready load/PV files.

### Report placement

Supporting material.

---

## Task 7 — Prepare data for advisor

**Phase:** Data  
**Start:** 9/25/2026  
**Deadline:** 9/27/2026  
**Priority:** Critical  
**Depends on:** 5,6

### What to do

Prepare source links, sample plots, data summary and questions for the advisor.

### Done when

Advisor data package.

### Report placement

Supporting material.

---

## Task 8 — Prepare Appendix D ethics material

**Phase:** Ethics  
**Start:** 9/27/2026  
**Deadline:** 10/3/2026  
**Priority:** Medium  
**Depends on:** 5

### What to do

Choose an appropriate engineering/professional code of ethics, identify one ethical issue related to our project or final software, analyze the issue using the selected code, and record an informed decision. This follows the final-report template Appendix D requirement.

### Done when

Working Appendix D ethics draft with code, issue, analysis and decision.

### Report placement

Appendix D — Recognition of Ethical and Professional Responsibility.

---

## Task 9 — Confirm the implementation baseline

**Phase:** Shadow Design  
**Start:** 9/27/2026  
**Deadline:** 9/29/2026  
**Priority:** Critical  
**Depends on:** 7

### What to do

Use the Term 1 design as the starting point and review the shadow design before coding. Do not change Term 1 methods unless a real need appears.

### Done when

Shadow design accepted as starting baseline.

### Report placement

Chapter 4 — implementation approach/software structure.

---

## Task 10 — Set up the code structure

**Phase:** Setup  
**Start:** 9/30/2026  
**Deadline:** 10/3/2026  
**Priority:** High  
**Depends on:** 9

### What to do

Create simple folders/modules for data, network, BESS, optimization, uncertainty and results. Keep it easy to change later.

### Done when

Runnable project structure.

### Report placement

Chapter 4 — implementation approach/software structure.

---

## Task 11 — Define basic input / output formats

**Phase:** Setup  
**Start:** 10/1/2026  
**Deadline:** 10/4/2026  
**Priority:** High  
**Depends on:** 9,10

### What to do

Decide how network data, time-series data, BESS settings and simulation results will be stored between modules.

### Done when

Simple data format/interface note.

### Report placement

Chapter 4 — implementation approach/software structure.

---

## Task 12 — Prepare the 5-bus test case

**Phase:** V1 - Network  
**Start:** 10/2/2026  
**Deadline:** 10/5/2026  
**Priority:** Critical  
**Depends on:** 4,11

### What to do

Create one small radial network that is easy to understand and debug.

### Done when

5-bus case ready for power flow.

### Report placement

Chapter 4 — V1 practical implementation, trials and calculations.

---

## Task 13 — Implement FBS for one time step

**Phase:** V1 - Network  
**Start:** 10/4/2026  
**Deadline:** 10/10/2026  
**Priority:** Critical  
**Depends on:** 12

### What to do

Implement the Forward-Backward Sweep method from Term 1 for one static network condition.

### Done when

FBS runs on the 5-bus case.

### Report placement

Chapter 4 — V1 practical implementation, trials and calculations.

---

## Task 14 — Verify the FBS result

**Phase:** V1 - Network  
**Start:** 10/8/2026  
**Deadline:** 10/12/2026  
**Priority:** Critical  
**Depends on:** 13

### What to do

Check that the FBS implementation is working correctly by comparing voltages, power balance and losses with a trusted/reference result or simple manual checks. This is implementation verification, not final project validation.

### Done when

FBS result verified for the small test case.

### Report placement

Chapter 4 — V1 practical implementation, trials and calculations.

---

## Task 15 — Show basic network results

**Phase:** V1 - Network  
**Start:** 10/10/2026  
**Deadline:** 10/14/2026  
**Priority:** High  
**Depends on:** 14

### What to do

Create simple tables/plots for bus voltage, line loading/current, losses and source power.

### Done when

Readable V1 result output.

### Report placement

Chapter 4 — V1 practical implementation, trials and calculations.

---

## Task 16 — Import load and PV profiles

**Phase:** V1 - Network  
**Start:** 10/11/2026  
**Deadline:** 10/15/2026  
**Priority:** High  
**Depends on:** 6,10

### What to do

Read the cleaned load/PV files and check timestamp, length, unit and scaling before simulation.

### Done when

Profiles load correctly.

### Report placement

Chapter 4 — V1 practical implementation, trials and calculations.

---

## Task 17 — Add the hourly simulation loop

**Phase:** V1 - Network  
**Start:** 10/14/2026  
**Deadline:** 10/18/2026  
**Priority:** Critical  
**Depends on:** 15,16

### What to do

Run the network over the full time series instead of only one time step.

### Done when

Time-series 5-bus simulation works.

### Report placement

Chapter 4 — V1 practical implementation, trials and calculations.

---

## Task 18 — Verify V1 network implementation

**Phase:** V1 - Network  
**Start:** 10/17/2026  
**Deadline:** 10/21/2026  
**Priority:** Critical  
**Depends on:** 14,17

### What to do

Check the time-series power flow, outputs and power balance. Fix any implementation problem before adding the battery. This verifies that V1 works correctly; it does not test the Term 1 project requirements yet.

### Done when

V1 network implementation verified and stable.

### Report placement

Chapter 4 — V1 practical implementation, trials and calculations.

---

## Task 19 — Write Chapter 4 - V1 network implementation

**Phase:** Documentation  
**Start:** 10/18/2026  
**Deadline:** 10/23/2026  
**Priority:** High  
**Depends on:** 18

### What to do

Write the V1 implementation while it is fresh: 5-bus setup, FBS implementation, time-series loop, outputs, problems found and how V1 was checked.

### Done when

Chapter 4 V1 subsection draft.

### Report placement

Chapter 4 — V1 practical implementation, trials and calculations.

---

## Task 20 — Set the starting BESS parameters

**Phase:** V2 - BESS  
**Start:** 10/18/2026  
**Deadline:** 10/20/2026  
**Priority:** High  
**Depends on:** 9

### What to do

Use the Term 1 BESS model as the baseline: P, E, SOC limits, efficiency and initial/final SOC rules.

### Done when

BESS settings written in code/config.

### Report placement

Chapter 4 — V2 BESS implementation, trials and calculations.

---

## Task 21 — Implement SOC update

**Phase:** V2 - BESS  
**Start:** 10/19/2026  
**Deadline:** 10/23/2026  
**Priority:** Critical  
**Depends on:** 20

### What to do

Code the battery energy/SOC update for charging and discharging.

### Done when

SOC changes correctly for simple tests.

### Report placement

Chapter 4 — V2 BESS implementation, trials and calculations.

---

## Task 22 — Add charge / discharge limits

**Phase:** V2 - BESS  
**Start:** 10/21/2026  
**Deadline:** 10/25/2026  
**Priority:** Critical  
**Depends on:** 21

### What to do

Enforce SOC, power, efficiency and no simultaneous charge/discharge rules.

### Done when

Battery limits enforced.

### Report placement

Chapter 4 — V2 BESS implementation, trials and calculations.

---

## Task 23 — Connect a fixed BESS to the network

**Phase:** V2 - BESS  
**Start:** 10/23/2026  
**Deadline:** 10/27/2026  
**Priority:** Critical  
**Depends on:** 15,22

### What to do

Place one fixed BESS at a chosen bus and make its charging/discharging affect the power flow.

### Done when

Fixed BESS changes network injection.

### Report placement

Chapter 4 — V2 BESS implementation, trials and calculations.

---

## Task 24 — Run fixed-BESS time series

**Phase:** V2 - BESS  
**Start:** 10/26/2026  
**Deadline:** 10/30/2026  
**Priority:** Critical  
**Depends on:** 17,23

### What to do

Run the 5-bus time series with one fixed BESS and save SOC/network results.

### Done when

Full V2 simulation completed.

### Report placement

Chapter 4 — V2 BESS implementation, trials and calculations.

---

## Task 25 — Verify V2 BESS implementation

**Phase:** V2 - BESS  
**Start:** 10/29/2026  
**Deadline:** 11/2/2026  
**Priority:** Critical  
**Depends on:** 24

### What to do

Check SOC by hand for simple steps and test SOC limits, power limits, charge/discharge behavior and network interaction. This verifies the battery code before using it in later stages.

### Done when

V2 BESS implementation verified.

### Report placement

Chapter 4 — V2 BESS implementation, trials and calculations.

---

## Task 26 — Write Chapter 4 - V2 BESS implementation

**Phase:** Documentation  
**Start:** 10/30/2026  
**Deadline:** 11/4/2026  
**Priority:** High  
**Depends on:** 25

### What to do

Write the fixed-BESS implementation: battery parameters, SOC update, charge/discharge limits, network connection, time-series behavior and fixes made during V2.

### Done when

Chapter 4 V2 subsection draft.

### Report placement

Chapter 4 — V2 BESS implementation, trials and calculations.

---

## Task 27 — Choose manual test cases

**Phase:** V3 - Manual Compare  
**Start:** 11/1/2026  
**Deadline:** 11/2/2026  
**Priority:** Medium  
**Depends on:** 25

### What to do

Pick a small set of buses, power ratings and energy capacities to compare before using GWO.

### Done when

Manual comparison table planned.

### Report placement

Chapter 4 — manual implementation trials requested by the template.

---

## Task 28 — Compare BESS locations

**Phase:** V3 - Manual Compare  
**Start:** 11/2/2026  
**Deadline:** 11/5/2026  
**Priority:** High  
**Depends on:** 27

### What to do

Keep P and E fixed and move the battery between selected buses. Compare the results.

### Done when

Location comparison results.

### Report placement

Chapter 4 — manual implementation trials requested by the template.

---

## Task 29 — Compare BESS P and E sizes

**Phase:** V3 - Manual Compare  
**Start:** 11/4/2026  
**Deadline:** 11/7/2026  
**Priority:** High  
**Depends on:** 27

### What to do

Keep location controlled and compare different battery power and energy sizes.

### Done when

Size comparison results.

### Report placement

Chapter 4 — manual implementation trials requested by the template.

---

## Task 30 — Summarize what changes the result

**Phase:** V3 - Manual Compare  
**Start:** 11/6/2026  
**Deadline:** 11/9/2026  
**Priority:** High  
**Depends on:** 28,29

### What to do

Write a short note showing how location, power and energy affect voltage, cost, curtailment or shedding.

### Done when

V3 reference results ready.

### Report placement

Chapter 4 — manual implementation trials requested by the template.

---

## Task 31 — Write Chapter 4 - V3 manual comparison

**Phase:** Documentation  
**Start:** 11/7/2026  
**Deadline:** 11/11/2026  
**Priority:** Medium  
**Depends on:** 30

### What to do

Document the manual BESS location and size trials. Explain what was changed, what stayed fixed, what we observed and how these trials helped prepare for optimization.

### Done when

Chapter 4 V3 subsection draft.

### Report placement

Chapter 4 — manual implementation trials requested by the template.

---

## Task 32 — Implement cost / curtailment / shedding metrics

**Phase:** V4 - Optimization  
**Start:** 11/7/2026  
**Deadline:** 11/11/2026  
**Priority:** Critical  
**Depends on:** 30

### What to do

Code the same main performance terms used in the Term 1 objective and make sure each one can be calculated separately.

### Done when

Evaluator returns all main metrics.

### Report placement

Chapter 4 — optimization implementation, trials and design calculations.

---

## Task 33 — Implement the Term 1 WSM objective

**Phase:** V4 - Optimization  
**Start:** 11/9/2026  
**Deadline:** 11/12/2026  
**Priority:** Critical  
**Depends on:** 32

### What to do

Combine the Term 1 criteria using the 0.50 / 0.25 / 0.25 baseline weights and clearly handle their scales/normalization.

### Done when

Working WSM fitness value.

### Report placement

Chapter 4 — optimization implementation, trials and design calculations.

---

## Task 34 — Implement GWO candidate variables

**Phase:** V4 - Optimization  
**Start:** 11/11/2026  
**Deadline:** 11/17/2026  
**Priority:** Critical  
**Depends on:** 33

### What to do

Implement GWO using BESS location B, power P and energy E as the candidate solution.

### Done when

GWO can create valid B,P,E candidates.

### Report placement

Chapter 4 — optimization implementation, trials and design calculations.

---

## Task 35 — Connect GWO to the simulator

**Phase:** V4 - Optimization  
**Start:** 11/15/2026  
**Deadline:** 11/20/2026  
**Priority:** Critical  
**Depends on:** 34

### What to do

For every wolf, run the battery/network simulation and return the WSM fitness plus constraint handling.

### Done when

GWO evaluates real simulation results.

### Report placement

Chapter 4 — optimization implementation, trials and design calculations.

---

## Task 36 — Run deterministic GWO

**Phase:** V4 - Optimization  
**Start:** 11/19/2026  
**Deadline:** 11/22/2026  
**Priority:** Critical  
**Depends on:** 35

### What to do

Run GWO using one deterministic load/PV profile and save convergence and best BESS result.

### Done when

First automatic BESS result.

### Report placement

Chapter 4 — optimization implementation, trials and design calculations.

---

## Task 37 — Build exhaustive-search reference

**Phase:** V4 - Optimization  
**Start:** 11/20/2026  
**Deadline:** 11/24/2026  
**Priority:** High  
**Depends on:** 30,33

### What to do

On the small 5-bus case, test a limited set of all allowed B,P,E combinations to find a known reference best result.

### Done when

Reference optimum for small case.

### Report placement

Chapter 4 — optimization implementation, trials and design calculations.

---

## Task 38 — Compare GWO with exhaustive search

**Phase:** V4 - Optimization  
**Start:** 11/23/2026  
**Deadline:** 11/27/2026  
**Priority:** Critical  
**Depends on:** 36,37

### What to do

Check whether GWO reaches the same or close result and record the difference and runtime.

### Done when

GWO validation result.

### Report placement

Chapter 4 — optimization implementation, trials and design calculations.

---

## Task 39 — Test GWO population and iterations

**Phase:** V4 - Optimization  
**Start:** 11/25/2026  
**Deadline:** 11/29/2026  
**Priority:** High  
**Depends on:** 38

### What to do

Try a few population sizes and iteration limits to see their effect on result quality and runtime.

### Done when

GWO setting comparison.

### Report placement

Chapter 4 — optimization implementation, trials and design calculations.

---

## Task 40 — Write Chapter 4 - V4 GWO implementation

**Phase:** Documentation  
**Start:** 11/26/2026  
**Deadline:** 12/1/2026  
**Priority:** High  
**Depends on:** 39

### What to do

Document the evaluator, WSM, GWO candidate variables, simulator connection, deterministic run, exhaustive-search comparison and GWO setting tests.

### Done when

Chapter 4 V4 subsection draft.

### Report placement

Chapter 4 — optimization implementation, trials and design calculations.

---

## Task 41 — Design Chapter 5 validation experiments

**Phase:** Validation Planning  
**Start:** 11/27/2026  
**Deadline:** 12/2/2026  
**Priority:** High  
**Depends on:** 39

### What to do

Plan the formal Chapter 5 experiments that will validate the Term 1 design specifications. For each experiment define: objective, relevant background, detailed work steps, tools, data/figures/tables to collect, and how the data will be analyzed. Map every Term 1 requirement to at least one experiment or direct evidence check.

### Done when

Chapter 5 experiment plan + requirement-to-evidence map.

### Report placement

Chapter 5 — validation experiment planning and requirement mapping.

---

## Task 42 — Implement ARIMA

**Phase:** V5 - Uncertainty  
**Start:** 11/22/2026  
**Deadline:** 11/28/2026  
**Priority:** High  
**Depends on:** 6

### What to do

Use the Term 1 ARIMA method on the selected historical data and generate forecasts.

### Done when

ARIMA forecast working.

### Report placement

Chapter 4 — uncertainty implementation, trials and justified changes.

---

## Task 43 — Verify ARIMA forecast accuracy

**Phase:** V5 - Uncertainty  
**Start:** 11/27/2026  
**Deadline:** 12/1/2026  
**Priority:** High  
**Depends on:** 42

### What to do

Check that the ARIMA implementation behaves correctly using held-out historical data, RMSE, MAPE and simple plots. Keep this as implementation verification in Chapter 4; it supports confidence in the uncertainty module.

### Done when

ARIMA implementation verified with forecast-error results.

### Report placement

Chapter 4 — uncertainty implementation, trials and justified changes.

---

## Task 44 — Generate 100 Monte Carlo scenarios

**Phase:** V5 - Uncertainty  
**Start:** 11/29/2026  
**Deadline:** 12/3/2026  
**Priority:** Critical  
**Depends on:** 43

### What to do

Use the ARIMA/error behavior to generate the 100 scenarios described in the Term 1 design.

### Done when

100 load/PV scenarios generated.

### Report placement

Chapter 4 — uncertainty implementation, trials and justified changes.

---

## Task 45 — Select the 45 Term 1 scenarios

**Phase:** V5 - Uncertainty  
**Start:** 12/2/2026  
**Deadline:** 12/5/2026  
**Priority:** Critical  
**Depends on:** 44

### What to do

Select 15 best, 15 worst and 15 random scenarios using clear rules.

### Done when

45 baseline scenarios ready.

### Report placement

Chapter 4 — uncertainty implementation, trials and justified changes.

---

## Task 46 — Verify scenario realism

**Phase:** V5 - Uncertainty  
**Start:** 12/4/2026  
**Deadline:** 12/7/2026  
**Priority:** High  
**Depends on:** 44,45

### What to do

Check that generated scenarios are realistic compared with historical load/PV behavior using range, mean, variation and profile shape, and check PV physical limits. This verifies the uncertainty implementation before final requirement validation.

### Done when

Monte Carlo scenarios verified as physically/statistically reasonable.

### Report placement

Chapter 4 — uncertainty implementation, trials and justified changes.

---

## Task 47 — Run GWO for the 45 scenarios

**Phase:** V5 - Uncertainty  
**Start:** 12/5/2026  
**Deadline:** 12/10/2026  
**Priority:** Critical  
**Depends on:** 36,45

### What to do

Use the implemented GWO and simulation on the retained scenarios as described in Term 1.

### Done when

Scenario optimization results.

### Report placement

Chapter 4 — uncertainty implementation, trials and justified changes.

---

## Task 48 — Apply WSM to the scenario results

**Phase:** V5 - Uncertainty  
**Start:** 12/9/2026  
**Deadline:** 12/12/2026  
**Priority:** Critical  
**Depends on:** 47

### What to do

Apply the Term 1 WSM process to the scenario outputs and produce the baseline uncertainty recommendation.

### Done when

Term 1 uncertainty workflow completed.

### Report placement

Chapter 4 — uncertainty implementation, trials and justified changes.

---

## Task 49 — Verify V5 uncertainty workflow

**Phase:** V5 - Uncertainty  
**Start:** 12/11/2026  
**Deadline:** 12/14/2026  
**Priority:** Critical  
**Depends on:** 46,48

### What to do

Check that the full ARIMA → Monte Carlo → 45-scenario → GWO/WSM workflow runs correctly and gives a clear usable BESS result. If there is a real technical problem, document it before changing the Term 1 method.

### Done when

V5 uncertainty workflow verified or issue clearly documented.

### Report placement

Chapter 4 — uncertainty implementation, trials and justified changes.

---

## Task 50 — Write Chapter 4 - V5 uncertainty implementation

**Phase:** Documentation  
**Start:** 12/11/2026  
**Deadline:** 12/16/2026  
**Priority:** High  
**Depends on:** 49

### What to do

Write how ARIMA, Monte Carlo, the 100 scenarios, the 45 selected scenarios, GWO and WSM were implemented. Record any issue found before changing the Term 1 method.

### Done when

Chapter 4 V5 subsection draft.

### Report placement

Chapter 4 — uncertainty implementation, trials and justified changes.

---

## Task 51 — Sketch the simple UI

**Phase:** V6 - Software  
**Start:** 12/1/2026  
**Deadline:** 12/4/2026  
**Priority:** Medium  
**Depends on:** 9

### What to do

Plan only the screens needed for network/data input, baseline run, optimization and results.

### Done when

Simple UI sketch/workflow.

### Report placement

Chapter 4 — final software assembly/integration with screenshots/images.

---

## Task 52 — Build network / data input UI

**Phase:** V6 - Software  
**Start:** 12/4/2026  
**Deadline:** 12/8/2026  
**Priority:** High  
**Depends on:** 51,17

### What to do

Let the user load or enter the network and load/PV data without editing source code.

### Done when

Input screen working.

### Report placement

Chapter 4 — final software assembly/integration with screenshots/images.

---

## Task 53 — Connect baseline simulation to UI

**Phase:** V6 - Software  
**Start:** 12/7/2026  
**Deadline:** 12/10/2026  
**Priority:** High  
**Depends on:** 52,18

### What to do

Add a button/workflow to run V1 and show the main baseline results.

### Done when

Baseline run works from UI.

### Report placement

Chapter 4 — final software assembly/integration with screenshots/images.

---

## Task 54 — Connect optimization and results to UI

**Phase:** V6 - Software  
**Start:** 12/10/2026  
**Deadline:** 12/14/2026  
**Priority:** Critical  
**Depends on:** 48,53

### What to do

Run the V4/V5 backend from the UI and show selected bus, P, E and main technical/economic results.

### Done when

Optimization works from UI.

### Report placement

Chapter 4 — final software assembly/integration with screenshots/images.

---

## Task 55 — Add progress, errors and save results

**Phase:** V6 - Software  
**Start:** 12/13/2026  
**Deadline:** 12/16/2026  
**Priority:** High  
**Depends on:** 54

### What to do

Show useful error messages/progress and allow key results to be saved/exported.

### Done when

Basic software usability completed.

### Report placement

Chapter 4 — final software assembly/integration with screenshots/images.

---

## Task 56 — Run one full end-to-end test

**Phase:** V6 - Software  
**Start:** 12/15/2026  
**Deadline:** 12/18/2026  
**Priority:** Critical  
**Depends on:** 55

### What to do

Start from input files and run the full workflow to the final BESS result without manual code edits.

### Done when

V6 full workflow works.

### Report placement

Chapter 4 — final software assembly/integration with screenshots/images.

---

## Task 57 — Write Chapter 4 - V6 software integration

**Phase:** Documentation  
**Start:** 12/16/2026  
**Deadline:** 12/20/2026  
**Priority:** High  
**Depends on:** 56

### What to do

Document the UI and final software integration: input flow, backend connection, results display, error handling, save/export and end-to-end operation. Include clear screenshots/images of the final product and show how the separate modules are assembled into one system.

### Done when

Chapter 4 V6/final-product subsection draft with screenshots.

### Report placement

Chapter 4 — final software assembly/integration with screenshots/images.

---

## Task 58 — Experiment 1 - Technical and economic performance

**Phase:** Validation  
**Start:** 12/17/2026  
**Deadline:** 12/20/2026  
**Priority:** Critical  
**Depends on:** 49,56

### What to do

Run the final baseline and optimized-BESS cases using the same inputs. Validate the Term 1 performance specifications such as load-shedding reduction, renewable-curtailment reduction, operational-cost reduction, voltage limits and SOC/DoD limits. Save the objective, background, detailed steps, tools, figures/tables, measured data and analysis for Chapter 5.

### Done when

Complete performance validation experiment with figures/tables and conclusions.

### Report placement

Chapter 5 — formal validation experiment.

---

## Task 59 — Experiment 2 - Optimizer and uncertainty requirements

**Phase:** Validation  
**Start:** 12/18/2026  
**Deadline:** 12/22/2026  
**Priority:** Critical  
**Depends on:** 39,49,58

### What to do

Formally test the Term 1 optimizer/uncertainty specifications. Check scenario count, GWO convergence/iteration limits and the behavior of the selected solution across the retained scenarios. Use the earlier sensitivity/robustness work as supporting evidence where useful. Save objective, background, steps, tools, data and analysis.

### Done when

Complete optimizer/uncertainty validation experiment with measured evidence.

### Report placement

Chapter 5 — formal validation experiment.

---

## Task 60 — Experiment 3 - Network scalability

**Phase:** Validation  
**Start:** 12/20/2026  
**Deadline:** 12/24/2026  
**Priority:** Critical  
**Depends on:** 18,49

### What to do

Run the stable final framework on the IEEE 33-bus network and use the same implementation workflow. Validate the Term 1 minimum-network-size/extendability requirement and collect the required experiment objective, background, steps, tools, figures/tables and analysis.

### Done when

Complete IEEE 33-bus scalability validation experiment.

### Report placement

Chapter 5 — formal validation experiment.

---

## Task 61 — Complete Chapter 5 validation results

**Phase:** Validation  
**Start:** 12/23/2026  
**Deadline:** 12/27/2026  
**Priority:** Critical  
**Depends on:** 58,59,60

### What to do

Combine the formal validation experiments and create the final requirement-evidence summary. For every Term 1 design requirement show the target, experiment/direct check, measured result, evidence location and status: Met, Partially Met or Not Met. Keep the detailed reasoning in the experiment analysis and Chapter 6.1.

### Done when

Chapter 5 complete with formal experiments + requirement-evidence summary.

### Report placement

Chapter 5 — validation results summary; feeds Chapter 6.1 Evaluation of Solution.

---

## Task 62 — Test common software failure cases

**Phase:** Implementation Verification  
**Start:** 12/21/2026  
**Deadline:** 12/25/2026  
**Priority:** High  
**Depends on:** 56

### What to do

Try bad files, missing data, disconnected network, invalid BESS limits and failed optimization. Fix important problems and record expected/actual behavior. This is software verification and should be documented with the implementation, not treated as final requirement validation unless a Term 1 requirement directly covers it.

### Done when

Software failure-case verification record.

### Report placement

Chapter 4 — implementation/failure-case trials unless directly used in a formal validation experiment.

---

## Task 63 — Freeze final cases and outputs

**Phase:** Final Results  
**Start:** 12/24/2026  
**Deadline:** 12/26/2026  
**Priority:** Critical  
**Depends on:** 58,59,60,62,61

### What to do

Stop changing the main setup. Save exact inputs, settings, seeds, plots and tables used in the final report.

### Done when

Reproducible final results package.

### Report placement

Evidence package used by Chapters 4–6.

---

## Task 64 — Merge and polish Chapter 4 to template

**Phase:** Documentation  
**Start:** 12/20/2026  
**Deadline:** 12/28/2026  
**Priority:** Critical  
**Depends on:** 56

### What to do

Combine the V1-V6 drafts and make sure Chapter 4 follows the final-report template: practical implementation details, multiple trials used to reach a satisfactory design, related design calculations, justified changes from the Term 1 baseline, and the final assembled product with multiple screenshots/images. Remove repeated text and make figures/tables consistent.

### Done when

Complete Chapter 4 matching the final-report template.

### Report placement

Chapter 4 final template compliance pass.

---

## Task 65 — Finish Chapter 5, Chapter 6 and Appendix D

**Phase:** Documentation  
**Start:** 12/23/2026  
**Deadline:** 12/30/2026  
**Priority:** Critical  
**Depends on:** 41,61,64

### What to do

Finish Chapter 5 using the required validation-experiment format: objectives, background, detailed work plan, tools, collected data in organized figures/tables, and analysis/conclusions. Then write Chapter 6 using the template headings: 6.1 Evaluation of Solution, 6.2 Impact of Solution, 6.3 Future Work, and 6.4 Conclusion. Finish Appendix D with the code of ethics, ethical issue, analysis and informed decision.

### Done when

Chapters 5-6 + Appendix D completed using the official template.

### Report placement

Chapter 5 + Chapter 6.1–6.4 + Appendix D.

---

## Task 66 — Prepare demo and final QA

**Phase:** Finalization  
**Start:** 12/27/2026  
**Deadline:** 12/31/2026  
**Priority:** Critical  
**Depends on:** 63,64,65

### What to do

Prepare the presentation/demo, run one clean reproducibility check, fix final critical issues and make the submission package ready.

### Done when

Demo + submission-ready project.

### Report placement

Final demo/QA.

---

