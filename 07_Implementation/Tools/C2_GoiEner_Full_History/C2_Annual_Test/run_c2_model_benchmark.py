"""C2 — compare 9 StatsForecast models for a single 8,784-hour annual horizon.

From original C2 year-ahead package, with LOAD and MODELLED PV POWER cases kept separate.
Run: python run_c2_model_benchmark.py
Optional: python run_c2_model_benchmark.py --baseline-only
Repository: https://github.com/Islahi/EE499-Team16.git
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

import c2_benchmark_settings as S
from c2_benchmark_core import (
    TRAIN_CLOCK, TEST_CLOCK, load_cases, make_model, predict_model,
    seasonal_naive_numpy, score_and_save, unsupported_reason,
)


def args_parse():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--models',nargs='*',default=list(S.MODELS),choices=S.MODELS,
                   help='Only specified models (default: all nine)')
    p.add_argument('--seasonalities',nargs='*',default=list(S.SEASONALITIES),choices=S.SEASONALITIES,
                   help='Only specified seasonality settings (default: all seven)')
    p.add_argument('--categories',nargs='*',default=['load','pv'],choices=['load','pv'])
    p.add_argument('--datasets',nargs='*',default=None,help='Optional dataset ID selection (see --prepare-only)')
    p.add_argument('--prepare-only',action='store_true',help='Validate data and write inventory; do not fit any model')
    p.add_argument('--baseline-only',action='store_true',help='Offline SeasonalNaive equivalent; does not require statsforecast')
    p.add_argument('--retry',action='store_true',help='Rerun even successful jobs')
    p.add_argument('--max-jobs',type=int,default=None,help='Restrict executed jobs for a quick functionality test')
    p.add_argument('--fail-fast',action='store_true',help='Stop on the first failing model')
    p.add_argument('--skip-reports',action='store_true')
    p.add_argument('--list-jobs',action='store_true',help='Print model/dataset/seasonality job list without fitting anything')
    return p.parse_args()


def refresh_reports():
    from c2_benchmark_reports import build_reports
    build_reports(S.OUTPUT)


def main():
    args=args_parse()
    if args.baseline_only:
        args.models=['SeasonalNaive']
    if not args.prepare_only and not args.baseline_only and not args.list_jobs:
        try:
            import statsforecast
        except ImportError as exc:
            raise SystemExit('StatsForecast is not installed. Run: python -m pip install -r requirements.txt\n'
                             'To validate source data and obtain an offline reference, use --baseline-only.') from exc
    else: statsforecast=None

    cases=load_cases()
    if args.datasets is not None:
        bad=set(args.datasets)-{c.dataset for c in cases}
        if bad: raise ValueError(f'Unknown dataset names: {sorted(bad)}')
        cases=[c for c in cases if c.dataset in args.datasets]
    cases=[c for c in cases if c.category in args.categories]
    if not cases: raise ValueError('Nothing selected')
    S.OUTPUT.mkdir(parents=True,exist_ok=True)
    metadata={
        'experiment':'C2 annual 9-model comparison',
        'repo':'https://github.com/Islahi/EE499-Team16.git',
        'source_package':'C2_Annual_Forecasting_and_Plotter_Updated(1).zip',
        'source_clock':'NASA UTC; GoiEner timezone-naive clock unspecified',
        'train_start':str(TRAIN_CLOCK[0]),'train_end':str(TRAIN_CLOCK[-1]),
        'test_start':str(TEST_CLOCK[0]),'test_end':str(TEST_CLOCK[-1]),
        'train_hours':len(TRAIN_CLOCK),'test_hours':len(TEST_CLOCK),
        'seasonality_periods_hours':S.SEASONALITIES,
        'fixed_period_warning':'monthly=720h and yearly=8760h are approximations, not calendar months or leap years',
        'forecast_mode':'single long-horizon forecast from training history, no daily refits or test-year feedback',
        'pv_model':'project piecewise irradiance_to_power, GHI proxy, rated 490kW/site, no temperature/tilt/inverter losses',
        'pv_night_correction':'Solar geometry night zero; site lat/lon from NASA source name; no actual future irradiance used',
        'mase':'MAE divided by train-only one-week (168-hour) seasonal-naive MAE; fixed scaling across models',
        'bias':'actual minus forecast: positive means model underforecast',
        'model_timing':'measured model.fit and model.predict only, excluding data reading/postprocessing',
        'python_version':platform.python_version(), 'statsforecast_version':getattr(statsforecast,'__version__',None),
        'generated_utc':datetime.now(timezone.utc).isoformat(),
        'available_datasets':[{ 'dataset':c.dataset,'category':c.category,'source':c.origin,
                                'train_mean_kw':float(c.y_train.mean()),
                                'test_mean_kw':float(c.y_test.mean()),
                                'train_min_kw':float(c.y_train.min()),'train_max_kw':float(c.y_train.max()),
                                'pv_site_lat':c.site_lat,'pv_site_lon':c.site_lon} for c in cases],
    }
    (S.OUTPUT/'experiment_settings.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    pd.DataFrame(metadata['available_datasets']).to_csv(S.OUTPUT/'data_inventory.csv',index=False)
    planned_rows=[]
    for c in cases:
        for name in S.MODELS:
            for season_name, periods in S.SEASONALITIES.items():
                reason=unsupported_reason(name,periods,len(c.y_train),S.TRY_INSUFFICIENT_YEARLY_MODELS)
                planned_rows.append({'category':c.category,'dataset':c.dataset,'model':name,
                    'seasonality':season_name,'periods_hours':str(periods),
                    'compatibility':'ELIGIBLE_TO_TRY' if reason is None else 'SKIP_NOT_RECOMMENDED',
                    'reason':reason or '', 'forecast_hours':len(TEST_CLOCK)})
    pd.DataFrame(planned_rows).to_csv(S.OUTPUT/'planned_model_matrix.csv',index=False)
    print(f'C2 training: {TRAIN_CLOCK[0]} through {TRAIN_CLOCK[-1]} ({len(TRAIN_CLOCK):,} h)')
    print(f'C2 test:     {TEST_CLOCK[0]} through {TEST_CLOCK[-1]} ({len(TEST_CLOCK):,} h)')
    print(f'Datasets: {[(c.category,c.dataset) for c in cases]}')
    if args.prepare_only:
        print('PREPARE-ONLY: data checks passed; no model fits or scores were computed')
        return
    if args.list_jobs:
        for item in planned_rows:
            if (item['model'] in args.models and item['seasonality'] in args.seasonalities
                    and item['dataset'] in {c.dataset for c in cases}):
                print(f"{item['dataset']:35s} {item['model']:15s} {item['seasonality']:30s} {item['compatibility']} {item['reason']}")
        return

    planned=0; success=0; failure=0; skipped=0; jobs_run=0
    total_start=perf_counter()
    for c in cases:
        for season_name in args.seasonalities:
            periods=S.SEASONALITIES[season_name]
            for name in args.models:
                planned+=1
                path=S.OUTPUT / c.category / c.dataset / f'{name}__{season_name}'
                path.mkdir(parents=True,exist_ok=True)
                result_file=path/'run_metrics.json'
                if result_file.exists() and not args.retry:
                    prior=json.loads(result_file.read_text(encoding='utf-8'))
                    if prior.get('status')=='OK' and prior.get('engine')==('numpy_equivalent' if args.baseline_only else 'statsforecast'):
                        print(f'[RESUME] {c.dataset} {name} {season_name}')
                        success+=1;continue
                why=unsupported_reason(name,periods,len(c.y_train),S.TRY_INSUFFICIENT_YEARLY_MODELS)
                if why is not None:
                    entry={'status':'SKIPPED_UNSUPPORTED','dataset':c.dataset,'category':c.category,
                           'model':name,'seasonality':season_name,'periods_hours':str(periods),
                           'reason':why,'unit':c.unit,'forecast_hours':len(TEST_CLOCK)}
                    result_file.write_text(json.dumps(entry,indent=2),encoding='utf-8')
                    skipped+=1
                    print(f'[SKIP] {c.dataset} {name} {season_name}: {why}',flush=True)
                    continue
                if args.max_jobs is not None and jobs_run>=args.max_jobs:
                    print('Max jobs reached, stopping cleanly. Re-run without --max-jobs to continue.')
                    if not args.skip_reports:refresh_reports()
                    return
                jobs_run+=1
                job_start=perf_counter()
                print(f'[{jobs_run:03d}] {c.category}/{c.dataset}: {name} [{season_name}]',flush=True)
                try:
                    if args.baseline_only:
                        if len(periods)>1:
                            continue
                        t=perf_counter()
                        raw=seasonal_naive_numpy(c.y_train,periods[0],len(TEST_CLOCK))
                        secs=perf_counter()-t
                        entry=score_and_save(c,name,season_name,raw,path,0.0,secs,'numpy_equivalent')
                    else:
                        model=make_model(name,periods,len(c.y_train))
                        raw, fit_seconds, predict_seconds=predict_model(model,c.y_train,len(TEST_CLOCK))
                        entry=score_and_save(c,name,season_name,raw,path,fit_seconds,predict_seconds,'statsforecast')
                    # Append measured total time to run file; report timestamps are for auditability.
                    entry['completed_utc']=datetime.now(timezone.utc).isoformat()
                    entry['job_wall_seconds']=round(perf_counter()-job_start,6)
                    result_file.write_text(json.dumps(entry,indent=2),encoding='utf-8')
                    success+=1
                    print(f'  -> RMSE={entry["rmse_kw"]:.3f}kW, MAE={entry["mae_kw"]:.3f}kW, '
                          f'WAPE={entry["wape_percent"]:.2f}%, MASE={entry["mase_weekly"]:.3f}, '
                          f'Bias={entry["bias_kw_actual_minus_forecast"]:.3f}kW, '
                          f'fit={entry["fit_seconds"]:.2f}s predict={entry["forecast_seconds"]:.2f}s',flush=True)
                except (Exception,KeyboardInterrupt) as exc:
                    failure+=1
                    entry={'status':'FAILED','dataset':c.dataset,'category':c.category,
                           'model':name,'seasonality':season_name,'periods_hours':str(periods),
                           'reason':f'{type(exc).__name__}: {exc}',
                           'job_wall_seconds':round(perf_counter()-job_start,6),
                           'traceback':traceback.format_exc(limit=10),
                           'failed_utc':datetime.now(timezone.utc).isoformat()}
                    result_file.write_text(json.dumps(entry,indent=2),encoding='utf-8')
                    print(f'  !! FAILED: {entry["reason"]}',flush=True)
                    if args.fail_fast or isinstance(exc,KeyboardInterrupt):
                        if not args.skip_reports:refresh_reports()
                        raise
    if not args.skip_reports:refresh_reports()
    print(f'Finished {planned} job slots: {success} completed, {skipped} unsupported, {failure} failed. '
          f'Elapsed wall time={perf_counter()-total_start:.1f}s')
    print(f'Results: {S.OUTPUT}')


if __name__=='__main__':
    main()
