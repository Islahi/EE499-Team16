# EE499 Team 16 — C5 Extreme Stress Test (15-bus System 1)

This is a **separate, reproducible, local validation kit** for the team's existing `07_Implementation/src_accelerated` code. The source modules are copied without modification from the C5 System 1 test kit; the stress case changes only the **external test settings, input profiles, orchestration, and plots**. This package has not been pushed into GitHub.

Project repository: https://github.com/Islahi/EE499-Team16.git

## Research question

With a weak radial distribution feeder, can a battery installed at any non-slack bus (buses 2–15) help maintain the **0.95–1.05 pu** voltage requirement while reducing both **unserved demand (load shedding)** and **unused available PV (curtailment)** when utility-grid imports and exports are constrained?

**Zero-export curtailment is not the same as energy exported to bus 1.** Exported kWh are separately counted, and the objective credits exports at the configured export tariff; curtailed kWh are penalized at the configured curtailment rate.

## Scenario — intentionally synthetic

`c5_settings.py` controls everything:

| Setting | Default | Meaning |
|---|---:|---|
| `START_DATE` | `2017-07-01` | Start date drawn from the original input archive |
| `HORIZON_MONTHS` | `1` | Calendar months, default full July 2017 (744 hours) |
| `HORIZON_DAYS` | `None` | Override with `2` for a 48h pilot |
| `LOAD_MULTIPLIER` | `1.60` | Multiply both active and reactive demand at all buses by 1.6 |
| `PV_BUS` | `13` | One modeled PV installation at bus 13 |
| `PV_RATING_KW` | `2000` | Installed PV nameplate; hourly output is lower and computed from observed irradiance via existing PV model |
| `GRID_IMPORT_LIMIT_KW` | `650` | Maximum allowed import through slack bus 1 |
| `GRID_EXPORT_LIMIT_KW` | `0` | Grid export prohibited in primary test |
| `VOLTAGE_MIN_PU` / `MAX` | `0.95` / `1.05` | Hard *post-control* voltage limits across every bus and hour |
| `DISPATCH_MODE` | `grid_aware` | Battery charges from available solar surplus and discharges against net demand |
| `ALLOW_PV_CURTAILMENT` / `ALLOW_LOAD_SHEDDING` | `True` / `True` | Physical corrective actions recorded and penalized |
| `ENFORCE_LINE_AMPACITY` | `False` | Ampacity values not verified for this feeder. **Thermal feasibility is not established.** |
| `ALLOWED_BUS_IDS` | `2...15` | 14 candidate locations; bus 1 excluded |
| `POWER_RATINGS_KW` | `100,250,500` | Discrete power ratings |
| `ENERGY_CAPACITIES_KWH` | `300,750,1500` | Discrete energy capacities |
| `RUN_SEEDS` | `20` | 20 seeded runs each of GA and GWO |

Total catalog size = **14 × 3 × 3 = 126 physical candidates**. The test uses the actual project FBS simulator, BESS state model, economic evaluator, and GA/GWO/exhaustive optimizers.

The 1.6× load and 2 MW installed PV rating are **stress-test assumptions**. They are *not* the historic feeder's observed load or installed solar capacity. It is not established that a single 2 MW PV plant would be permitted on this feeder. Do not describe them as measured.

## Installation and execution

Install a modern Python 3 environment and dependencies:

```powershell
python -m pip install numpy pandas matplotlib openpyxl
python run_c5.py
python verify_c5_results.py
```

The scripts assume the distributed GoiEner load ZIP, NASA POWER irradiance CSV, original `T04_15-Bus_System_1.xlsx`, and the `src_accelerated/` Python package are present in the extracted folder (all included).

To shorten a new run, edit `HORIZON_DAYS = 2` in `c5_settings.py` and optionally `RUN_SEEDS = 2`. For longer runs, set `HORIZON_DAYS = None` and `HORIZON_MONTHS = 2` or more. Time horizon must lie within the source demand/irradiance overlap. **Each run overwrites results in `C5_results/`.** Make a copy first if preserving the completed reference outputs.

## Experiment design

