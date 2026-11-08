# StatsForecast / AutoARIMA library correction

## Why

The preceding integrated release used `pmdarima.ARIMA`, whereas the referenced
forecasting tutorial used Nixtla's StatsForecast `AutoARIMA`. This update
replaces the forecasting backend while preserving the economic model, GA/GWO,
network solver and mostly unchanged desktop UI.

## Files changed

- `src_accelerated/forecasting.py`: Fits Nixtla `StatsForecast` with a
  long-format `unique_id`, `ds`, `y` DataFrame. Uses `AutoARIMA` to select model
  orders automatically; supports seasonal, nonseasonal and known-calendar
  regression modes. Maintains chronological validation and exports identical
  load/PV CSV formats. No more pmdarima or direct statsmodels ARIMA dependency.
- `src_accelerated/ui.py`: Default method AutoARIMA, same Forecasting dialog
  design; retains alternative mode choices using explicit item data.
- `requirements.txt`: `statsforecast>=2.0,<3.0` replaces pmdarima.
- `tests/test_integrated_upgrade.py`: Strict mock-based StatsForecast API and
  data-contract coverage (including seasonal and calendar covariate modes).
- `tests/test_statsforecast_installed.py`: Optional **real library** smoke test,
  skips only when StatsForecast is not installed.
- `README_UPGRADE.md`: Updated library details, instructions and limitations.

## Models and behavior

| GUI choice | Backend | Daily seasonal period | Exogenous features |
| --- | --- | --- | --- |
| AutoARIMA (seasonal) | AutoARIMA | 24 hours | none |
| AutoARIMA (nonseasonal) | AutoARIMA | disabled | none |
| AutoARIMA (SARIMA) | AutoARIMA | 24 hours | none |
| AutoARIMA (SARIMAX + calendar) | AutoARIMA | 24 hours | hour/day-of-week sine/cosine |

The first and third rows are equivalent by design; the extra label preserves
familiar naming from the preceding forecasting menu. The automatic stepwise
search is bounded for interactive responsiveness; its selected order is
chosen by StatsForecast, not fixed at `(1,0,1)`.

## Testing limits

- Syntax and XML verification passed.
- 11 fast regression cases passed with an API-compatible StatsForecast test double.
- Live StatsForecast execution **was not possible** in the build environment,
  because `statsforecast` could not be downloaded/installed there.
- On your Windows system, run `py -m pip install -r requirements.txt` then
  `py -m pytest -q tests` to execute the installed-library smoke test.

## References

- Video from user's `Source.txt`: https://youtu.be/fxx_E0ojKrc
- Official AutoARIMA API: https://nixtlaverse.nixtla.io/statsforecast/docs/models/autoarima.html
- Official long-form data and forecast interface: https://nixtlaverse.nixtla.io/statsforecast/docs/getting-started/getting_started_short.html
- Official exogenous regressor interface: https://nixtlaverse.nixtla.io/statsforecast/docs/how-to-guides/exogenous.html
