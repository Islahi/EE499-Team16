"""C2: One full-year ahead benchmark, trained on all eligible years since 2017.

Run after prepare_goiener_v71.py and optionally download_nasa_full_history.py.
Nine StatsForecast models, daily/weekly/monthly/yearly seasonalities, and
MAE/RMSE/WAPE/MASE/Bias per category. Each model runs in an isolated process,
so a failed/OOM model does not terminate the entire comparison.

Reference repo: https://github.com/Islahi/EE499-Team16.git
"""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd
import c2_benchmark_settings as S
from c2_benchmark_core import (scoring, postprocess, SeriesCase,
                               unsupported_reason)

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'C2_full_history_data'
OUT=ROOT/'C2_full_history_results'


def parser_args():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--models',nargs='*',default=list(S.MODELS),choices=S.MODELS)
    p.add_argument('--seasonalities',nargs='*',default=list(S.SEASONALITIES),choices=S.SEASONALITIES)
    p.add_argument('--categories',nargs='*',default=['load','pv'],choices=['load','pv'])
    p.add_argument('--test-year',type=int,default=None,help='Default: latest full source year')
    p.add_argument('--train-start-year',type=int,default=2017)
    p.add_argument('--timeout-seconds',type=int,default=10800,help='Per-model deadline (default 3 hours)')
    p.add_argument('--unsafe-long-single-season',action='store_true',
                   help='Attempt high-memory ARIMA/ETS/etc monthly and yearly configurations')
    p.add_argument('--max-jobs',type=int,default=None)
    p.add_argument('--retry',action='store_true')
    p.add_argument('--load-only',action='store_true')
    p.add_argument('--list-jobs',action='store_true')
    p.add_argument('--output',type=Path,default=OUT)
    return p.parse_args()


def read_case(path,category,year,first_year):
    data=pd.read_csv(path,parse_dates=['timestamp'])
    cols={'timestamp','p_kw'}
    if not cols.issubset(data.columns):raise ValueError(f'{path} missing columns {cols}')
    data=data.sort_values('timestamp')
    if data.timestamp.duplicated().any():raise ValueError(f'{path}: duplicate timestamps')
    clock=pd.date_range(f'{first_year}-01-01',f'{year}-12-31 23:00',freq='h')
    data=data.set_index('timestamp').reindex(clock)
    if data.p_kw.isna().any():
        raise ValueError(f'{path.name}: {data.p_kw.isna().sum()} missing hours in {first_year}..{year}')
    values=data.p_kw.to_numpy(float)
    if not np.all(np.isfinite(values)) or np.any(values<-1e-9):
        raise ValueError(f'{path.name}: nonfinite/negative hourly values')
    if 'filled_hour' not in data.columns: data['filled_hour']=0
    filled=data.filled_hour.fillna(1).to_numpy(bool)
    offset=len(pd.date_range(f'{first_year}-01-01',f'{year-1}-12-31 23:00',freq='h'))
    if offset<=168 or len(values)-offset not in (8760,8784):
        raise ValueError(f'Expected one calendar test year; got train={offset}, test={len(values)-offset}')
    ix=pd.DatetimeIndex(clock[offset:])
    label='GoiEner_FullHistory_Load' if category=='load' else path.stem.replace('nasa_pv_','PV_')
    lat=lon=None
    if category=='pv':lat,lon=float(data.site_lat.iloc[0]),float(data.site_lon.iloc[0])
    return SeriesCase(label,category,'kW',values[:offset],values[offset:],str(path),lat,lon),ix,~filled[offset:]


def score_case(case,actual,pred,valid,clock):
    actual,pred=np.asarray(actual),np.asarray(pred)
    if not np.any(valid):raise ValueError('No valid test observations for scoring')
    d=scoring(actual[valid],pred[valid],case.y_train)
    frame=pd.DataFrame({'timestamp':clock,'actual_kw':actual,'forecast_kw':pred,'valid_actual':valid})
    frame['month']=frame.timestamp.dt.strftime('%Y-%m')
    rows=[]
    for month,df in frame.groupby('month',sort=True):
        df=df.loc[df.valid_actual]
        if df.empty:continue
        metrics=scoring(df.actual_kw,df.forecast_kw,case.y_train)
        actual_energy=float(df.actual_kw.sum()); forecast_energy=float(df.forecast_kw.sum())
        rows.append({'month':month,'valid_hours':len(df),**metrics,
                     'actual_energy_kwh':actual_energy,'forecast_energy_kwh':forecast_energy,
                     'energy_bias_kwh':actual_energy-forecast_energy})
    monthly=pd.DataFrame(rows)
    if len(monthly):
        d['monthly_energy_abs_percent_error']=float(np.mean(
            100*np.abs(monthly.actual_energy_kwh-monthly.forecast_energy_kwh)/
            np.maximum(monthly.actual_energy_kwh,1e-9)))
    d['peak_demand_error_kw']=float(abs(np.max(actual[valid])-np.max(pred[valid])))
    d['evaluated_hours']=int(np.sum(valid))
    d['excluded_actual_filled_hours']=int(np.sum(~valid))
    return d,monthly,frame


