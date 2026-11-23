"""Observed-versus-forecast accuracy, never computed on fitting observations.

The 2021 accuracy comparison is an out-of-sample *holdout evaluation* only
when models trained before the 2021 forecast origin. For genuinely future
forecasts with no matching historical observations, scores are unavailable.
"""
from pathlib import Path
import numpy as np
import pandas as pd

from .distributed_dataset import SECTORS


def compare_forecast(history, predicted, assignments, training_end=None):
    """Return category error records and timestamp-aligned observations.

    No interpolation, no silent clock conversion, and no zero-filled missing
    actuals. All power values are in kW; hourly energy is kWh.
    """
    before = pd.DatetimeIndex(history.timestamps)
    after = pd.DatetimeIndex(predicted.timestamps)
    if before.tz != after.tz:
        raise ValueError('Forecast and historical clock definitions differ')
    if training_end is not None and after[0] <= pd.Timestamp(training_end):
        raise ValueError('Forecast error scoring would overlap training history')
    a, b = before.get_indexer(after), np.arange(len(after))
    present = a >= 0
    if present.sum() == 0:
        return [], []
    a, b = a[present], b[present]
    rows, series = [], []
    categories = [(sector, [bus for bus, label in assignments.items() if label == sector])
                  for sector in SECTORS]
    categories.append(('solar_pv', list(predicted.pv_p_kw)))
    for category, buses in categories:
        attr = 'pv_p_kw' if category == 'solar_pv' else 'load_p_kw'
        history_map, forecast_map = getattr(history, attr), getattr(predicted, attr)
        # Include only buses that have both an actual and a forecast. For PV,
        # exclude buses with zero generation throughout both periods: they are
        # not PV installation sites and must not dilute per-bus average errors.
        matched = [bus for bus in buses if bus in history_map and bus in forecast_map]
        if category == 'solar_pv':
            matched = [bus for bus in matched if np.any(np.asarray(history_map[bus])[a] != 0)
                       or np.any(np.asarray(forecast_map[bus])[b] != 0)]
        if not matched:
            # Do not display a fictitious zero-error profile for a sector or
            # PV category with no observed-and-forecast bus in the holdout.
            continue
        observed_matrix = np.stack([np.asarray(history_map[bus], dtype=float)[a] for bus in matched])
        forecast_matrix = np.stack([np.asarray(forecast_map[bus], dtype=float)[b] for bus in matched])
        if (observed_matrix.shape != forecast_matrix.shape or
                not np.isfinite(observed_matrix).all() or not np.isfinite(forecast_matrix).all()):
            raise ValueError(f'Invalid actual/forecast alignment for {category}')
        deltas = forecast_matrix - observed_matrix
        per_bus_mae = np.mean(np.abs(deltas), axis=1)
        per_bus_rmse = np.sqrt(np.mean(deltas * deltas, axis=1))
        absolute_actual = np.sum(np.abs(observed_matrix), axis=1)
        per_bus_total_error = np.sum(np.abs(deltas), axis=1)
        positive = absolute_actual > 0
        observed = observed_matrix.sum(axis=0)
        forecast = forecast_matrix.sum(axis=0)
        aggregate_delta = forecast - observed
        pooled_denominator = float(absolute_actual.sum())
        rows.append(dict(category=category, hours=len(a), start=str(after[b[0]]),
                         end=str(after[b[-1]]), bus_count=len(matched),
                         # Display: equal weight per bus, not sum of sector power.
                         mae_kw=float(per_bus_mae.mean()),
                         rmse_kw=float(per_bus_rmse.mean()),
                         wape_percent=(float(np.mean(100 * per_bus_total_error[positive] /
                                                         absolute_actual[positive])) if positive.any() else None),
                         # Retain aggregate errors for audit and legacy comparison.
                         aggregate_mae_kw=float(np.mean(np.abs(aggregate_delta))),
                         aggregate_rmse_kw=float(np.sqrt(np.mean(aggregate_delta**2))),
                         pooled_wape_percent=(float(100 * per_bus_total_error.sum() /
                                                    pooled_denominator) if pooled_denominator > 0 else None),
                         observed_energy_kwh=float(observed.sum()),
                         forecast_energy_kwh=float(forecast.sum())))
        series.extend(dict(timestamp=str(after[index]), category=category,
                           actual_kw=float(y), forecast_kw=float(yhat))
                      for index, y, yhat in zip(b, observed, forecast))
    return rows, series


def save_comparison(folder, history, predicted, assignments, training_end=None):
    """Create truthful offline-report data; return None if no actuals exist."""
    score, series = compare_forecast(history, predicted, assignments, training_end)
    if not score:
        return []
    folder = Path(folder)
    pd.DataFrame(score).to_csv(folder / 'forecast_errors.csv',index=False)
    pd.DataFrame(series).to_csv(folder / 'forecast_comparison.csv',index=False)
    return score
