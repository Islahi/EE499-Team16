"""StatsForecast model adapters, known-bad seasonal settings, numeric guardrails."""
import numpy as np
import c2_config as C

def unsupported_reason(model, seasons, n_train):
    if len(seasons)>1 and model not in C.MULTI_SEASON_MODELS:
        return 'This model only supports one seasonal cycle'
    if max(seasons)>n_train:
        return 'Training shorter than longest seasonal period'
    if model=='AutoARIMA' and max(seasons)>168:
        return 'AVOID_MEMORY_ERROR: seasonal ARIMA with 720+ lag exceeded memory in prior benchmark'
    if model in ('AutoETS','HoltWinters') and max(seasons)>168:
        return 'AVOID_FIT_FAILURE: monthly ETS/HoltWinters failed on all seven prior cases'
    if model in ('AutoCES','AutoTheta') and max(seasons)>=8760:
        return 'Annual single-season period requires prohibitively large seasonal state'
    if model=='MSTL' and len(seasons)>1 and (max(seasons)*2>n_train):
        return 'MSTL decomposition requires at least two complete cycles'
    if model=='MSTL' and max(seasons)>=8760 and len(seasons)==1:
        return 'MSTL annual LOESS decomposition too memory-intensive on long hourly history'
    return None

def make_model(model, periods):
    from statsforecast import models as m
    period=periods[0]
    common={'alias':'C2Forecast'}
    if model=='AutoARIMA':return m.AutoARIMA(season_length=period,max_p=C.AUTOARIMA_MAX_P,
        max_q=C.AUTOARIMA_MAX_Q,max_P=C.AUTOARIMA_MAX_SEASONAL_P,max_Q=C.AUTOARIMA_MAX_SEASONAL_Q,
        max_order=4,nmodels=C.AUTOARIMA_NMODELS,stepwise=True,approximation=True,**common)
    if model=='AutoETS':return m.AutoETS(season_length=period,**common)
    if model=='AutoCES':return m.AutoCES(season_length=period,**common)
    if model=='AutoTheta':return m.AutoTheta(season_length=period,**common)
    if model=='MSTL':return m.MSTL(season_length=list(periods),
        trend_forecaster=m.AutoETS(season_length=1,model='ZZN'),**common)
    if model=='AutoTBATS':return m.AutoTBATS(season_length=list(periods),
        use_boxcox=C.TBATS_USE_BOXCOX,use_arma_errors=C.TBATS_USE_ARMA_ERRORS,**common)
    if model=='AutoMFLES':return m.AutoMFLES(test_size=C.AUTOMFLES_VALIDATION_HOURS,
        season_length=list(periods),n_windows=C.AUTOMFLES_N_WINDOWS,metric='mae',**common)
    if model=='SeasonalNaive':return m.SeasonalNaive(season_length=period,**common)
    if model=='HoltWinters':return m.HoltWinters(season_length=period,error_type='A',**common)
    raise ValueError(f'Unknown model: {model}')

def predict(model_name, periods, train, horizon):
    """Scale training power (mean≈1) to improve numerical conditioning; reverse on output."""
    from time import perf_counter
    y=np.asarray(train,float)
    scale=max(float(np.mean(np.abs(y))),1e-6) if C.NORMALIZE_INPUTS else 1.0
    if model_name=='SeasonalNaive':
        # Identical last-cycle repetition, without requiring StatsForecast for the reference.
        t=perf_counter()
        k=periods[0]
        if len(y)<k:raise ValueError('SeasonalNaive needs at least one full past cycle')
        raw=np.resize(y[-k:],horizon)
        seconds=perf_counter()-t
        return raw,0.0,seconds,scale
    model=make_model(model_name,periods)
    t=perf_counter()
    model.fit(y/scale)
    fit_s=perf_counter()-t
    t=perf_counter()
    output=model.predict(h=horizon)
    pred_s=perf_counter()-t
    raw=np.asarray(output['mean'],float).reshape(-1)*scale
    if len(raw)!=horizon or not np.isfinite(raw).all():
        raise FloatingPointError('Nonfinite prediction or wrong number of forecast hours')
    peak=float(np.max(np.abs(y)))
    if peak>0 and np.max(np.abs(raw))>peak*C.UNREALISTIC_MAX_MULTIPLE_OF_TRAIN_PEAK:
        raise FloatingPointError('Raw prediction exceeded 100 times training peak (numerically unstable)')
    return raw,fit_s,pred_s,scale
