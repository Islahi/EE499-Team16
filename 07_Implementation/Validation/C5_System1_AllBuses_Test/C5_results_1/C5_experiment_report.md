# EE499 C5 — Strict-voltage and extended-horizon findings

**Study period:** 2019-01-01 00:00:00 to 2019-02-01 00:00:00 (exclusive), 744 hourly steps.  
**Dispatch:** `scheduled`.  
**PV location:** bus 13. **Battery search locations:** all buses (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15) (excludes slack bus 1).  
**Strict voltage requirement:** 0.95–1.05 pu at every bus and hour, after permitted controls.  
**Optimization objective:** lowest **annualized economic cost** among feasible catalog candidates; voltage improvement is **not** a term in the objective.  

## Source and assumptions

GoiEner distributed demand uses the T04 System 1 nominal bus load values, checked against the T04 network workbook. Irradiance is NASA POWER GHI; PV generation is modeled at **bus 13**, 490 kW rated, using the project's PV model. NASA timestamps are UTC; GoiEner timestamps have an unspecified timezone and are aligned by label. Economic inputs are illustrative C4 figures, not verified current prices.

The original `GridAwareDispatchPolicy` cannot request solar charging in this data: measured/modelled **solar surplus hours = 0**. In the scheduled mode, power requested by the test policy is negative at hours (0, 1, 2, 3, 4) (grid charge) and positive at (17, 18, 19, 20) (discharge), subject to the original SOC/power limits.

## Exhaustive reference and optimizers

- Catalog: 126 discrete configurations; **126 feasible** under the strict network limits.
- Exhaustive best candidate: **bus 13; 100.0 kW / 300.0 kWh**.
- Annualized cost, no BESS: **$58,851,875.80** (illustrative).
- Annualized cost, catalog-best BESS: **$57,857,342.29** (illustrative).
- Change in annualized cost (BESS minus base): **$-994,533.51**.
- Exact catalog matches across seeds: **GA: 15/20, GWO: 20/20**.
- Entire catalog cost spread: **1.658%**. The 5% pass criterion is non-discriminating for this catalog.
- Exhaustive simulation elapsed time: **303.70 s**; optimizer search timing mode: **precomputed objective lookup (not end-to-end)**.

## Technical base/BESS comparison

The **uncorrected no-BESS baseline** has **5123 voltage-violation bus-hours** (minimum 0.857438 pu); the corrected baseline is simulated with voltage controls enabled. These are different operating points, so the corrected baseline may have **load shedding**. Strict voltage compliance is evaluated *after* those controls, not at the raw power-flow operating point. See `raw_baseline_voltage_hourly.csv` and the baseline comparison figures. 

| Metric | Controlled base | Optimized BESS |
|---|---:|---:|
| Feasible | True | True |
| Minimum bus voltage (pu) | 0.950000 | 0.950000 |
| Maximum bus voltage (pu) | 1.000000 | 1.000000 |
| Voltage violation bus-hours | 0.00 | 0.00 |
| Line losses (kWh) | 33308.46 | 34035.19 |
| Grid import (kWh) | 783515.28 | 792306.09 |
| Curtailment (kWh) | 0.00 | 0.00 |
| Load shedding (kWh) | 403472.95 | 396073.56 |
| BESS grid-side charge (kWh) | 0 | 7694.21 |
| BESS grid-side discharge (kWh) | 0 | 7029.52 |

**Interpretation:** Minimum and maximum voltages are across all simulated hours and buses; they may occur at different times. Improvements cannot be inferred from these two extrema alone: check `base_vs_best_voltage_hourly.csv` and voltage plots. Feasibility means that allowed corrective actions have already been applied; any shedding/curtailment still needs reporting.

## Artifacts

- `base_vs_optimized_summary.csv` — raw base, controlled base and GA/GWO/Exhaustive technical and economic comparison.
- `raw_baseline_voltage_hourly.csv`, `raw_vs_controlled_baseline_min_voltage.png`, `raw_vs_controlled_baseline_buses.png` — show voltage violations *before* any load shedding or other corrections.
- `base_vs_best_voltage_hourly.csv` — every bus and hour, base and optimized cases.
- `voltage_by_bus_worst_hour.png` / `minimum_voltage_over_horizon.png` / `voltage_change_worst_hour.png` — comparisons.
- `voltage_by_bus_max_effect_hour.png`, `voltage_change_max_effect_hour.png`, `voltage_difference_heatmap_full_horizon.png`, `voltage_impact_by_bus.csv` — make even small actual voltage effects visible.
- `voltage_heatmap_base.png`, `voltage_heatmap_optimized.png` — worst-base-voltage day, common scale.
- `optimized_bess_hourly.csv`, `bess_power_and_soc.png` — energy operation and cycle evidence.
- `exhaustive_candidates.csv`, `search_runs.csv`, `algorithm_summary.csv`, `convergence_comparison.png` — optimization verification.

## Essential limitations

1. If the strict voltage constraint is already satisfied in the no-BESS case, the chosen battery need not improve voltage; economics remains the **only** optimized objective.
2. Flat grid tariffs mean scheduled grid charging may increase cost; this experiment is a battery-operation/algorithm validation, **not proof of economic advantage**.
3. With lookup mode, GA/GWO runtimes exclude physical simulator costs. Do not claim those times are end-to-end search runtimes.
4. The cost coefficients ($770/kW and $385/kWh) are carried over from the illustrative C4 example. In NREL Storage Futures Study 2024 high-cost 2h case, these are different unit expressions of one cost, not two additive costs. See NREL/TP-6A20-77449, Appendix Table A-5: https://www.nrel.gov/docs/fy21osti/77449.pdf .
5. This is a single specified historical period and modeled PV with an unverified time-zone mapping. It is not universal network or financial validation.
