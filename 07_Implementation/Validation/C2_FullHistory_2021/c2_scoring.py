"""MAE, RMSE, WAPE, weekly MASE, Bias, physically adjusted PV; per-month diagnostics."""
import numpy as np
import pandas as pd
import c2_config as C
from c2_data import TEST,daylight_utc

def postprocess(raw,case):
    y=np.asarray(raw,dtype=float)
    if len(y)!=len(TEST) or not np.isfinite(y).all():raise ValueError('Nonfinite/wrong-length prediction')
    neg=int((y<0).sum())
    p=np.maximum(y,0)
    capped=night=0
    if case.category=='pv':
        capped=int((p>C.PV_RATED_KW).sum())
        p=np.minimum(p,C.PV_RATED_KW)
        if C.FORCE_NIGHT_ZERO:
            isday=daylight_utc(TEST,case.lat,case.lon)
            night=int(((p>0)&~isday).sum())
            p[~isday]=0
    return p,{'negative_forecasts_corrected':neg,'pv_over_rated_corrected':capped,
            'pv_night_forecasts_corrected':night,'min_raw_forecast':float(np.min(y)),
            'max_raw_forecast':float(np.max(y))}

def scores(actual,forecast,train):
    y=np.asarray(actual,float);p=np.asarray(forecast,float);hist=np.asarray(train,float)
    if len(y)!=len(p) or not np.isfinite(p).all():raise ValueError('Invalid scoring input')
    diff=y-p
    mae=float(np.mean(np.abs(diff)))
    den=float(np.mean(np.abs(hist[168:]-hist[:-168])))
    actsum=float(np.sum(abs(y)))
    return {'mae':mae,'rmse':float(np.sqrt(np.mean(diff*diff))),
        'wape_percent':100*float(np.sum(abs(diff)))/actsum if actsum else None,
        'mase_weekly':mae/den if den else None,
        'bias_actual_minus_forecast':float(np.mean(diff)),
        'smape_percent':float(np.mean(200*np.abs(diff)/np.maximum(np.abs(y)+np.abs(p),1e-8)))}

def save_case(case,raw,outdir):
    outdir.mkdir(parents=True,exist_ok=True)
    pred,cor=postprocess(raw,case)
    metric=scores(case.actual,pred,case.train)
    hourly=pd.DataFrame({'timestamp':TEST,'actual':case.actual,'forecast':pred,
                         'actual_minus_forecast':case.actual-pred})
    hourly.to_csv(outdir/'hourly_comparison.csv',index=False)
    monthly=[]
    for mon,group in hourly.groupby(hourly.timestamp.dt.to_period('M')):
        m=scores(group.actual,group.forecast,case.train)
        monthly.append({'month':str(mon),**m,'actual_kwh':float(group.actual.sum()),
                        'forecast_kwh':float(group.forecast.sum())})
    pd.DataFrame(monthly).to_csv(outdir/'monthly_metrics.csv',index=False)
    metric['mean_actual']=float(np.mean(case.actual))
    metric['mean_forecast']=float(np.mean(pred))
    metric['monthly_energy_error_percent']=float(np.mean([100*abs(m['actual_kwh']-m['forecast_kwh'])/max(m['actual_kwh'],1e-9) for m in monthly]))
    metric['annual_energy_error_percent']=100*abs(float(np.sum(case.actual)-np.sum(pred)))/max(float(np.sum(case.actual)),1e-9)
    metric['peak_error']=float(abs(np.max(case.actual)-np.max(pred)))
    return {**metric,**cor}
