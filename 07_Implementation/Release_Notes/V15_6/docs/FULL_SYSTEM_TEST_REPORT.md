# V15.6 cleanup · system validation

## Follow-up desktop refinement

The baseline passed 143 tests and 21 subtests. The revised Windows test launcher passed 147 tests and 21 subtests. The follow-up exercised real Qt widgets for empty-state folder and file selection, the multi-case picker, Apply and Cancel, the restored GA controls, and the simplified header. Worker tests checked phase-aware exceptions, actual hour counts, and persisted log levels. The three editable GA controls were traced to the optimizer configuration, and the deterministic test compared one and two workers.

The IEEE 33-bus case imported all 43,921 source hours in 3.01 s. The forecast workflow generated and simulated 48 hourly steps, and the desktop produced the offline HTML and manifest. An older archived dashboard was also regenerated on a copy with its numerical metadata hash intact.

The matched 8,760-hour optimization selected the same two installations at buses 14 and 17. No-BESS and fleet results matched the earlier run for duration, annual cost, shedding, curtailment and minimum and maximum voltage. All 730 battery-day records passed SOC restoration and power-factor checks. The revised run took 558 s, including 178 s of GA screening and a 26 s numerical export. The earlier run took 535 s overall and 158 s in GA screening. These are single runs with validation tasks sharing the machine, so they do not establish a performance change.

The [renaming map](COMPONENT_RENAMING_MAP.md) documents historical metadata aliases and replay. The following sections record the earlier V15.6 validation. Interactive browser controls and live irradiance providers were outside this follow-up run.

## Source and scope

The source was extracted from `BESS_Planning_Karve_Multi_v15_6_Session_Serialization_Fix.zip`, SHA-256 `15747da8895c1ae3643934d78828caac10c80b6fdf6c67c9724f661a22f3299a`. Changes and tests ran in an isolated Windows implementation directory. The package contains runnable Python source, Qt Designer forms, the offline report, tests, startup instructions and the [control inventory](UI_CONTROL_AUDIT.csv).

The final Windows launcher run passed 143 tests and 21 subtests. The original suite passed 132 tests and 21 subtests after resolving the tests package import needed to run pytest on the local Windows installation.

## Changes and coverage

| Subsystem | Executed verification and outcome |
|---|---|
| Startup and launchers | Windows Python 3.14.7 runtime check loaded the desktop forms, Numba FBS, PySide6/Qt WebEngine imports, the XGBoost and LightGBM estimators, and performed a real corrective-control example. Runtime report written to a path containing spaces. Full suite run through the Windows test launcher. |
| Desktop controls | Actual Qt instances exercised settings navigation, eligible-bus Clear and Select all, Apply, Cancel, integer 24/48/72-hour restoration, optimizer readiness and the simulation button. The inventory counted 153 Designer controls before and 99 after. It records 56 retired controls and 2 additions. Runtime-created menu items are described below. |
| Input and provenance | Imported the user's prepared IEEE33 case with 43,921 source hours and five PV installations. CSV/XLSX tests checked leap-day continuity, unsorted rows, missing/duplicate hours, sidecar identity, source snapshots and old setup files with a null start. This workbook had no frequency field, so the test specified 60 Hz. The source manifest declares UTC for use in the study and identifies it as a study assumption for the demand source. |
| FBS and network | Radial 33-bus workbook, slack bus 1, 32 branches. Independent pandapower Newton–Raphson reference at nominal load gave minimum voltage 0.913080074 pu and active loss 202.678292 kW. Numba FBS gave 0.913080091 pu and 202.678220 kW. Largest voltage magnitude difference was 1.73×10⁻⁸ pu, and the FBS active-balance residual magnitude was 0.00043 kW. |
| Forecasting | Trained the approved sector and PV models on the prepared case's 2020 history, generated the first 48 hours of 2021 and verified aligned residential, commercial, manufacturing and solar holdout scores. The main window's Simulation button processed the resulting 48 forecast hours. Training and export took 14.53 s. |
| Strict Sindi and BESS | Simulated 24 h, 48 h, 336 h and 8,760 h using real inputs. Short regressions cover the operating horizons, PF, charge/discharge exclusivity, failure handling, daily SOC restoration, and distinct-bus dispatch. The full-year single-battery run now reports metrics from the final fleet-state record. |
| Joint GA | Real 2021 IEEE33 optimization with the small configurable catalogs and up to 2 units. All 32 non-slack buses were eligible, and 27 appeared in evaluated chromosomes. The run evaluated 66 unique fleets, stopped after 12 generations on the existing stall rule, used 12 representative days and screened up to 9 fleets on independent stress days. The first annual finalist passed. |
| Economics | Real CRF, inverter kVA CAPEX and annual O&M reconciled with the operating-cost ledger. No storage and selected fleet use the same tariffs and penalties within each comparison. Short runs retain technical metrics and report annual costs as unavailable. |
| Sessions and export | Tested nested NumPy values, atomic manifest replacement, retry after a numerical export write failure, annual results retained after session registration failure, and preservation after an HTML generation failure. Valid CSV and JSON artifacts can be loaded independently of HTML rendering. |
| Offline report | Regenerated saved 48-hour and 8,760-hour reports. Checked strict audits, scenario metadata, compressed series, lossless CSV exports, and JavaScript syntax. The report exposes hourly voltage, branch current and loading when an ampacity is declared, battery P/Q and SOC, distinct annual and screening results, PNG export and side-by-side saved report comparison. |
| Failure and cancellation | Tested bad inputs, inadmissible sizes, solver failure handling, unavailable annual costs, export retry, cancellation at numerical checkpoints and the non-interruptible commit boundary. |

