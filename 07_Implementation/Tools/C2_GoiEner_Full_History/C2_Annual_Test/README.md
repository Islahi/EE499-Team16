# EE499 Team 16 — C2 year-ahead forecasting and profile plotter

Repository: https://github.com/Islahi/EE499-Team16.git

This is the **year-ahead** alternative requested for C2. It runs ONE forecast
spanning the entire held-out year, **not** 366 forecasts with daily refitting.
The original project `src_accelerated/forecasting.py`, `data_loader.py`, and
`pv_model.py` are unchanged and imported directly.

## Running on Windows

Extract the ZIP into a folder. Open PowerShell in that folder:

```powershell
python -m pip install -r requirements.txt
python run_c2_annual.py
python plot_profiles.py
```

`run_c2_annual.py` needs no ZIP or file arguments. Settings are at the top.
If the StatsForecast package fails to install, resolve the Python/package
compatibility issue before running the model; do not treat preparation-only
results as forecast validation.

## Chronological split

- **Training**: June 1, 2017 00:00 through February 28, 2019 23:00:
  **15,312 observed hourly values**.
- **Test**: March 1, 2019 00:00 through February 29, 2020 23:00:
  **8,784 hourly values (366 days)**.
- **Forecast horizon**: 8,784 hours generated all at once, with 24-hour
  seasonality. There are no actual test-year observations in model fitting.
- **Load/PV public API**: `generate_forecast()` performs its *internal* 24-hour
  validation fit on 15,288 earlier observations, then refits on all 15,312
  training observations and predicts 8,784 hours. This is the original
  application's behavior, not a replacement forecasting model.
- **Irradiance**: the original `_fit_predict()` function is called directly,
  because the public load/PV forecasting API is not designed for irradiance.
  It fits on exactly 15,312 values and predicts the next 8,784 values.

## Cases

| Case | Model input | Output |
| --- | --- | --- |
| A — Whole GoiEner | Cleaned **sector sums** of residential, commercial, and manufacturing load | Predicted total load and 3 sector-specific load profiles |
| B — 15-bus | Cleaned average-customer sector *shapes* distributed over the nominal T04 15-bus network using the distributor's formula | Predicted total 15-bus load and individual bus profiles |
| C — Irradiance (five sites) | NASA POWER hourly GHI | Forecast irradiance in W/m² for each site |

The 15-bus customer category assignment is the source distributor's **illustrative demo cycle**;
these are *constructed* 15-bus historical loads, not physical feeder measurements.
The category normalization is fitted using training dates only.

Solar input data is NASA POWER hourly Wh/m², which the original project reader
converts to equivalent hourly mean W/m². This is not PV electrical output.
Solar timestamps are UTC; GoiEner's timezone-naive clock is undocumented. Do
not infer alignment between the two datasets.

## Output format

The results are placed in `C2_annual_results/` after execution. The actual and
forecast files always use **the same columns and timestamp range**, so the
plot application can compare them directly. The input `load_profile.csv` is
not overwritten.

### For A and B (load)

- `A_GoiEner_Total_Load/actual_load_profile.csv`
- `A_GoiEner_Total_Load/forecast_load_profile.csv`
- `B_GoiEner_Distributed_15Bus/actual_load_profile.csv`
- `B_GoiEner_Distributed_15Bus/forecast_load_profile.csv`

All four use the exact project's original load-profile format:

```csv
timestamp,bus_id,p_kw,q_kvar
2019-03-01 00:00:00,2,100.0,50.0
```

The row above only illustrates the schema, **not a measured/predicted result**.
The corresponding `actual_pv_profile.csv` and `forecast_pv_profile.csv` files
also use the same four-column format, but contain zero-valued PV placeholders
because the supplied load datasets are load-only. For the project's
`ProfileData` API, use matching load and PV profiles together.

### For C (irradiance)

- `C_Irradiance_<site>/actual_irradiance.csv`
- `C_Irradiance_<site>/forecast_irradiance.csv`

Both use the **prepared irradiance CSV** format supported by the project's
`read_irradiance(path, source="prepared")`:

```csv
timestamp,irradiance_w_m2
2019-03-01 00:00:00,0.0
```