1. Generate hourly profiles from source archives. Verify that all 15 demand buses are included and that the loaded network matches the original nominal bus loads before scaling.
2. Run the uncorrected no-BESS baseline, with both curtailment and shedding disabled. Record raw bus voltages and grid exchange, but do not call it feasible.
3. Run the controlled no-BESS baseline with 650 kW import and 0 kW export limits, allowing curtailment/shedding as needed. Record both penalties.
4. Run a **separate unrestricted-export counterfactual**: change only the **export cap** to `None`, keeping the same voltage, import, load, and PV settings. This shows the consequence of export rules; voltage constraints can still require curtailment.
5. Evaluate all 126 BESS configurations against the same **capped** baseline, with grid-aware dispatch, strict final voltage limits, and recorded battery SOC.
6. Exhaustive search gives the catalog optimum. Run GA and GWO on the **same precomputed physical evaluations**, 20 seeds each, to assess search reliability. These search timings **exclude** the earlier physical simulations.
7. Re-simulate representative GA, GWO, and exact optimum candidates to produce hourly voltage, controls and battery-operation plots.

## Cost objective and caveats

The program's **single optimization objective** is annualized financial cost:

`annual_cost = annualized_BESS_capex_and_OM + annual_grid_cost + annual_curtailment_penalty + annual_shedding_penalty + annual_terminal_SOC_adjustment`

The settings use **illustrative, not independently validated** coefficients: import $0.20/kWh, export revenue $0.05/kWh, curtailment penalty $0.07/kWh, load shedding penalty $12/kWh, BESS cost coefficients $770/kW power + $385/kWh energy, 6% discount rate, 10-year lifetime, 2% annual O&M. The two BESS unit rates are **independent assumed model coefficients**, not a quote from a published battery cost table.

An export fee is **not** modeled. Export would enter as a credit, not a curtailment cost. Without evidence of actual export fees, none should be fabricated. When grid export is capped at zero, resulting exported energy is approximately zero, with small numerical tolerance.

The model annualizes the tested period with a simple `8760 / simulated_hours` multiplier. One-month synthetic-stress annualized totals are **comparative objective scores**, not a forecast of actual annual Saudi or European costs.

## Expected output files

- `C5_results/C5_experiment_report.md`: measured run results and interpretation.
- `C5_results/test_settings.json`: exactly what settings and file SHA checksums generated results.
- `C5_results/exhaustive_candidates.csv`: 126 candidate scores and technical outcomes.
- `C5_results/algorithm_summary.csv`, `search_runs.csv`, `convergence_history.csv`: GA/GWO validation.
- `C5_results/best_cost_by_bus.png`, `feasible_candidates_by_bus.png`: location-by-location performance and strict-feasibility screening.
- `C5_results/base_vs_optimized_summary.csv`: raw base, controlled capped base, uncapped-export base, and best BESS.
- `C5_results/unrestricted_export_baseline_summary.csv`: no-export-limit counterfactual.
- `C5_results/raw_baseline_voltage_hourly.csv`: all bus/hour pre-control voltages.
- `C5_results/base_vs_best_voltage_hourly.csv`: every post-control bus/hour with and without BESS.
- `C5_results/optimized_bess_hourly.csv`: requested versus actual charge/discharge, SOC, and grid energy flow.
- `C5_results/raw_vs_controlled_min_max_voltage.png`: displays *both* undervoltage and overvoltage.
- `C5_results/solar_surplus_first_72h.png`, `net_load_and_surplus_full_horizon.png`: visual evidence that modeled PV sometimes exceeds total demand.
- `C5_results/curtailment_comparison.png`, `shedding_comparison.png`, `slack_power_comparison.png`: effects of the actual controller actions.
- `C5_results/bess_power_and_soc.png`, `voltage_difference_heatmap_full_horizon.png`, `convergence_comparison.png`: physical and optimization diagnostics.

## Interpret correctly

- **Uncorrected voltage violations** show a genuine physical stress case.
- **Post-control voltage compliance** may be achieved by refusing to serve some demand and turning down PV. These outcomes must not be confused with solving the voltage problem without consequences.
- **BESS dispatch is heuristic**. The optimizer chooses location/power/energy, not a mathematically optimal 744-hour charge/discharge schedule.
- **No verified ampacity limits:** this package cannot claim complete network feasibility.
- **Time-zone mismatch:** the source GoiEner load archive carries naive timestamps; NASA POWER hourly stamps are UTC and are matched by label without confirmed synchronization.
- **Cost sensitivity:** results depend strongly on assumed value of lost load and battery capital prices.
