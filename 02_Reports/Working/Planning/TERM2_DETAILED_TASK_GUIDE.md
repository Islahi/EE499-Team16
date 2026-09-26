# Term 2 Detailed Task Guide

**Last aligned:** 26 Sep 2026  
**Official final-report deadline:** 30 Nov 2026  
**Official final-presentation window:** 6–10 Dec 2026

This file explains the live Task Register in simple wording. The Google Sheet is the main collaborative schedule; this file is the version-controlled explanation.

## Official milestones

- **22 Oct** — Progress Update submission.
- **25–29 Oct** — Progress Update presentation.
- **30 Nov** — Final Term 2 report submission.
- **6–10 Dec** — Final presentation/demo.

Because the final report is due 30 Nov, several tasks overlap after the Progress Update. Work in parallel when dependencies allow.

## Report rule

- **Chapter 4 — Implementation:** practical implementation details, multiple trials, design calculations, justified changes from Term 1, and final-product screenshots/images.
- **Chapter 5 — Validation Experiments:** formal experiments that validate the Term 1 design specifications.
- **Chapter 6:** 6.1 Evaluation of Solution, 6.2 Impact of Solution, 6.3 Future Work, 6.4 Conclusion.
- **Appendix D:** use the Saudi Council of Engineers Engineer Charter 2025; select one project ethical issue, analyze it using the Charter, and make an informed decision.

## Ethics rule

The separate ethics assignment is an **individual 3–5 page report**, not only Appendix D. Each member must analyze **two distinct ethical issues** and cover stakeholders, alternatives/decision-making, safety/risk/compliance, data/privacy/security, broader impacts, professional integrity, IP/attribution, mitigation and reflection. The provided schedule does not give an ethics deadline, so **7 Oct is only an internal draft target**.

---

# Data and early preparation

## Task 1 — Define the data we need
**Start:** 20 Sep 2026  
**Deadline:** 21 Sep 2026  
**What to do:** List the load, PV/weather, network and BESS/economic data needed.  
**Done when:** One clear data checklist exists.

## Task 2 — Get load data
**Start:** 20 Sep 2026  
**Deadline:** 24 Sep 2026  
**What to do:** Find one usable historical load profile and record source, unit, time step and date range.  
**Done when:** Load dataset is ready.

## Task 3 — Get PV / weather data
**Start:** 20 Sep 2026  
**Deadline:** 24 Sep 2026  
**What to do:** Find irradiance/weather/PV generation data that can be matched with the load data.  
**Done when:** PV/weather dataset is ready.

## Task 4 — Get network data
**Start:** 22 Sep 2026  
**Deadline:** 24 Sep 2026  
**What to do:** Prepare a small 5-bus debugging case and the IEEE 33-bus data for later final/scalability testing.  
**Done when:** Both network datasets are ready.

## Task 5 — Check the selected data
**Start:** 23 Sep 2026  
**Deadline:** 25 Sep 2026  
**What to do:** Check sources, units, timestamps, missing values and whether datasets can be used together.  
**Done when:** Short data-quality note is ready.

## Task 6 — Clean and align the data
**Start:** 24 Sep 2026  
**Deadline:** 26 Sep 2026  
**What to do:** Fix missing values as needed and align load/PV data to common time steps and units.  
**Done when:** Simulation-ready profiles are available.

## Task 7 — Prepare data for advisor
**Start:** 25 Sep 2026  
**Deadline:** 27 Sep 2026  
**What to do:** Prepare source links, sample plots, dataset summary and advisor questions.  
**Done when:** Advisor data package is ready.

## Task 8 — Prepare individual ethical analysis + final-report ethics material
**Start:** 27 Sep 2026  
**Internal draft target:** 7 Oct 2026  
**What to do:** Each member prepares the required individual 3–5 page ethics analysis. Include project context, stakeholders, two ethical issues, alternatives and decisions using the SCE Engineer Charter 2025, safety/risk/compliance, data/privacy/security, broader impacts, professional integrity, IP/attribution, mitigation and reflection.  
**Done when:** Each member has a usable individual draft/outline and the team has reusable material for Chapter 6.2 and Appendix D.

---

# Shadow baseline and setup

