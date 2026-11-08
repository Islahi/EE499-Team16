# IMPORTANT — Designer wiring fix (v4)

The current release fixes the `Unknown backend: None` and invalid AutoARIMA method errors. Qt Designer `.ui` remains the owner of the visible layout. See `CHANGELOG_DESIGNER_WIRING_FIX_V4.md` for technical details.

# Latest: Qt Designer–Unified UI v3

The current release is `BESS_Planning_Tool_Designer_Unified_v3`. The six main actions, Fit/Zoom/Rotate network controls, toolbar spacing, icon paths, labels, and tooltips live directly in `src_accelerated/assets/main_window.ui`. All permanent Settings controls are in `settings_dialog.ui`; the Forecast dialog is in `forecast_dialog.ui`.

Open these `.ui` files in **Qt Widgets Designer** to preview or edit the layout directly. The primary and network actions share one **36-pixel-high toolbar** above the Network/Results tabs. The old hidden sidebar and empty menu/header have been removed. `ui.py` only loads the forms and attaches behavior; it does not build the toolbar or inject the Settings fields.

**Run on Windows:** extract the ZIP to a fresh directory and double-click `start_windows.bat`, or run `py -m pip install -r requirements.txt`, then `py -m src_accelerated.ui`.

**Test:** `py -m pytest -q tests` (35 passed, 1 optional StatsForecast test skipped in the packaging environment). XML/structural tests and compilation passed; interactive PySide6/Windows display validation is still needed. The existing algorithm, forecasting engine, data formats and economic calculations are preserved.

See `CHANGELOG_DESIGNER_UNIFIED_V3.md` for details.

---

# BESS Planning Tool — integrated source upgrade

**Date:** 2026-11-05. This ZIP contains editable Python source. It is **not a rebuilt Windows EXE**.
The earlier `BESS_Planning_Tool.exe` was compiled separately and has not been modified.
Keep a backup of your existing source and use this archive in a separate directory.

## Windows installation

1. Extract this archive, retaining `src_accelerated/`, `assets/` within that package, and the root `requirements.txt`.
2. Install Python (ideally 3.11–3.13 or a version supported by all dependencies).
3. Run `start_windows.bat` (installs packages and launches the GUI). Alternatively:
   ```powershell
   py -m pip install -r requirements.txt
   py -m src_accelerated.ui
   ```
4. For tests: `py -m pytest -q tests`.

## Implemented changes

- **Annual economic objective:** `annual_total_cost = annualized CAPEX + annual O&M + annual grid import/export cost + annual PV curtailment penalty + annual unserved-energy penalty + terminal stored-energy settlement`.
- **Default literature assumptions (USD):** 770 USD/kW, 385 USD/kWh, 10 years, 6% annual discount, 2% annual O&M, 0.07 USD/kWh curtailment, 12 USD/kWh shedding. These are from the papers provided with the proposal. **Grid import and export tariffs default to 0 and are not sourced prices; set them in Settings before making economic claims.**
- **Time basis:** energy-related costs are converted to an annual basis with `8760 / simulated_hours`. For short profiles this assumes repetition of the observed hours; use complete one-year data for decisions. For multi-year runs the result is average annual cost rather than the summed cost of all years.
- **Storage end state:** terminal SOC settlement values lost initial energy using the purchase tariff (or an explicit battery end-energy price). Optional strict terminal SOC tolerance is available in Settings. The strict constraint is OFF by default because a rule-based dispatch cannot guarantee closure.
- **Same objective for GA and GWO:** select method in the existing Optimization settings. GA uses catalog-based chromosomes, tournament selection, conventional single-point crossover producing two complementary offspring, per-gene mutation, and elitism, adapted from the user's GA instructional videos. GA has its own population and generation controls; GWO has its own population and iteration controls. Fixed seeds and evaluator caching are retained.
- **Explicit no-BESS alternative:** after each search, evaluate no storage on identical profiles and network constraints. If feasible and less expensive, select **No battery** as the economic result. Feasible no-storage results are displayed as such, not as a fake 0-kW battery candidate.
- **Revised dispatch:** `GridAwareDispatchPolicy` can store excess PV and discharge against load; import/export caps influence dispatch requests. The separate net-load-target policy and its GUI input were removed. The actual power is limited by battery SOC, rating and reserve. This is a *rule-based approximation*, not a globally optimal multi-hour economic dispatch.
- **Network limits:** existing active import/export caps, optional terminal SOC requirement, and ampacity checks when branch ratings are provided. The transformer-kVA cap was intentionally removed from this scope. An overloaded line is marked infeasible; it is not automatically remedied by the shedding controller.
- **Forecasting replaces scenarios:** independent `src_accelerated/forecasting.py` uses Nixtla **`statsforecast.models.AutoARIMA`** for automatic ARIMA model-order selection instead of `pmdarima.ARIMA` and the earlier `statsmodels` implementation. It supports ARIMA, SARIMA, and SARIMAX with *calendar variables known in advance*. It reports chronological-holdout MAE, RMSE and sMAPE alongside the hour-of-day baseline, then exports ordinary load/PV CSVs to the session's `forecasts` folder. It does not generate random scenarios.
- **Source date handling:** full hourly interval is detected from the imported load CSV, with no Study Period control. Load and PV hours must match; non-hourly inputs are rejected. Synthetic-only load (without a dated CSV) is not part of this workflow.
- **Results:** annual monetary metrics and the no-BESS comparison are included in summary and CSV exports.

