"""Internal process-isolated worker. Do not run directly unless debugging."""
import argparse,json,time,traceback,warnings,sys
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
import cohort_config as C
from cohort_cases import TEST

def score(actual,forecast,train):
    d=np.asarray(actual)-np.asarray(forecast);q=np.asarray(actual);p=np.asarray(forecast)
    den=np.mean(np.abs(train[168:]-train[:-168])) if len(train)>168 else 0
    return {'rmse':float(np.sqrt(np.mean(d*d))),'mae':float(np.mean(abs(d))),
        'wape_percent':float(100*np.sum(abs(d))/np.sum(abs(q))) if np.sum(abs(q))>0 else None,
        'mase_weekly':float(np.mean(abs(d))/den) if den else None,
        'bias_actual_minus_forecast':float(np.mean(d)),
        'smape_percent':float(np.mean(200*abs(d)/np.maximum(abs(q)+abs(p),1e-8))),
        'annual_energy_error_percent':float(100*abs(np.sum(d))/max(np.sum(abs(q)),1e-8)),
        'peak_error_kw':float(abs(np.max(q)-np.max(p)))}

def baseline(name,season,train):
    if name=='Naive':return np.full(len(TEST),train[-1]),{'type':'last_observation'}
    if name=='YearAgoCalendarNaive':
        dates=pd.date_range(TEST[0]-pd.DateOffset(years=1),periods=len(TEST),freq='h')
        prior_dates=pd.DatetimeIndex([t-pd.DateOffset(years=1) for t in TEST])
        prev=pd.Series(train,index=pd.date_range('2017-06-01 00:00:00',periods=len(train),freq='h'))
        forecast=prev.reindex(prior_dates).to_numpy(dtype=float)
        if not np.isfinite(forecast).all():raise ValueError('Prior calendar-year timestamps unavailable')
        return forecast,{'type':'same_calendar_date_previous_year','leap_year_handling':'match by month/day/hour'}
    raise ValueError(name)

def physical(pred,case):
    pred=np.asarray(pred,float)
    corrected={'negative_forecast_values':int((pred<0).sum())}
    pred=np.maximum(pred,0)
    if case['category']=='pv':
        # Preserve same solar-cap calculation for comparison: crop only to known observed PV nameplate
        maxval=case.get('cap_kw')
        if maxval is not None:
            corrected['above_pv_cap']=int((pred>maxval).sum());pred=np.minimum(pred,maxval)
        # Not invent UTC for GoiEner. PV timestamps explicitly NASA UTC.
        if case.get('lat') is not None and case.get('lon') is not None:
            from math import radians
            ix=TEST;d=ix.dayofyear.to_numpy(float)
            hour=ix.hour.to_numpy(float)+.5
            ndays=np.where(ix.is_leap_year,366.,365.)
            gamma=2*np.pi/ndays*(d-1+(hour-12)/24)
            eqtime=229.18*(.000075+.001868*np.cos(gamma)-.032077*np.sin(gamma)-.014615*np.cos(2*gamma)-.040849*np.sin(2*gamma))
            decl=.006918-.399912*np.cos(gamma)+.070257*np.sin(gamma)-.006758*np.cos(2*gamma)+.000907*np.sin(2*gamma)-.002697*np.cos(3*gamma)+.00148*np.sin(3*gamma)
            angle=np.radians((hour*60+eqtime+4*float(case['lon']))/4-180)
            daylight=(np.sin(radians(float(case['lat'])))*np.sin(decl)+np.cos(radians(float(case['lat'])))*np.cos(decl)*np.cos(angle))>0
            corrected['nighttime_predictions_set_zero']=int(((pred>0)&~daylight).sum())
            pred[~daylight]=0
    return pred,corrected

def compact_fitted_state(model):
    """Small audit-friendly selected-fit state; exclude long fitted vectors/matrices."""
    if model is None:return {}
    state=getattr(model,'model_',None)
    if not isinstance(state,dict):return {'fitted_class':type(model).__name__}
    selected={}
    # Common StatsForecast state variables that can identify fitted model choice.
    interesting=('arma','sigma2','aic','aicc','bic','method','components','model','season_length',
      'damped','mse','m','trend','phi','params','opt_crit','n')
    for key in interesting:
        if key not in state:continue
        value=state[key]
        if isinstance(value,(int,float,str,bool,np.integer,np.floating)):
            if isinstance(value,(float,np.floating)) and not np.isfinite(value):continue
            selected[key]=value.item() if hasattr(value,'item') else value
        elif isinstance(value,(tuple,list,np.ndarray)) and len(value)<=16:
            arr=np.asarray(value)
            if arr.ndim==1 and arr.dtype.kind in 'ibuf' and np.isfinite(arr.astype(float)).all():
                selected[key]=arr.tolist()
            elif arr.ndim==1 and arr.dtype.kind in 'US':selected[key]=arr.astype(str).tolist()
    return {'fitted_class':type(model).__name__,'state_summary':selected,
            'note':'Compact summary only; full trained state requires --save-fitted-models'}

