# C2 — Nine StatsForecast Models, Annual Load/PV Power Benchmark

**EE499 Team 16:** https://github.com/Islahi/EE499-Team16.git

This is an **addition to your uploaded `C2_Annual_Forecasting_and_Plotter_Updated(1).zip`**. The original `run_c2_annual.py`, `plot_profiles.py`, source datasets and network/profiles are retained unchanged. The new benchmark is separate from the main GitHub implementation.

## What is being tested?

- **9 models:** `AutoARIMA`, `AutoETS`, `AutoCES`, `AutoTheta`, `MSTL`, `AutoTBATS`, `AutoMFLES`, `SeasonalNaive`, `HoltWinters`.
- **Four single-season settings:** daily **24h**; weekly **168h**; *approximate* month **720h**; *approximate* year **8,760h**. These are four independent model variants, **not** an assertion that all models simultaneously understand four seasonalities.
- **Extra multi-season settings for MSTL, AutoTBATS and AutoMFLES:** `[24,168]`, `[24,168,720]`, `[24,168,720,8760]`.
- **Same chronological test for every variant:** train June 1, 2017–February 28, 2019 (**15,312 hours**); make **one single forecast** for March 1, 2019–February 29, 2020 (**8,784 hours**). No daily refitting, no use of test-year values during fitting or model selection.
- **Separate categories:** two load cases (total GoiEner sectors and constructed 15-bus demand); five independent NASA POWER solar-site cases, converted to **modelled 490 kW PV output in kW** using the *unmodified project's* `irradiance_to_power()` piecewise equation. This is a solar-production **proxy derived from irradiance**, not a metered PV power dataset. It does not model tilt, temperature, inverter losses, or actual PV hardware.
- **Scores:** MAE (kW), RMSE (kW), WAPE (%), MASE (dimensionless), Bias (kW; **actual minus forecast**, so positive = underestimated), plus sMAPE, monthly energy error, peak error, and positive-actual MAPE for context. **All models use the SAME training-only 168-hour MASE denominator** for fair comparison.
- **Speed:** separate `fit_seconds`, `forecast_seconds` and `total_model_seconds` per model, excluding input preparation and charts. Failed/skipped jobs remain visible in `model_comparison_all_statuses.csv`.

## Simplest Windows start

1. Extract the ZIP fully.
2. Open the `C2_Annual_Test` folder.
3. Run `01_INSTALL_AND_CHECK_WINDOWS.bat` (installs Python dependencies and validates the datasets).
4. Run `02_SMOKE_TEST_WINDOWS.bat` (tries the live API of all nine StatsForecast models on small synthetic data, then completes one annual reference).
5. Run `03_RUN_ALL_WINDOWS.bat` to evaluate all supported variants on the full 8,784-hour held-out year.
6. Run `04_REBUILD_REPORTS_WINDOWS.bat` after a partial run if you want updated charts.

The initial ZIP intentionally **does not include any previously generated benchmark scores**. Every `OK` result in the new output comes from your machine. Successfully completed jobs are resumed, not repeated. Models that cannot fit a given seasonality are recorded as `SKIPPED_UNSUPPORTED`; fitting errors are captured as `FAILED`, allowing the rest to continue. The Python version recommended for easiest installation on Windows is 3.11 or 3.12.

## Installation (Windows PowerShell)

Extract the ZIP. Open PowerShell inside the `C2_Annual_Test` folder:

```powershell
python -m pip install -r requirements.txt
python test_c2_model_benchmark.py
python run_c2_model_benchmark.py
```

`python run_c2_model_benchmark.py` schedules every applicable model and seasonality for **all 7 datasets**. Many long-period models can be computationally heavy. The script writes each job's results immediately and *resumes successful StatsForecast jobs* on subsequent runs. Interrupted jobs may be retried with `--retry` (which reruns all chosen jobs). The script is intentionally **not** modifying the repository's GUI or forecasting backend.

### Smaller runs / useful commands

```powershell
# Validate all inputs, 15,312/8,784 clock, site coordinates and data alignment
python run_c2_model_benchmark.py --prepare-only

# Genuine simple SeasonalNaive-equivalent forecasts, runnable offline without StatsForecast
python run_c2_model_benchmark.py --baseline-only

# First test three model families, daily and weekly seasons, all 7 datasets
python run_c2_model_benchmark.py --models AutoARIMA AutoETS MSTL --seasonalities daily weekly

# Run ALL models, all supported seasonality variants, all datasets (default)
python run_c2_model_benchmark.py

# Run one model / season / dataset
python run_c2_model_benchmark.py --models AutoTBATS --seasonalities daily_weekly --datasets B_GoiEner_Distributed_15Bus

# Rebuild ranking tables and figures from completed jobs
python c2_benchmark_reports.py
```

You can split the benchmark into multiple runs on your machine. Completed **native StatsForecast** fits will not be repeated unless you pass `--retry`.

### Ranking and outputs

All files are saved in `C2_model_benchmark_results/`:

- `model_comparison_all_statuses.csv`: every attempted, completed, unsupported or failed job with error notes.
- `load_model_scores.csv` and `pv_model_scores.csv`: measured five-metric results and timing, **never mixed across categories**.
- `load_rankings_by_dataset.csv` and `pv_rankings_by_dataset.csv`: models ranked by observed RMSE (for retrospective analysis **only**).
- `pv_models_mean_across_sites.csv`: averages across solar sites; use `all_sites_complete=True` for a fair common-sites comparison.
- `load/<dataset>/<model>__<season>/hourly_comparison.csv`: timestamp, actual kW, predicted kW, error kW.
- `pv/<dataset>/<model>__<season>/hourly_comparison.csv`: same schema for modeled PV power, NOT irradiance.
- `.../monthly_metrics.csv`, `.../run_metrics.json`: each individual test's performance.
- `.../rmse_top_10.png`, `.../accuracy_vs_time.png`, `.../best_monthly_profile.png`: per-dataset plots after scores exist.
- `C2_benchmark_report.md`: short completed-job status and ranking narrative.

To export a specific variant into the **original plotter and EE499 application format** (`timestamp,bus_id,p_kw,q_kvar`):

```powershell
python export_c2_benchmark_profiles.py --dataset B_GoiEner_Distributed_15Bus --model MSTL --seasonality daily_weekly
python plot_profiles.py
```

Select the generated `project_compatible_profiles/actual_load_profile.csv` and `forecast_load_profile.csv` inside the chosen variant. For solar choose `--dataset PV_040d42N_003d70W` and plot the `actual_pv_profile.csv` and `forecast_pv_profile.csv`. Bus-level load allocation uses only training-period hourly shares and historical Q/P ratios; it is a constructed approximation, **not an independent bus-level demand forecast**.

## Seasonality restrictions and fairness

1. A calendar **month** is not always 720 hours, and a year is not always 8,760 hours. The values are fixed-hour approximations required by several of these models. The held-out leap year is **8,784 hours** and remains untouched.
2. Some single-season methods are undefined or impractical when the training history contains **fewer than two full yearly cycles**. They are recorded as `SKIPPED_UNSUPPORTED` with a clear explanation rather than secretly fitting a smaller season. StatsForecast's SeasonalNaive does accept one past-year lag. AutoTBATS and AutoMFLES are *attempted* with a one-cycle yearly Fourier period but should be treated as exploratory and may fail or take a long time. You can set `TRY_INSUFFICIENT_YEARLY_MODELS=True` to attempt otherwise skipped cases; this is **not recommended** as valid evidence.
3. AutoMFLES internally tunes parameters with historical rolling windows (`AUTOMFLES_VALIDATION_HOURS=336`) using **training history only**. This is not the same as a long-horizon validation, which is a study limitation.
4. For PV, the forecast is clipped to [0,490] kW and set to zero at astronomical night, based only on known UTC site coordinates/date. This identical physical correction is applied to all models. Actual irradiance is not used to decide future daylight.
5. Scores are determined using the entire unseen test year. Sorting the scores gives the **ex-post winner** for experiment reporting, not a defensible strategy for selecting a model beforehand. For genuine model selection, add an earlier rolling validation period within the training history, then evaluate the selected method on the untouched year.
6. Sources have differing clock conventions: NASA site data are **UTC**, whereas the cleaned GoiEner dataset is **timezone-naive with unspecified source timezone**. This benchmark compares each separately and **does not align them to one solar+load grid simulation**.
7. The daily/weekly fixed-period naive and ARIMA models can fail to capture seasonal changes across an entire year. A simple model may beat a more complicated one; this is the reason for a common reference.

## What was validated in the preparation environment?

- The uploaded package's source CSVs, the training/test timestamps, all seven series, and project PV conversion were opened and checked.
- `test_c2_model_benchmark.py` passed offline checks for metric calculations, 7 data series, physical PV bounds, calendar continuity, constructor *argument names* via mock objects, project format exports and result writing.
- The `--baseline-only` method was previously executed for 28 full-year SeasonalNaive variants in the development folder; its output files are intentionally omitted from this clean distribution. You can reproduce them on your PC.
- **StatsForecast is not installed in the file-creation environment, and external package downloads are unavailable**. I verified the `AutoTBATS` constructor against the current Nixtla source and corrected the argument to `season_length`. Therefore the other eight models' fitting, runtime measurements, and forecast errors **have not been executed here**. Do not present them as completed experimental results. Running `python run_c2_model_benchmark.py` locally after installing requirements will calculate them.

## Relevant sources

- Project implementation: https://github.com/Islahi/EE499-Team16.git
- StatsForecast: https://github.com/Nixtla/statsforecast
- StatsForecast model source (model constructor names/arguments): https://github.com/Nixtla/statsforecast/blob/main/python/statsforecast/models.py
- Original input/data/profiles: uploaded `C2_Annual_Forecasting_and_Plotter_Updated(1).zip`.
