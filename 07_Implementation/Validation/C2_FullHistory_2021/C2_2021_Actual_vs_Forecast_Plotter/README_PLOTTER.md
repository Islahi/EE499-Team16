# EE499 Team 16 — C2 2021 Actual vs Forecast Plotter

Repository: https://github.com/Islahi/EE499-Team16.git

## Install (no rerun of forecasting needed)

1. Extract the **contents of this ZIP** into the **`C2_FullHistory_2021`** directory from the latest C2 benchmark, next to its `data/` and `results/` directories. Keep its completed results; do not overwrite them.
2. Double-click **`10_PLOT_C2_RESULTS_WINDOWS.bat`**, or run `python c2_plotter_gui.py` from the same folder.
3. If required, install with `python -m pip install -r plotter_requirements.txt` (Tkinter normally comes with standard Windows Python).
4. If it does not automatically find the experiment, click **Open C2 experiment folder** and select the folder that contains `data/` and `results/`.
5. Choose dataset, model and seasonality. Ctrl+click to overlay different completed models. Choose bus only in **`15-bus network — reconstructed from category forecasts`**.
6. Click **Plot actual + forecast**, then select Hourly, Daily mean/peak, Weekly mean, Monthly mean or Energy. Set From/To for a date interval. Mouse wheel zooms horizontally; Matplotlib toolbar allows pan and rectangular zoom. Save PNG or export the currently displayed hourly pairs to CSV.

## Crucial interpretation

- **`Distributed_15Bus_Load`** is the original *directly fitted total-load forecast*. It has no independently forecast per-bus series. Its bus option remains **Total**.
- **`15-bus network — reconstructed from category forecasts`** uses pre-existing *residential/commercial/manufacturing* forecasts of the **same model + seasonality**, applies each bus's verified fixed category scale (obtained from **training data only**), then compares those derived bus predictions with the actual distributed bus load. This does **not** fit any model to individual buses. It is a different method from the direct total-load forecast.
- The reconstructed mode only lists model+seasonality pairs **completed for all three categories**. If none match, finish or locate those outputs. This plotter **does not rerun forecasting**.
- The source network contains 14 load buses (2–15). Bus 1 is slack and has zero constructed load.
- Metrics displayed below the graph are calculated on the selected **hourly** interval, even if the graph shows averaged or aggregated days/months.
- **Positive error** means the model underpredicted actual demand; negative means it overpredicted.
- **Bilbao_Modelled_PV** is illustrative electrical output calculated from NASA POWER irradiance, not a measured solar plant output. Its time basis may differ from the GoiEner source clock.
- Reconstructed bus values are **active power only (kW)**. No reactive-power forecasts are invented.
- Failed, skipped, or unfinished benchmark jobs are not presented as completed forecasts.

## Output folder structure expected

```
C2_FullHistory_2021/
  c2_plotter_core.py
  c2_plotter_gui.py
  10_PLOT_C2_RESULTS_WINDOWS.bat
  data/
    distributed_15bus_load.csv
    goiener_category_means.csv
    bus_assignments_used.csv
  results/
    load/
      Distributed_15Bus_Load/
        AutoTBATS__daily_weekly_monthly/
          hourly_comparison.csv
          run_metrics.json
      GoiEner_Residential_PerMeter/
      GoiEner_Commercial_PerMeter/
      GoiEner_Manufacturing_PerMeter/
    pv/
      Bilbao_Modelled_PV/
        ...
```

Each completed `hourly_comparison.csv` must have `timestamp,actual,forecast` columns. Works with partial/resumed benchmarks and locates all available successful configurations.

**If you only have `load_model_scores.csv` and `pv_model_scores.csv`, that is insufficient for graphing**. You need the per-job `hourly_comparison.csv` files from the full `results` directory.

No original code or benchmark output is modified by the plotter.