## IEEE33 optimized 2021 run

The optimization used 25–250 kW with 25 kW steps, 75–750 kWh with 75 kWh steps, 2–12 h nameplate duration, and 0.10/0.05 USD/kWh import/export tariffs. The case includes 6,000 kW of modeled PV. The run was feasible under the configured network constraints and corrective actions.

| Outcome | No battery | Optimized fleet |
|---|---:|---:|
| Hours verified | 8,760 | 8,760 |
| Annual cost (USD) | 35,675,172.94 | 33,060,173.22 |
| Load shedding (kWh) | 2,779,621.76 | 2,556,479.16 |
| PV curtailment (kWh) | 0 | 0 |

The selected fleet installed 125 kW / 450 kWh at bus 14 and 125 kW / 525 kWh at bus 17. All 730 battery-day records passed SOC restoration and discharge PF checks. Annual cost fell by $2,614,999.72 (7.33%) and unserved energy fell by 223,142.60 kWh (8.03%). The remaining load shedding is significant and is reported as unserved demand.

## Before and after timing

Measured wall time on the same Windows machine and shared workload. Short-run export rows include session archive creation and HTML generation. This was a single trial while other validation jobs were active, so the differences do not establish a speedup.

| Workload | Original V15.6 | Cleanup |
|---|---:|---:|
| Import 43,921-hour IEEE33 case | 3.08 s | 2.84 s |
| Simulate 24 h, no battery | 1.49 s | 1.30 s |
| Simulate and export 48 h, manual BESS | 21.27 s | 21.03 s |
| Simulate 336 h, manual BESS | 13.21 s | 13.36 s |
| Simulate and evaluate 8,760 h, no battery | 163.88 s | 164.97 s |
| Simulate and evaluate 8,760 h, one manual BESS | Terminal-state reporting error | 195.50 s |

The before/after no-BESS annual cost and shedding matched. The cleanup's full-year manual run reported $32,858,214.10 under the same GUI default tariffs used for this benchmark. The full Joint GA run with explicit tariffs took 535 s including export and the first HTML build. The GA portion took 158 s. In its selected full-year simulation, the Sindi MILP took 15.30 s, coordinated LP control took 110.70 s and Numba FBS calls took 7.74 s. These are instrumented substage times. The dominant cost in this run was coordinated network control. No solver tolerances or physical constraints were relaxed to shorten execution.

Regenerating the same saved annual run took 5.96 s for the original 3.32 MB dashboard and 12.90 s for the cleanup's 15.75 MB dashboard. The increase comes with hourly bus-voltage and branch-current histories for the feeder interaction. The numerical solver and its CSV exports are independent of that HTML build.

## Limits

The numerical forecast, full-year baseline, manual BESS and optimized fleet were run on real prepared data. Live irradiance provider requests and a frozen Windows executable were outside the executed checks. The source package launches with the existing Python installation. Interactive browser verification stopped when the active Windows browser URL could not be identified. Offline HTML generation, regeneration and compressed report-data checks passed separately. A full-year GA baseline timing under identical settings was not executed. Parallel and sequential numerical regressions used shorter deterministic cases rather than a second full-year search. Existing NumPy/pandas deprecation warnings are visible in the test suite.
