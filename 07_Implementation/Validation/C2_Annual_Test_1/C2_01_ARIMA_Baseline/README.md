# Initial AutoARIMA test

Source archive: `C2_annual_results(1).7z`

7 cases, 25 series. The recorded forecast runs span March 2019 through February 2020. The initial test evaluates one design. Its ranking PDF orders baseline errors within comparable target groups.

| Open | Contents |
|---|---|
| Analysis.pdf | Findings, experimental scope, interpretation, limitations and forecast figures |
| Rankings.pdf | ARIMA performance by load total, sector, bus and irradiance site |
| Dashboard.html | Self-contained interactive explorer |
| README_DASHBOARD.md / START_DASHBOARD.bat | Windows instructions and double-click launcher |
| Rankings.xlsx | Sortable performance, coverage and supporting tables |
| Tables/ | CSV tables, monthly and residual statistics, completeness audits, source and figure inventories |
| Figures/ | 550 separate PNGs, organized by dataset and configuration |
| Hourly_data/ | Actual and forecast columns on the original hourly clock, one gzip-compressed CSV per target |
| Source_records/ | Original run settings and summary records. Source summaries use their original conventions. |
| Verify_metrics.py | Optional numerical verification script. Run `py Verify_metrics.py` after installing pandas and NumPy. |

The standard hourly chart always shows July 1–14, 2019. Full-year scores use 8,784 hourly pairs. A positive signed bias means the model underforecast. Units appear in the performance table and on every chart. A period integral uses all observed hours (1 h per observation).

Project reference: [EE499-Team16 forecasting implementation](https://github.com/Islahi/EE499-Team16/blob/aaf17445f1a9c97f25f45188dd8053c65c177fb8/07_Implementation/src_accelerated/forecasting.py).