def main():
    p=argparse.ArgumentParser()
    for x in ['case','model','season','out']:p.add_argument('--'+x,required=True)
    p.add_argument('--save-fitted-model',action='store_true')
    p.add_argument('--experiment-version',default=C.EXPERIMENT_VERSION)
    p.add_argument('--dataset-sha256',default='')
    p.add_argument('--source-group',default='')
    a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    metadata=json.loads((C.DATA/'cases.json').read_text())
    case=next(z for z in metadata['cases'] if z['name']==a.case)
    z=np.load(C.DATA/(a.case+'.npz'));train=z['train'];actual=z['actual']
    periods=C.SEASONALITIES[a.season]
    start=time.perf_counter();caught=[]
    record={**{k:case[k] for k in ('name','category','unit')},'dataset':a.case,
            'model':a.model,'seasonality':a.season,'seasonal_periods_hours':list(periods),
            'train_hours':len(train),'test_hours':len(actual),
            'experiment_version':a.experiment_version,
            'dataset_sha256':a.dataset_sha256,
            'source_group':a.source_group,
            'date_train_end':str(TEST[0]-pd.Timedelta(hours=1)),
            'date_forecast_start':str(TEST[0])}
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('default')
            if a.model in ('Naive','YearAgoCalendarNaive'):
                ts=time.perf_counter();raw,params=baseline(a.model,periods,train)
                fit_seconds=0.;predict_seconds=time.perf_counter()-ts
                fitted=None;scale=1.
            elif a.model in C.CLASSIC:
                from cohort_models import predict
                raw,fit_seconds,predict_seconds,scale,fitted,params=predict(a.model,periods,train,len(TEST))
            else:
                from extra_models import execute
                raw,fit_seconds,predict_seconds,scale,fitted,params=execute(a.model,periods,train)
        if len(raw)!=len(TEST) or not np.isfinite(raw).all():raise ValueError('Nonfinite/wrong-length forecast')
        adjusted,changes=physical(raw,case)
        metrics=score(actual,adjusted,train)
        h=pd.DataFrame({'timestamp':TEST,'actual':actual,'forecast':adjusted,
            'actual_minus_forecast':actual-adjusted})
        h.to_csv(out/'hourly_comparison.csv',index=False)
        monthly=[]
        for month,group in h.groupby(h.timestamp.dt.to_period('M')):
            monthly.append({'month':str(month),**score(group.actual.to_numpy(),group.forecast.to_numpy(),train),
               'actual_energy_kwh':float(group.actual.sum()),'predicted_energy_kwh':float(group.forecast.sum())})
        pd.DataFrame(monthly).to_csv(out/'monthly_metrics.csv',index=False)
        record.update(metrics)
        record.update(changes)
        record.update(status='OK_WITH_WARNINGS' if caught else 'OK',
           fit_seconds=fit_seconds,forecast_seconds=predict_seconds,model_seconds=fit_seconds+predict_seconds,
           input_scale_factor=scale)
        record['auto_fit_info']=params
        record['fitted_state_summary']=compact_fitted_state(fitted)
        if a.model in C.EXTRAS+C.NEURAL:
            record['time_split_note']='fit_seconds includes optimization, final fit and prediction; these custom methods do not report prediction time separately.'
        (out/'fitted_configuration.json').write_text(json.dumps({
          'model':a.model,'periods_hours':list(periods),'auto_fit_info':params,
          'fitted_state_summary':compact_fitted_state(fitted),
          'training_hours':len(train),'forecast_hours':len(TEST),
          'important':'Selected settings saved for reproducibility. This JSON is NOT the trained model itself.'},indent=2,default=str),encoding='utf-8')
        if a.save_fitted_model and fitted is not None:
            try:
                import joblib
                joblib.dump(fitted,out/'fitted_model.joblib',compress=3)
                record['fitted_model_file']='fitted_model.joblib'
            except Exception as exc:
                record['fitted_model_save_error']=f'{type(exc).__name__}: {exc}'
        if a.save_fitted_model and fitted is None:record['fitted_model_note']='Baseline has no trainable fitted object'
    except Exception as exc:
        record.update(status='FAILED',reason=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc(limit=12))
    grouped=Counter((w.category.__name__,str(w.message)) for w in caught)
    record['warnings']=[{'type':k[0],'message':k[1],'count':v} for k,v in grouped.most_common(35)]
    record['warning_count']=len(caught)
    record['wall_seconds']=time.perf_counter()-start
    (out/'warnings.json').write_text(json.dumps(record['warnings'],indent=2),encoding='utf-8')
    (out/'run_metrics.json').write_text(json.dumps(record,indent=2,allow_nan=False,default=str),encoding='utf-8')
    print(f"{record['status']} {a.case} {a.model} {a.season} RMSE={record.get('rmse')} in {record['wall_seconds']:.1f}s",flush=True)
    if record['status']=='FAILED':print(record['reason'],flush=True)
if __name__=='__main__':main()