## Task 9 — Confirm the implementation baseline
**Start:** 27 Sep 2026  
**Deadline:** 29 Sep 2026  
**What to do:** Review the Term 1 baseline and shadow design. Keep FBS, GWO, ARIMA, Monte Carlo, the 45-scenario selection and WSM baseline unless a real implementation reason appears.  
**Done when:** Team agrees what will be implemented first.

## Task 10 — Set up the code structure
**Start:** 30 Sep 2026  
**Deadline:** 3 Oct 2026  
**What to do:** Create simple folders/modules for data, network, BESS, optimization, uncertainty and results.  
**Done when:** Project runs with a clean starting structure.

## Task 11 — Define basic input / output formats
**Start:** 1 Oct 2026  
**Deadline:** 4 Oct 2026  
**What to do:** Decide how network data, time-series data, BESS settings and results move between modules.  
**Done when:** Simple interface/data-format note exists.

---

# V1 — Network simulator

## Task 12 — Prepare the 5-bus test case
**Start:** 2 Oct 2026  
**Deadline:** 5 Oct 2026  
**What to do:** Build a small radial case that is easy to understand and debug.  
**Done when:** 5-bus case is ready for FBS.

## Task 13 — Implement FBS for one time step
**Start:** 4 Oct 2026  
**Deadline:** 10 Oct 2026  
**What to do:** Implement the Term 1 Forward-Backward Sweep method for one static condition.  
**Done when:** FBS solves the 5-bus case.

## Task 14 — Verify the FBS result
**Start:** 8 Oct 2026  
**Deadline:** 12 Oct 2026  
**What to do:** Compare voltages, power balance and losses against manual/trusted reference results.  
**Done when:** FBS result is credible enough to continue.

## Task 15 — Show basic network results
**Start:** 10 Oct 2026  
**Deadline:** 14 Oct 2026  
**What to do:** Produce simple voltage, line loading/current, losses and source-power tables/plots.  
**Done when:** V1 outputs are readable.

## Task 16 — Import load and PV profiles
**Start:** 11 Oct 2026  
**Deadline:** 15 Oct 2026  
**What to do:** Read cleaned load/PV files and check timestamps, length, units and scaling.  
**Done when:** Profiles load without manual editing.

## Task 17 — Add the hourly simulation loop
**Start:** 14 Oct 2026  
**Deadline:** 18 Oct 2026  
**What to do:** Run power flow over the full time series.  
**Done when:** Time-series network simulation works.

## Task 18 — Verify V1 network implementation
**Start:** 17 Oct 2026  
**Deadline:** 21 Oct 2026  
**What to do:** Check time-series outputs and power balance; fix implementation problems before adding BESS.  
**Done when:** V1 is stable.

## Task 19 — Write Chapter 4: V1 network implementation
**Start:** 18 Oct 2026  
**Deadline:** 23 Oct 2026  
**What to do:** Document 5-bus setup, FBS implementation, time-series loop, outputs, trials/problems and checks.  
**Done when:** Chapter 4 V1 draft exists.

---

# V2 — Fixed BESS

## Task 20 — Set the starting BESS parameters
**Start:** 11 Oct 2026  
**Deadline:** 13 Oct 2026  
**What to do:** Put Term 1 BESS P, E, SOC limits, efficiency and initial/final SOC rules into configuration/code.  
**Done when:** BESS settings are defined.

## Task 21 — Implement SOC update
**Start:** 12 Oct 2026  
**Deadline:** 14 Oct 2026  
**What to do:** Code charging/discharging energy and SOC updates.  
**Done when:** Simple SOC tests behave correctly.

## Task 22 — Add charge / discharge limits
**Start:** 14 Oct 2026  
**Deadline:** 16 Oct 2026  
**What to do:** Enforce SOC, power, efficiency and no-simultaneous-charge/discharge rules.  
**Done when:** BESS constraints are enforced.

## Task 23 — Connect a fixed BESS to the network
**Start:** 16 Oct 2026  
**Deadline:** 18 Oct 2026  
**What to do:** Place one fixed BESS at a selected bus and make its power affect FBS/network injections.  
**Done when:** Charging/discharging changes network results correctly.

## Task 24 — Run fixed-BESS time series
**Start:** 18 Oct 2026  
**Deadline:** 19 Oct 2026  
**What to do:** Run the full 5-bus time series with the fixed BESS.  
**Done when:** SOC and network results are saved.

