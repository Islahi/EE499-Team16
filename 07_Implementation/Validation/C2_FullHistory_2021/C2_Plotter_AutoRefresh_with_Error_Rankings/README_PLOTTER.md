# EE499 Team 16 — C2 plotter with live rankings

Project repository: https://github.com/Islahi/EE499-Team16.git

This is a **drop-in replacement** for the older 2021 Actual vs Forecast C2 plotter. It **does not train any model** or change benchmark data.

## Install and launch (Windows)

1. **Do not delete your existing `results/` folder.** Extract the five plotter files from this ZIP into the folder `C2_FullHistory_2021/`, **beside** `data/` and `results/`, replacing the older `c2_plotter_gui.py` and `c2_plotter_core.py` if Windows asks.
2. Double-click `10_PLOT_C2_RESULTS_WINDOWS.bat`.
3. If dependencies are missing: `python -m pip install -r plotter_requirements.txt`.
4. If necessary, click **Open C2 experiment folder…** and choose the folder containing `results/` and `data/`. You may plot completed configurations while other benchmark jobs are still running. To discover files completed **after opening the plotter**, click **Open C2 experiment folder…** again to reload them.

## Features

- Compare measured (`Actual`) with saved forecast (`Forecast`) results for the 2021 **8,760-hour** test year.
- **Automatically redraw** when you change dataset, bus, graph resolution, selected models or From/To dates. The date fields use a short delay to avoid redrawing with every keystroke.
- **Show error panel** checkbox: hide/show the signed `(Actual − Forecast)` graph underneath. The current horizontal zoom is preserved when toggling this checkbox.
- **Rank the available completed configurations by**: RMSE, MAE, WAPE, MASE, absolute Bias, sMAPE, fitting time, forecasting time, total fitting + forecasting time, and warning count.
- Pick a ranking from the **Rank completed forecasts by** dropdown, or click RMSE/MAE/WAPE/MASE/Bias/sMAPE/Fit/Predict/Warnings column headings. The table is sorted from **best to worst** and the first row is **automatically plotted** when the ranking metric changes.
- Use **Plot #1 (best)** to select the first row after comparing multiple models. Use Ctrl+click to overlay multiple rows on the same chart.
- The ranking respects the **selected dataset, individual bus and date interval**. If no dates are specified, the direct-forecast ranking uses the full-year saved benchmark scores. If dates are specified, it recalculates error metrics on that interval. Times always refer to the saved **full-year model run**, not the graph interval.
- Display **Hourly**, **Daily mean**, **Daily peak**, **Weekly mean**, **Monthly mean**, **Daily energy**, or **Monthly energy** plots. Rank calculations are **always based on hourly pairs**, even when the visual resolution is aggregated.
- Save the visible plot to PNG, or export its underlying selected hourly actual/forecast/error pairs to CSV.
- Use the toolbar, mouse wheel, **Zoom in**, and **Zoom out** for visual inspection.

## Meaning of rankings

- **MAE, RMSE:** lower is better, in the dataset's original units.
- **WAPE and sMAPE:** lower percentages are better. They use the same formulas as `c2_scoring.py` in the benchmark.
- **MASE:** lower is better; scale is the 168-hour seasonal-naive training error for that dataset or reconstructed bus. If the baseline is zero or unavailable, this is shown as `N/A` and ranked last.
- **Bias:** displayed as signed `(Actual − Forecast)`; sort uses **absolute Bias** (closest to zero), not the most negative value.
- **Fit, Predict, Fit + forecast:** lower recorded elapsed compute times are better. For category-derived bus forecasts, the reported times are sums of the three corresponding category jobs; this is *not* a newly measured per-bus model fit or necessarily parallel elapsed wall time.
- **Warnings:** lower number of saved warning messages is better; zero warnings does not by itself imply a more accurate model.
- `N/A` metrics always sort to the bottom. Only fully saved `hourly_comparison.csv` forecasts are listed; a failed/skipped/unfinished model is never silently treated as successful.

## Crucial method distinction

- `Distributed_15Bus_Load` is the saved **direct model forecast of the summed 15-bus load**. The individual bus options are not available for it.
- `15-bus network — reconstructed from category forecasts` produces bus-level comparisons by taking the **saved residential/commercial/manufacturing forecasts** of one model/seasonality and applying the verified train-only fixed bus scaling. It **does not** train separate forecasting models for each bus. This category-derived method is not equivalent to independently forecasting 14 individual bus time series.
- Reconstructed forecasts require completed results for **all three categories** with the **same model + seasonality**. Bus 1 is the slack bus and has zero load in the constructed profile. On Bus 1, all zero forecasts may have equal errors and WAPE/MASE are undefined.
- `Bilbao_Modelled_PV` is a modeled PV output derived from NASA POWER irradiance, not a measured plant.
- `GoiEner_*_PerMeter` is in **kW/customer**, while network load is in **kW**; do not compare absolute errors across these different scales directly.

## Example layout

```
C2_FullHistory_2021/
  10_PLOT_C2_RESULTS_WINDOWS.bat
  c2_plotter_gui.py
  c2_plotter_core.py
  c2_plotter_ranking.py
  plotter_requirements.txt
  data/
    distributed_15bus_load.csv
    goiener_category_means.csv
    bus_assignments_used.csv
    ...
  results/
    load/Distributed_15Bus_Load/AutoTBATS__daily_weekly_monthly/
      hourly_comparison.csv
      run_metrics.json
    load/GoiEner_Residential_PerMeter/...
    load/GoiEner_Commercial_PerMeter/...
    load/GoiEner_Manufacturing_PerMeter/...
    pv/Bilbao_Modelled_PV/...
```

No GitHub changes are performed by the plotter.
