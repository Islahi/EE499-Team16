# EE499 C2 — fixed cohort, 22 ranked configurations + 6 new optimized model families

Repository reference: https://github.com/Islahi/EE499-Team16.git

## Purpose

Reconstruct **the same customer-ID cohort** from the original GoiEner 2022 release's
`imp-pre.tzst`, `imp-in.tzst`, and `imp-post.tzst` without transferring the archives.
Then compare 2021 single-shot, 8,760-hour forecasts for the three load categories,
optionally each *individual* distribution bus, and Bilbao NASA-derived modeled PV.

The files in this ZIP are standalone. **They do not modify the main GitHub repo.**
A small manifests-only `Cleaned.zip`, extracted from your prior `Cleaned.zip`
upload, is already bundled and identifies customer IDs classified in all three
archives. No raw customer meter readings are present in that small ZIP.

## Data source

Original DOI/Zenodo record: https://zenodo.org/records/7362094

Your previously uploaded manifests identify **10,184** consistently categorized IDs:
9,938 residential (including unverified tariff proxies), 164 commercial and
82 manufacturing. This was verified from your earlier `Cleaned.zip`; the counts
may change if you supply different manifests.

**Important qualification:** Common ID in all archives does *not* mean every meter
has valid records in every hour. The new output reports available meters and
coverage by hour. Category mean uses **available meters from the fixed ID cohort**;
no missing observations are silently assigned zero.

## 1. Put your existing original archives under `Input/`

The manifests-only `Cleaned.zip` and Bilbao solar CSV are bundled. You only need
to copy your **three large original `.tzst` archives** to the Input folder.

- `Input/imp-pre.tzst`
- `Input/imp-in.tzst`
- `Input/imp-post.tzst`
- `Input/Cleaned.zip` — **already included** in this ZIP: exact three original customer-quality manifests from your earlier upload (not raw meter readings)
- `Input/nasa_pv_043d26N_002d94W.csv` — **already included**: the Bilbao NASA-derived PV series from your earlier upload

Do not unzip the `.tzst` files. The script decompresses them incrementally using
`zstandard`. It creates a **temporary disk-backed** float32 customer×hour matrix:
approximately **1.8 GiB** for the ~10,184 customer cohort and 2017–2022 hourly
range, plus space for the original archives, output CSVs and Python overhead.
Allow at least 4–6 GiB free *beyond* your downloaded archives.

## 2. Install dependencies

Double-click `01_INSTALL_BASE_WINDOWS.bat`.

Optional new models Prophet, LightGBM and XGBoost:
`01B_INSTALL_NEW_MODELS_WINDOWS.bat`. Python package compatibility varies,
particularly on Python 3.14. If packages cannot be installed, use Python 3.12
in a separate virtual environment; no need to alter a working Python installation.

For neural models, separately install `requirements_neural_optional.txt`. Those
experimental jobs are **not** included in the default run because of their memory,
compatibility and runtime requirements.

## 3. Rebuild the common cohort from the big local archives

Double-click `02_BUILD_FIXED_COHORT_WINDOWS.bat`, or run:

```powershell
python 01_build_common_cohort.py --manifests-zip "Input\Cleaned.zip" --pre "Input\imp-pre.tzst" --during "Input\imp-in.tzst" --post "Input\imp-post.tzst" --out cohort_output --max-gap-hours 168
```

**Interpolation:** linear inside a *single customer's* observed overall time span,
across archive boundaries too. It fills runs of at most 168 consecutive missing
hours by default. It **never extrapolates** before the first or after the last
reading, because a member might not yet have been active. Use `--max-gap-hours 0`
only if you deliberately want to interpolate *all* interior gaps, including
multi-month gaps (a strong assumption that can conceal changes).

At overlapping timestamps the latest archive's valid reading takes priority:
Post > During > Pre. All original files remain unchanged.

### Cleaner outputs

- `cohort_output/cohort_customer_manifest.csv` — selected common IDs/category
- `cohort_output/customer_interpolation_report.csv` — missing/imputed by customer
- `cohort_output/hourly_cohort_coverage.csv` — available customers each hour
- `cohort_output/cohort_quality_report.json` — coverage, skipped members, caveats
- `cohort_output/residential.csv`, `commercial.csv`, `manufacturing.csv`
- `cohort_output/goiener_three_profiles.csv`
- `cohort_output/goiener_distributor_ready.csv` — *only if* 3 categories cover
  a continuous common period, with the same headers as your old distributor

