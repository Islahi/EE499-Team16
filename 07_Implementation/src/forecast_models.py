"""Matched implementation of the attached C2 extra_models.py calendar regressors.

Historical reference: C2_FixedCohort_Ranked22_Updated/extra_models.py.
Tuning is training-only; predictions depend only on deterministic calendar coordinates.
Historical binary dependencies/selected hyperparameters cannot be reconstructed exactly.
"""
from __future__ import annotations
from time import perf_counter
import numpy as np
import pandas as pd

PERIODS=(24,168,720,8760)
SEED=16
VALIDATION_DAYS=120
BOOST_GRID={
 'LightGBM':[
  {'n_estimators':300,'learning_rate':.05,'num_leaves':15},
  {'n_estimators':500,'learning_rate':.03,'num_leaves':31},
  {'n_estimators':700,'learning_rate':.03,'num_leaves':63}],
 'XGBoost':[
  {'n_estimators':300,'learning_rate':.05,'max_depth':3},
  {'n_estimators':500,'learning_rate':.03,'max_depth':5},
  {'n_estimators':700,'learning_rate':.03,'max_depth':6}],
}

def fourier_basis(times, periods, richness=1):
    t=(pd.DatetimeIndex(times)-pd.Timestamp('2017-01-01')).total_seconds().to_numpy()/3600.
    cols=[np.ones(len(t),dtype=float),t/8760.]
    for p in periods:
        n=min(12,max(1,round({24:3,168:3,720:2,8760:6}.get(p,3)*richness)))
        if p==8760:p=365.2425*24
        if p==720:p=365.2425*24/12
        for k in range(1,n+1):
            angle=2*np.pi*t*k/p
            cols.extend((np.sin(angle),np.cos(angle)))
    return np.column_stack(cols)

def calendar_features(times,periods=PERIODS,richness=1.0):
    ix=pd.DatetimeIndex(times); periods=tuple(periods)
    base=fourier_basis(ix,periods,richness)
    cols=[base.astype('float32')]
    h=ix.hour.to_numpy();dow=ix.dayofweek.to_numpy();doy=ix.dayofyear.to_numpy()
    if 24 in periods:
        cols.append(np.column_stack([(h==j).astype('float32') for j in range(1,24)]))
    if 168 in periods:
        weekend=dow>=5
        cols.append(np.column_stack([(dow==j).astype('float32') for j in range(1,7)]))
        cols.append(weekend.astype('float32')[:,None])
        if 24 in periods:
            cols.append(np.column_stack([((h==j)&weekend).astype('float32') for j in range(1,24)]))
    if 8760 in periods:
        months=ix.month.to_numpy()
        cols.append(np.column_stack([(months==m).astype('float32') for m in range(1,12)]))
        if 24 in periods:
            annual_phase=2*np.pi*(doy-1)/365.2425
            daily_phase=2*np.pi*h/24
            cols.append(np.column_stack((np.sin(annual_phase)*np.sin(daily_phase),
                 np.cos(annual_phase)*np.cos(daily_phase),
                 np.sin(annual_phase)*np.cos(daily_phase))).astype('float32'))
    return np.column_stack(cols).astype('float32')

class FeatureCache:
    def __init__(self,train_dates,test_dates):
        self.train_dates=pd.DatetimeIndex(train_dates)
        self.test_dates=pd.DatetimeIndex(test_dates)
        self.cache={}
    def get(self,richness=1.0):
        if richness not in self.cache:
            self.cache[richness]=(calendar_features(self.train_dates,PERIODS,richness),
                                   calendar_features(self.test_dates,PERIODS,richness))
        return self.cache[richness]

def estimator(family,setting):
    if family=='CalendarRidge':
        from sklearn.linear_model import Ridge
        return Ridge(alpha=float(setting['alpha']))
    if family=='XGBoost':
        from xgboost import XGBRegressor
        return XGBRegressor(random_state=SEED,n_jobs=2,tree_method='hist',
            objective='reg:squarederror',**setting['selected_hyperparameters'])
    if family=='LightGBM':
        from lightgbm import LGBMRegressor
        return LGBMRegressor(random_state=SEED,n_jobs=2,verbosity=-1,
            **setting['selected_hyperparameters'])
    raise ValueError(f'Unrecognized family: {family}')

def training_scale(y):
    return max(float(np.mean(np.abs(y))),1e-6)

def training_only_tune(family,train,features):
    """Use identical 120-day MAE tuning rules from supplied C2 extra_models.py.
    Only the first 31,440 training hours are passed; no 2021 observed targets.
    Returns selected settings, all candidates' validation errors, wall seconds.
    """
    t0=perf_counter();train=np.asarray(train,float)
    y=train/training_scale(train)
    split=len(y)-VALIDATION_DAYS*24
    assert split>=24*180
    results=[]
    if family=='CalendarRidge':
        for richness in (0.5,1.0,1.5):
            x,_=features.get(richness)
            for alpha in (.1,10.,1000.):
                setting={'fourier_richness':richness,'alpha':alpha}
                model=estimator(family,setting)
                ts=perf_counter();model.fit(x[:split],y[:split]);p=model.predict(x[split:])
                results.append({**setting,'validation_mae_scaled':float(np.mean(np.abs(y[split:]-p))),
                                'candidate_seconds':perf_counter()-ts})
    else:
        x,_=features.get(1.0)
        for params in BOOST_GRID[family]:
            setting={'selected_hyperparameters':params}
            model=estimator(family,setting)
            ts=perf_counter();model.fit(x[:split],y[:split]);p=model.predict(x[split:])
            results.append({**setting,'validation_mae_scaled':float(np.mean(np.abs(y[split:]-p))),
                            'candidate_seconds':perf_counter()-ts})
    best=min(results,key=lambda x:x['validation_mae_scaled'])
    selected={k:v for k,v in best.items() if k!='candidate_seconds'}
    selected['validation_days']=VALIDATION_DAYS
    selected['selection_target']='representative_bus_training_only'
    return selected,results,perf_counter()-t0

def fit_predict(family,train,features,setting):
    """Independent fresh fit on one target; fixed family settings from training-only tune."""
    ts=perf_counter()
    train=np.asarray(train,float)
    scale=training_scale(train)
    y=train/scale
    x,x_future=features.get(setting.get('fourier_richness',1.0))
    model=estimator(family,setting)
    fit_start=perf_counter();model.fit(x,y);fit_seconds=perf_counter()-fit_start
    pred_start=perf_counter();raw=np.asarray(model.predict(x_future),float);pred_seconds=perf_counter()-pred_start
    pred=raw*scale
    if pred.shape!=(len(features.test_dates),) or not np.isfinite(pred).all():
        raise ValueError('Incorrect or non-finite annual prediction')
    if np.max(np.abs(pred))>100*np.max(np.abs(train)):
        raise ValueError('C2 guardrail: forecast exceeds 100 * training peak')
    negatives=int((pred<0).sum())
    pred=np.maximum(0.,pred)
    return pred,{'fit_seconds':fit_seconds,'forecast_seconds':pred_seconds,
        'total_seconds':perf_counter()-ts,'scale_kw':scale,'negative_raw_values_clipped':negatives,
        'model_class':type(model).__name__}
