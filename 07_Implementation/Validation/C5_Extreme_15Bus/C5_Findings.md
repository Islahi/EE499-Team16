# C5 — Extreme Solar / Grid Constraint Experiment: Findings

**Network:** 15-bus System 1 (T04), based on the original EE499 Team 16 accelerated power-flow implementation. All non-slack buses **2–15** were eligible for battery installation. No GitHub files were changed by this local experiment.

Repository: https://github.com/Islahi/EE499-Team16.git

## Why another C5 case was needed

The preceding 15-bus C5 experiment used low installed PV and unrestricted grid import/export. It showed no PV curtailment, meaning that case could not verify the optimizer's ability to reduce curtailment. This new scenario intentionally stresses BOTH the load-serving and excess-PV operating conditions. Its purpose is to test the program, not represent measured system conditions.

## Synthetic test case, July 2017 (744 hours)

- The load profiles from the GoiEner distribution archive are increased to **1.60 times** the source profile at every bus, for active and reactive load.
- One PV plant is modeled at **bus 13**, rated at **2,000 kW**; actual hourly power follows the provided NASA POWER irradiance profile and the project's existing PV model.
- The grid connection at slack bus 1 permits **up to 650 kW import**, and **zero export**.
- Voltage limits **0.95 to 1.05 pu** are enforced for every accepted final operating point, but **PV curtailment and load shedding are allowed corrective actions**. A feasible case can therefore still shed load or curtail solar.
- Line thermal limits were deliberately disabled because complete validated line ampacities were unavailable.
- BESS power choices: **100, 250, 500 kW**; energy capacity choices: **300, 750, 1,500 kWh**; location choices: **2–15**. Total **126** discrete candidates.
- BESS uses the original `GridAwareDispatchPolicy` (solar-surplus charging/net-demand discharging); SOC **20–100%**, initial SOC **50%**, with charging/discharging efficiencies **95%** each.

## Before any corrective controls

- Minimum network voltage **0.897321 pu**; maximum **1.084622 pu**.
- **1,794 undervoltage bus-hours**, **65 overvoltage bus-hours**, **1,859 total violated bus-hours** across 744 hours × 15 buses.
- **154 hours** contained more aggregate modeled PV than total modeled load.

Without BESS but **with** corrective controls and the import/export caps, final voltage is maintained within the allowed range by curtailing PV and shedding load. Thus the strict feasibility result should NEVER be described as zero loss of service.

## Why limiting export produces curtailment

| No-BESS condition | Export cap 0 kW | No export cap |
|---|---:|---:|
| Curtailed solar (kWh) | 40,648.17 | 14,536.92 |
| Exported energy (kWh) | Approximately zero | 23,278.89 |
| Shed demand (kWh) | 189,272.08 | 189,272.08 |

Removing the grid export restriction lowers curtailment by **26,111.25 kWh** but does not remove it, because voltage constraints can still limit high PV injection. The no-export-cap counterfactual keeps the *same* demand, PV, voltage limit and grid import cap.

## Exhaustive versus GA/GWO

- **114/126** catalog configurations were feasible.
- **12 candidates** were infeasible: all combinations with **bus 12 or 13**, **250 or 500 kW** and the three energy capacities. Those retained overvoltage up to **1.054251 pu** in the final operating point. The optimizer correctly rejected them.
- **Exhaustive catalog best:** **bus 15**, **250 kW**, **1,500 kWh**.
- **GA** found this exact configuration in **14 of 20 runs**; **GWO** in **17 of 20 runs**. Both methods were within 5% of the exact cost in **20 of 20 runs**.
- Entire feasible catalog spans about **5.125%** from lowest to highest cost.
- These GA/GWO timings use a lookup table of scores that were **first physically evaluated** by the original simulator. Search times do not include the physical-evaluation time. The exhaustive physical run took about **336 seconds** in this execution environment.

## Main technical results (controlled base vs catalog-best BESS)

| Metric | No BESS | Optimal BESS |
|---|---:|---:|
| PV curtailment (kWh) | 40,648.17 | 23,051.10 |
| Load shedding (kWh) | 189,272.08 | 178,702.90 |
| Grid import (kWh) | 327,860.07 | 324,807.07 |
| Grid export (kWh) | ~0 | ~0 |
| Network losses (kWh) | 47,417.55 | 49,709.56 |
| Battery charge / discharge (kWh) | — | 21,644.89 / 19,962.02 |
| Min/max final voltage (pu) | 0.95 / 1.05 | 0.95 / 1.05 |
| Illustrative annualized modeled cost (USD/yr) | $27,547,873.31 | $26,153,990.71 |

**Compared with the controlled base, the selected BESS reduced load shedding by 10,569.19 kWh (5.58%), PV curtailment by 17,597.08 kWh (43.29%), and illustrative annualized modeled cost by about 5.06%.** Line losses, however, **increased by 2,292.01 kWh** (4.83%). It does not improve every metric. It also does not eliminate all shedding or curtailment.

## Interpretation and cautions

1. These are **stress-test results from synthetic load and solar scaling**, not a real feeder deployment outcome.
2. The **650 kW import cap** drives substantial shedding, which dominates the result because the assumed lost-load penalty is **$12/kWh**. A different limit or penalty could change the ranking substantially.
3. The objective minimizes **one annualized cost**, combining battery cost, grid cost/revenue, PV-curtailment penalty, load-shedding penalty, and terminal SOC adjustment. Voltage is a **hard constraint**, not a direct maximization of voltage.
4. Exported energy and curtailed energy are **not the same**. The program credits exported kWh at its configured export tariff; it separately penalizes curtailed kWh. This test does **not** include an export fee.
5. If the PV curtailment penalty is intended solely to represent *lost export revenue*, then treating it as an additional penalty alongside the export revenue opportunity could **double-count** the economic consequence. The underlying economic interpretation and any real tariffs must be justified in the report.
6. The $770/kW and $385/kWh BESS coefficients are treated as **two independent illustrative model inputs**. Their sum should not be attributed to a specific published battery-price table; the NREL table previously discussed uses those units as alternative expressions for a specific configuration.
7. The sample-to-year economic conversion `8760 / 744` creates annualized **comparison scores**, not a verified real annual cost prediction.
8. High generation at bus 13 may require equipment upgrades. **Thermal/line-ampacity feasibility is not established** because line current limits are not verified.
9. The PV and load data originate from different sources with unverified time-zone alignment. The PV is generated through a model, not directly measured onsite.
10. GWO is the standard implementation in the included project source snapshot, and the dispatch is rule-based; the test does not claim an improved GWO or optimal multi-hour charging schedule.

## Most relevant outputs

- `C5_results/C5_experiment_report.md` — automatically generated findings with full metrics.
- `C5_results/base_vs_optimized_summary.csv` — all baseline and representative optimized cases.
- `C5_results/exhaustive_candidates.csv` — individual results for all 126 combinations.
- `C5_results/algorithm_summary.csv` and `search_runs.csv` — GA/GWO validation.
- `C5_results/raw_vs_controlled_min_max_voltage.png` — both voltage limits before/after controls.
- `C5_results/curtailment_comparison.png`, `shedding_comparison.png` — effect of BESS.
- `C5_results/solar_surplus_first_72h.png` and `net_load_and_surplus_full_horizon.png` — evidence of PV surplus.
- `C5_results/best_cost_by_bus.png`, `feasible_candidates_by_bus.png` — comparison of all possible locations.
- `C5_results/bess_power_and_soc.png` — actual battery behavior.

Run `python run_c5.py` and then `python verify_c5_results.py` from the extracted directory; see `README.md` for configurations and dependency installation.
