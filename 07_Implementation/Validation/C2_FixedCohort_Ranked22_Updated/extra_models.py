"""Calendar-aware model alternatives with train-only chronological tuning.

No target from the unseen forecast year is used in feature construction or fitting.
All models return the 8760-hour holdout prediction and a fitted object if serializable.
Neural models use causal 168-hour blocks chained using only their own predictions.
Optional packages imported only for the associated model.
"""
from __future__ import annotations
from time import perf_counter
import warnings
import numpy as np
import pandas as pd
import cohort_config as C
from cohort_cases import TRAIN,TEST


def Fourier_basis(times,periods,richness=1):
    t=(pd.DatetimeIndex(times)-pd.Timestamp('2017-01-01')).total_seconds().to_numpy()/3600.0
    # More basis functions for long annual cycle; bounded to keep regression well-conditioned.
    cols=[np.ones(len(t),dtype=float),t/8760.0]
    for p in periods:
        n=min(12,max(1,round({24:3,168:3,720:2,8760:6}.get(p,3)*richness)))
        if p==8760: p=365.2425*24   # calendar-year approx rather than leap-hour drift
        if p==720: p=365.2425*24/12  # average solar-month; label remains approximate monthly
        for k in range(1,n+1):
            angle=2*np.pi*t*k/p
            cols.extend((np.sin(angle),np.cos(angle)))
    return np.column_stack(cols)


def calendar_features(times, periods, richness=1.0):
    """Only include seasonal features explicitly requested by this configuration.

    Ordinary trend is always included. Calendar predictors (not future demand or
    weather) are known for the entire forecast year. Previous versions added
    all seasonalities even when a single period was requested, making the
    individual seasonality comparisons invalid.
    """
    ix = pd.DatetimeIndex(times)
    periods = tuple(periods)
    base = Fourier_basis(ix, periods, richness=richness)
    cols = [base.astype('float32')]
    h = ix.hour.to_numpy()
    dow = ix.dayofweek.to_numpy()
    doy = ix.dayofyear.to_numpy()
    if 24 in periods:
        cols.append(np.column_stack([(h == j).astype('float32') for j in range(1, 24)]))
    if 168 in periods:
        weekend = (dow >= 5)
        cols.append(np.column_stack([(dow == j).astype('float32') for j in range(1, 7)]))
        cols.append(weekend.astype('float32')[:, None])
        if 24 in periods:
            cols.append(np.column_stack([((h == j) & weekend).astype('float32')
                                         for j in range(1, 24)]))
    if 8760 in periods:
        months = ix.month.to_numpy()
        cols.append(np.column_stack([(months == m).astype('float32') for m in range(1, 12)]))
        if 24 in periods:
            annual_phase = 2 * np.pi * (doy - 1) / 365.2425
            daily_phase = 2 * np.pi * h / 24
            cols.append(np.column_stack((
                np.sin(annual_phase) * np.sin(daily_phase),
                np.cos(annual_phase) * np.cos(daily_phase),
                np.sin(annual_phase) * np.cos(daily_phase),
            )).astype('float32'))
    return np.column_stack(cols).astype('float32')


def optimize_regression(name,y,periods,train_dates=TRAIN,forecast_dates=TEST):
    from sklearn.linear_model import Ridge,LinearRegression
    # Held-out final 120 days OF TRAINING ONLY.
    split=len(y)-C.VALIDATION_DAYS*24
    if split<24*180:raise ValueError('Not enough training data for chronological validation')
    designs=[]
    for richness in (0.5,1.0,1.5):
        X=Fourier_basis(train_dates,periods,richness) if name=='FourierOLS' else calendar_features(train_dates,periods,richness)
        for alpha in ([0.] if name=='FourierOLS' else [0.1,10.,1000.]):
            designs.append((richness,alpha,X))
    best=None
    for richness,alpha,X in designs:
        model=LinearRegression() if alpha==0 else Ridge(alpha=alpha)
        model.fit(X[:split],y[:split]);pred=model.predict(X[split:])
        mae=float(np.mean(abs(y[split:]-pred)))
        if best is None or mae<best[0]:best=(mae,richness,alpha)
    mae,richness,alpha=best
    X_train=Fourier_basis(train_dates,periods,richness) if name=='FourierOLS' else calendar_features(train_dates,periods,richness)
    X_future=Fourier_basis(forecast_dates,periods,richness) if name=='FourierOLS' else calendar_features(forecast_dates,periods,richness)
    model=LinearRegression() if alpha==0 else Ridge(alpha=alpha)
    model.fit(X_train,y)
    return np.asarray(model.predict(X_future),float),model,{
        'validation_mae_scaled':mae,'fourier_richness':richness,'alpha':alpha,
        'validation_days':C.VALIDATION_DAYS,'uses_future_observations':False}


