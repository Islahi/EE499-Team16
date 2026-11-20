# C5 Validation — 15-Bus System 1, all 14 non-slack BESS locations

**Completed run:** January 1–31, 2019 (744 consecutive hours), with `T04_15-Bus_System_1.xlsx`, PV at bus 13 (490 kW rated), user-supplied GoiEner distributed load and NASA POWER irradiance, strict final 0.95–1.05 pu limits, and original `src_accelerated` physical simulation/economic/search functions.

## 1. Reference network, raw baseline, and controlled baseline

The *uncorrected* network (no BESS, no curtailment and no shedding permitted) reached **0.857438 pu** and experienced **5,123 violating bus-hours** over the month. This is an infeasible reference, not an acceptable cost comparison. It differs from the static nominal-load C1 result because the real-input hourly loads vary significantly.

The *controlled* no-BESS baseline permits the simulator's corrective actions. It achieved **0.950000–1.000000 pu** at every bus-hour, but required **403,472.95 kWh of load shedding**. This makes the comparison meaningful: the optimized BESS must be judged against the *same* corrective controls, and reduction in shedding must not be confused with eliminating the underlying overload.

## 2. Exact catalog comparison

| Property | Value |
|---|---:|
| Eligible BESS locations | 2–15, all 14 non-slack buses |
| Power options | 50, 100, 150 kW |
| Energy options | 100, 200, 300 kWh |
| Exhaustive catalog | 126 combinations |
| Candidates feasible *after controls* | 126/126 |
| Lowest cost BESS | **bus 13, 100 kW, 300 kWh** |
| GA exact best found | **15/20** seeds |
| GWO exact best found | **20/20** seeds |
| GA/GWO within 5% of exact best | 20/20 each |
| Catalog total cost spread | **1.658%** |

**Important:** Because every feasible configuration is within 5% of the best, the 5% success criterion is **non-discriminating in this catalog**. Exact optimum matches (15/20 GA, 20/20 GWO) give stronger evidence of search quality. GA and GWO use a precomputed table of values from all real physical-simulation evaluations; search time is not comparable to end-to-end power-flow optimization time.

## 3. Network outcomes: controlled baseline versus BESS

| Metric | Controlled no BESS | Optimal BESS | Interpretation |
|---|---:|---:|---|
| Minimum bus voltage (pu) | 0.950000 | 0.950000 | Both comply after shedding/controls |
| Maximum bus voltage (pu) | 1.000000 | 1.000000 | Slack/reference contributes the maximum |
| Voltage violations (bus-hours) | 0 | 0 | Both compliant after controls |
| Load shedding (kWh/month) | 403,472.95 | 396,073.56 | **Reduced by 7,399.39 kWh (1.83%)** |
| PV curtailment (kWh/month) | 0 | 0 | None required |
| Network losses (kWh/month) | 33,308.46 | 34,035.19 | **Increased by 726.73 kWh** |
| Grid import (kWh/month) | 783,515.28 | 792,306.09 | Increased with battery charging and served load |
| BESS charging (kWh/month) | — | 7,694.21 | Grid-charged scheduled mode |
| BESS discharging (kWh/month) | — | 7,029.52 | Accepted by battery/controller |
| Annualized cost (illustrative USD/year) | $58,851,875.80 | $57,857,342.29 | **Reduced by $994,533.51 (1.69%)** |

The optimization primarily rewards reducing shedding under the assumed **$12/kWh** unserved-energy penalty. This makes the modeled annual cost and savings very sensitive to that penalty and the artificial annualization of a high-load month. Neither should be represented as a verified utility cost saving.

At the hour of maximum measured BESS voltage effect (January 12, 2019, 18:00), bus voltages differ by as much as **0.006941 pu** versus the controlled no-BESS baseline. However, the BESS does **not** eliminate the need for corrective load shedding; both cases reach the 0.95 pu boundary after controls. The slight voltage improvement, higher network losses, and reduction in unserved demand should all be shown, rather than selecting only the favorable metrics.

## 4. Essential interpretation and limitations

1. **Voltage strictly enforced:** All 126 *feasible* candidates and the controlled base case pass final 0.95–1.05 pu. The uncorrected baseline deliberately fails. The simulator may shed load to satisfy the limits; a compliant voltage is not sufficient evidence that storage independently corrected undervoltage.
2. **All bus locations evaluated:** The catalog includes each bus from 2 through 15, including PV bus 13, and excludes slack bus 1.
3. **Long horizon, not repeated synthetic day:** January 2019 data provides 744 measured/profile-derived hourly entries, not a repeated 24-hour profile. `HORIZON_MONTHS` and `HORIZON_DAYS` allow changing the period.
4. **Dispatch:** The experimental scheduled policy charges from grid during 00–04 and requests discharging 17–20. It is not optimal dispatch or renewable-surplus-only charging. Charge/discharge efficiencies are 95% each, SOC 20%–100%.
5. **Source alignment:** NASA POWER irradiance is UTC near Madrid; GoiEner load stamps have no documented time zone. Solar power is modeled from irradiance and a chosen 490 kW rating. Calendar-label alignment is an assumption.
6. **Costs:** The previous C4 two-coefficient example ($770/kW and $385/kWh) was reused for a *validation scenario*. NREL's Appendix Table A-5 gives these as equivalent unit descriptions of one two-hour total storage cost rather than independent additive components. See [NREL Storage Futures Study](https://www.nrel.gov/docs/fy21osti/77449.pdf). Imported electricity, shedding and O&M costs are other test assumptions.
7. **Search baseline:** The comparison is between feasible **installed-BESS candidates**. An optimizer that cannot choose zero capacity does not directly decide whether to install a battery at all; the no-BESS case is reported separately.

## 5. Reproducible files

- `run_c5.py`: generate source profiles, run raw and controlled baseline, evaluate all 126 candidates, run GA/GWO, produce voltage/SOC/convergence figures.
- `prepare_c5_inputs.py`: validate source workbook and generate continuous hourly inputs with provenance.
- `c5_settings.py`: edit months, days, start date, bus choices, SOC, costs and search settings.
- `verify_c5_results.py`: independently checks input and voltage tables, all bus locations, counts and SOC limits.
- `C5_results/C5_experiment_report.md`: detailed numerical run report.
- `C5_results/raw_vs_controlled_baseline_buses.png`: raw versus controlled bus voltages at the raw worst hour.
- `C5_results/voltage_by_bus_max_effect_hour.png`: controlled baseline versus optimal BESS voltages where their difference is greatest.
- `C5_results/base_vs_optimized_summary.csv`: full comparison, including infeasible raw baseline flagged as such.

**Implementation reference:** https://github.com/Islahi/EE499-Team16.git — `07_Implementation/src_accelerated/optimizer.py`, `simulation.py`, `fbs.py`, `metrics.py`, `bess.py`.