## Task 25 — Verify V2 BESS implementation
**Start:** 19 Oct 2026  
**Deadline:** 20 Oct 2026  
**What to do:** Hand-check SOC steps and test SOC/power/charge/discharge limits and network interaction.  
**Done when:** BESS implementation is trusted enough for V3/V4.

## Task 26 — Write Chapter 4: V2 BESS implementation
**Start:** 20 Oct 2026  
**Deadline:** 22 Oct 2026  
**What to do:** Document BESS parameters, equations, limits, network connection, trials and fixes.  
**Done when:** Chapter 4 V2 draft exists.

---

# V3 — Manual BESS trials + Progress Update

## Task 27 — Choose manual test cases
**Start/Deadline:** 20 Oct 2026  
**What to do:** Pick a small controlled set of buses, power ratings and energy capacities.  
**Done when:** Manual comparison table is planned.

## Task 28 — Compare BESS locations
**Start:** 20 Oct 2026  
**Deadline:** 21 Oct 2026  
**What to do:** Keep P/E fixed and move BESS among selected buses.  
**Done when:** Location comparison results are ready.

## Task 29 — Compare BESS P and E sizes
**Start:** 20 Oct 2026  
**Deadline:** 21 Oct 2026  
**What to do:** Control location and compare several P/E combinations.  
**Done when:** Size comparison results are ready.

## Task 30 — Summarize what changes the result
**Start:** 21 Oct 2026  
**Deadline:** 22 Oct 2026  
**What to do:** Explain how B, P and E influence voltage/cost/curtailment/shedding.  
**Done when:** V3 reference note is ready.

## Task 31 — Write Chapter 4 V3 + prepare Progress Update content
**Start:** 21 Oct 2026  
**Deadline:** 22 Oct 2026  
**What to do:** Write V3 trials and prepare current implementation status, working results, problems, next steps and reusable figures for the official Progress Update.  
**Done when:** Progress Update technical content is ready for 22 Oct and presentation reuse during 25–29 Oct.

---

# V4 — Deterministic optimization

## Task 32 — Implement cost / curtailment / shedding metrics
**Start:** 22 Oct 2026  
**Deadline:** 25 Oct 2026  
**What to do:** Code each Term 1 objective component separately.  
**Done when:** Evaluator returns all main metrics.

## Task 33 — Implement the Term 1 WSM objective
**Start:** 24 Oct 2026  
**Deadline:** 27 Oct 2026  
**What to do:** Implement 0.50/0.25/0.25 baseline weights and handle scaling/normalization clearly.  
**Done when:** One working WSM fitness value is produced.

## Task 34 — Implement GWO candidate variables
**Start:** 25 Oct 2026  
**Deadline:** 29 Oct 2026  
**What to do:** Represent candidate BESS location B, power P and energy E inside GWO.  
**Done when:** GWO produces valid candidates.

## Task 35 — Connect GWO to the simulator
**Start:** 28 Oct 2026  
**Deadline:** 1 Nov 2026  
**What to do:** For each wolf, run the network+BESS simulation and return WSM fitness/constraint handling.  
**Done when:** GWO evaluates real simulation results.

## Task 36 — Run deterministic GWO
**Start:** 31 Oct 2026  
**Deadline:** 3 Nov 2026  
**What to do:** Optimize one deterministic load/PV profile and save convergence and best BESS result.  
**Done when:** First automatic BESS result exists.

## Task 37 — Build exhaustive-search reference
**Start:** 29 Oct 2026  
**Deadline:** 2 Nov 2026  
**What to do:** On the small case, enumerate a limited finite B/P/E space to get a known reference optimum.  
**Done when:** Reference optimum is available.

## Task 38 — Compare GWO with exhaustive search
**Start:** 2 Nov 2026  
**Deadline:** 4 Nov 2026  
**What to do:** Compare solution quality/objective and runtime.  
**Done when:** GWO implementation verification result is recorded.

## Task 39 — Test GWO population and iterations
**Start:** 3 Nov 2026  
**Deadline:** 5 Nov 2026  
**What to do:** Try a few population sizes/iteration limits and record result-quality/runtime effects.  
**Done when:** Setting comparison exists.

