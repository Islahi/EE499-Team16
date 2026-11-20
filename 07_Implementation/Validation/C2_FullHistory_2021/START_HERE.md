# C2: stable nine-model, 2021 one-year-ahead benchmark

**EE499 Team 16:** https://github.com/Islahi/EE499-Team16.git

This package uses the FOUR user-provided uploads:
- Original 9-model annual benchmark (for model selection/scoring definitions)
- Distributed 15-bus GoiEner load, 43,992 hours, 2017-05-30–2022-06-06
- Combined GoiEner three-category cleaned profiles, 43,969 hours, 2017-05-31–2022-06-06, plus category meter totals
- NASA POWER Bilbao modeled PV, 2017–2022, 490-kW rated site

**No repository files were changed.** This is a self-contained, portable test package.

## Launch on Windows

Extract the entire ZIP into a short writable path, e.g. `C:\EE499\C2_FullHistory_2021\`.

1. `01_INSTALL_WINDOWS.bat` — install StatsForecast, NumPy, pandas, statsmodels, scikit-learn, psutil, Matplotlib; run dataset checks.
2. `02_CHECK_DATA_WINDOWS.bat` — confirm all 6 datasets and date split, create planning matrix.
3. `03_LIVE_MODEL_SMOKE_TEST_WINDOWS.bat` — quick live API fit/predict on **48-hour** toy forecasts for all nine models; optional but strongly recommended.
4. `04_QUICK_REFERENCE_WINDOWS.bat` — run SeasonalNaive for all six cases; simple baseline, works without StatsForecast.
5. **`05_RUN_ALL_WINDOWS.bat`** — run all eligible model and seasonal combinations. It **resumes** on later runs.
6. `06_REBUILD_REPORTS_WINDOWS.bat` — refresh comparisons any time.

If you primarily need the BESS inputs, use `07_RUN_DISTRIBUTED_AND_PV_WINDOWS.bat` to evaluate only the constructed 15-bus load and single-site Bilbao modeled PV. Later `05_RUN_ALL_WINDOWS.bat` will **reuse those saved results** and run the additional GoiEner category cases.

## Data and time split

- Training: **2017-06-01 00:00** to **2020-12-31 23:00** inclusive = **31,440 hours**.
- Unseen test: **2021-01-01 00:00** to **2021-12-31 23:00** = **8,760 hours**, forecast in a single model call; no test-year observations during model fitting.
- 6 cases: `Distributed_15Bus_Load`, `GoiEner_Residential_PerMeter`, `GoiEner_Commercial_PerMeter`, `GoiEner_Manufacturing_PerMeter`, `GoiEner_ThreeSector_SummedMeters`, `Bilbao_Modelled_PV`.
- Per-meter metrics are in kW/customer, distributed and summed categories in kW; **do not compare their RMSE numbers directly across different units/scales**.
- The three-sector sum is a sum of sector meter totals. **Meter membership changes over time** (not an actual feeder measurement); any shift near March 2020 and May 2021 may be a customer-cohort change. The 15-bus profile was built with bus-level mean scaling and assignments.
- PV data is **modeled from NASA POWER GHI** at (43.26°N, -2.94°W) and capped at 490 kW; it is not metered PV output. NASA timestamps are UTC, while GoiEner timestamps are timezone-naive. Each source is forecast/scored against itself; source-clock alignment is required before simultaneous power-flow simulations.
- Combined raw category overlap starts May 31; distributed file starts May 30. Training starts June 1 so both include the entire intended train/test period.

## Models/periods/error metrics

Models: AutoARIMA, AutoETS, AutoCES, AutoTheta, MSTL, AutoTBATS, AutoMFLES, SeasonalNaive, HoltWinters.
Periods: `daily` (24h), `weekly` (168h), `monthly_30d` (720h), `yearly_365d` (8,760h), and combined daily+weekly, daily+weekly+monthly, daily+weekly+monthly+yearly for **the three multi-season models only**. Monthly/yearly fixed-period lengths are approximate, not calendar-aware.

Each successful run records MAE, RMSE, WAPE, weekly-reference MASE, Bias (positive means underforecast), sMAPE, mean power, annual and monthly energy error, peak error, fit seconds, forecast seconds, warning count, raw forecast extrema, number of physical corrections. Results and errors are **separated into `results/load/` and `results/pv/`**.

## What changed to address the previous numerical errors

| Previous behavior | Change in this package |
|---|---|
| AutoARIMA 720h failed with `MemoryError: bad allocation` for every prior case | Automatically `SKIPPED_UNSUPPORTED` at monthly/yearly, with explicit reason. Daily and weekly are tested. |
| AutoETS and HoltWinters 720h raised `Parameters out of range` for every prior case | Monthly/yearly versions skipped; daily/weekly retained. |
| AutoTBATS could produce internal `overflow encountered in square/reduce` | Inputs are normalized to mean power ~1, with inverse transformation of forecasts. The AutoTBATS grid is configured with `use_boxcox=False, use_arma_errors=False`, rather than its unrestricted automatic options. This *reduces* unstable branches but does not guarantee zero warnings. This is a **model configuration change**; compare the results accordingly. |
| AutoARIMA `possible convergence problem: minimize gave code 2` | Series normalization and model constraints may reduce the frequency. Remaining warnings are captured as `OK_WITH_WARNINGS`, with `warnings.json` containing messages; we never assert convergence if it did not happen. |
| A failing/out-of-memory model could destabilize the entire benchmark | Every fit runs in an independent subprocess, monitored using `psutil`. Default 8-GiB per-process RSS and 3600-second timeout. Failures become `MEMORY_LIMIT` or `TIMEOUT`. Others continue. |
| Extremely large values could overflow scoring | Nonfinite or *extreme* raw output (>100x train peak) is marked `FAILED`; no fabricated error scores. Negative loads are physically clipped to zero, and PV is clipped at night and to 490 kW, with correction counts recorded. |
| No intermediate audit | Every job has `run_metrics.json`, `warnings.json`, `job_output.log`, and (when successful) `hourly_comparison.csv` and `monthly_metrics.csv`. Report rebuilding never refits models. |

Settings can be inspected/changed in `c2_config.py`; use identical settings when comparing models. **Do not hide warnings or claim every numerical issue is solved**. Windows memory is not allocated in advance; the worker only consumes what its model needs.

## Controls in PowerShell

From this directory:

```powershell
python -m pip install -r requirements.txt
python c2_tests.py
python c2_tests.py --live-api
python -u run_c2.py --models SeasonalNaive --seasons daily weekly yearly_365d
python -u run_c2.py --datasets Distributed_15Bus_Load Bilbao_Modelled_PV
python -u run_c2.py                         # all cases, all eligible combinations
python -u run_c2.py --timeout-seconds 7200 --memory-gb 12
python -u run_c2.py --max-jobs 5             # five unprocessed fits; then resume
python -u run_c2.py --retry-failed           # retry prior failed and timed-out jobs
python c2_reports.py
```

- Default max wall time = **1 hour per fitting job** and default max *child process RSS* = **8 GiB**. Increase if a legitimate model is being stopped prematurely; setting `--memory-gb 0` disables RSS monitoring. `psutil` must be installed for the RSS guard.
- **To stop safely:** press `Ctrl+C`. Already completed jobs remain saved. Re-run to resume. Failed runs are also retained and skipped on resume unless `--retry-failed` is passed.
- Output directory: `results/`. Key files: `load_model_scores.csv`, `pv_model_scores.csv`, `model_comparison_all_statuses.csv`, `benchmark_report.md`.
- For full analysis, send a ZIP of the **entire `results` folder**.
- The full benchmark may run for **many hours**, particularly MSTL/TBATS annual combinations. The prior 7-dataset, 21-month-training run completed in ~**6h 33m** on the user's PC (November 15–16, 2026). The new experiment has longer training, six datasets and some newly eligible annual-seasonality runs; previous time does **not** predict its completion time reliably.

## Reproducibility and model-selection caveats

This is a **test-year comparison**, not an unbiased claim of future production accuracy. If 2021 is used to pick a winner, validate the selection on a *different* later period (e.g., a partial 2022 period) before reporting independent accuracy. Solar only extends to 2022 in the submitted file; the cleaned all-category GoiEner overlap ends June 6, 2022. The 2021 forecast may be affected by the COVID-period load regime and changes in source customer composition.

The isolated-worker implementation has been checked with the real submitted data and NumPy SeasonalNaive full-year jobs. StatsForecast itself is **not installed in the packaging environment**, so live AutoARIMA/MSTL/TBATS/etc fitting must be checked in your own Python environment with the included live API test.
