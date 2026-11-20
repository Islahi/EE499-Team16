# EE499 Team 16 — Measured findings

**Reference repository (unchanged):** https://github.com/Islahi/EE499-Team16.git

## Outcome

Approach A (sum histories by sector, then fit one sector model) and Approach B (fit all 14 loaded buses independently, then sum forecasts) produced **the same recorded full-year and monthly metrics** and no detectable A-minus-B differences at 12-decimal-kW CSV precision in this matched rerun. Forecasts were produced at the 2021-01-01 fixed origin without observed 2021 loads used in model tuning or fitting.

| Target | MAE (kW), both | RMSE (kW), both | WAPE (%), both | Weekly MASE, both | Signed bias (kW), both | sMAPE (%), both |
|---|---:|---:|---:|---:|---:|---:|
| Residential | 16.88097 | 22.23174 | 9.57657 | 1.43972 | -2.97023 | 9.47832 |
| Commercial | 46.46051 | 69.34361 | 12.78956 | 1.04152 | 5.49958 | 13.36364 |
| Manufacturing | 112.68960 | 166.02330 | 16.20245 | 0.77851 | 2.39567 | 18.07017 |
| Feeder | 138.62558 | 207.18390 | 11.22427 | 0.79739 | 4.92502 | 11.68138 |

**Full-year differences:** RMSE reduction = 0.000000% and WAPE difference = 0.000000 percentage points for all four targets (to exported 12-decimal accuracy). Monthly results are provided for each month and each target with both methods.

## Measured runtime (same process, sequential fits)

| Method | Main fresh fits | Fit sum (s) | Forecast sum (s) | Wall clock (s) |
|---|---:|---:|---:|---:|
| A sum-first | 3 | 2.5141 | 0.0781 | 2.6069 |
| B bus-first | 14 | 13.7542 | 0.4379 | 14.2007 |

Approach A was **5.45 times faster** on measured main-fit wall time. Three sector hyperparameter-selection passes took an additional 14.368 seconds and are excluded from both measured main-fit totals. The 14 bus fits were actually run; no duplicate-result or fitted-model reuse.

## Source data variability audit

- 43,921 uninterrupted hourly records, 2017-06-01 to 2022-06-05 inclusive, with zero gaps, duplicate (timestamp,bus) records, or missing p_kw values.
- Training 31,440 h (2017-06-01 to 2020-12-31), evaluation 8,760 h (2021); p_kw is active power.
- Bus 1 has zero demand. All sector pairs exactly equal for complete 43,921-h and for 2021: residential buses 2/5/10/13 (4); commercial 3/8/9/12/14 (5); manufacturing 4/6/7/11/15 (5). Each sector varies over time.
- There are three distinct nonzero network demand histories. No pair in a sector is unequal, so proportional-but-unequal testing was not exercised.
- The entire-feeder 2021 energy is 10,819,058.333 kWh. The 2021 feeder is exactly four residential profiles plus five commercial plus five manufacturing profiles.

| Representative 2021 bus | Min kW | Mean kW | Max kW | Std kW | CoV | Energy kWh |
|---|---:|---:|---:|---:|---:|---:|
| R — bus 2 | 21.659 | 44.068 | 101.424 | 12.996 | 0.295 | 386039.0 |
| C — bus 3 | 28.324 | 72.654 | 233.202 | 39.391 | 0.542 | 636447.2 |
| M — bus 4 | 28.600 | 139.102 | 352.540 | 77.754 | 0.559 | 1218533.2 |

**2021 cross-sector Pearson correlation** (a pattern diagnostic, not an equality test):

| Sector | Residential | Commercial | Manufacturing |
|---|---:|---:|---:|
| Residential | 1.0000 | 0.2964 | 0.2733 |
| Commercial | 0.2964 | 1.0000 | 0.7631 |
| Manufacturing | 0.2733 | 0.7631 | 1.0000 |

## Reproduction provenance

Recovered the original C2 `extra_models.py` calendar features, mean-absolute-train scaling, 120-day chronological holdout for tuning, regressor hyperparameter grids, 16 random seed, booster 2-thread policy, and zero floor. The archived C2 explorer contains 2021 bus traces and actuals. The original per-job tuned settings and exact fitted-library binaries were not preserved; this is therefore a **matched rerun**, not a certified exact recreation of the benchmark.

| Sector | Archived vs rerun mean RMSE (one bus, kW) | Max absolute diff (kW) |
|---|---:|---:|
| Residential | 0.000560 | 0.001787 |
| Commercial | 1.653513 | 13.185101 |
| Manufacturing | 0.000000 | 0.000000 |

The archived **actual kW** values match source 2021 bus data exactly. The original XGBoost trace differs from this rerun by 1.6535 kW RMS for a representative commercial bus; this is not silently presented as a byte-identical rerun.

**Upstream leakage caveat:** the distributor normalized over 2017-06-01 through 2022-06-05, including 2021. The downstream model fitting and tuning are causal given the distributed input, but upstream normalization is **not** an independently prospective preparation of the holdout data. No train/test boundary interpolation proof was supplied.

## Program implementation recommendation

For this *constructed* feeder, **prefer Approach A** if the objective is low computational cost: three fits instead of fourteen, equal numerical accuracy and training-justified equal-share allocation produce all 14 required bus forecasts without a loss of accuracy on this case. The allocated bus predictions sum back to each sector total to better than 1e-8 kW hourly.

For real feeders with independently varying bus histories, Approach B is directly applicable and preserves spatial variation; no such network was tested here. Avoid exporting this feeder-specific tie as a general accuracy claim. Future work should revalidate with nonidentical bus histories and train-only upstream normalization.

PV: retain `XGBoost__daily_weekly_monthly_yearly` as the chosen Bilbao modeled-PV configuration. No PV data/model were fitted; input `pv_profile.csv` is a zero placeholder. Shared irradiance data do not imply identical electrical output across PV installations of different ratings.

## Reproduction checks

Run `python forecast_bench.py --verify-only`; it recalculates all annual, monthly and per-bus metrics and validates all 8,760 forecast timestamps for each sector and feeder, bus-to-sector sums, equal-share reconstruction and 14-bus feeder identity. `results/verification.json` shows **PASS** from this run.