Examine `cohort_quality_report.json` before forecasting. A result is not
necessarily population-stable if coverage varies sharply at archive boundaries.

## 4. Prepare the forecast input series

Double-click `03_PREPARE_CATEGORIES_AND_PV_WINDOWS.bat`, or:

```powershell
python cohort_cases.py --cohort cohort_output --pv "Input\nasa_pv_043d26N_002d94W.csv"
```

This prepares three **independent category** forecast cases, the cohort meter-load
sum as an auxiliary baseline, and PV as a separate data source.

**Single-shot experiment:** Train 2017-06-01 through 2020-12-31 (31,440 hours),
forecast **2021-01-01 through 2021-12-31** (8,760 hours) in one forecast.
No actual 2021 load or PV observations are provided to the models in fitting.
The NASA PV source uses UTC, whereas GoiEner source-clock interpretation has not
been independently verified. They are scored separately.

## 5. Run the model comparison — categories first

Use `04_QUICK_REFERENCE_WINDOWS.bat` for a short baseline check, then
`05_RUN_CATEGORY_BENCHMARK_WINDOWS.bat` for the full comparison.

The default `--suite selected --group all` configuration contains precisely:

- **22 retained configurations**: the last 20 **overall-ranked** configurations
  (across residential/commercial/manufacturing/PV/15-bus/aggregate, not the
  former 15-bus-only top 20), plus **AutoTBATS D+W+M+Y** and **AutoETS weekly**.
- **42 additional optimized configurations**: FourierOLS, CalendarRidge,
  Prophet, LightGBM, XGBoost and FourierSARIMAX, each evaluated on all seven
  seasonal choices: D, W, M, Y, D+W, D+W+M, D+W+M+Y.
- **3 extra baseline controls**: Naive (last observation), SeasonalNaive daily
  and previous-calendar-year naive. The other SeasonalNaive weekly/monthly/yearly
  references are already in the 22, avoiding duplicate runs.

**Total: 67 unique model–seasonality configurations per dataset.**
A new `model_catalog.py` is the single auditable source of that selection.
The additional AutoNHITS and AutoNBEATSx models remain **optional experimental**
trials; they do not have comparable selectable fixed seasonalities.

For a run in shorter batches:

```powershell
python run_benchmark.py --scope categories --group legacy22
python run_benchmark.py --scope categories --group new
python run_benchmark.py --scope categories --group baselines
python run_benchmark.py --scope pv --group all
```

Re-run the same command to resume completed jobs. See the Windows `.bat`
launchers for the equivalent double-click steps. `--suite all` extends the
classic-model candidate grid beyond the selected 22, for deliberate exhaustive
tests only.

Some models already perform their own automatic fitting (AutoARIMA, AutoETS,
AutoCES, AutoTheta, AutoTBATS, AutoMFLES). New calendar-aware models automatically
select hyperparameters on the **final 120 days of the training data**, then refit
on all training hours. MSTL uses its automatic ETS trend model but fixed requested
seasonal decomposition periods. Naive models have no training step.

`--suite all --group all` additionally attempts all nine previous model families
across supported seasonalities. It is broader than the 22-model shortlist and
is NOT the recommended initial run.

You can run one model before a lengthy benchmark, for example:

```powershell
python run_benchmark.py --scope categories --models CalendarRidge --max-jobs 5
python run_benchmark.py --scope categories --suite all
```

**Different seasonal settings are genuinely distinct for calendar-aware Ridge:**
`calendar_features()` now creates daily/weekly/monthly/yearly seasonal features
only when requested. Earlier code included annual and daily features even in
weekly-only configurations. FourierOLS also selects harmonic complexity using
training-period holdout data. `train-only` means no 2021 measurements leak into
hyperparameter fitting.

**Each fit is isolated in a child process**, has configurable time and memory
limits and records failures/warnings. Re-run the same command to resume;
completed successful jobs are skipped unless you explicitly remove their result
folder. Note: there is NO guarantee that models will fit every seasonal setting.
Some models (especially TBATS/MSTL annual cycles) may take very long.

