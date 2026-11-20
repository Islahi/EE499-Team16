"""Historical hourly ARIMA-family forecasting, without scenario generation.

Implements the Nixtla StatsForecast AutoARIMA workflow:
long-format (unique_id, ds, y) -> automatic order selection -> hourly forecast.
Retains a chronological holdout and a simple hourly baseline for comparison.
Only known calendar covariates can be used for future exogenous inputs;
future observed irradiance or load is never used for model fitting.
"""
from dataclasses import dataclass
from datetime import timedelta
from io import StringIO
from math import sqrt
from warnings import catch_warnings, simplefilter

import numpy as np
import pandas as pd

from .data_loader import ProfileData


@dataclass(frozen=True)
class ForecastConfig:
    horizon_hours: int = 24
    train_hours: int = 672  # 4 weeks of history (runtime-friendly)
    validation_hours: int = 24
    method: str = "autoarima"  # autoarima, arima (nonseasonal), sarima, sarimax
    seasonal_period: int = 24
    # Bound automatic order search for responsive interactive forecasting.
    max_p: int = 2
    max_q: int = 2
    max_P: int = 1
    max_Q: int = 1
    nmodels: int = 20

    def __post_init__(self):
        if self.method not in ("autoarima", "arima", "sarima", "sarimax"):
            raise ValueError("Forecast method must be autoarima, arima, sarima or sarimax")
        for name in ("horizon_hours", "train_hours", "validation_hours", "seasonal_period", "nmodels"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("max_p", "max_q", "max_P", "max_Q"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.train_hours < 48:
            raise ValueError("Forecast needs at least 48 training observations")


@dataclass
class ForecastReport:
    profiles: ProfileData
    scores: dict[str, dict[str, float]]
    model_info: dict[str, str]
    historical_end: object
    horizon_hours: int


def _score(actual, forecast):
    actual, forecast = np.asarray(actual, dtype=float), np.asarray(forecast, dtype=float)
    return {
        "mae": float(np.mean(np.abs(actual - forecast))),
        "rmse": float(sqrt(np.mean((actual - forecast) ** 2))),
        "smape_percent": float(100 * np.mean(2 * np.abs(actual - forecast) /
                                np.maximum(np.abs(actual) + np.abs(forecast), 1e-8))),
    }


def _hourly_baseline(y, source_times, future_times):
    """Repeat average hour-of-day pattern over training period only."""
    hours = np.asarray([int(pd.Timestamp(t).hour) for t in source_times])
    mean = float(np.mean(y))
    means = {hour: float(np.mean(y[hours == hour])) if np.any(hours == hour) else mean
             for hour in range(24)}
    return np.array([means[int(pd.Timestamp(t).hour)] for t in future_times], dtype=float)


def _calendar_x(dates):
    """Calendar variables are known at forecast time (unlike future weather)."""
    idx = pd.DatetimeIndex(dates)
    hours = idx.hour.to_numpy(dtype=float)
    weekdays = idx.dayofweek.to_numpy(dtype=float)
    return np.column_stack((np.sin(2*np.pi*hours/24), np.cos(2*np.pi*hours/24),
                            np.sin(2*np.pi*weekdays/7), np.cos(2*np.pi*weekdays/7)))


def _fit_predict(y, dates, next_dates, cfg):
    """Fit Nixtla StatsForecast AutoARIMA and return future hourly values.

    AutoARIMA automatically chooses (p,d,q) and (P,D,Q) when seasonal.
    Unlike the prior implementation, this fits the original series directly,
    not an ARIMA model of deviations from an hourly mean.  No information
    from validation or future targets is included in a training fit.
    """
    try:
        from statsforecast import StatsForecast
        from statsforecast.models import AutoARIMA
    except ImportError as exc:
        raise ImportError(
            "StatsForecast is required for forecasting. Install dependencies "
            "using 'python -m pip install -r requirements.txt'."
        ) from exc

    dates = pd.DatetimeIndex(dates)
    next_dates = pd.DatetimeIndex(next_dates)
    y = np.asarray(y, dtype=float)
    if len(dates) != len(y) or len(next_dates) == 0:
        raise ValueError("Training dates and values must match; forecast horizon must be nonempty")
    if not np.all(np.isfinite(y)):
        raise ValueError("Training profile contains non-finite data")
    if next_dates[0] != dates[-1] + pd.Timedelta(hours=1):
        raise ValueError("Forecast must start exactly one hour after training history")

    seasonal = cfg.method in ("autoarima", "sarima", "sarimax")
    model = AutoARIMA(
        seasonal=seasonal,
        season_length=cfg.seasonal_period if seasonal else 1,
        max_p=cfg.max_p, max_q=cfg.max_q,
        max_P=cfg.max_P if seasonal else 0,
        max_Q=cfg.max_Q if seasonal else 0,
        max_order=4, nmodels=cfg.nmodels,
        stepwise=True, approximation=True,
        alias="AutoARIMA",
    )
    train = pd.DataFrame({"unique_id": "feeder", "ds": dates, "y": y})
    future_covariates = None
    if cfg.method == "sarimax":
        feature_names = ("hour_sin", "hour_cos", "weekday_sin", "weekday_cos")
        train[ list(feature_names) ] = _calendar_x(dates)
        future_covariates = pd.DataFrame({"unique_id": "feeder", "ds": next_dates})
        future_covariates[list(feature_names)] = _calendar_x(next_dates)

    # forecast() avoids storing a huge fitted-value history. A new estimator
    # is trained for the validation split and again using all training data.
    with catch_warnings():
        simplefilter("ignore")
        sf = StatsForecast(models=[model], freq="h", n_jobs=1)
        predicted_df = sf.forecast(df=train, h=len(next_dates), X_df=future_covariates)
    if "AutoARIMA" not in predicted_df:
        raise RuntimeError("StatsForecast output does not contain the AutoARIMA column")
    predicted_df = predicted_df.sort_values("ds")
    returned_times = pd.DatetimeIndex(predicted_df["ds"])
    if len(returned_times) != len(next_dates) or not np.array_equal(returned_times.to_numpy(), next_dates.to_numpy()):
        raise RuntimeError("StatsForecast returned timestamps that differ from the requested forecast period")
    predicted = predicted_df["AutoARIMA"].to_numpy(dtype=float)
    if not np.all(np.isfinite(predicted)):
        raise RuntimeError("StatsForecast produced non-finite predictions")
    return np.maximum(predicted, 0.0)


def _forecast_total(y, times, future_times, cfg):
    y = np.asarray(y, dtype=float)
    times = pd.DatetimeIndex(times)
    fit_from = max(0, len(y) - cfg.train_hours - cfg.validation_hours)
    y = y[fit_from:]
    times = times[fit_from:]
    if len(y) <= cfg.validation_hours + 48:
        raise ValueError("Not enough history for this training and holdout period")
    split = len(y) - cfg.validation_hours
    validation_t = times[split:]
    baseline = _hourly_baseline(y[:split], times[:split], validation_t)
    validation_pred = _fit_predict(y[:split], times[:split], validation_t, cfg)
    scores = {"baseline": _score(y[split:], baseline),
              "autoarima": _score(y[split:], validation_pred)}
    forecast = _fit_predict(y, times, future_times, cfg)
    return forecast, scores


def _allocate(history, field_p, field_q, aggregate_prediction, target_times):
    """Fast, time-of-day bus allocation; O(buses * history) not O(buses * horizon * history).

    P and Q are assigned using historic hourly shares. This is an engineering
    approximation, not customer-level forecast inference.
    """
    active = getattr(history, field_p)
    reactive = getattr(history, field_q)
    bus_ids = sorted(active)
    hour = np.asarray(pd.DatetimeIndex(history.timestamps).hour, dtype=int)
    target_hour = np.asarray(pd.DatetimeIndex(target_times).hour, dtype=int)
    nsteps = len(target_times)
    nbuses = len(bus_ids)
    historical_hour_count = np.maximum(np.bincount(hour, minlength=24), 1)
    hourly_mean = np.zeros((nbuses, 24), dtype=float)
    hourly_ratio = np.zeros((nbuses, 24), dtype=float)
    limits = np.zeros(nbuses)
    for j, bus in enumerate(bus_ids):
        p = np.asarray(active[bus], dtype=float)
        q = np.asarray(reactive[bus], dtype=float)
        hourly_mean[j] = np.bincount(hour, weights=p, minlength=24) / historical_hour_count
        hourly_q = np.bincount(hour, weights=q, minlength=24) / historical_hour_count
        hourly_ratio[j] = np.divide(hourly_q, hourly_mean[j],
                                     out=np.zeros(24), where=hourly_mean[j] > 1e-9)
        limits[j] = p.max(initial=0)
    weights = hourly_mean[:, target_hour]
    denominator = weights.sum(axis=0)
    share = np.divide(weights, denominator[None, :],
                      out=np.zeros_like(weights), where=denominator[None, :] > 0)
    result = np.maximum(0, share * np.asarray(aggregate_prediction)[None, :])
    if field_p == 'pv_p_kw':
        result = np.minimum(result, limits[:, None])
        # A bus cannot produce at clock hours where every historical observation
        # was zero, even if residual fitting introduces a positive night bias.
        result = np.where(weights > 1e-9, result, 0.0)
    q_result = result * hourly_ratio[:, target_hour]
    return ({bus: result[j].tolist() for j, bus in enumerate(bus_ids)},
            {bus: q_result[j].tolist() for j, bus in enumerate(bus_ids)})


def generate_forecast(history: ProfileData, cfg: ForecastConfig) -> ForecastReport:
    if len(history.timestamps) < cfg.validation_hours + 50:
        raise ValueError("A longer historical profile is needed to validate and fit AutoARIMA")
    timestamps = pd.DatetimeIndex(history.timestamps)
    if timestamps.tz is not None:
        raise ValueError("Use one consistent timezone-naive hourly reference before forecasting")
    future_times = pd.date_range(timestamps[-1] + pd.Timedelta(hours=1),
                                 periods=cfg.horizon_hours, freq="h")
    predictions = {}
    scores = {}
    for key, field in (("load", "load_p_kw"), ("pv", "pv_p_kw")):
        values = getattr(history, field)
        y = np.sum(np.array(list(values.values()), dtype=float), axis=0)
        if np.max(np.abs(y)) < 1e-8:
            predicted = np.zeros(cfg.horizon_hours)
            scores[key] = {"baseline": {"mae": 0.0, "rmse": 0.0, "smape_percent": 0.0},
                           "autoarima": {"mae": 0.0, "rmse": 0.0, "smape_percent": 0.0}}
        else:
            predicted, scores[key] = _forecast_total(y, timestamps, future_times, cfg)
        if key == "pv":
            cap = sum(max(values) for values in history.pv_p_kw.values())
            predicted = np.clip(predicted, 0.0, cap)
        predictions[key] = predicted
    lp, lq = _allocate(history, "load_p_kw", "load_q_kvar", predictions["load"], future_times)
    pp, pq = _allocate(history, "pv_p_kw", "pv_q_kvar", predictions["pv"], future_times)
    def rows(p, q):
        return (dict(timestamp=ts.isoformat(sep=" "), bus_id=bus,
                     p_kw=p[bus][j], q_kvar=q[bus][j])
                for j, ts in enumerate(future_times) for bus in sorted(p))
    load = pd.DataFrame(rows(lp, lq))
    pv = pd.DataFrame(rows(pp, pq))
    future_profiles = ProfileData(StringIO(load.to_csv(index=False)), StringIO(pv.to_csv(index=False)))
    return ForecastReport(future_profiles, scores,
                          {"method": cfg.method, "estimator": "statsforecast.models.AutoARIMA",
                           "order_selection": "automatic (AICc)",
                           "seasonal_period": str(cfg.seasonal_period if cfg.method != 'arima' else 1),
                           "uses_calendar_regressors": str(cfg.method == 'sarimax'),
                           "train_hours": str(cfg.train_hours),
                           "validation_hours": str(cfg.validation_hours)},
                          timestamps[-1], cfg.horizon_hours)