def safe_name(name):return name.replace('/','_').replace('\\','_')


def build_summary(out):
    rows=[]
    for p in out.glob('*/*/*/run_metrics.json'):
        try:rows.append(json.loads(p.read_text(encoding='utf-8')))
        except Exception:continue
    if not rows:return
    tab=pd.DataFrame(rows)
    tab.to_csv(out/'all_model_scores.csv',index=False)
    for category in ('load','pv'):
        group=tab[tab.category==category].copy()
        group.to_csv(out/f'{category}_model_scores.csv',index=False)
        if len(group):
            ok=group.loc[group.status=='OK'].copy()
            if len(ok):
                ok.sort_values('rmse_kw',inplace=True)
                summary=ok.groupby('dataset',sort=True).head(10)
                summary.to_csv(out/f'{category}_top_models.csv',index=False)
                print(f'\nTop {category} results (by RMSE):',flush=True)
                print(summary[['dataset','model','seasonality','rmse_kw','mae_kw','wape_percent','total_model_seconds']].to_string(index=False),flush=True)


def main():
    args=parser_args()
    report_file=DATA/'goiener_preprocessing_report.json'
    if not report_file.is_file():
        raise SystemExit('Run: python prepare_goiener_v71.py (after downloading the GoiEner .zst file)')
    report=json.loads(report_file.read_text(encoding='utf-8'))
    test_year=args.test_year or int(report['end_year'])
    if args.train_start_year>=test_year:raise ValueError('Training start must precede test year')
    cases=[]; missing_solar=[]
    if 'load' in args.categories:
        cases.append(read_case(DATA/'goiener_hourly_load.csv','load',test_year,args.train_start_year))
    if 'pv' in args.categories and not args.load_only:
        # Five site files are optional, generated from NASA (not GoiEner).
        for p in sorted(DATA.glob('nasa_pv_*.csv')):
            cases.append(read_case(p,'pv',test_year,args.train_start_year))
        if not any(c.category=='pv' for c,_,_ in cases):
            print('PV not ready: run python download_nasa_full_history.py '
                  'for matching NASA POWER site data. Load benchmarking can run now.',flush=True)
    if not cases:raise SystemExit('No datasets to benchmark')
    args.output.mkdir(parents=True,exist_ok=True)
    meta={'repo':'https://github.com/Islahi/EE499-Team16.git','test_year':test_year,
          'test_hours':len(cases[0][1]),'train_start_year':args.train_start_year,
          'goiener_source':'https://zenodo.org/records/22313409',
          'load_panel':report,'pv':'NASA POWER modelled PV, not GoiEner metered PV',
          'timebases':'GoiEner annual matrix ISO hourly clock; NASA solar UTC, compared separately',
          'model_fit_isolation':'Each model runs in a separate Python subprocess',
          'generated_utc':datetime.now(timezone.utc).isoformat(),
          'python_version':platform.python_version()}
    (args.output/'experiment_settings.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    for case,clock,valid in cases:
        print(f'{case.category}/{case.dataset}: train={len(case.y_train):,} h; '
              f'test={len(clock):,} h; excluded actual filled hours={sum(~valid)}',flush=True)
    jobs=0
    study_base={k:report.get(k) for k in ('source_size_bytes','source_mtime_ns','start_year',
                   'end_year','population','selected_meter_count','max_imputed_fraction','hours')}
    study_base.update({'test_year':test_year,'train_start_year':args.train_start_year})
    for case,clock,valid in cases:
        source_path=Path(case.origin)
        stat=source_path.stat()
        signature={**study_base,'case':case.dataset,'input_size':stat.st_size,
                   'input_mtime_ns':stat.st_mtime_ns}
        study_id=hashlib.sha256(json.dumps(signature,sort_keys=True).encode('utf8')).hexdigest()[:16]
        case_path=args.output/case.category/safe_name(case.dataset)
        case_path.mkdir(parents=True,exist_ok=True)
        train_file=case_path/'training.npy'
        np.save(train_file,case.y_train)
        for season in args.seasonalities:
            periods=S.SEASONALITIES[season]
            for model_name in args.models:
                folder=case_path/f'{model_name}__{season}'
                result_file=folder/'run_metrics.json'
                if result_file.is_file() and not args.retry:
                    try:
                        prior=json.loads(result_file.read_text())
                        if prior.get('status')=='OK' and prior.get('study_id')==study_id:
                            print(f'[RESUME] {case.dataset} {model_name} {season}',flush=True);continue
                    except Exception:pass
                reason=unsupported_reason(model_name,periods,len(case.y_train),
                                          S.TRY_INSUFFICIENT_YEARLY_MODELS)
                if max(periods)>168 and len(periods)==1 and model_name in (
                    'AutoARIMA','AutoETS','AutoCES','AutoTheta','HoltWinters'
                ) and not args.unsafe_long_single_season:
                    reason='Memory-risk long single season; use --unsafe-long-single-season to force'
                # SeasonalNaive and long periods are cheap, and multiple seasons only supported by MSTL/TBATS/MFLES.
                if reason:
                    entry={'category':case.category,'dataset':case.dataset,'model':model_name,
                           'seasonality':season,'status':'SKIPPED_UNSUPPORTED','reason':reason,
                           'study_id':study_id}
                    if not args.list_jobs:
                        folder.mkdir(parents=True,exist_ok=True)
                        result_file.write_text(json.dumps(entry,indent=2))
                    print(f'[SKIP] {case.dataset} {model_name} {season}: {reason}',flush=True)
                    continue
                jobs+=1
                if args.list_jobs:
                    print(f'[PLAN] {case.dataset} {model_name} {season}',flush=True)
                    continue
                if args.max_jobs is not None and jobs>args.max_jobs:
                    build_summary(args.output)
                    print('Job cap reached; restart without --max-jobs to continue',flush=True)
                    return
                folder.mkdir(parents=True,exist_ok=True)
                spec={'model':model_name,'periods':list(periods),'forecast_hours':len(clock),
                      'training_file':str(train_file),'output_file':str(folder/'raw_forecast.npy'),
                      'status_file':str(folder/'worker_result.json')}
                spec_file=folder/'worker_config.json'
                spec_file.write_text(json.dumps(spec,indent=2),encoding='utf-8')
                print(f'[{jobs:03d}] {case.category}/{case.dataset}: {model_name} [{season}]',flush=True)
                started=perf_counter()
                try:
                    r=subprocess.run([sys.executable,str(ROOT/'c2_full_history_worker.py'),str(spec_file)],
                                     cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                     encoding='utf-8',errors='replace',timeout=args.timeout_seconds)
                    (folder/'worker_console.txt').write_text('STDOUT:\n'+r.stdout+'\nSTDERR:\n'+r.stderr,
                                                             encoding='utf-8')
                    state_file=folder/'worker_result.json'
                    if not state_file.is_file():raise RuntimeError('Worker terminated without result; see worker_console.txt')
                    state=json.loads(state_file.read_text(encoding='utf8'))
                    if state['status']!='OK':raise RuntimeError(state.get('reason','worker failed'))
                    raw=np.load(folder/'raw_forecast.npy')
                    # Do not use old C2 fixed 2019-2020 clock: the new test year is dynamic.
                    corrected=np.maximum(raw.astype(float),0)
                    corrections={'negative_values_clipped':int(np.count_nonzero(raw<0)),
                                 'pv_values_above_rating_clipped':0,
                                 'nighttime_nonzero_forecasts_corrected':0}
                    if case.category=='pv':
                        from c2_benchmark_core import daylight_mask_utc
                        corrections['pv_values_above_rating_clipped']=int(np.count_nonzero(corrected>S.PV_RATED_KW))
                        corrected=np.minimum(corrected,S.PV_RATED_KW)
                        if S.FORCE_NIGHT_ZERO:
                            night=~daylight_mask_utc(clock,case.site_lat,case.site_lon)
                            corrections['nighttime_nonzero_forecasts_corrected']=int(np.count_nonzero((corrected>0)&night))
                            corrected[night]=0
                    metrics,months,hourly=score_case(case,case.y_test,corrected,valid,clock)
                    hourly.to_csv(folder/'hourly_comparison.csv',index=False)
                    months.to_csv(folder/'monthly_metrics.csv',index=False)
                    entry={'status':'OK','category':case.category,'dataset':case.dataset,
                           'model':model_name,'seasonality':season,'seasonal_period_hours':list(periods),
                           'study_id':study_id,
                           **metrics,**corrections,
                           'fit_seconds':float(state['fit_seconds']),
                           'forecast_seconds':float(state['forecast_seconds']),
                           'total_model_seconds':float(state['fit_seconds']+state['forecast_seconds']),
                           'job_wall_seconds':perf_counter()-started,
                           'warning_count':state.get('warning_count',0),
                           'warning_examples':state.get('warning_examples',[]),
                           'train_hours':len(case.y_train),'forecast_hours':len(clock)}
                    result_file.write_text(json.dumps(entry,indent=2),encoding='utf-8')
                    print(f' -> RMSE={entry["rmse_kw"]:.2f} kW; WAPE={entry["wape_percent"]:.2f}% '
                          f'| fit={entry["fit_seconds"]:.2f}s forecast={entry["forecast_seconds"]:.2f}s',flush=True)
                except Exception as e:
                    entry={'status':'FAILED','category':case.category,'dataset':case.dataset,
                           'model':model_name,'seasonality':season,'reason':str(e),'study_id':study_id,
                           'job_wall_seconds':perf_counter()-started}
                    result_file.write_text(json.dumps(entry,indent=2),encoding='utf-8')
                    print(f' !! FAILED: {e}',flush=True)
                build_summary(args.output)
    build_summary(args.output)
    print('Done; results at',args.output,flush=True)

if __name__=='__main__':main()