## 6. Next: genuinely independent bus-by-bus forecasting

The constructed 15-bus loads **must be regenerated** from the NEW
`cohort_output/goiener_distributor_ready.csv`, using your original GoiEner Load
Distributor and the same bus assignments, network workbook, and scaling method.
This is intentionally not automatically substituted with the old distributed file.

Once you export the *new* distributed file, rename/copy it to
`Input/distributed_load_from_NEW_cohort.csv` and run:

```powershell
python cohort_cases.py --cohort cohort_output --pv "Input\nasa_pv_043d26N_002d94W.csv" --distributed "Input\distributed_load_from_NEW_cohort.csv"
python run_benchmark.py --scope buses --suite selected
```

The program will create distinct `Bus_01`, `Bus_02`, ... series from each
bus's actual *constructed* history. Each model will fit each bus independently,
not allocate an aggregate forecast. **Note:** since your construction scales
three category curves, many buses may still be identical up to scale; this is a
limitation of the synthetic demonstration, not proof of true feeder diversity.

## 7. PV benchmark

```powershell
python run_benchmark.py --scope pv --suite selected
```

NASA PV output remains modeled (490-kW PV nameplate), **not metered generation**.

## 8. Which results and fitted configurations are saved?

**Every completed model job automatically saves:**

```
results/load/<dataset>/<model>__<seasonality>/
    hourly_comparison.csv             # timestamp, actual, forecast, error
    monthly_metrics.csv                # monthly accuracy and energy
    run_metrics.json                   # metrics, fit time, warnings, status
    fitted_configuration.json          # requested seasons + automatic settings
    warnings.json
    job_output.log
```

These contain **forecast results and an audit trail**; they are not the fully
trained model itself. The previous C2 scripts did not save fitted models.

`results/planned_model_matrix_<scope>_<group>_<suite>.csv` lists every
configuration, selected period(s), original selection group, and skip reason.
`results/benchmark_settings_*.json` records the full 22-model shortlist.
The `experiment_version` and a SHA-256 fingerprint of each prepared dataset
are included in job results to avoid accidentally resuming results obtained
with different scripts or customer data. Rankings exclude stale job results.

If you want to serialize the *actual fitted model object* for later reuse, add
`--save-fitted-models` **before** running the model. It will attempt to save
`fitted_model.joblib`. **Important:** some fitted models do not serialize
reliably, and saving objects can consume substantial disk space; failures to
save are recorded without invalidating valid forecasts. The optional flag
cannot retroactively save models from previous completed runs.

Afterwards:

```powershell
python report_rankings.py
```

Rankings are available **separately for each dataset**:
`results/rankings/<dataset>/ranked_rmse.csv`, `ranked_mae.csv`,
`ranked_wape_percent.csv`, `ranked_mase_weekly.csv`,
`ranked_abs_bias.csv`, `ranked_smape_percent.csv`, and timing tables.

The results can be inspected with your latest C2 actual-vs-forecast plotter
using its hourly-comparison CSV fields. Some GUI dataset auto-discovery features
may expect the older `C2_FullHistory_2021/data` layout and are not guaranteed
on this new package without adaptation.

## 9. Tests and limitations

Run `python tests/test_cohort.py` and `python tests/test_benchmark.py`.
These synthetic fixtures passed. The massive original `.tzst` archives were
not available in the authoring environment, so a real-data run must be validated
on your computer. The installation of several optional model libraries, as well
as experimental AutoNHITS/AutoNBEATSx, was likewise not fully tested here.
Neural models learn temporal patterns internally rather than receiving the requested
seasonal-period list; the single neural configuration must not be interpreted
as a controlled comparison of daily versus yearly seasonality.

**A clean cohort is an improved *control*, not proof that demand trends become
predictable or customer consumption is stationary.** Consider inspecting each
customer category's 2020 and 2021 monthly averages before judging models.

## Model list / updated Windows launchers (22+6 release)

