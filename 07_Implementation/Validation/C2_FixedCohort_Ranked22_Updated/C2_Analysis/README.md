# EE499 C2 forecasting evaluation

Open **00_Overview/C2_Analysis_Report.pdf** for the 15-page project report, **00_Overview/C2_Forecast_Explorer.html** in a current desktop browser for interactive plots, or **00_Overview/C2_Rankings.xlsx** for the workbook. The dashboard is self-contained and requires no server. Extract the ZIP before opening individual files.

## Run and scope

The two input archives contained 8,889 forecasting files and 10 feeder files. The hourly checks found 1,444 successful annual forecasts and 5 failed jobs on the zero slack bus. There were 0 skipped terminal records, 0 partial traces and no unaccounted-for planned job. The two older neural failures at bus 1 lie outside the 1,447-job deduplicated plan. The 20 nonzero datasets each have 69 successful configurations. The 64 successful zero-slack traces have individual plots and metrics. WAPE and weekly MASE are undefined for that target, so it has no official score or top five. Scope outside the selected grid is identified separately, without interpreting untested combinations as failures.

## Dataset folders and figures

The four cohort folders, the individual bus folders, Distributed_Total, and Bilbao PV each contain one wide **hourly_forecasts.csv**. Every row identifies its dataset and hour, followed by the aligned actual and a column per exact model__seasonality configuration. For example, XGBoost__daily_weekly_monthly_yearly is a single configuration. Units are kW/customer for the three individual cohort datasets and kW elsewhere. Full-precision metrics, runtimes, and each target's rankings are in neighboring CSV files. Job inventory records original completion, failures and the reported input fingerprint.

Each successful dataset/configuration has 22 separate PNGs in its own folder under PNG. The seven standard forecast charts show hourly power over July 1–14 and full-year daily, weekly and monthly mean power and energy. The six supplemental error zooms show hourly detail for high- and low-MAE days, complete weeks and months. The nine diagnostic charts cover hourly signed and absolute errors, the annual residual histogram, weekly mean signed and absolute errors, and four seasonal profiles. See 00_Overview/plot_inventory.csv for paths and ranges.

Each dataset also has a PNG/Main_Comparison folder with the seven standard charts and six supplementary zooms. The main comparison includes Actual, AutoARIMA__daily and the three highest-ranked eligible candidates. Candidate slots exclude AutoARIMA variants and catalog baseline controls. The zero-load slack bus has two main traces because its weighted score is undefined. In the main comparison, selected zooms use the mean hourly absolute error of the displayed forecasts. Historical top-five tables and zoom-period CSVs are retained for reference. The inventory records the windows used by the revised figures.

Open README_DASHBOARD.md for the Windows guide, or double-click START_DASHBOARD.bat. The dashboard embeds the annual observations and forecasts. The ARIMA comparisons for all configurations are available in each dataset folder.

Mean power uses the arithmetic mean over included samples. Energy integrates hourly samples over one hour. Daily, Monday–Sunday weekly and calendar-month intervals follow the recorded clock. The two boundary weeks are partial calendar weeks (72/168 and 120/168 h). The period_coverage files contain the included hours, denominator and percentage for every aggregation. An automatically selected extreme is the complete calendar period with the highest or lowest hourly MAE, with the earliest tie chosen. Drag, scroll or use the period menu in the dashboard. ISO week 53 in seasonal views contains the opening days that belong to the previous ISO year.

## Official score and deployment comparison

Within each dataset, minimize ranks for MAE (5), RMSE (5), WAPE (5), weekly MASE (2), absolute bias (4) and sMAPE (3). Sum products and divide by 24. Metrics equal to ten significant digits receive averaged ranks. Equal configuration scores share the minimum occupied rank. Exact configuration ID orders tied rows for display. Lower scores are better. The 15-bus group averages scores over 14 loaded buses. Overall group weights are 1 each for the three single cohorts and PV, 3 for the combined meter total, and 2 for the entire bus group, divided by 9. Distributed_Total is shown separately. All 69 scored configurations are present in all eligible groups. Unit-dependent errors never enter a cross-dataset raw average.

Strategy A selects the minimum mean bus score (LightGBM). B selects each sector-cohort winner and uses its configuration on the mapped buses. C uses individual bus winners. D uses B with no bus-specific exception supported on these inputs. All strategies use sums of saved bus forecasts. Separately, XGBoost leads Bilbao modeled PV. The recommendation requires user approval. No training, retry, simulation, deployment or project changes were performed.

## Reading time and quality fields

Positive signed bias means underprediction. Model time combines fit and forecast as reported. The wall time includes worker overhead. For optimized custom methods a zero forecast field may mean forecasts were timed inside the fit field. Consult the specific neural stage timings. Peak memory is unrecorded, so memory cells are intentionally empty. Strength and weakness fields state the most and least favorable metric ranks within each finalist. The source and audit CSVs preserve warnings as well as failures. Only complete finite ordered hourly files are eligible. The empty partial-coverage table is intentional.

## Reproduce the visual revision

See Reproduce/Revision/README.md. The retained numerical scripts document the original evaluation. The 2021 inputs and official ranking tables are included in this package.