## Important limitations

- **GUI runtime was not exercised on Windows in this build environment** (PySide6 was unavailable); source compiles and UI XML parses, and Qt-free regression tests pass. Launch and test interactively on your machine before relying on the application.
- The third tutorial's publicly linked notebook could not be verified end-to-end from this session. The forecasting code follows its *baseline → fit → chronological validation → forecast → metrics* teaching pattern and now uses **StatsForecast AutoARIMA**, as requested; it remains an adaptation rather than a verbatim transcription of the tutorial.
- Forecasts are of aggregate load and PV, redistributed using historic hour-of-day bus shares. They are *not* separately fitted to every individual bus or manufactured customer category. Multi-year input histories are usable, with a training-window control to limit model fitting time.
- Future measured NASA irradiance must not be supplied as a future known predictor. SARIMAX currently uses calendar features only.
- Financial defaults are study assumptions from research papers (not current supplier quotes or Saudi tariffs). The 0 tariff defaults intentionally need replacement before evaluating grid energy economics.
- Economic PV benefits require nonzero PV generation inputs; `pv_profile.csv` with all zeros cannot show improvements in PV curtailment.
- If all BESS candidates fail an overly strong reserve or ampacity constraint, the result reports infeasibility; expand ratings or revise appropriately justified operational assumptions.
- The objective annualizes the one-time upfront capital with a fixed CRF and fixed O&M; it does not model battery aging/replacements unless included in the provided O&M assumption.
- Forecast history and training period need to be chosen chronologically and independently from final optimizer test data to make valid out-of-sample claims.

## Source references

1. Ali, Shaaban, Sindi (2022), *Sustainability* 14, 13209, https://doi.org/10.3390/su142013209 — power/energy cost split, 10-year lifetime, 6% discount and 2% O&M (the supplied paper attributes battery parameter table to an earlier reference).
2. Córdova et al. (2022), *IEEE Transactions on Smart Grid*, https://doi.org/10.1109/TSG.2022.3170871 — curtailment and unserved load cost study assumptions (not universal values).
3. Mirjalili et al. (2014), *Advances in Engineering Software*, https://doi.org/10.1016/j.advengsoft.2013.12.007 — GWO.
4. GA instructional videos from the provided Source.txt: https://youtu.be/nhT56blfRpE and https://youtu.be/uQj5UNhCPuo; tutorial code https://github.com/kiecodes/genetic-algorithms . Algorithmic mechanisms adapted, no copied knapsack objective.
5. ARIMA tutorial: https://youtu.be/fxx_E0ojKrc and linked notebook https://github.com/marcopeix/youtube_tutorials/blob/main/YT_03_forecasting_stats.ipynb .
6. Nixtla StatsForecast AutoARIMA official API: https://nixtlaverse.nixtla.io/statsforecast/docs/models/autoarima.html and exogenous regressors: https://nixtlaverse.nixtla.io/statsforecast/docs/how-to-guides/exogenous.html .

