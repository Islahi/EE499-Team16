# EE499 Team 16 — C5 on 15-Bus System 1 (all eligible bus locations)

Original source repository: https://github.com/Islahi/EE499-Team16.git

Standalone C5 validation kit built around the **unchanged** `src_accelerated` FBS, storage, simulation, cost, GA and GWO source modules. The test scripts and settings are separate; no upstream project files are patched.

## What changed versus the previous System 2 kit

- **Feeder:** `T04_15-Bus_System_1.xlsx`, from Latreche et al., *Comprehensive Review of Radial Distribution Test Systems*, Table 4. The supplied GoiEner demand was already distributed using this feeder's nominal bus load data; the input generator checks bus-by-bus P/Q against the network workbook.
- **BESS placement:** **every non-slack bus, 2 through 15**, including the solar bus 13. Bus 1 is the source/slack bus and is excluded. Power choices (50, 100, 150 kW) and energy choices (100, 200, 300 kWh) are retained. Total catalog = **14 × 3 × 3 = 126 configurations**.
- **Default period:** **January 2019**, one complete 744-hour calendar month. This is a high-load real-input period chosen because System 1 has significant uncorrected undervoltage here. July 2017 with these time-varying loads would be an easier operating case despite nominal static C1 undervoltage.
- **Three network comparisons:** raw no-BESS baseline **without corrective controls**, controlled no-BESS baseline **with** allowed controls, and lowest-cost feasible BESS. GA and GWO representatives are also recorded.

## Run

From the kit folder:

```powershell
python -m pip install numpy pandas matplotlib openpyxl
python run_c5.py
python verify_c5_results.py
```

The complete default run evaluates all **126** configurations with the actual month-long simulation, then performs **20 seeded GA and 20 seeded GWO** searches using cached, previously simulated deterministic candidate scores. Those algorithm timings therefore **exclude physical simulation time**. The exhaustive stage's simulation runtime is recorded separately.

For a quick check, change `HORIZON_DAYS = 2` and `RUN_SEEDS = 1` in `c5_settings.py` and rerun. Restore both for actual validation. The verification program expects a completed search and available feasible candidate; in the event that all candidates are infeasible, `run_c5.py` keeps candidate evaluations and explicitly reports no feasible winner.

## Adjustable horizon

Edit `c5_settings.py`:

```python
START_DATE = "2019-01-01"
HORIZON_MONTHS = 1         # Change to 2, 3, 6, etc.
HORIZON_DAYS = None        # Set e.g. 2 for a shorter pilot, overriding months
```

The generator selects **actual consecutive hourly records**, not a repeated 24-hour template. It automatically rebuilds `inputs/load_profile.csv`, `inputs/pv_profile.csv`, `inputs/irradiance.csv`, and input metadata. For January 2019 there are 744 hourly points × 15 load buses. Both source files must cover the entire specified horizon (full calendar months between roughly June 2017 and February 2020 are within the overlap). `START_DATE` should be midnight of the chosen start day. Forecasted data is not used in this C5 test.

## Voltage and corrective actions: crucial interpretation

**Strict feasibility:** Every bus and hour must have final, *post-control* voltage in **0.95–1.05 pu**. An infeasible candidate is excluded from the economic optimization minimum. Voltage itself is a **constraint**, not a separate voltage-deviation objective.

`simulate_timeseries()` may shed load or curtail PV in order to restore feasibility. Therefore voltage compliance does **not** imply zero unmet demand. This test deliberately reports:

1. **Raw (uncontrolled) no-BESS:** shows actual voltage violations before load shedding/curtailment, is often **infeasible** and must *not* be treated as an acceptable cost baseline.
2. **Controlled no-BESS:** the grid with the **same permissive load-shedding and curtailment rules as the BESS candidates**. Voltage compliance may be achieved at a large load-shedding cost.
3. **Feasible BESS candidates:** the same limits, load, PV, operating controls and economics, but with installed storage. Compare voltage, loss, load shedding, SOC, charge/discharge, total cost.

**Source/network nuance:** C1's static nominal-load System 1 minimum was ~0.94452 pu. This is **not** the minimum of a month-long hourly case. January 2019 includes much larger time-varying peaks and therefore is reported separately. All outputs must be interpreted with their particular time stamps, feeder and load/PV assumptions.

**Ampacity:** `ENFORCE_LINE_AMPACITY=False` because source workbook lacks complete current ratings; this does **not** relax voltage constraints. Grid import/export are not capped. Both PV curtailment and load shedding are enabled for the *controlled* simulations.

## BESS, PV, dispatch and economics

