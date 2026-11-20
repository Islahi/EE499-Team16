# C2 2021 neural-only update — Python 3.12

Project: https://github.com/Islahi/EE499-Team16.git

This is a **drop-in patch** for the local directory:
`07_Implementation/Validation/C2_FixedCohort_Ranked22_Updated/`.
It is not a replacement for the fixed-cohort data, existing results, or the Python 3.14 environment.

## Files to copy

Extract ZIP contents **directly into** `C2_FixedCohort_Ranked22_Updated` (not into an extra subfolder), allowing replacement of the listed scripts:

- `extra_models.py` — routes only `AutoNHITS` and `AutoNBEATSx` through the new neural-only implementation. All other model functions are unchanged.
- `neural_recursive_2021.py` — new 2021 causal recursive forecast code.
- `run_benchmark.py` — adds optional `--exclude-cases Bus_01` (existing arguments and behavior unchanged).
- `requirements_neural_optional.txt` — pins NeuralForecast 3.1.9 to keep existing API compatibility.
- `10_EXPERIMENTAL_NEURAL_WINDOWS.bat` — now runs the safe **one-job pilot**, explicitly under `.venv-neural`.
- `10B_RUN_NEURAL_CATEGORIES_PY312.bat` — categories.
- `10C_RUN_NEURAL_BUSES_PY312.bat` — buses excluding zero-load slack Bus 1.
- `10D_RUN_NEURAL_PV_PY312.bat` — PV.

**Do not extract over or delete `results/`, `prepared_cases/`, `cohort_output/`, `Input/`, or `.venv-neural/`.**
The ZIP contains no such directories.

## Verify the Python environment

Open PowerShell in the C2 directory:

```powershell
.\.venv-neural\Scripts\python.exe --version
.\.venv-neural\Scripts\python.exe -c "import neuralforecast; print(neuralforecast.__version__)"
```

Expected: Python 3.12.x and NeuralForecast 3.1.9.
The existing `.venv-neural` already has the packages in this project; no reinstall needed. If configuring a clean environment:

```powershell
py -3.12 -m venv .venv-neural
.\.venv-neural\Scripts\python.exe -m pip install -r requirements_neural_optional.txt
```

## Verify the patched scripts (fast, no model fitting)

```powershell
.\.venv-neural\Scripts\python.exe -m unittest -v test_neural_recursive_2021.py
```

This checks causal recursive chaining, a full 8,760-hour rollout, timestamps, calendar features, and bounded model settings.

## Run the pilot

```powershell
.\.venv-neural\Scripts\python.exe run_benchmark.py --scope categories --group neural --include-neural --models AutoNHITS --retry-failed --max-jobs 1 --timeout-seconds 7200 --memory-gb 12
```

Or double-click `10_EXPERIMENTAL_NEURAL_WINDOWS.bat`.
The *same* full settings apply to the pilot and full benchmark, so the pilot is not an incomparable quick-training run.
If the job fails, inspect:

```powershell
Get-Content ".\results\load\Cohort_Residential\AutoNHITS__daily_weekly_monthly_yearly\job_output.log" -Tail 100
```

## Run each C2 group sequentially

```powershell
# 1: Four category datasets, two neural models = 8 jobs
.\.venv-neural\Scripts\python.exe run_benchmark.py --scope categories --group neural --include-neural --retry-failed --timeout-seconds 7200 --memory-gb 12

# 2: Fourteen nonzero buses + distributed total, two models = 30 jobs
.\.venv-neural\Scripts\python.exe run_benchmark.py --scope buses --group neural --include-neural --exclude-cases Bus_01 --retry-failed --timeout-seconds 7200 --memory-gb 12

# 3: Bilbao PV, two models = 2 jobs
.\.venv-neural\Scripts\python.exe run_benchmark.py --scope pv --group neural --include-neural --retry-failed --timeout-seconds 7200 --memory-gb 12
```

The scripts use the existing `results/` path and skip successful jobs. `--retry-failed` deliberately overwrites **failed neural job records** only for the same dataset/model ID, and does not rerun successful statistical/ML configurations. No parallel benchmark processes in the same directory.

## Produce rankings using the original Python 3.14 installation

```powershell
py -3.14 report_rankings.py
```

## What the new neural forecast does

- Train data: June 2017–December 2020, with the final 2,880 training hours reserved for Optuna validation during tuning; the chosen model is refitted on the available training history.
- `h=168` hours (one week), 672-hour input context, 2 Optuna trials (120/200 train steps).
- 8 deterministic sin/cos calendar features for daily, weekly, approximately monthly, and yearly variation; no future target or weather observations.
- Fit once on the original pre-2021 training history; then produce the complete 2021 forecast as 52 full weekly blocks plus a last 24-hour block (53 calls to the fitted model).
- **All 2021 input history is the model's own previous predictions, not observed 2021 demand/PV.** Predicted values are constrained nonnegative before feeding them into the next block; the worker retains its existing PV-nighttime and nameplate postprocessing.
- Outputs still include `run_metrics.json`, `fitted_configuration.json`, `hourly_comparison.csv`, and `monthly_metrics.csv` in the original C2 structure. The neural metadata explicitly identifies the new rollout strategy.
- Historical strategy differs from direct full-year models; this is a full-year out-of-sample *evaluation* but a recursive forecast, subject to accumulation of error.

This update is only for the neural experiment. The `cohort_config.py` experiment version is deliberately unchanged to avoid invalidating 1,404 already completed model results. Neural strategy has its own version under `auto_fit_info.neural_strategy_version`. If you later change neural settings, clear only the relevant neural result folders or use a new experiment output directory; successful jobs otherwise resume without rerunning.

### Test scope

40 meaningful model×dataset combinations: 8 categories + 30 distributed load + 2 solar PV. The zero-load Bus 1 is skipped for neural runs, but remains present in the original distribution-network data.

### Validation limitation

The patch has source/static tests and a mocked causal recursion test. Full AutoNHITS/AutoNBEATSx training under Windows Python 3.12 cannot be executed in this packaging environment. Verify the single real pilot on your PC before running all 40 jobs. Report remaining runtime or memory failures rather than treating them as poor model accuracy.
