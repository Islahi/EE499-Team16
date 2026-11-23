"""Approved sector-sum calendar models and one independent modeled-PV winner."""
from dataclasses import dataclass, field, asdict
from time import perf_counter
from importlib.metadata import version, PackageNotFoundError

import numpy as np
import pandas as pd

from .data_loader import ProfileData
from .distributed_dataset import SECTORS, validate_assignments
from .forecast_models import FeatureCache, fit_predict, estimator, training_scale, BOOST_GRID
from .solar_source import daylight

LOAD_SETTINGS = {
    "residential": ("CalendarRidge", {"fourier_richness":.5, "alpha":.1}),
    "commercial": ("XGBoost", {"selected_hyperparameters":{"n_estimators":300,"learning_rate":.05,"max_depth":3}}),
    "manufacturing": ("LightGBM", {"selected_hyperparameters":{"n_estimators":500,"learning_rate":.03,"num_leaves":31}}),
}


@dataclass(frozen=True)
class ForecastConfig:
    horizon_hours: int = 24
    training_start: object = None
    training_end: object = None  # inclusive
    forecast_start: object = None
    train_hours: int | None = None  # optional explicit restriction; all history by default
    method: str = "sector_sum"

    def __post_init__(self):
        if self.method != "sector_sum":
            raise ValueError("Only approved sector-sum calendar winners are executable")
        if isinstance(self.horizon_hours, bool) or not isinstance(self.horizon_hours, int) or self.horizon_hours < 1:
            raise ValueError("Forecast horizon must be a positive number of hours")
        if self.train_hours is not None and (isinstance(self.train_hours,bool) or not isinstance(self.train_hours,int) or self.train_hours<8760):
            raise ValueError("Annual-feature forecasting requires at least one year of history")


@dataclass
class ForecastReport:
    profiles: ProfileData
    scores: dict
    model_info: dict
    historical_end: object
    horizon_hours: int
    sector_predictions: dict = field(default_factory=dict)
    pv_capacity_factor: object = None


def _allocate_sector(history, members, prediction, future_times):
    hours = pd.DatetimeIndex(history.timestamps).hour.to_numpy()
    future_hours = pd.DatetimeIndex(future_times).hour.to_numpy()
    means, ratios = [], []
    totals = np.array([np.mean(history.load_p_kw[b]) for b in members])
    fallback = totals/totals.sum() if totals.sum()>0 else np.ones(len(members))/len(members)
    for b in members:
        p, q = np.asarray(history.load_p_kw[b]), np.asarray(history.load_q_kvar[b])
        counts = np.maximum(np.bincount(hours, minlength=24), 1)
        mp = np.bincount(hours, weights=p, minlength=24)/counts
        mq = np.bincount(hours, weights=q, minlength=24)/counts
        ratio = q.sum()/p.sum() if p.sum()>1e-9 else 0.
        means.append(mp)
        ratios.append(np.divide(mq,mp,out=np.full(24,ratio),where=mp>1e-9))
    means = np.array(means)
    denominator = means.sum(axis=0)
    shares = np.divide(means,denominator[None,:],out=np.repeat(fallback[:,None],24,axis=1),where=denominator[None,:]>0)
    shares /= shares.sum(axis=0)
    active = shares[:,future_hours]*prediction
    # Compensate floating point residual at the largest share, without changing totals.
    for i in range(len(future_times)):
        active[np.argmax(shares[:,future_hours[i]]),i] += prediction[i]-active[:,i].sum()
    if not np.allclose(active.sum(axis=0),prediction,atol=1e-8,rtol=1e-12) or (active < -1e-10).any():
        raise RuntimeError("Sector allocation failed conservation")
    return ({b:active[j].tolist() for j,b in enumerate(members)},
            {b:(active[j]*ratios[j][future_hours]).tolist() for j,b in enumerate(members)})


def _pv_predict(reference, train_times, future, features):
    started = perf_counter()
    series = pd.Series(reference.p_kw,index=pd.DatetimeIndex(reference.timestamps))
    y = series.reindex(train_times).to_numpy(dtype=float)
    if not np.isfinite(y).all() or not y.any():
        raise ValueError("PV reference must cover every selected training hour with genuine nonzero history")
    split = len(y)-120*24
    if split < 180*24:
        raise ValueError("PV training-only selection requires 120 validation days and 180 earlier fitting days")
    x,_ = features.get(1.)
    scale = training_scale(y)  # C2 preprocessing uses the full pre-origin training interval
    scores = []
    for params in BOOST_GRID['XGBoost']:
        model = estimator('XGBoost',{'selected_hyperparameters':params})
        model.fit(x[:split], y[:split]/scale)
        pred = np.asarray(model.predict(x[split:]))*scale
        if not np.isfinite(pred).all():
            raise ValueError("PV candidate produced non-finite validation predictions")
        scores.append({'parameters':params,'validation_mae_kw':float(np.mean(np.abs(pred-y[split:])))})
    best = min(scores,key=lambda row:row['validation_mae_kw'])
    prediction,timing = fit_predict('XGBoost',y,features,{'selected_hyperparameters':best['parameters']})
    prediction = np.clip(prediction,0,reference.capacity_kw)
    prediction[~daylight(future,reference.site)] = 0
    return prediction/reference.capacity_kw, {
        'model':'XGBoost__daily_weekly_monthly_yearly', 'configuration_status':'PV-specific training-only reselected winner; exact historical fitted settings unavailable',
        'selected_hyperparameters':best['parameters'], 'validation_candidates':scores,
        'validation_start':str(train_times[split]),'validation_end':str(train_times[-1]),
        'reference_capacity_kw':reference.capacity_kw,'source':reference.provenance,'site':asdict(reference.site),
        'night_mask':'NOAA approximate elevation at hourly midpoint in explicit UTC',
        **timing,'total_with_selection_seconds':perf_counter()-started}