See also `CHANGELOG_STATSFORECAST.md` for the focused migration details and live-library test limitations.

## Source navigation

| Component | Location |
|---|---|
| Economic analysis | `src_accelerated/metrics.py` |
| GWO and GA | `src_accelerated/optimizer.py` |
| BESS dispatch, network limits, SOC | `src_accelerated/simulation.py` |
| Forecasting | `src_accelerated/forecasting.py` |
| Automatic CSV interval / workflow | `src_accelerated/ui_workflow.py` |
| Existing GUI with minimal new controls | `src_accelerated/ui.py` |
| Monetary results exports | `src_accelerated/results.py` |
| Regression tests | `tests/test_integrated_upgrade.py` |

## StatsForecast AutoARIMA correction (2026-11-05)

- The active forecasting implementation now imports `StatsForecast` and `AutoARIMA` from Nixtla's `statsforecast` package. The `pmdarima` dependency is removed.
- Forecasting uses the library's long-form DataFrame (`unique_id`, `ds`, `y`) and the `forecast(df=..., h=..., X_df=...)` API. Model orders are selected automatically (default information criterion AICc), with bounded stepwise search and daily seasonal period 24 for seasonal options.
- GUI default is **AutoARIMA (seasonal)**, and the drop-down retains nonseasonal, SARIMA, and SARIMAX+calendar variations. All are AutoARIMA-based.
- The holdout validation is chronological and reports baseline and AutoARIMA MAE/RMSE/sMAPE. Both load and PV use the same logic; zero PV remains zero.
- Only calendar features known at forecast time are passed as exogenous regressors, not future measured irradiance.
- **Verification limitation:** This container could not install `statsforecast` because network/package-index access failed. Syntax, data framing, GUI wiring, and unit tests with a strict StatsForecast-compatible test double pass, but a real installed-library execution on Windows is still required. Do not interpret mocked tests as verification against the actual StatsForecast runtime.

## Scope simplification — 2026-11-05

- Removed **Net-load target** from the settings GUI, deleted its policy class, and removed the unused target field from `GridAwareDispatchPolicy`. **Net electrical load (load minus PV) remains**, because the grid-aware dispatch must use it.
- Removed the optional **transformer kVA** setting and check. Grid import/export kW caps, voltage limits, terminal SOC, and line ampacity checks remain.
- Battery operating policy choices are now **Idle (diagnostic)** and **Grid-aware rule-based dispatch** (default). The latter charges from PV surplus and requests discharge against positive net demand, subject to SOC, efficiencies, reserve and grid limits. It does not optimize hourly prices or predict future load/PV.
- **Updated GA crossover:** One crossover probability check is made per parent pair. On crossover, choose one cut between genes and produce two complementary children. Otherwise both parents are copied. Apply per-gene mutation to each offspring. Separate GA population and generation controls are present in the same settings group.

### Tests for this revision

Use `py -m pytest -q tests`. PySide6 and StatsForecast must be installed on your Windows machine for live GUI and forecasting verification; the numerical tests do not replace these integration checks.

## GA standard two-offspring crossover update — 2026-11-05

- `src_accelerated/optimizer.py` draws crossover probability **once per parent pair** rather than once per gene.
- On crossover, a random single-point cut yields **two complementary offspring**. Otherwise both parents carry through unchanged (before mutation).
- Each offspring undergoes independent per-gene mutation. Elitism and tournament selection are unchanged.
- Added explicit **GA population size** and **GA generations** spinboxes to the existing settings group; GWO controls remain independent. The random seed is shared, with a neutral label.
- Defaults: 12 GA individuals, 20 generations, 0.80 crossover and 0.12 mutation.
- Tested crossover at either possible cut and with no crossover; tested odd/even GA population sizes. Tests do not require PySide6 or StatsForecast.

See `CHANGELOG_STANDARD_GA_TWO_OFFSPRING.md` for further details; older GA release notes are superseded.


## UI revision

See [UI_REFINEMENT_NOTES.md](UI_REFINEMENT_NOTES.md) for the compact top-toolbar interface, updated controls and test limitations.
