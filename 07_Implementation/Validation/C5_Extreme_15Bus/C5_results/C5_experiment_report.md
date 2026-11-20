# EE499 C5 — Extreme import/export and voltage stress (System 1)

**Test date:** 2017-07-01 00:00:00 through 2017-08-01 00:00:00 (exclusive); **744 hours**.  
**Network:** 15-bus System 1, T04 workbook. **Candidate buses:** 2–15 (all non-slack buses).  
**Stress:** historical load ×1.60 for both P and Q; modeled solar rating 2000 kW on bus 13.  
**Bus 1 grid limits:** import ≤650.0 kW; export ≤0.0 kW (zero export).  
**Voltage constraint:** 0.95–1.05 pu at EVERY bus/hour *after* permitted correction.  
**Dispatch:** `grid_aware`; charges from solar surplus, discharges against net demand when possible.  

**Important:** This scenario is deliberately synthetic. Scaled demand and enlarged PV rating are not a forecast, not a historical measurement, and not a claim of engineering realism for this feeder. Line ampacity checks are disabled because verified limits are unavailable.

## 1. Evidence of genuine stress

- Source-derived sample demand **908,355.1 kWh** and modeled available PV **479,288.6 kWh** (after synthetic scaling).
- Hours with *aggregate* solar surplus: **154**.
- Raw no-BESS minimum/maximum voltages: **0.897321 / 1.084622 pu**.
- Raw undervoltage bus-hours: **1794**; raw overvoltage bus-hours: **65**. Total raw bus-hours outside allowed band: **1859**.
- Correction is allowed to shed demand or curtail PV to restore the feasible network operating point. **Feasible does not mean all demand served or all PV used.**

## 2. Why the export limit matters

| No-BESS comparison | Export limited to 0.0 kW | Unlimited grid export |
|---|---:|---:|
| PV curtailed (kWh) | 40,648.17 | 14,536.92 |
| Grid export (kWh) | 0.0001 | 23,278.89 |
| Load shed (kWh) | 189,272.08 | 189,272.08 |
| Annualized modeled cost (USD) | 27,547,873.31 | 27,512,648.07 |

Unlimited export does NOT remove voltage constraints. Any remaining curtailment with unlimited export can be caused by network voltage behavior; see hourly profiles.

## 3. Exhaustive optimization against GA/GWO

- Options: **126** = 14 locations × 3 power sizes × 3 energy sizes; **114 feasible** after allowed controls.
- Catalog optimum: **bus 15, 250 kW / 1500 kWh**.
- Exact matches (GA/GWO): **GA: 14/20, GWO: 17/20**.
- Entire feasible catalog cost spread: **5.125%**. The 5% pass metric is discriminating for this catalog.
- Exhaustive real simulation time: **790.98s**. Search timing is **lookup-only, not end-to-end**.

## 4. Main no-BESS vs best-BESS comparison (same strict limits)

| Metric | Controlled no BESS | Best BESS |
|---|---:|---:|
| Feasible after corrective controls | True | True |
| Voltage min (pu) | 0.950000 | 0.950000 |
| Voltage max (pu) | 1.050000 | 1.050000 |
| PV curtailment (kWh) | 40,648.17 | 23,051.10 |
| Load shedding (kWh) | 189,272.08 | 178,702.90 |
| Grid import (kWh) | 327,860.07 | 324,807.07 |
| Grid export (kWh) | 0.0001 | 0.0000 |
| Line losses (kWh) | 47,417.55 | 49,709.56 |
| Battery charge (kWh) | 0 | 21,644.89 |
| Battery discharge (kWh) | 0 | 19,962.02 |
| Annualized modeled cost (USD/year) | 27,547,873.31 | 26,153,990.71 |

**Change:** shedding decreased by **10,569.19 kWh** (5.58%); PV curtailment decreased by **17,597.08 kWh** (43.29%). Cost changed by **$-1,393,882.60/year** (a sample-extrapolated illustration, not a validated yearly prediction).

## 5. Cost interpretation

- `annual_grid_cost = annual_factor × (import_price × import_kWh − export_credit × export_kWh)`.
- `annual_curtailment_cost = annual_factor × (curtailment_penalty × curtailed_kWh)`.
- `annual_shedding_cost = annual_factor × (VoLL × shed_kWh)`.
- Battery capital is annualized with CRF plus O&M; initial/end SOC imbalance corrected separately.
- **Exported power is not curtailed**. In this model export receives a credit; NO export fee is assumed. A curtailment penalty is an assumed opportunity-cost proxy, NOT an actual payment charged by the grid.
- Import, export, shedding and curtailment monetary coefficients are illustrative, as are both independent battery capital unit rates; sources of current tariffs/fees have not been established.

## 6. Files

- `inputs/input_manifest.json`: original input provenance, stress multipliers, sample energy and count of surplus hours.
- `raw_baseline_voltage_hourly.csv`, `raw_vs_controlled_min_max_voltage.png`: both uncorrected voltage boundaries.
- `unrestricted_export_baseline_summary.csv`: same strict network limits with the grid export cap removed.
- `base_vs_optimized_summary.csv`: technical and economic comparisons.
- `exhaustive_candidates.csv`, `search_runs.csv`, `algorithm_summary.csv`: all candidates and heuristic performance.
- `base_vs_best_voltage_hourly.csv`, `voltage_impact_by_bus.csv`: every bus/hour and voltage changes.
- `curtailment_comparison.png`, `shedding_comparison.png`, `slack_power_comparison.png`: actual network actions and Bus 1 exchange.
- `optimized_bess_hourly.csv`, `bess_power_and_soc.png`: battery operation.

## Limitations and next checks

- Full available PV and source load were intentionally distorted; solar on a single bus at 2 MW may be physically unsuitable without feeder reinforcements. This is an **algorithm stress test**.
- Grid-aware battery control follows a heuristic, not optimal joint dispatch. Any reduction is under that specific policy, not the best achievable operational benefit.
- Line thermal/ampacity constraints are NOT enforced; results cannot demonstrate thermal feasibility.
- The NASA irradiance UTC and GoiEner unspecified local time are matched by timestamp label, not validated in a common physical timezone.
- Monthly results annualized with 8760/simulated_hours assume this window repeats all year. Do NOT interpret as observed annual outcomes.
