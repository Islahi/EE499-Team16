"""Pure data preparation, physical PV proxy, scoring and StatsForecast adapters for C2.
No actual held-out values enter model fitting. Works with the input package unchanged.
https://github.com/Islahi/EE499-Team16.git
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

import c2_benchmark_settings as S
from src_accelerated.pv_model import read_irradiance, PVModelConfig, irradiance_to_power

TRAIN_CLOCK = pd.date_range(S.TRAIN_START, periods=int((pd.Timestamp(S.TEST_START)-pd.Timestamp(S.TRAIN_START))/pd.Timedelta(hours=1)), freq='h')
TEST_CLOCK = pd.date_range(S.TEST_START, S.TEST_END, freq='h')
ALL_CLOCK = TRAIN_CLOCK.append(TEST_CLOCK)


@dataclass
class SeriesCase:
    dataset: str
    category: str
    unit: str
    y_train: np.ndarray
    y_test: np.ndarray
    origin: str
    site_lat: float | None = None
    site_lon: float | None = None


def check_times(times: pd.DatetimeIndex, label: str):
    times = pd.DatetimeIndex(pd.to_datetime(times))
    if times.tz is not None or not times.is_unique or not times.is_monotonic_increasing:
        raise ValueError(f'{label}: expected increasing unique timezone-naive timestamps')
    if not times.equals(ALL_CLOCK):
        raise ValueError(f'{label}: expected all {len(ALL_CLOCK):,} continuous train/test hours, got {len(times)}')


def split_series(values, title):
    y = np.asarray(values, dtype=float)
    if len(y) != len(ALL_CLOCK) or np.any(~np.isfinite(y)) or np.any(y < -1e-9):
        raise ValueError(f'{title}: invalid values or length')
    return y[:len(TRAIN_CLOCK)], y[len(TRAIN_CLOCK):]


def _load_aggregate(profile_csv, label):
    # This is the original project-compatible timestamp,bus_id,p_kw,q_kvar format.
    tab = pd.read_csv(profile_csv, usecols=['timestamp', 'bus_id', 'p_kw'])
    if tab.duplicated(['timestamp', 'bus_id']).any():
        raise ValueError(f'{label}: duplicate bus/hour rows')
    groups = tab.groupby('timestamp', sort=True, observed=True)['p_kw'].sum()
    times = pd.DatetimeIndex(pd.to_datetime(groups.index))
    # Original packages have longer inputs than needed; select exact study range.
    mask = (times >= ALL_CLOCK[0]) & (times <= ALL_CLOCK[-1])
    times = times[mask]
    check_times(times, label)
    return split_series(groups.to_numpy(dtype=float)[mask], label)


def pv_power_from_ghi(ghi):
    """Vector equivalent of src_accelerated.pv_model.irradiance_to_power()."""
    g = np.asarray(ghi, dtype=float)
    if not np.all(np.isfinite(g)) or np.any(g < 0):
        raise ValueError('NASA irradiance must be nonnegative and finite')
    k, standard, critical = S.PV_RATED_KW, S.PV_STANDARD_IRRADIANCE_W_M2, S.PV_CRITICAL_IRRADIANCE_W_M2
    return k * np.where(g < critical, g * g / (standard * critical), np.minimum(g / standard, 1.0))


def site_coordinates(stem):
    # eg 040d42N_003d70W = 40.42 degrees north, 3.70 degrees west.
    m = re.search(r'(\d{2,3})d(\d{2})([NS])_(\d{2,3})d(\d{2})([EW])', stem)
    if m is None:
        raise ValueError(f'Cannot determine NASA site lat/lon from {stem!r}')
    lat = (int(m[1]) + int(m[2])/100) * (1 if m[3]=='N' else -1)
    lon = (int(m[4]) + int(m[5])/100) * (1 if m[6]=='E' else -1)
    return lat, lon


def daylight_mask_utc(dates, lat, lon):
    """Approximate solar-center-above-horizon at middle of UTC hourly interval.
    Known future calendar/site geometry only. Not inferred from held-out irradiance.
    Uses the common fractional-year/equation-of-time/declination approximation.
    """
    ix = pd.DatetimeIndex(dates)
    doy = np.asarray(ix.dayofyear, dtype=float)
    hour = np.asarray(ix.hour + ix.minute/60.0 + 0.5, dtype=float)
    leap_n = np.where(ix.is_leap_year, 366.0, 365.0)
    gamma = 2 * np.pi / leap_n * (doy - 1 + (hour - 12) / 24)
    eqtime = 229.18*(0.000075+0.001868*np.cos(gamma)-0.032077*np.sin(gamma)
                     -0.014615*np.cos(2*gamma)-0.040849*np.sin(2*gamma))
    decl = (0.006918-0.399912*np.cos(gamma)+0.070257*np.sin(gamma)
            -0.006758*np.cos(2*gamma)+0.000907*np.sin(2*gamma)
            -0.002697*np.cos(3*gamma)+0.00148*np.sin(3*gamma))
    hour_angle = np.radians(((hour * 60 + eqtime + 4 * lon) / 4) - 180)
    la = math.radians(lat)
    cos_zenith = np.sin(la)*np.sin(decl)+np.cos(la)*np.cos(decl)*np.cos(hour_angle)
    return cos_zenith > 0


def load_cases():
    result = []
    entries = (
        ('A_GoiEner_Total_Load', S.RUN_GOIENER_TOTAL),
        ('B_GoiEner_Distributed_15Bus', S.RUN_DISTRIBUTED_15BUS),
    )
    for label, enabled in entries:
        if not enabled: continue
        path = S.DATA_LOAD / label / 'load_profile.csv'
        if not path.is_file():
            # Generate compatible original prepared input if absent.
            from c2_inputs import prepare_total_load, prepare_distributed_15bus
            if label.startswith('A_'): prepare_total_load(path.parent)
            else: prepare_distributed_15bus(path.parent, S.TRAIN_START, S.TEST_START)
        a, b = _load_aggregate(path, label)
        result.append(SeriesCase(label, 'load', 'kW', a, b, str(path.relative_to(S.ROOT))))
    if S.RUN_SOLAR_SITES:
        sources = sorted(S.DATA_SOLAR.glob('POWER_Point_Hourly_*.csv'))
        if len(sources) == 0:
            raise FileNotFoundError(f'No NASA POWER CSV files in {S.DATA_SOLAR}')
        for src in sources:
            tbl = read_irradiance(src, source='nasa_power')
            times = pd.DatetimeIndex(tbl.timestamp)
            ix = times.get_indexer(ALL_CLOCK)
            if np.any(ix < 0):
                raise ValueError(f'{src.name}: missing times from training/test calendar')
            ghi = tbl.irradiance_w_m2.to_numpy(dtype=float)[ix]
            lat, lon = site_coordinates(src.stem)
            name = 'PV_' + src.stem.split('_20141101_20201129_')[-1].replace('_UTC','')
            a, b = split_series(pv_power_from_ghi(ghi), name)
            result.append(SeriesCase(name, 'pv', 'kW', a, b, str(src.relative_to(S.ROOT)), lat, lon))
    return result


def scoring(y, f, training, scale_lag=168):
    """Return identical metrics for all models and seasons; positive bias=underforecast.
    MASE: denominator is training-only seasonal-naive one-week in-sample MAE.
    """
    y, f, training = [np.asarray(v, dtype=float) for v in (y, f, training)]
    if len(y) != len(f) or not len(y) or not np.all(np.isfinite(f)):
        raise ValueError('Cannot score mismatched or nonfinite forecast')
    err = y - f
    abs_error = np.abs(err)
    mae = float(np.mean(abs_error))
    denominator = float(np.mean(np.abs(training[scale_lag:] - training[:-scale_lag]))) if len(training)>scale_lag else 0
    actual_magnitude = float(np.sum(np.abs(y)))
    return {
        'mae_kw': mae,
        'rmse_kw': float(np.sqrt(np.mean(err*err))),
        'wape_percent': float(100 * np.sum(abs_error)/actual_magnitude) if actual_magnitude>0 else np.nan,
        'mase_weekly': float(mae / denominator) if denominator>0 else np.nan,
        'bias_kw_actual_minus_forecast': float(np.mean(err)),
        'smape_percent': float(np.mean(200*abs_error/np.maximum(np.abs(y)+np.abs(f), 1e-8))),
        'mean_actual_kw': float(np.mean(y)),
        'mean_forecast_kw': float(np.mean(f)),
        'monthly_energy_abs_percent_error': np.nan,  # replaced below
    }


def monthly_scores(y, f, training):
    frame = pd.DataFrame({'timestamp': TEST_CLOCK, 'actual_kw':y, 'forecast_kw':f})
    frame['month'] = frame.timestamp.dt.to_period('M').astype(str)
    entries=[]
    for m, part in frame.groupby('month',sort=True):
        d = scoring(part.actual_kw,part.forecast_kw,training)
        d['month'] = m
        d['actual_energy_kwh'] = float(part.actual_kw.sum())
        d['forecast_energy_kwh'] = float(part.forecast_kw.sum())
        d['energy_bias_kwh'] = float(part.actual_kw.sum()-part.forecast_kw.sum())
        entries.append(d)
    monthly = pd.DataFrame(entries)
    actual_by_month = monthly.actual_energy_kwh.to_numpy()
    pred_by_month = monthly.forecast_energy_kwh.to_numpy()
    mape = 100*np.abs(actual_by_month-pred_by_month)/np.maximum(np.abs(actual_by_month),1e-9)
    summary = scoring(y,f,training)
    summary['monthly_energy_abs_percent_error']=float(np.mean(mape))
    summary['peak_demand_error_kw']=float(abs(max(y) - max(f)))
    # For PV, use daylight-only MAPE of nonzero actual values as supporting metric.
    positive = np.asarray(y)>1e-9
    summary['positive_actual_hours_mape_percent']=(float(np.mean(100*np.abs(y[positive]-f[positive])/y[positive]))
                                                   if np.any(positive) else np.nan)
    return summary,monthly


def postprocess(pred, case: SeriesCase):
    p = np.asarray(pred, dtype=float).copy()
    if len(p)!=len(TEST_CLOCK) or not np.all(np.isfinite(p)):
        raise ValueError('Predict output must be finite and have exactly the full year of hours')
    neg_count = int(np.count_nonzero(p < 0))
    p = np.maximum(p,0)
    cap_count, night_count=0,0
    if case.category=='pv':
        cap_count=int(np.count_nonzero(p>S.PV_RATED_KW))
        p=np.minimum(p,S.PV_RATED_KW)
        if S.FORCE_NIGHT_ZERO:
            mask=daylight_mask_utc(TEST_CLOCK,case.site_lat,case.site_lon)
            night_count=int(np.count_nonzero((p>0)&(~mask)))
            p[~mask]=0
    return p, {'negative_values_clipped':neg_count,'pv_values_above_rating_clipped':cap_count,
               'nighttime_nonzero_forecasts_corrected':night_count}


def seasonal_naive_numpy(y_train, season, h):
    """Exact repeating-last-cycle point forecast, independent of StatsForecast installation."""
    if season>len(y_train): raise ValueError('Training has fewer samples than season length')
    return np.resize(np.asarray(y_train[-season:],float),h)


def unsupported_reason(name, lengths, n_train, try_insufficient=False):
    if len(lengths)>1 and name not in S.MULTI_SEASON_MODELS:
        return 'Model API supports only one seasonal period'
    longest=max(lengths)
    if n_train < longest:
        return 'Fewer training hours than the seasonal period'
    # Yearly period represents approximately 365 days; two full cycles are unavailable.
    if longest>=8760 and n_train < 2*longest and not try_insufficient:
        if name in ('MSTL','AutoETS','AutoCES','AutoTheta','HoltWinters','AutoARIMA'):
            return 'Requires or strongly benefits from >=2 full yearly cycles; only 21 months supplied'
        if name in ('AutoTBATS','AutoMFLES') and not S.ALLOW_SINGLE_CYCLE_FOURIER_YEARLY:
            return 'Yearly Fourier fitting disabled with fewer than two yearly cycles'
    if name=='MSTL' and 2*longest > n_train and not try_insufficient:
        return 'MSTL needs at least two complete cycles for its longest seasonal period'
    return None


def make_model(name, season_lengths, n_train):
    """Instantiate Nixtla public model classes, deferring imports to allow offline preparation."""
    from statsforecast import models as m
    lengths = tuple(season_lengths)
    period = lengths[0]
    alias = 'C2Model'
    if name=='AutoARIMA':
        return m.AutoARIMA(season_length=period, seasonal=True,
             max_p=S.AUTOARIMA_MAX_P,max_q=S.AUTOARIMA_MAX_Q,
             max_P=S.AUTOARIMA_MAX_SEASONAL_P,max_Q=S.AUTOARIMA_MAX_SEASONAL_Q,
             max_order=4,nmodels=S.AUTOARIMA_NMODELS,stepwise=True,approximation=True,alias=alias)
    if name=='AutoETS': return m.AutoETS(season_length=period,alias=alias)
    if name=='AutoCES': return m.AutoCES(season_length=period,alias=alias)
    if name=='AutoTheta': return m.AutoTheta(season_length=period,alias=alias)
    if name=='MSTL': return m.MSTL(season_length=list(lengths),
                  trend_forecaster=m.AutoETS(model='ZZN',season_length=1),alias=alias)
    if name=='AutoTBATS': return m.AutoTBATS(season_length=list(lengths),alias=alias)
    if name=='AutoMFLES':
        # train-only internal rolling CV, no test-year access.
        return m.AutoMFLES(test_size=S.AUTOMFLES_VALIDATION_HOURS,
            season_length=list(lengths),n_windows=S.AUTOMFLES_N_WINDOWS,
            metric='mae',alias=alias)
    if name=='SeasonalNaive': return m.SeasonalNaive(season_length=period,alias=alias)
    if name=='HoltWinters': return m.HoltWinters(season_length=period,error_type='A',alias=alias)
    raise ValueError('Unknown StatsForecast model '+str(name))


def predict_model(model,y_train,h):
    fit_start=perf_counter()
    model.fit(np.asarray(y_train,dtype=float))
    fit_seconds=perf_counter()-fit_start
    forecast_start=perf_counter()
    result=model.predict(h=h)
    prediction_seconds=perf_counter()-forecast_start
    if isinstance(result,dict):
        raw=result['mean']
    elif hasattr(result,'__getitem__'):
        raw=result['mean']
    else:
        raise ValueError('Unexpected StatsForecast predict return type')
    forecast = np.asarray(raw, dtype=float).reshape(-1)
    if forecast.size != h or not np.all(np.isfinite(forecast)):
        raise ValueError(f'{type(model).__name__} returned {forecast.size} predictions for {h} hours or non-finite values')
    return forecast,fit_seconds,prediction_seconds


def score_and_save(case,model_name,season_name,predicted,outdir,fit_seconds,predict_seconds,engine):
    outdir=Path(outdir)
    outdir.mkdir(parents=True,exist_ok=True)
    p, corrections=postprocess(predicted,case)
    score,monthly=monthly_scores(case.y_test,p,case.y_train)
    table=pd.DataFrame({'timestamp':TEST_CLOCK,'actual_kw':case.y_test,'forecast_kw':p})
    table['error_kw_actual_minus_forecast']=table.actual_kw-table.forecast_kw
    table.to_csv(outdir/'hourly_comparison.csv',index=False)
    monthly.to_csv(outdir/'monthly_metrics.csv',index=False)
    info={**score,**corrections,'status':'OK','category':case.category,'dataset':case.dataset,
          'model':model_name,'seasonality':season_name,'periods_hours':str(S.SEASONALITIES[season_name]),
          'engine':engine,'training_hours':len(case.y_train),'forecast_hours':len(case.y_test),
          'fit_seconds':round(float(fit_seconds),6),'forecast_seconds':round(float(predict_seconds),6),
          'total_model_seconds':round(float(fit_seconds+predict_seconds),6),'unit':case.unit,
          'comparison_postprocessed':True}
    if max(S.SEASONALITIES[season_name])>=8760:
        info['yearly_cycle_warning']='21 months of training supplies fewer than two yearly cycles'
    pd.Series(info,dtype=object).to_json(outdir/'run_metrics.json',indent=2)
    return info
