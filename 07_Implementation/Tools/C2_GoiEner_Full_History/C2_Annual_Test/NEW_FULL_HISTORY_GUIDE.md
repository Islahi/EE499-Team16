# C2 — Full GoiEner history (2017 to latest full year)

EE499 Team 16 — https://github.com/Islahi/EE499-Team16.git

## Data to download

- GoiEner v7.1 Zenodo: https://zenodo.org/records/22313409
- Download **annual_consumption_raw.csv.zst** (about 1.4 GB) and **README.txt**.
- Place the `.zst` file, **still compressed**, at `Data/GoiEner_v71/annual_consumption_raw.csv.zst`.
- Do **not** download all six 1GB+ `profiles_part*.tar.zst` archives: this benchmark uses the processed annual matrix.

The v7.1 release's last measurement year **must be determined from the file**; do not confuse the 2026 publication date with the date of its last measured load record.

## Windows (one-time installation, then 3 steps)

1. `05_PREPARE_GOIENER_FULL_HISTORY_WINDOWS.bat` to scan all annual records, assess year coverage, select a fixed-meter cohort, and produce `C2_full_history_data/goiener_hourly_load.csv`.
2. `06_DOWNLOAD_NASA_FOR_MATCHING_YEARS_WINDOWS.bat` (optional but recommended) to obtain 5 separate site solar-irradiance histories through the same last full year. NASA data are converted to *modelled PV power* at an illustrative 490 kW/site using our project model; they are **not GoiEner metered PV output**.
3. `08_QUICK_CHECK_FULL_HISTORY_WINDOWS.bat` to test the prepared load for one easy model; then `07_RUN_FULL_HISTORY_ALL_MODELS_WINDOWS.bat` for the full 9-model comparison.

Python 3.12 is a conservative choice if Python 3.14 produces model errors. Check available Python installations with `py -0p`. We do not require a version change unless necessary.

## Command-line controls

```powershell
py -m pip install -r requirements.txt
py -m pip install zstandard
py prepare_goiener_v71.py --start-year 2017 --population balanced
py download_nasa_full_history.py
py run_c2_full_history.py --models SeasonalNaive --seasonalities weekly --categories load
py run_c2_full_history.py
```

Change the final comparison calendar year if needed:

```powershell
py prepare_goiener_v71.py --start-year 2017 --end-year 2021 --min-panel 20
py run_c2_full_history.py --test-year 2021
```

For other scripts:

- `--models AutoARIMA AutoETS AutoCES AutoTheta MSTL AutoTBATS AutoMFLES SeasonalNaive HoltWinters`
- `--seasonalities daily weekly monthly_30d yearly_365d daily_weekly daily_weekly_monthly daily_weekly_monthly_yearly`
- `--categories load pv`
- `--max-jobs 5` to test a few model settings first
- `--timeout-seconds 3600` for per-job timeouts
- `--unsafe-long-single-season` to force extremely memory-hungry 720/8760-hour seasonal state models (not recommended on ordinary PCs)

## How the GoiEner file is processed

The published annual matrix has **one row per customer and ISO year**, with 8,904 ISO week/day/hour positions. The converter reconstructs real calendar timestamps with `date.fromisocalendar()`, skips non-existent ISO week-53 days, then sums customer hourly electricity consumption into a time series.

**Important:** Summing different customers in 2017 and the latest year can produce artificial jumps caused by changing customer counts. Our default (`--population balanced`) selects customers with complete eligible annual records throughout the selected years. The resulting *continuous fixed-meter cohort* is appropriate for annual forecasting comparison, but is **not the consumption of all GoiEner customers**. To use all available complete annual records, choose `--population all_complete` and document how the population changes over time. Do not interpret customer-entry effects as changes in electricity demand.

Each hourly `kWh` observation is interpreted as the **average kW during that one hour**. An unmeasured actual value is never silently represented as a true observation; the converter marks any filled timestamp with `filled_hour=1`, and the scoring script **excludes those hours from accuracy metrics**.

**There is only one forecast issued at the start of the last full year**. The model is trained on the preceding years starting in 2017; it is not retrained daily using future data. One held-out calendar year has 8,760 hours, or 8,784 for a leap year.

## Models, metrics, and run isolation

The exact same nine forecasting methods as the earlier C2 benchmark are included:
AutoARIMA, AutoETS, AutoCES, AutoTheta, MSTL, AutoTBATS, AutoMFLES, SeasonalNaive, HoltWinters.
All supported daily (24), weekly (168), approximate monthly (720), annual (8760), and relevant multi-seasonality options can be tested.

Metrics for **load** and **modelled PV** are separate: MAE, RMSE, WAPE, MASE (train-only 168-hour denominator), Bias (actual minus predicted), monthly energy error and peak error. Fit/forecast durations are recorded. Each job runs in a **separate subprocess** and results are written to disk for restart; the console warning log stays in `worker_console.txt`. Memory-intensive single-period models are marked SKIPPED by default for monthly/yearly cases, with an explicit option to force them.

Output: `C2_full_history_results/load_model_scores.csv`, `pv_model_scores.csv`, `all_model_scores.csv`, and per-run `hourly_comparison.csv`/`monthly_metrics.csv` files.

## Solar caveat and timezones

The first GoiEner datasets are Spanish end-user smart-meter load profiles. This new v7.1 download alone does **not** provide a matched irradiance history for all five C2 sites. The optional NASA POWER downloader uses the official hourly API, requested in UTC. GoiEner annual time series are reconstructed from an ISO grid with its own local DST handling. These two series are therefore evaluated **independently** and must not be presented as co-measured power at the same distribution system.

NASA POWER reference: https://power.larc.nasa.gov/docs/services/api/temporal/hourly/

## Execution status

The authoring environment cannot download the 1.4 GB GoiEner source or install/run StatsForecast. The converter and runner are provided for local execution and can be checked on small synthetic fixtures. **Do not claim final nine-model results until your Windows run produces actual metrics.**

## Plot outputs

After completing the benchmark, run `09_PLOT_FULL_HISTORY_RESULTS_WINDOWS.bat` (or `py plot_c2_full_history.py`). It generates:

- Best-model RMSE rankings, separately for each load/PV dataset.
- Model execution time comparisons.
- Best-model monthly actual-versus-forecast plots.

All plots are saved in `C2_full_history_results/plots/`.