- `05_RUN_CATEGORY_BENCHMARK_WINDOWS.bat`: all 67 configurations on categories.
- `05A_RUN_22_SELECTED_WINDOWS.bat`: the 22 historical finalists only.
- `05B_RUN_6_NEW_MODELS_WINDOWS.bat`: 42 new optimized combinations only.
- `05C_RUN_EXTRA_BASELINES_WINDOWS.bat`: three extra controls only.
- `07_RUN_INDEPENDENT_BUSES_WINDOWS.bat`: bus-by-bus, **only once you regenerate
  the distributed load from the fixed-cohort customer profiles**.
- `08_RUN_SOLAR_WINDOWS.bat`: Bilbao modeled PV, same 67 configurations.
- `10_EXPERIMENTAL_NEURAL_WINDOWS.bat`: optional two auto-tuned neural models.
- `11_CHECK_MODEL_CATALOG_WINDOWS.bat`: validates the shortlist and seasonality
  feature construction, without fitting any model.
- `12_PREVIEW_PLAN_WINDOWS.bat`: prints the eligible vs unsupported run counts
  and saves `planned_model_matrix_*.csv` (requires prepared cases).

**Use this as an update to your existing processing folder:** preserve the
existing `.tzst` files, `cohort_output/`, `prepared_cases/`, and `results/`.
After replacing the scripts, run **03_PREPARE_CATEGORIES_AND_PV_WINDOWS.bat**
again (or **06_PREPARE_DISTRIBUTED_BUSES_WINDOWS.bat** if you have already
created bus files). This only refreshes the compact `prepared_cases/` and
its source fingerprints; you **do not** need to rerun the hours-long original
archive cleaning step. The update-only ZIP includes changed scripts, no archives.

### Practical and scientific cautions

- The **22** are 22 model–seasonality pairs, not 22 different model algorithms.
- Original cohort membership is fixed but active meter coverage still varies
  hour to hour. Inspect coverage before interpreting trends.
- Selecting parameters on the final 120 training days is NOT the same as
  proving performance across multiple future years. Historical forecasting
  models still cannot foresee actual weather or unexpected industrial changes.
- SARIMAX, MSTL and TBATS can be slow or fail for long seasonal periods;
  their failures/warnings are recorded and should not be hidden.
- AutoTBATS uses `use_boxcox=False` and `use_arma_errors=False` as in the previous
  fixed-cohort package to reduce instability; previous test parameters differed.
- `report_rankings.py` creates rankings within each dataset and metric, not
  one automatic universal winner. Respect your dataset and metric priorities
  when selecting final models.

## Distributor-compatible export (updated 02 launcher)

The `02_BUILD_FIXED_COHORT_WINDOWS.bat` launcher now has **two steps**: (1) build
fixed-customer cohort, (2) export the exact **original cleaner-style six-column**
category CSVs into `cohort_output/Distributor_Compatible/`.

**If step 02 already completed on your PC, do NOT rerun it.** Instead use
`02B_EXPORT_ONLY_FOR_DISTRIBUTOR_WINDOWS.bat`, which converts the small existing
`cohort_output` files without reading any large `.tzst` archive.

In the old **GoiEner Load Distributor** GUI select the folder:

```
cohort_output/Distributor_Compatible/
```

It contains:

- `residential.csv`, `commercial.csv`, `manufacturing.csv` (original cleaner
  columns `timestamp,load_kwh,load_kw,average_customer_kw,active_customers,no_customer_data_hour`)
- `goiener_three_profiles.csv` (original three-sector wide columns)
- `goiener_distributor_ready.csv` (longest common contiguous hourly interval,
  with **average** per-customer profiles by default)
- `quality_report.json` and `README_DISTRIBUTOR.txt` (coverage and provenance)

Choose **Average** in the GUI to preserve your previous distributor workflow.
If you select the folder, the distributor can also use **Sum** from `load_kw`;
if you select `goiener_distributor_ready.csv` directly, its values are *always*
those selected at export time (default **Average**).

No additional interpolation or demand smoothing is performed by this export.
Original fixed-cohort outputs are retained in `cohort_output/` and remain
usable by `03_PREPARE_CATEGORIES_AND_PV_WINDOWS.bat`.
If any hours have no customers in a category, the distributor-ready file uses
only the longest uninterrupted all-category interval; inspect
`quality_report.json` before forecasting.