The original NASA provider CSVs contain metadata and additional columns; the
paired output uses the project's normalized prepared format, not the raw NASA
provider format.

### Evaluation and metadata

- `c2_annual_summary.csv` — accuracy and runtime across cases
- `<case>/summary.json` — detailed results
- `<case>/total_load_hourly_comparison.csv` or `irradiance_hourly_comparison.csv`
- `<case>/*_monthly_metrics.csv` — MAE/RMSE/NRMSE/sMAPE by month
- `<load case>/bus_metrics.csv` — errors for individual buses/sectors
- `experiment_settings.json` — train/test dates and settings

**Important**: The project environment used for preparing this package did not
have the `statsforecast` dependency available. Therefore no genuine annual
AutoARIMA forecasts or accuracy scores are bundled or claimed. Input
preparation, file shapes, date alignment, and output-writing code paths have
been checked; you must run the model locally to obtain actual forecasts.

## Plotting application (`plot_profiles.py`)

1. Run `python plot_profiles.py` on your desktop.
2. Click **Add CSV files**, and select **one or more** CSV files. For
   example, choose just `actual_load_profile.csv` to plot one series, or choose
   both `actual_load_profile.csv` and `forecast_load_profile.csv` from the
   **same case** to compare them.
3. For load/PV: choose active power `p_kw` or reactive power `q_kvar`.
   Select **Total (all buses)** or an individual bus. For solar: irradiance
   is selected automatically.
4. Choose `Hourly`, `Daily mean`, `Daily peak`, `Weekly mean`, or `Monthly mean`.
   Use `Daily mean` as the initial full-year overview and `Hourly` to inspect
   a particular week.
5. Optionally enter start/end dates, then click **Plot files**.
6. Use the **Zoom In +** and **Zoom Out −** buttons to change the visible scale.
   You can also use the **mouse wheel** over the graph to zoom around the
   pointer. Click **Reset View** to return to the complete plotted range.
   The Matplotlib toolbar also supports **Pan** (drag to move the visible
   area), rectangle zoom, and Home.
7. Use **Save PNG** to export the currently visible graph.

The app accepts a single CSV or overlays multiple CSVs of **one matching schema at a time**. It
cannot directly overlay load and irradiance because their units differ.
The output CSVs remain unchanged by the plotting app.

## Preparing inputs without forecasting

To check the input files before installing StatsForecast, temporarily set:

```python
PREPARE_ONLY = True
```

Run `python run_c2_annual.py`. This exports the observed test-year profiles,
but **does not generate predictions**. Set it back to `False` for the actual C2 experiment.

## How this differs from the previous C2 protocol

The previous script used **366 rolling daily forecasts**, potentially ingesting
new actual measurements each day. This script instead evaluates a **single
8,784-hour year-ahead forecast** based only on 21 months of history. If this
becomes the primary Chapter 5 result, revise the Chapter 5 methodology to
match this exact experiment; do not describe it as daily rolling forecasting.

## Compatibility note (November 2026)

The training period length is calculated using Python's `datetime` difference,
then the hourly clock is built using `pd.date_range(..., periods=TRAIN_HOURS,
freq="h")`. No NumPy or pandas timedelta is subtracted. This avoids the
previously observed generic-timedelta deprecation warning from the old
`pd.Timestamp(TEST_START) - pd.Timedelta(hours=1)` line. The test still uses
15,312 historical hours and predicts 8,784 hours; forecast logic is unchanged.

## Updated plotting controls

The plotter has no minimum file count: **one CSV** plots one curve, and **two
or more CSVs** of the same supported schema produce overlaid curves. It accepts
both the load/PV 4-column schema and prepared irradiance 2-column schema;
these two schemas are not mixed in one graph. To zoom, use the mouse wheel over
the graph or the Zoom In/Zoom Out buttons. Reset View restores the complete
range, while the toolbar's Pan control lets you drag around a zoomed plot.

The date-range and zoom calculations have been checked, and the GUI tested with
one load file, two load files, and one irradiance file. The actual annual
AutoARIMA model has **not** been run as part of this revision.
