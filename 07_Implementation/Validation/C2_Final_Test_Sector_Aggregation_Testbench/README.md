# EE499 Team 16 — 15-bus sector aggregation forecasting

Reference repository (read-only; not modified): https://github.com/Islahi/EE499-Team16.git

## Scientific question

A: **sum same-sector hourly bus kW, then fit and forecast that sector total** (3 fresh fits). B: **fit and forecast each of the 14 buses separately, then sum their forecasts**. Both employ the same sector-specific winning configuration and fixed selected hyperparameters. **This is not a comparison against a single feeder-wide forecast.** No Distributed_Total MSTL, Cohort_SumOfMeterLoads, or reported prior 18.13% improvement is used as a comparator.

Selected family/configuration: residential `CalendarRidge__daily_weekly_monthly_yearly`, commercial `XGBoost__daily_weekly_monthly_yearly`, manufacturing `LightGBM__daily_weekly_monthly_yearly`; Bilbao modeled PV `XGBoost__daily_weekly_monthly_yearly` is **not** trained here.

## Run on Windows 10/11 (PowerShell)

Extract the complete ZIP with Windows Explorer. Launch PowerShell in the extracted folder and run:

```powershell
py -3 --version
py -3 -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS = "2"
$env:OMP_NUM_THREADS = "2"
$env:MKL_NUM_THREADS = "2"
py -3 forecast_bench.py --recompute
py -3 forecast_bench.py --verify-only
Start-Process .\dashboard.html
Start-Process .\EE499_Sector_Aggregation_Report.pdf
```

Or double-click `RUN_WINDOWS.bat` (installs dependencies, tunes using training only, runs 17 fresh main fits, generates all outputs and verifies them). `VERIFY_WINDOWS.bat` checks the already packaged outputs **without retraining**; it only requires NumPy and pandas. A full rerun requires XGBoost, LightGBM, scikit-learn, matplotlib and ReportLab. Run time depends on processor, library versions and available threads; saved times were measured during this package's run, not predicted for your computer.

The browser dashboard is self-contained (no file fetch, network access, local server or external library). Choose sector/feeder and July, full-year daily, full-year monthly or a custom inclusive range; toggle the three traces and inspect A-minus-B on a separate axis.

## Data and holdout

- Source: `input/load_profile.csv` 43,921 consecutive hours, 2017-06-01 00:00 through 2022-06-05 00:00; 15 buses, with bus 1 zero-demand slack. `bus_assignments_used.csv` is authoritative for types.
- Training: 2017-06-01 through 2020-12-31 23:00, 31,440 hours. **Model forecast origin:** 2021-01-01 00:00. Test: 2021-01-01 through 2021-12-31 23:00, 8,760 hours, a single fixed-origin annual horizon.
- Original distributor construction normalized its raw sector input using the **complete 2017–2022 period** (including the 2021 holdout). This is documented separately from the downstream model's strictly training-only normalizer, tuning and fitting. The upstream preprocessing may leak information into the benchmark; it is not independently corrected here, because that would change the supplied network inputs.
- Source `pv_profile.csv` is a zero placeholder. Common irradiance does *not* mean identical actual PV kW across separately rated installations. PV is not compared.
- Inputs are **bus active-demand kW**. Do not substitute the cohort's normalized `kW/customer` histories.

## Matched old-code implementation, not certified bitwise historical reproduction

From the archived `C2_FixedCohort_Ranked22_Updated/extra_models.py`:

- Calendar features consist of continuous linear trend and sin/cos Fourier components of 24, 168, approximately 720, approximately 8760 hours, hour-of-day dummies, day-of-week/weekday-weekend effects, and month-of-year effects. The archived definitions, with only the requested seasons included, are mirrored in `forecast_models.py`.
- Input normalization is `scale=max(mean(abs(y_train)),1e-6)`; each target is normalized before fitting and denormalized afterwards. Negative forecasts are clipped at zero.
- The last 120 days of **training only** are the validation period. On one representative bus per sector, CalendarRidge chooses Fourier richness (0.5,1.0,1.5) and alpha (0.1,10,1000); XGBoost/LightGBM select one of the original three boosting settings using validation MAE. The selected settings are **frozen** for both A and B and saved in `results/model_settings.json`.
- Booster `random_state=16`, `n_jobs=2`, XGBoost `tree_method=hist`, regression squared-error loss. One sequential outer fit at a time; shared calendar features only, no fitted-model or prediction reuse. The sector tune is counted separately from the 3 and 14 main fits.
- The C2 archive did not include exact per-job selected settings or guaranteed matching fitted binary versions; `reference/archived_reproduction_bus14.npz` includes the 14 archived 2021 forecast traces decoded from the standalone C2 explorer. `results/archived_reproduction_check.csv` reports measured deviations and source actual drift. The label is therefore **matched rerun**, not guaranteed byte-for-byte reproduction.

## Accuracy metrics and files

Scoring uses identical actual sector totals for A and B. The feeder is the **sum of the three sector forecasts from each approach**, never a feeder-wide fit. Error is actual minus forecast. `MASE_168` divides MAE by the mean absolute **training-only** 168-hour difference of each target. WAPE = 100 sum abs error / sum abs actual; sMAPE = mean 200 abs error / max(abs actual + abs forecast, 1e-8). The yearly and monthly metrics score summed hourly predictions before calculating nonlinear metrics. A positive `A_rmse_reduction_vs_B_pct = 100*(RMSE_B-RMSE_A)/RMSE_B` favors A. `B_minus_A_wape_percentage_points` favors A if positive.

`results/` contains: full-year & monthly scores/differences, per-bus statistics (complete and 2021), per-bus allocated/direct forecast accuracy, 26 within-sector bus pair comparisons per period, 2021 and complete correlation matrices, archival 2021 reproduction comparisons, 17 per-fit runtimes, overall timing, model and library versions, scaling diagnostics, duplicate fit agreement and verification JSON. `*_hourly.csv` has 8,760 timestamps/actual/A/B for each sector and feeder; `bus_forecasts_hourly.csv` has 131,400 rows (15 buses incl. slack x 8760), including direct B and allocated A values. `figures/` contains **separate PNG** charts for all four targets, a dedicated near-zero difference view, 2021 monthly means and a representative-bus variability view. `dashboard.html` and `EE499_Sector_Aggregation_Report.pdf` present the results offline.

## Interpretation limits

The 14 loaded buses in this test use **exactly three** nonzero hourly histories; buses *within a sector are identical*, not statistically independent. Equal-share allocation is therefore justified only for this case. Approach A needs an allocation method for each bus before power flow; Approach B returns bus predictions directly. Results on this feeder reveal differences under scaling/algorithm numerical behavior and computational overhead; they cannot establish which approach forecasts independently varying real-world distribution buses more accurately. Before production integration, revalidate with spatially different bus histories and a truly prospective input-normalization pipeline.