## Task 40 — Write Chapter 4: V4 GWO implementation
**Start:** 5 Nov 2026  
**Deadline:** 7 Nov 2026  
**What to do:** Document evaluator, WSM, GWO variables, simulator connection, deterministic run and implementation trials.  
**Done when:** Chapter 4 V4 draft exists.

## Task 41 — Design Chapter 5 validation experiments
**Start:** 5 Nov 2026  
**Deadline:** 7 Nov 2026  
**What to do:** Map each Term 1 design requirement to a formal experiment/direct check. For each experiment define objective, background, detailed steps, tools, data/figures/tables and analysis method.  
**Done when:** Chapter 5 experiment plan and requirement-to-evidence map are ready.

---

# V5 — Uncertainty

## Task 42 — Implement ARIMA
**Start:** 27 Oct 2026  
**Deadline:** 1 Nov 2026  
**What to do:** Implement the Term 1 ARIMA method on selected historical data.  
**Done when:** Forecast is generated.

## Task 43 — Verify ARIMA forecast accuracy
**Start:** 1 Nov 2026  
**Deadline:** 2 Nov 2026  
**What to do:** Use held-out data, RMSE/MAPE and simple plots to check implementation behavior.  
**Done when:** Forecast-error evidence exists.

## Task 44 — Generate 100 Monte Carlo scenarios
**Start:** 2 Nov 2026  
**Deadline:** 4 Nov 2026  
**What to do:** Generate the 100 scenarios described in Term 1.  
**Done when:** 100 load/PV scenarios exist.

## Task 45 — Select the 45 Term 1 scenarios
**Start:** 4 Nov 2026  
**Deadline:** 5 Nov 2026  
**What to do:** Select 15 best, 15 worst and 15 random cases using explicit rules.  
**Done when:** 45-scenario baseline set is ready.

## Task 46 — Verify scenario realism
**Start:** 5 Nov 2026  
**Deadline:** 6 Nov 2026  
**What to do:** Compare generated scenarios with historical ranges, means, variability/profile shapes and physical PV limits.  
**Done when:** Scenario-realism evidence is recorded.

## Task 47 — Run GWO for the 45 scenarios
**Start:** 5 Nov 2026  
**Deadline:** 9 Nov 2026  
**What to do:** Run implemented GWO/simulation over retained scenarios as described in Term 1.  
**Done when:** Scenario optimization results exist.

## Task 48 — Apply WSM to the scenario results
**Start:** 8 Nov 2026  
**Deadline:** 10 Nov 2026  
**What to do:** Apply the Term 1 WSM process and produce the baseline uncertainty recommendation.  
**Done when:** Term 1 uncertainty workflow produces a recommendation.

## Task 49 — Verify V5 uncertainty workflow
**Start:** 10 Nov 2026  
**Deadline:** 11 Nov 2026  
**What to do:** Check the full ARIMA → MC → 45 scenarios → GWO/WSM workflow. Document any real problem before changing the baseline method.  
**Done when:** Workflow is verified or a justified issue is documented.

## Task 50 — Write Chapter 4: V5 uncertainty implementation
**Start:** 11 Nov 2026  
**Deadline:** 13 Nov 2026  
**What to do:** Document ARIMA, MC, 100→45 scenario selection, GWO/WSM and any implementation-driven change.  
**Done when:** Chapter 4 V5 draft exists.

---

# V6 — Integrated software

## Task 51 — Sketch the simple UI
**Start:** 5 Nov 2026  
**Deadline:** 7 Nov 2026  
**What to do:** Plan only screens needed for input, baseline run, optimization and results.  
**Done when:** UI workflow/sketch exists.

## Task 52 — Build network / data input UI
**Start:** 7 Nov 2026  
**Deadline:** 10 Nov 2026  
**What to do:** Allow users to load/enter network and load/PV data without editing source code.  
**Done when:** Input screen works.

## Task 53 — Connect baseline simulation to UI
**Start:** 9 Nov 2026  
**Deadline:** 11 Nov 2026  
**What to do:** Run V1 from the UI and display main baseline results.  
**Done when:** Baseline runs from UI.