def optimize_boosting(name,y,periods):
    x=calendar_features(TRAIN,periods)
    x_next=calendar_features(TEST,periods)
    split=len(y)-C.VALIDATION_DAYS*24
    if name=='LightGBM':
        from lightgbm import LGBMRegressor
        options=[{'n_estimators':300,'learning_rate':.05,'num_leaves':15},
                 {'n_estimators':500,'learning_rate':.03,'num_leaves':31},
                 {'n_estimators':700,'learning_rate':.03,'num_leaves':63}]
        def make(q):return LGBMRegressor(random_state=16,n_jobs=2,verbosity=-1,**q)
    else:
        from xgboost import XGBRegressor
        options=[{'n_estimators':300,'learning_rate':.05,'max_depth':3},
                 {'n_estimators':500,'learning_rate':.03,'max_depth':5},
                 {'n_estimators':700,'learning_rate':.03,'max_depth':6}]
        def make(q):return XGBRegressor(random_state=16,n_jobs=2,tree_method='hist',objective='reg:squarederror',**q)
    best=None
    for q in options:
        fit=make(q);fit.fit(x[:split],y[:split]);p=fit.predict(x[split:]);mae=float(np.mean(abs(y[split:]-p)))
        if best is None or mae<best[0]:best=(mae,q)
    mae,params=best
    final=make(params);final.fit(x,y)
    return np.asarray(final.predict(x_next),float),final,{
        'validation_mae_scaled':mae,'selected_hyperparameters':params,
        'validation_days':C.VALIDATION_DAYS,'future_predictors':'known calendar variables only'}


def optimize_prophet(y,periods):
    from prophet import Prophet
    ix=TRAIN
    split=len(y)-C.VALIDATION_DAYS*24
    params=[{'changepoint_prior_scale':0.01,'seasonality_prior_scale':2.0},
            {'changepoint_prior_scale':0.05,'seasonality_prior_scale':5.0}]
    def make(params):
        model=Prophet(yearly_seasonality=False,weekly_seasonality=False,daily_seasonality=False,
                      uncertainty_samples=0,**params)
        for p in periods:
            # Months approximated by ~30.44 days; year by 365.2425 days.
            days={24:1.0,168:7.0,720:365.2425/12,8760:365.2425}[p]
            order={24:5,168:4,720:3,8760:10}[p]
            model.add_seasonality(name=f'cycle_{p}',period=days,fourier_order=order)
        return model
    df=pd.DataFrame({'ds':ix,'y':y})
    val=df.iloc[split:].copy()
    best=None
    for cfg in params:
        m=make(cfg).fit(df.iloc[:split]);pred=m.predict(val[['ds']])['yhat'].to_numpy()
        mae=float(np.mean(abs(pred-val.y.to_numpy())))
        if best is None or mae<best[0]:best=(mae,cfg)
    mae,cfg=best
    m=make(cfg).fit(df)
    pred=m.predict(pd.DataFrame({'ds':TEST}))['yhat'].to_numpy()
    return np.asarray(pred,float),m,{'validation_mae_scaled':mae,'selected_hyperparameters':cfg,
                                 'validation_days':C.VALIDATION_DAYS}


def optimize_sarimax(y,periods):
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    # Restrict very long seasonal states: Fourier terms represent the cycles in exog.
    X=Fourier_basis(TRAIN,periods,richness=.5)[:,2:]
    X_future=Fourier_basis(TEST,periods,richness=.5)[:,2:]
    split=len(y)-C.VALIDATION_DAYS*24
    orders=[(0,0,0),(1,0,0),(1,0,1)]
    best=None
    for order in orders:
        try:
            model=SARIMAX(y[:split],exog=X[:split],order=order,trend='c',
                          enforce_stationarity=False,enforce_invertibility=False)
            res=model.fit(disp=False,maxiter=50)
            pr=res.get_forecast(steps=len(y)-split,exog=X[split:]).predicted_mean
            err=float(np.mean(abs(y[split:]-np.asarray(pr))))
            if np.isfinite(err) and (best is None or err<best[0]):best=(err,order)
        except (ValueError,np.linalg.LinAlgError):continue
    if best is None:raise RuntimeError('No SARIMAX order converged')
    err,order=best
    final=SARIMAX(y,exog=X,order=order,trend='c',
                 enforce_stationarity=False,enforce_invertibility=False).fit(disp=False,maxiter=75)
    pred=final.get_forecast(steps=len(TEST),exog=X_future).predicted_mean
    return np.asarray(pred,float),final,{'validation_mae_scaled':err,'selected_order':order,
                                        'validation_days':C.VALIDATION_DAYS}


def run_neural(name, y, periods):
    """Neural-only 2021 recursive forecast; train data never includes 2021 targets."""
    from neural_recursive_2021 import run_neural_recursive
    return run_neural_recursive(name, y, periods, TRAIN, TEST)


def execute(name,periods,training,save_fitted=False):
    from cohort_models import make_model
    raw=np.asarray(training,float)
    scale=max(float(np.mean(abs(raw))),1e-6)
    y=raw/scale
    fit_t=perf_counter()
    if name in ('FourierOLS','CalendarRidge'):
        pred,model,settings=optimize_regression(name,y,periods)
    elif name in ('LightGBM','XGBoost'):
        pred,model,settings=optimize_boosting(name,y,periods)
    elif name=='Prophet':pred,model,settings=optimize_prophet(y,periods)
    elif name=='FourierSARIMAX':pred,model,settings=optimize_sarimax(y,periods)
    elif name in ('AutoNHITS','AutoNBEATSx'):pred,model,settings=run_neural(name,y,periods)
    else:raise ValueError(name)
    elapsed=perf_counter()-fit_t
    result=pred*scale
    if len(result)!=len(TEST) or not np.isfinite(result).all():
        raise FloatingPointError('Invalid or incomplete annual forecast')
    if max(abs(result))>max(abs(raw))*C.UNREALISTIC_MAX_MULTIPLE_OF_TRAIN_PEAK:
        raise FloatingPointError('Numerical instability: unrealistic prediction scale')
    return result,elapsed,0.,scale,model,settings