def generate_forecast(history: ProfileData, cfg: ForecastConfig, *, assignments=None,
                      network=None, pv_reference=None, pv_ratings=None) -> ForecastReport:
    cfg.__post_init__()
    if network is None or assignments is None:
        raise ValueError("Sector forecasting requires the network and explicit distributed-folder assignments")
    times = pd.DatetimeIndex(history.timestamps)
    origin = pd.Timestamp(cfg.forecast_start) if cfg.forecast_start is not None else (
        pd.Timestamp(cfg.training_end)+pd.Timedelta(hours=1) if cfg.training_end is not None else times[-1]+pd.Timedelta(hours=1))
    if times.tz is not None or origin.tz is not None:
        raise ValueError("Use the same explicit source-clock hourly axis for load and PV")
    end = origin if cfg.training_end is None else pd.Timestamp(cfg.training_end)+pd.Timedelta(hours=1)
    if end != origin:
        raise ValueError("Training must end exactly one hour before forecast origin")
    train = history.slice(cfg.training_start,end)
    if cfg.train_hours is not None:
        train = train.slice(train.timestamps[max(0,len(train.timestamps)-cfg.train_hours)])
    train_times = pd.DatetimeIndex(train.timestamps)
    if len(train_times)<8760 or train_times[-1]+pd.Timedelta(hours=1) != origin:
        raise ValueError("Use at least one continuous year of training observations ending one hour before origin")
    ids = {b.bus_id for b in network.buses}
    slack = network.slack_bus_id()
    required = {b for b,p in train.load_p_kw.items() if b!=slack and np.any(p)}
    if set(train.load_p_kw)-ids:
        raise ValueError("Forecast load profiles contain unknown buses")
    mapping = validate_assignments(pd.DataFrame(list(assignments.items()),columns=['bus_id','category']),ids,slack,required)
    if any(not np.isfinite(p).all() or np.min(p)<0 for p in map(np.asarray,train.load_p_kw.values())):
        raise ValueError("Load history must be finite nonnegative bus demand in kW")
    if np.any(train.load_p_kw.get(slack,[0])):
        raise ValueError("Slack demand must be zero")
    future = pd.date_range(origin,periods=cfg.horizon_hours,freq='h')
    features = FeatureCache(train_times,future)
    zero = np.zeros(len(future))
    active = {b:zero.tolist() for b in ids}
    reactive = {b:zero.tolist() for b in ids}
    sector_predictions,info = {},{}
    for sector in SECTORS:
        members = sorted(b for b,s in mapping.items() if s==sector and b in train.load_p_kw)
        target = np.sum([train.load_p_kw[b] for b in members],axis=0) if members else np.zeros(len(train_times))
        family,setting = LOAD_SETTINGS[sector]
        if not target.any():
            prediction, timing = zero.copy(), {'fit_skipped':'empty or all-zero sector'}
        else:
            prediction,timing = fit_predict(family,target,features,setting)
        sector_predictions[sector] = prediction
        if members:
            p,q = _allocate_sector(train,members,prediction,future)
            active.update(p); reactive.update(q)
        info[sector] = {'model':family+'__daily_weekly_monthly_yearly','settings':setting,'members':members,**timing}
    if not np.allclose(np.sum(list(active.values()),axis=0),np.sum(list(sector_predictions.values()),axis=0),atol=1e-8,rtol=1e-12):
        raise RuntimeError("Bus and sector forecasts do not reconstruct feeder demand")
    ratings = pv_ratings
    if ratings is None:
        ratings = {}
        for unit in network.pv_units:
            ratings[unit.bus_id] = ratings.get(unit.bus_id,0)+unit.p_rated_kw
    if set(ratings)-ids or any(not np.isfinite(r) or r<0 for r in ratings.values()):
        raise ValueError("Invalid PV installation bus/nameplate")
    cf = zero.copy()
    if sum(ratings.values())>0:
        if pv_reference is None:
            raise ValueError("Installed PV requires a validated common historical modeled-power reference and site/clock")
        cf,info['pv'] = _pv_predict(pv_reference,train_times,future,features)
    else:
        info['pv'] = {'fit_skipped':'zero installed PV capacity'}
    pv = {b:(cf*ratings.get(b,0.)).tolist() for b in ids}
    profiles = ProfileData.from_arrays(future,active,reactive,pv,{b:zero.tolist() for b in ids})
    libraries = {}
    for name in ('numpy','pandas','scikit-learn','xgboost','lightgbm'):
        try: libraries[name]=version(name)
        except PackageNotFoundError: libraries[name]='unavailable'
    info.update(training_start=str(train_times[0]),training_end=str(train_times[-1]),training_hours=len(train_times),
        forecast_start=str(future[0]),forecast_end=str(future[-1]),versions=libraries,
        allocation='training-only per-sector hour-of-day P shares; overall/equal fallback; bus historical Q/P',
        fixed_load_settings=True, conservation_atol_kw=1e-8, final_pv_ratings=ratings)
    return ForecastReport(profiles,{},info,train_times[-1],len(future),sector_predictions,cf)