## Task 54 — Connect optimization and results to UI
**Start:** 11 Nov 2026  
**Deadline:** 14 Nov 2026  
**What to do:** Run V4/V5 backend and display selected B, P, E plus main technical/economic results.  
**Done when:** Optimization works from UI.

## Task 55 — Add progress, errors and save results
**Start:** 14 Nov 2026  
**Deadline:** 15 Nov 2026  
**What to do:** Add useful messages/progress and export/save key results.  
**Done when:** Basic usability is complete.

## Task 56 — Run one full end-to-end test
**Start:** 15 Nov 2026  
**Deadline:** 16 Nov 2026  
**What to do:** Start from inputs and reach final BESS result without editing code manually.  
**Done when:** Full V6 workflow runs cleanly.

## Task 57 — Write Chapter 4: V6 software integration
**Start:** 16 Nov 2026  
**Deadline:** 18 Nov 2026  
**What to do:** Document UI/backend integration, outputs, errors, save/export and final-product assembly. Capture clear screenshots/images.  
**Done when:** V6/final-product Chapter 4 draft exists.

---

# Formal validation and final report

## Task 58 — Experiment 1: Technical and economic performance
**Start:** 16 Nov 2026  
**Deadline:** 19 Nov 2026  
**What to do:** Compare final no-BESS baseline and optimized BESS using the same inputs. Test shedding, curtailment, operating cost, voltage and SOC/DoD requirements. Follow the full Chapter 5 experiment format.  
**Done when:** Performance validation experiment has figures/tables and conclusions.

## Task 59 — Experiment 2: Optimizer and uncertainty requirements
**Start:** 19 Nov 2026  
**Deadline:** 21 Nov 2026  
**What to do:** Formally test scenario count, GWO convergence/iteration limits and selected-solution behavior across scenarios, using earlier trials as supporting evidence.  
**Done when:** Optimizer/uncertainty experiment has measured evidence and conclusions.

## Task 60 — Experiment 3: Network scalability
**Start:** 19 Nov 2026  
**Deadline:** 22 Nov 2026  
**What to do:** Run the stable framework on IEEE 33-bus and validate minimum-network-size/extendability requirements.  
**Done when:** IEEE33 validation experiment is complete.

## Task 61 — Complete Chapter 5 validation results
**Start:** 22 Nov 2026  
**Deadline:** 24 Nov 2026  
**What to do:** Combine formal experiments and create requirement → target → evidence → measured result → Met/Partially Met/Not Met summary.  
**Done when:** Chapter 5 is complete.

## Task 62 — Test common software failure cases
**Start:** 15 Nov 2026  
**Deadline:** 18 Nov 2026  
**What to do:** Test bad files, missing data, disconnected network, invalid BESS limits and optimizer failures; record/fix important behavior.  
**Done when:** Failure-case verification record exists.

## Task 63 — Freeze final cases and outputs
**Start:** 24 Nov 2026  
**Deadline:** 25 Nov 2026  
**What to do:** Freeze exact inputs, settings, seeds, plots and tables used in the report.  
**Done when:** Results package is reproducible.

## Task 64 — Merge and polish Chapter 4 to template
**Start:** 18 Nov 2026  
**Deadline:** 26 Nov 2026  
**What to do:** Merge V1–V6 drafts; ensure practical details, trials, calculations, baseline changes and final screenshots are included; remove repetition.  
**Done when:** Chapter 4 matches the official template.

## Task 65 — Finish Chapter 5, Chapter 6 and Appendix D
**Start:** 26 Nov 2026  
**Deadline:** 29 Nov 2026  
**What to do:** Finalize Chapter 5 experiments; write 6.1 Evaluation of Solution, 6.2 Impact of Solution, 6.3 Future Work and 6.4 Conclusion; finish Appendix D using SCE Charter 2025 and one selected ethical issue.  
**Done when:** Final-report content is ready for the official **30 Nov** submission.

---

# Final presentation

## Task 66 — Prepare and deliver final presentation/demo
**Start:** 1 Dec 2026  
**Official window:** 6–10 Dec 2026  
**What to do:** Use the already-submitted report/results to build slides and a stable live demo. Rehearse the workflow, run a clean reproducibility check and fix only critical presentation/demo issues.  
**Done when:** Presentation/demo is ready and delivered during the official window.
