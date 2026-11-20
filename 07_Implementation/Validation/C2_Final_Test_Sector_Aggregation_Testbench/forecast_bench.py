"""EE499 Team 16: A sum-then-forecast vs B forecast-then-sum, T04 feeder.

Run: python forecast_bench.py --recompute
Verify package without model dependencies: python forecast_bench.py --verify-only
The original repository is never written or modified.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
from pathlib import Path
from time import perf_counter
import numpy as np
import pandas as pd

BASE=Path(__file__).resolve().parent
SECTORS=('residential','commercial','manufacturing')
FAMILIES={'residential':'CalendarRidge','commercial':'XGBoost','manufacturing':'LightGBM'}


def json_dump(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,default=lambda o:o.item() if hasattr(o,'item') else str(o),allow_nan=False),encoding='utf-8')

def hashfile(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def get_config():
    return json.loads((BASE/'config.json').read_text(encoding='utf-8'))

def load_data(cfg):
    load=BASE/cfg['input_load_profile'];assignment=BASE/cfg['input_assignments']
    raw=pd.read_csv(load,parse_dates=['timestamp'])
    ass=pd.read_csv(assignment)
    expected=cfg['buses']
    if raw.duplicated(['timestamp','bus_id']).any(): raise ValueError('Duplicate timestamp/bus rows')
    if raw[['p_kw','timestamp','bus_id']].isna().any().any():raise ValueError('Missing network load inputs')
    found={sector:sorted(ass.loc[ass.category==sector,'bus_id'].astype(int).tolist()) for sector in SECTORS}
    for sector in SECTORS:
        if found[sector]!=sorted(expected[sector]):raise ValueError(f'{sector}: unexpected assignments {found[sector]}')
    wide=raw.pivot(index='timestamp',columns='bus_id',values='p_kw').sort_index()
    if list(wide.columns)!=list(range(1,16)):raise ValueError('Missing network bus IDs')
    if wide.isna().any().any():raise ValueError('Incomplete bus-time grid')
    if not wide.index.equals(pd.date_range('2017-06-01',periods=43921,freq='h')):
        raise ValueError('Full source timestamp grid is not exactly 43,921 consecutive hours')
    if not np.array_equal(wide[1].to_numpy(),np.zeros(len(wide))):
        raise ValueError('Bus 1 must be a zero slack load')
    train=wide.loc[cfg['training_start']:cfg['training_end']]
    test=wide.loc[cfg['test_start']:cfg['test_end']]
    if len(train)!=31440 or len(test)!=8760:raise ValueError(f'Expected 31440 training / 8760 holdout hours, got {len(train)}/{len(test)}')
    if not train.index.equals(pd.date_range('2017-06-01',periods=31440,freq='h')):
        raise ValueError('Wrong chronological training grid')
    if not test.index.equals(pd.date_range('2021-01-01',periods=8760,freq='h')):
        raise ValueError('Wrong chronological test grid')
    if (wide.to_numpy()<0).any():raise ValueError('Negative kW input')
    return raw,ass,wide,train,test

def audit(cfg,raw,ass,wide,train,test):
    out=BASE/'results';out.mkdir(exist_ok=True)
    expected=pd.date_range(wide.index[0],wide.index[-1],freq='h')
    def stats(frame,year):
        rows=[]
        for bus in frame.columns:
            v=frame[bus].to_numpy(float)
            mean=float(v.mean());std=float(v.std(ddof=0))
            rows.append({'period':year,'bus_id':int(bus),
                         'category':next((s for s in SECTORS if int(bus) in cfg['buses'][s]),'slack'),
                         'min_kw':float(v.min()),'mean_kw':mean,'max_kw':float(v.max()),
                         'std_kw':std,'coefficient_of_variation':std/mean if mean else np.nan,
                         'hours':len(v),'changes_over_time':bool(np.ptp(v)>0),
                         'energy_kwh':float(v.sum())})
        return pd.DataFrame(rows)
    stats(wide,'complete_43921h').to_csv(out/'per_bus_stats_complete.csv',index=False)
    stats(test,'2021_8760h').to_csv(out/'per_bus_stats_2021.csv',index=False)
    rows=[]
    for period,frame in [('complete_43921h',wide),('2021_8760h',test)]:
        for sector in SECTORS:
            bs=cfg['buses'][sector]
            for i,b1 in enumerate(bs):
                for b2 in bs[i+1:]:
                    a=frame[b1].to_numpy(float);b=frame[b2].to_numpy(float)
                    ratio=float(np.dot(a,b)/np.dot(b,b)) if np.dot(b,b)>0 else float('nan')
                    resid=float(np.max(np.abs(a-ratio*b)))
                    rows.append({'period':period,'sector':sector,'bus_a':b1,'bus_b':b2,
                     'max_abs_difference_kw':float(np.max(np.abs(a-b))),
                     'exact_equality':bool(np.array_equal(a,b)),
                     'best_proportional_factor':ratio,
                     'max_abs_error_after_scaling_kw':resid,
                     'proportional_at_1e_10_rel':bool(resid<=1e-10*max(float(np.max(np.abs(a))),1.))})
        rep=pd.DataFrame({s:frame[cfg['buses'][s][0]] for s in SECTORS})
        rep.corr().rename_axis('sector').to_csv(out/('cross_sector_correlation_'+('complete' if period.startswith('complete') else '2021')+'.csv'))
    pair=pd.DataFrame(rows);pair.to_csv(out/'pairwise_within_sector.csv',index=False)
    unique={hashlib.sha256(np.asarray(wide[b].to_numpy(),dtype='<f8').tobytes()).hexdigest() for b in range(2,16)}
    distinct2021={hashlib.sha256(np.asarray(test[b].to_numpy(),dtype='<f8').tobytes()).hexdigest() for b in range(2,16)}
    summary={'timestamp_min':str(wide.index[0]),'timestamp_max':str(wide.index[-1]),
      'total_hours':len(wide),'test_hours':len(test),'training_hours':len(train),
      'timestamp_gaps':len(expected.difference(wide.index)),
      'timestamp_duplicates':int(wide.index.duplicated().sum()),
      'bus_timestamp_duplicates':int(raw.duplicated(['timestamp','bus_id']).sum()),
      'missing_p_kw':int(raw.p_kw.isna().sum()),
      'missing_2021_p_kw':int(test.isna().sum().sum()),
      'bus_ids':[int(b) for b in wide.columns],
      'bus_assignment_count':{s:len(cfg['buses'][s]) for s in SECTORS},
      'slack_bus_1_nonzero_hours':int(np.count_nonzero(wide[1])),
      'loaded_bus_distinct_nonzero_series_full':len(unique),
      'loaded_bus_distinct_nonzero_series_2021':len(distinct2021),
      'all_within_sector_pairs_equal_full':bool(pair.loc[pair.period=='complete_43921h','exact_equality'].all()),
      'all_within_sector_pairs_equal_2021':bool(pair.loc[pair.period=='2021_8760h','exact_equality'].all()),
      'within_sector_pairs_per_period':int(len(pair)/2),
      'source_manifest_normalization':json.loads((BASE/'input/manifest.json').read_text()).get('normalization'),
      'source_manifest_normalization_time_span':'2017-06-01 through 2022-06-05, including 2021 holdout',
      '2021_14_bus_energy_kwh':float(test.loc[:,2:15].to_numpy().sum())}
    if not (summary['all_within_sector_pairs_equal_full'] and len(unique)==3):
        raise ValueError('Cannot use equal-share allocation: sector buses not identical')
    json_dump(out/'audit_summary.json',summary)
    ass.to_csv(out/'assignments_verified.csv',index=False)
    return summary

def score(y,p,history):
    y=np.asarray(y,float);p=np.asarray(p,float);h=np.asarray(history,float)
    if len(y)!=len(p) or not np.isfinite(y).all() or not np.isfinite(p).all():raise ValueError('Invalid score arrays')
    r=y-p;absr=np.abs(r)
    den=np.mean(np.abs(h[168:]-h[:-168]))
    return {'mae_kw':float(np.mean(absr)), 'rmse_kw':float(np.sqrt(np.mean(r*r))),
     'wape_pct':float(100*np.sum(absr)/np.sum(np.abs(y))) if np.sum(np.abs(y)) else np.nan,
     'mase_weekly':float(np.mean(absr)/den) if den else np.nan,
     'bias_actual_minus_forecast_kw':float(np.mean(r)),
     'smape_pct':float(np.mean(200*absr/np.maximum(np.abs(y)+np.abs(p),1e-8)))}

def make_scoring_tables(train,test,sector_forecasts,feeder):
    out=BASE/'results';annual=[];monthly=[]
    for sector in (*SECTORS,'feeder'):
        buses=range(2,16) if sector=='feeder' else get_config()['buses'][sector]
        history=train.loc[:,buses].sum(axis=1).to_numpy(float)
        data=feeder if sector=='feeder' else sector_forecasts[sector]
        for method,key in [('A_sum_then_forecast','forecast_A_kw'),('B_forecast_then_sum','forecast_B_kw')]:
            record={'target':sector,'method':method,'hours':len(data),**score(data['actual_kw'],data[key],history)}
            annual.append(record)
            for month,grp in data.groupby(pd.to_datetime(data.timestamp).dt.to_period('M'),sort=True):
                rr={'month':str(month),'target':sector,'method':method,'hours':len(grp),
                    **score(grp['actual_kw'],grp[key],history)}
                monthly.append(rr)
    a=pd.DataFrame(annual);m=pd.DataFrame(monthly)
    a.to_csv(out/'full_year_metrics.csv',index=False,float_format='%.12f')
    m.to_csv(out/'monthly_metrics.csv',index=False,float_format='%.12f')
    def diff_table(df,groupcols):
        rows=[]
        for name,grp in df.groupby(groupcols,sort=False):
            x=grp.set_index('method')
            A=x.loc['A_sum_then_forecast']; B=x.loc['B_forecast_then_sum']
            row=dict(zip(groupcols, name if isinstance(name,tuple) else (name,)))
            row.update({'A_rmse_kw':float(A.rmse_kw),'B_rmse_kw':float(B.rmse_kw),
               'B_minus_A_mae_kw':float(B.mae_kw-A.mae_kw),
               'B_minus_A_rmse_kw':float(B.rmse_kw-A.rmse_kw),
               'A_rmse_reduction_vs_B_pct':float(100*(B.rmse_kw-A.rmse_kw)/B.rmse_kw) if B.rmse_kw else np.nan,
               'B_minus_A_wape_percentage_points':float(B.wape_pct-A.wape_pct),
               'A_mase_weekly':float(A.mase_weekly),'B_mase_weekly':float(B.mase_weekly),
               'A_bias_kw':float(A.bias_actual_minus_forecast_kw),'B_bias_kw':float(B.bias_actual_minus_forecast_kw)})
            rows.append(row)
        return pd.DataFrame(rows)
    diff_table(a,['target']).to_csv(out/'full_year_differences.csv',index=False,float_format='%.12f')
    diff_table(m,['month','target']).to_csv(out/'monthly_differences.csv',index=False,float_format='%.12f')
    return a,m

def benchmark():
    from forecast_models import FeatureCache,training_only_tune,fit_predict
    cfg=get_config();raw,ass,wide,train,test=load_data(cfg)
    audit(cfg,raw,ass,wide,train,test)
    out=BASE/'results';out.mkdir(exist_ok=True)
    cache=FeatureCache(train.index,test.index)
    tuning={};timings=[];wtime={};models={};
    for sector in SECTORS:
        bs=cfg['buses'][sector]; family=FAMILIES[sector]
        settings,candidates,elapsed=training_only_tune(family,train[bs[0]].to_numpy(),cache)
        tuning[sector]={'configuration':f'{family}__daily_weekly_monthly_yearly',
          'selected_setting':settings,'training_only_tuning_seconds':elapsed,
          'candidate_grid_results':candidates,'candidate_source':'supplied extra_models.py',
          'frozen_for_all_targets':True}
        print('selected',sector,settings, 'tuning_s',round(elapsed,2),flush=True)
    json_dump(out/'model_settings.json',tuning)
    allbus_B={};allbus_A={};sectors={}
    start_A=perf_counter()
    for sector in SECTORS:
        bus_ids=cfg['buses'][sector];family=FAMILIES[sector]
        historical=train[bus_ids].sum(axis=1).to_numpy()
        print('A',sector,'sector bus count',len(bus_ids),flush=True)
        forecast,meas=fit_predict(family,historical,cache,tuning[sector]['selected_setting'])
        sectors[sector]={'A':forecast,'actual':test[bus_ids].sum(axis=1).to_numpy(float)}
        timings.append({'approach':'A_sum_then_forecast','sector':sector,'target':'sector_total',
         'bus_id':0,'model':family,**meas})
        print(' A fit',round(meas['fit_seconds'],3),'sec forecast',round(meas['forecast_seconds'],3),flush=True)
    wtime['approach_A_wall_seconds']=perf_counter()-start_A
    start_B=perf_counter()
    for sector in SECTORS:
        ids=cfg['buses'][sector];family=FAMILIES[sector];combined=[]
        for bus in ids:
            forecast,meas=fit_predict(family,train[bus].to_numpy(),cache,tuning[sector]['selected_setting'])
            allbus_B[bus]=forecast
            combined.append(forecast)
            timings.append({'approach':'B_forecast_then_sum','sector':sector,'target':f'bus_{bus:02d}',
                'bus_id':bus,'model':family,**meas})
            print('B',sector,bus,'fit_s',round(meas['fit_seconds'],3),'forecast_s',round(meas['forecast_seconds'],3),flush=True)
        sectors[sector]['B']=np.sum(combined,axis=0)
    wtime['approach_B_wall_seconds']=perf_counter()-start_B
    # Training-only equal allocation: confirmed buses within each sector are bitwise identical.
    rows=[]
    for sector in SECTORS:
        bs=cfg['buses'][sector];n=len(bs)
        for b in bs:
            allbus_A[b]=sectors[sector]['A']/n
            rows.append(pd.DataFrame({'timestamp':test.index,'bus_id':b,'sector':sector,
             'actual_kw':test[b].to_numpy(),'forecast_A_allocated_kw':allbus_A[b],
             'forecast_B_direct_kw':allbus_B[b],
             'B_minus_A_bus_kw':allbus_B[b]-allbus_A[b]}))
    # Include slack bus as an explicit zero-demand output, not as a fitted model.
    rows.append(pd.DataFrame({'timestamp':test.index,'bus_id':1,'sector':'slack',
       'actual_kw':np.zeros(len(test)),'forecast_A_allocated_kw':np.zeros(len(test)),
       'forecast_B_direct_kw':np.zeros(len(test)), 'B_minus_A_bus_kw':np.zeros(len(test))}))
    busdf=pd.concat(rows,ignore_index=True).sort_values(['timestamp','bus_id'])
    busdf.to_csv(out/'bus_forecasts_hourly.csv',index=False,float_format='%.12f')
    busstats=[]
    for bus in range(2,16):
        frame=busdf.loc[busdf.bus_id==bus].sort_values('timestamp')
        cat=str(frame.sector.iloc[0])
        for method,col in [('A_allocated','forecast_A_allocated_kw'),('B_direct','forecast_B_direct_kw')]:
            busstats.append({'bus_id':bus,'sector':cat,'method':method,'hours':len(frame),
              **score(frame.actual_kw,frame[col],train[bus].to_numpy())})
    pd.DataFrame(busstats).to_csv(out/'per_bus_accuracy.csv',index=False,float_format='%.12f')
    report_sector={}
    for sector in SECTORS:
        v=sectors[sector];df=pd.DataFrame({'timestamp':test.index,'actual_kw':v['actual'],
           'forecast_A_kw':v['A'],'forecast_B_kw':v['B'],'A_minus_B_kw':v['A']-v['B']})
        df.to_csv(out/f'{sector}_hourly.csv',index=False,float_format='%.12f');report_sector[sector]=df
    feeder=pd.DataFrame({'timestamp':test.index,
     'actual_kw':sum((x['actual'] for x in sectors.values())),
     'forecast_A_kw':sum((x['A'] for x in sectors.values())),
     'forecast_B_kw':sum((x['B'] for x in sectors.values()))})
    feeder['A_minus_B_kw']=feeder.forecast_A_kw-feeder.forecast_B_kw
    feeder.to_csv(out/'feeder_hourly.csv',index=False,float_format='%.12f')
    annual,monthly=make_scoring_tables(train,test,report_sector,feeder)
    pd.DataFrame(timings).to_csv(out/'per_fit_runtime.csv',index=False,float_format='%.8f')
    t=pd.DataFrame(timings)
    for a,key in [('A_sum_then_forecast','approach_A'),('B_forecast_then_sum','approach_B')]:
        wtime[key+'_fit_seconds']=float(t.loc[t.approach==a,'fit_seconds'].sum())
        wtime[key+'_forecast_seconds']=float(t.loc[t.approach==a,'forecast_seconds'].sum())
        wtime[key+'_model_total_seconds']=float(t.loc[t.approach==a,'total_seconds'].sum())
    wtime['tuning_seconds_not_in_A_B_wall']=float(sum(tuning[s]['training_only_tuning_seconds'] for s in SECTORS))
    wtime['calendars_cached_shared']=True
    wtime['fresh_models_fitted_A']=3;wtime['fresh_models_fitted_B']=14
    wtime['sequential_outer_fits']=True;wtime['internal_boosting_threads']=2
    wtime['no_model_or_prediction_caching']=True
    json_dump(out/'runtime_summary.json',wtime)
    diag=[];equal=[]
    for sector in SECTORS:
        ids=cfg['buses'][sector]; rep=allbus_B[ids[0]];a=sectors[sector]['A'];b=sectors[sector]['B']
        diff=a-len(ids)*rep
        diag.append({'sector':sector,'bus_count':len(ids),
          'mean_abs_A_minus_N_times_rep_B_kw':float(np.mean(np.abs(diff))),
          'max_abs_A_minus_N_times_rep_B_kw':float(np.max(np.abs(diff))),
          'mean_abs_A_minus_B_kw':float(np.mean(np.abs(a-b))),
          'max_abs_A_minus_B_kw':float(np.max(np.abs(a-b)))})
        for bus in ids[1:]:
            d=allbus_B[bus]-rep
            equal.append({'sector':sector,'bus':bus,'reference_bus':ids[0],
             'max_abs_forecast_difference_kw':float(np.max(np.abs(d))),
             'bitwise_identical_output':bool(np.array_equal(allbus_B[bus],rep))})
    pd.DataFrame(diag).to_csv(out/'scaling_diagnostics.csv',index=False,float_format='%.12f')
    pd.DataFrame(equal).to_csv(out/'duplicate_bus_fit_agreement.csv',index=False,float_format='%.12f')
    archived=BASE/cfg['archived_reference']
    check=[]
    if archived.exists():
        with np.load(archived) as arr:
            for bus in sorted(allbus_B):
                ref=arr[f'bus{bus:02d}_forecast'];ar=arr[f'bus{bus:02d}_actual'];pred=allbus_B[bus]
                check.append({'bus_id':bus,'sector':next(s for s in SECTORS if bus in cfg['buses'][s]),
                  'archived_actual_max_abs_drift_kw':float(np.max(np.abs(ar-test[bus].to_numpy()))),
                  'archived_forecast_rmse_difference_kw':float(np.sqrt(np.mean((pred-ref)**2))),
                  'archived_forecast_mae_difference_kw':float(np.mean(np.abs(pred-ref))),
                  'archived_forecast_max_abs_difference_kw':float(np.max(np.abs(pred-ref)))})
    pd.DataFrame(check).to_csv(out/'archived_reproduction_check.csv',index=False,float_format='%.12f')
    provenance={'status':'MATCHED_RERUN_NOT_CERTIFIED_BITWISE_HISTORICAL_REPRODUCTION',
       'reasons':['Archived per-job selected hyperparameters and fitted model binary versions unavailable',
                  'Distributor normalization used complete 2017-2022 history including holdout',
                  'Exact training-side imputation across 2020/2021 boundary cannot be independently audited'],
       'version_utc':pd.Timestamp.utcnow().isoformat(),
       'python':sys.version,'platform':platform.platform(),
       'cpu_count':os.cpu_count(),'numpy':np.__version__,'pandas':pd.__version__,
       'library_versions':{x:(importlib.metadata.version(x) if importlib.metadata.packages_distributions() else 'unavailable') for x in ('scikit-learn','lightgbm','xgboost','matplotlib')},
       'source_hashes_sha256':{'load_profile.csv':hashfile(BASE/'input/load_profile.csv'),
         'bus_assignments_used.csv':hashfile(BASE/'input/bus_assignments_used.csv'),
         'legacy_extra_models.py':hashfile(BASE/'reference/extra_models.py')},
       'repository_reference':'https://github.com/Islahi/EE499-Team16.git',
       'repository_source_reviewed':'07_Implementation/src_accelerated/forecasting.py on main, AutoARIMA feeder-sum and allocation workflow',
       'reference_historical_model_code':'C2_FixedCohort_Ranked22_Updated/extra_models.py',
       'features':'known calendar covariates; no 2021 actual load in features',
       'normalization':'per-target mean absolute 2017-06 to 2020-12 demand, applied before fitting',
       'distributor_normalization':'mean of 2017-06-01 to 2022-06-05, as specified by archive manifest',
       'historical_training_hours':31440,'historical_test_hours':8760,
       'tuning':'120-day chronological train-only selection on representative bus, fixed for A and B',
       'PV':'not refitted or scored'}
    json_dump(out/'provenance_versions.json',provenance)
    print('\nFULL YEAR SCORE\n'+annual.to_string(index=False,float_format=lambda v:f'{v:.5f}'),flush=True)
    print('\nRUN TIMES\n'+json.dumps(wtime,indent=2),flush=True)
    verify_package() # independent recomputation of all saved metrics and identities
    from output_views import generate_all
    generate_all()


def verify_package():
    cfg=get_config();raw,ass,wide,train,test=load_data(cfg);out=BASE/'results'
    b=pd.read_csv(out/'bus_forecasts_hourly.csv',parse_dates=['timestamp'])
    problems=[];checks={}
    expected_test=test.index
    for sector in (*SECTORS,'feeder'):
        f=pd.read_csv(out/f'{sector}_hourly.csv',parse_dates=['timestamp'])
        if len(f)!=8760 or not pd.DatetimeIndex(f.timestamp).equals(expected_test):
            problems.append(f'{sector}: wrong forecast timestamps or incomplete hours')
        if f.isna().any().any() or not np.isfinite(f.select_dtypes(include=[np.number]).to_numpy()).all():
            problems.append(f'{sector}: non-finite forecast')
        bs=range(2,16) if sector=='feeder' else cfg['buses'][sector]
        actual=test.loc[:,bs].sum(axis=1).to_numpy()
        if not np.allclose(f.actual_kw,actual,rtol=0,atol=1e-8):
            problems.append(f'{sector}: actual not equal to sum of buses')
        fb=b.loc[b.bus_id.isin(bs)].pivot(index='timestamp',columns='bus_id',values='forecast_B_direct_kw').sum(axis=1).to_numpy()
        fa=b.loc[b.bus_id.isin(bs)].pivot(index='timestamp',columns='bus_id',values='forecast_A_allocated_kw').sum(axis=1).to_numpy()
        if not np.allclose(f.forecast_A_kw,fa,atol=1e-8,rtol=0):problems.append(f'{sector}: allocated A does not sum')
        if not np.allclose(f.forecast_B_kw,fb,atol=1e-8,rtol=0):problems.append(f'{sector}: direct B does not sum')
        if not np.allclose(f.A_minus_B_kw,f.forecast_A_kw-f.forecast_B_kw,atol=1e-8,rtol=0):problems.append(f'{sector}: difference mismatch')
        checks[sector]={'hours':len(f),'actual_equal_bus_sum':bool(np.allclose(f.actual_kw,actual,rtol=0,atol=1e-8)),
           'alloc_A_max_abs_sum_residual_kw':float(np.max(np.abs(f.forecast_A_kw-fa))),
           'direct_B_max_abs_sum_residual_kw':float(np.max(np.abs(f.forecast_B_kw-fb)))}
    # Reproduce all 14 x 2 bus-level errors from the saved hourly predictions.
    busaccuracy=[]
    for bus in range(2,16):
        frame=b.loc[b.bus_id==bus].sort_values('timestamp')
        cat=str(frame.sector.iloc[0])
        for method,col in [('A_allocated','forecast_A_allocated_kw'),('B_direct','forecast_B_direct_kw')]:
            busaccuracy.append({'bus_id':bus,'sector':cat,'method':method,'hours':len(frame),
                **score(frame.actual_kw,frame[col],train[bus].to_numpy())})
    oldbus=pd.read_csv(out/'per_bus_accuracy.csv').set_index(['bus_id','method']).sort_index()
    newbus=pd.DataFrame(busaccuracy).set_index(['bus_id','method']).sort_index()
    if not oldbus.index.equals(newbus.index) or not np.allclose(
        oldbus.select_dtypes(include=[np.number]).to_numpy(),
        newbus.select_dtypes(include=[np.number]).to_numpy(),atol=1e-8,rtol=0,equal_nan=True):
        problems.append('per_bus_accuracy.csv: score recomputation changed')
    if len(b)!=15*8760 or b.duplicated(['timestamp','bus_id']).any():
        problems.append('bus long output wrong size or duplicates')
    feeder=pd.read_csv(out/'feeder_hourly.csv',parse_dates=['timestamp'])
    ssum=[pd.read_csv(out/f'{s}_hourly.csv') for s in SECTORS]
    for col in ('actual_kw','forecast_A_kw','forecast_B_kw'):
        if not np.allclose(feeder[col],sum(x[col] for x in ssum),atol=1e-8,rtol=0):
            problems.append(f'feeder mismatch: {col}')
    # Independent scoring from written hourly CSV, with same train-only MASE denominator.
    annual=[];monthly=[]
    for sec in (*SECTORS,'feeder'):
        bus=range(2,16) if sec=='feeder' else cfg['buses'][sec]
        hist=train.loc[:,bus].sum(axis=1).to_numpy()
        df=pd.read_csv(out/f'{sec}_hourly.csv',parse_dates=['timestamp'])
        for method,col in [('A_sum_then_forecast','forecast_A_kw'),('B_forecast_then_sum','forecast_B_kw')]:
            annual.append({'target':sec,'method':method,'hours':len(df),**score(df.actual_kw,df[col],hist)})
            for m,g in df.groupby(df.timestamp.dt.to_period('M')):
                monthly.append({'month':str(m),'target':sec,'method':method,'hours':len(g),
                  **score(g.actual_kw,g[col],hist)})
    for name,new,keys in [('full_year_metrics.csv',pd.DataFrame(annual),['target','method']),
        ('monthly_metrics.csv',pd.DataFrame(monthly),['month','target','method'])]:
        old=pd.read_csv(out/name).set_index(keys).sort_index()
        new=new.set_index(keys).sort_index()
        if not old.index.equals(new.index):problems.append(name+': keys changed');continue
        cols=[x for x in new.columns if x in old.columns]
        if not np.allclose(old[cols].to_numpy(float),new[cols].to_numpy(float),equal_nan=True,rtol=0,atol=1e-8):
            problems.append(name+': score recomputation changed')
    if not np.allclose(test.loc[:,2:15].sum(axis=1),
       4*test[2].to_numpy()+5*test[3].to_numpy()+5*test[4].to_numpy(),rtol=0,atol=1e-10):
        problems.append('4R + 5C + 5M feeder identity failed')
    try:
        rec=json.loads((out/'audit_summary.json').read_text())
        if rec['total_hours']!=43921 or rec['loaded_bus_distinct_nonzero_series_full']!=3:
            problems.append('Source audit mismatch')
    except Exception as e:problems.append(f'Audit unavailable: {e}')
    result={'status':'PASS' if not problems else 'FAIL','errors':problems,'targets':checks,
       'scoring_reproduced_from_hourly_CSV':not any('metrics.csv' in x for x in problems),
       'train_hours':len(train),'test_hours':len(test),
       'all_2021_hourly_actuals_and_A_B_forecasts_verified':not problems,
       'PV_retraining_excluded':True}
    json_dump(out/'verification.json',result)
    print('VERIFICATION',result['status'],problems,flush=True)
    if problems:raise RuntimeError('Package verification failed: '+str(problems))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--recompute',action='store_true',help='Retrain and regenerate outputs (17 fresh fits + training-only tuning)')
    g.add_argument('--verify-only',action='store_true',help='Recompute saved 2021 metrics and verify identity without retraining')
    a=p.parse_args()
    if a.recompute:benchmark()
    else:verify_package()