- PV: **490 kW at bus 13** (downstream, weak-voltage bus), reactive power 0 kVAr. NASA POWER GHI irradiance is transformed into modeled power using the existing `irradiance_to_power()` function. Source location: approximately **40.4168°N, 3.7038°W**. This is **modeled PV, not measured plant generation**.
- Time-zone caveat: NASA data timestamps are UTC, but the distributed load file does **not** specify a time zone. Clock labels are matched without inventing a time-zone shift.
- BESS SOC: 20% min / 50% initial / 100% max. Charge efficiency 95%; discharge efficiency 95%; round-trip efficiency 90.25%.
- `DISPATCH_MODE = "scheduled"` by default: request grid charging at local *timestamp-label* hours 00–04 and discharging 17–20, both as fractions of each candidate's power rating. This policy is intentionally held fixed across configurations (though power requests scale with rating). The original BESS physical limits and simulator network corrections remain active. It is **not optimized dispatch** or solar-only charging. `"grid_aware"` is available but solar-surplus charging seldom occurs because this dataset has no aggregate PV surplus.
- Economic inputs (illustrative): 770 USD/kW **plus** 385 USD/kWh, 6% discount rate, 10-year lifetime, 2% annual O&M, $0.20/kWh import, $0.05/kWh export, $0.07/kWh curtailed PV penalty, $12/kWh unserved load penalty, 8,760 annual equivalent hours. `EconomicConfig` annualizes the selected horizon's operating energy using 8,760 / horizon hours. This is a model assumption, **not** a measured annual outcome from the chosen month.

**Cost reference caveat:** Frazier et al., NREL *Storage Futures Study*, NREL/TP-6A20-77449, Appendix Table A-5, gives 2024 high-cost two-hour prices of **$770/kW and $385/kWh as alternative unit representations of the same total cost**. Adding them as two separate terms is only the *previous C4 illustrative validation convention*, **not a NREL-endorsed cost decomposition**. See https://www.nrel.gov/docs/fy21osti/77449.pdf. Do not interpret resulting monetary savings as validated project economics without a defensible independent cost breakdown.

## Optimizer and evaluation design

- Algorithms: **exhaustive search**, unchanged `genetic_optimize()` (GA) and unchanged `optimize()` (GWO).
- Catalog: 126 configurations. Score: minimum annualized total cost among **post-control feasible** options, with the same deterministic candidate evaluator.
- Stochastic evaluation: 20 distinct seeds per algorithm, population 12, 20 iterations. Records exact catalog-optimal matches, percentage gap, convergence and unique evaluated configurations.
- `USE_PRECOMPUTED_SCORES = True` (default) runs expensive simulations **once per candidate**, then uses identical cached scores for both heuristics. Set `False` to measure end-to-end optimizer runs, at much higher runtime.
- The no-BESS case is **reported**, but not included as a selectable candidate in `exhaustive_search()`; if it is economically better, do not claim that the optimized installed BESS is economically desirable.

## Output guide (`C5_results/`)

| File | Contents |
|---|---|
| `C5_experiment_report.md` | Automatic computed findings and limitations |
| `raw_baseline_summary.csv`, `raw_baseline_voltage_hourly.csv` | No-BESS, no correction; reveals original under/overvoltage |
| `raw_baseline_violation_counts.json` | Exact raw bus-hour counts, raw lowest voltage, number of affected hours |
| `base_case_summary.csv`, `base_voltage_hourly.csv` | No-BESS after voltage controls, including load shedding |
| `raw_vs_controlled_baseline_min_voltage.png` | Full-month **raw vs controlled** hourly minimum voltage |
| `raw_vs_controlled_baseline_buses.png` | All buses at the **worst raw-voltage hour** |
| `base_vs_optimized_summary.csv` | All three cases, including GA/GWO best configurations |
| `base_vs_best_voltage_hourly.csv` | Controlled no-BESS vs exhaustive-best BESS; bus-hour voltage and deltas |
| `voltage_by_bus_worst_hour.png`, `minimum_voltage_over_horizon.png` | Hourly / bus-by-bus voltage comparison with strict thresholds |
| `voltage_by_bus_max_effect_hour.png`, `voltage_difference_heatmap_full_horizon.png` | Identifies small or localized BESS effects |
| `optimized_bess_hourly.csv`, `bess_power_and_soc.png` | Real accepted BESS power, SOC, shedding and curtailment records |
| `exhaustive_candidates.csv`, `search_runs.csv`, `algorithm_summary.csv`, `convergence_comparison.png` | Candidate cost/feasibility, search quality and convergence |
| `inputs/` | Derived hourly load, PV, irradiance, metadata; same CSV input schema as project |

The static network and internal source are copied into the package. All changes are local test harness changes; **no GitHub commit has been performed**.
