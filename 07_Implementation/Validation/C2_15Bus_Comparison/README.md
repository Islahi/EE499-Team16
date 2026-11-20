# C2 — 15-bus independent vs category-aggregate forecasting test bench

**Project:** [EE499 Team 16](https://github.com/Islahi/EE499-Team16)

This is an **isolated experimental branch**. Nothing in `main` has been changed.

## Goal

Compare two ways to produce 2021 hourly demand for the same 15-bus distribution system:

- **Bus-by-bus:** separately obtained 2021 predictions for each non-slack bus, using its winning load-category configuration.
- **Category aggregate then distribute:** one 2021 prediction per load category, distributed to buses using each bus's *pre-2021 historical mean load share*.

Solar PV is evaluated **separately**, against its own ARIMA baseline where provided, rather than included in the sum of load demand.

**This program evaluates forecast inputs; it does not train/retrain forecasting models, run power flow, or perform BESS optimization.** For a controlled comparison, use the identical 2021 test year and original profiles, and do not use 2021 observations to determine distribution shares.

## Required input files (CSV)

You must export the relevant data from the project archives into the following canonical format. The uploaded archives' internal structure has not been verified by this test bench, so input mapping must be checked carefully.

1. `history.csv` — `timestamp,bus,category,kw` — training history **before 2021-01-01**. Same timestamps for all included buses. Exclude the zero-load slack bus from both input sides, unless you consistently include it and explicitly adapt the zero-category allocation handling.
2. `actual_2021.csv` — `timestamp,bus,category,kw` — 8,760 hourly observations for each included non-slack bus during 2021.
3. `bus_forecast_2021.csv` — `timestamp,bus,kw` — one independent unseen 2021 forecast per bus, using the model selected for that bus's **category**.
4. `category_forecast_2021.csv` — `timestamp,category,kw` — one unseen 2021 forecast per category (Residential, Commercial, Manufacturing), fitted/forecast on the category aggregate time series.

Optional `pv_forecast_2021.csv`: `timestamp,actual_kw,predicted_kw,arima_kw`. The `arima_kw` column is optional.

Rows can appear in any order; timestamps must be hourly without timezone offsets and must align with each other. All values are power **kW**, not energy kWh. The category names and bus identifiers must match exactly across files. Each model forecast **must** be generated without reading actual 2021 observations. Do not distribute a category aggregate using shares calculated from the 2021 test set.

**Important:** category-aggregate forecasting should be trained on **the sum of the selected network's buses in that category**, not a per-customer normalized series or an aggregate with different customers/units. If your C2 cohort aggregate forecast does not represent the same 15-bus category totals, retrain the winning category configuration on the correct historical category totals before running this comparison; do not use an incorrectly scaled forecast.

## Run in PowerShell

From the directory containing `testbench.py`:

```powershell
py -3.14 -m pip install numpy pandas matplotlib
py -3.14 testbench.py --history history.csv --actual actual_2021.csv --bus-forecast bus_forecast_2021.csv --category-forecast category_forecast_2021.csv --out comparison_results
```

With solar PV:

```powershell
py -3.14 testbench.py --history history.csv --actual actual_2021.csv --bus-forecast bus_forecast_2021.csv --category-forecast category_forecast_2021.csv --pv-forecast pv_forecast_2021.csv --out comparison_results
```

Do not run until the four required CSVs have been prepared from the real project results and load data. These examples are **commands**, not generated outcomes.

## Outputs

- `training_only_bus_allocation_shares.csv`: category-wise allocation factors, summing to 1 in each category.
- `same_category_profile_audit.csv`: paired correlations, normalized-profile differences, optimal proportional scaling, scaled-shape verdict.
- `aligned_bus_predictions_2021.csv`: aligned actual, independent, and distributed forecasts.
- `per_bus_strategy_metrics.csv`: 2021 MAE, RMSE, WAPE, MASE(24), Bias, sMAPE.
- `category_predictions_2021.csv` and `category_strategy_metrics.csv`.
- `network_predictions_2021.csv` and `network_strategy_metrics.csv`.
- One **14-day single-panel hourly comparison PNG** per bus, July 1–14, 2021.
- `pv_forecasting_metrics.csv` when the optional PV file is supplied.

Metrics are evaluated over the same 8,760 hours of 2021. Signed bias means *actual minus forecast*, so positive is underprediction. MASE uses a **24-hour seasonal-naive training baseline**, which may differ from the C2 benchmark's MASE convention; document this when comparing other results. PV MASE is blank because PV training history is not an input to this bench.

## Interpretation

If `effectively_scaled_same_shape=True` and normalized-profile RMSE is effectively zero for each pair of same-category buses, those bus series differ by scale, not independent load *shape*. Such buses may vary strongly throughout the day and year, but their normalized temporal patterns do not differ.

A strong correlation alone does **not** imply exact scaling or data leakage. Conversely, forecast performance on scaled copies is not independent evidence that a model generalizes to genuinely different feeder locations.

**Primary comparison:** compare the two strategies on each bus and, critically, on the **summed network load forecast**. Aggregate totals must be evaluated by summing predicted bus kW *before* computing the error metrics. Model names/selected winning configurations should be recorded in your C2 report; this bench only scores their exported predictions.

## Status and cautions

The repository's archives were not readable in the assistant's current execution environment, so the identity of current category/PV winners and the 15-bus profile verdict remain **unverified**. This code has been reviewed but was **not executed against the attached archives**.

This is a dedicated comparison test bench on a new branch, not a modification to the existing C2 benchmark or BESS simulation.
