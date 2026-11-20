"""Resumable C2 2021 benchmark, per-category and optionally per-bus.

1. Build cohort with 01_build_common_cohort.py
2. Prepare category/bus/PV cases with cohort_cases.py
3. python run_benchmark.py --scope categories --suite selected
4. python run_benchmark.py --scope buses --suite selected
5. python report_rankings.py
"""
import argparse,json,subprocess,sys,time,os
from pathlib import Path
from datetime import datetime,timezone
import pandas as pd
import cohort_config as C
from cohort_models import unsupported_reason

from model_catalog import select_pairs, RANKED_22, NEW_OPTIMIZED, BASELINES
EXPERIMENT_VERSION = C.EXPERIMENT_VERSION

def pairs(suite, include_neural, group='all'):
    return select_pairs(group=group, include_neural=include_neural, suite=suite)

def run_child(cmd,log,timeout,limit_gb):
    try:import psutil
    except ImportError:psutil=None
    t=time.perf_counter();failure=None
    with log.open('w',encoding='utf-8',errors='replace') as f:
        proc=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,cwd=C.ROOT)
        try:
            while proc.poll() is None:
                if timeout>0 and time.perf_counter()-t>timeout:
                    failure=('TIMEOUT',f'Model took longer than {timeout} seconds');break
                if limit_gb>0 and psutil:
                    try:
                        pr=psutil.Process(proc.pid)
                        mem=pr.memory_info().rss
                        for kid in pr.children(recursive=True):
                            try:mem+=kid.memory_info().rss
                            except psutil.Error:pass
                        if mem>limit_gb*1024**3:
                            failure=('MEMORY_LIMIT',f'Child memory usage exceeded {limit_gb} GiB');break
                    except psutil.Error:pass
                time.sleep(.5)
        except KeyboardInterrupt:
            proc.kill();proc.wait();raise
        if failure:proc.kill();proc.wait()
    return proc.returncode,failure,time.perf_counter()-t

def select_cases(meta,scope):
    cases=meta['cases']
    if scope=='categories':return [c for c in cases if c['name'].startswith('Cohort_')]
    if scope=='buses':return [c for c in cases if c['name'].startswith('Bus_') or c['name']=='Distributed_Total']
    if scope=='pv':return [c for c in cases if c['category']=='pv']
    return cases

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('--scope',choices=('categories','buses','pv','all'),default='categories')
    p.add_argument('--suite',choices=('selected','all'),default='selected',help='selected=ranked22 + optimized new models + controls; all=also broader classic grid')
    p.add_argument('--group',choices=('all','legacy22','new','baselines','neural'),default='all',help='Run one candidate group or all; group=new has six families across seven seasonalities')
    p.add_argument('--include-neural',action='store_true',help='EXPERIMENTAL: AutoNHITS and AutoNBEATSx, may require GPU/high RAM')
    p.add_argument('--save-fitted-models',action='store_true',help='Save trained objects (.joblib) in addition to configurations and forecasts; can use many GB')
    p.add_argument('--max-jobs',type=int)
    p.add_argument('--retry-failed',action='store_true')
    p.add_argument('--timeout-seconds',type=int,default=C.DEFAULT_JOB_TIMEOUT_SECONDS)
    p.add_argument('--memory-gb',type=float,default=C.DEFAULT_PROCESS_MEMORY_GB)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--exclude-cases',nargs='+',default=[],help='Optional dataset names to exclude (e.g. Bus_01 zero-load slack bus)')
    p.add_argument('--models',nargs='+',choices=C.MODELS,help='Optional filter to listed models')
    p.add_argument('--seasons',nargs='+',choices=C.SEASONALITIES,help='Optional filter')
    a=p.parse_args()
    if not (C.DATA/'cases.json').exists():raise FileNotFoundError('First run cohort_cases.py to prepare datasets')
    meta=json.loads((C.DATA/'cases.json').read_text())
    chosen=[c for c in select_cases(meta,a.scope) if c['name'] not in a.exclude_cases]
    if not chosen:raise ValueError(f'No cases for {a.scope}. If buses, prepare --distributed from NEW cohort.')
    if any(not case.get('dataset_sha256') for case in chosen):
        raise ValueError('Prepared cases lack dataset fingerprints from this updated version. '                          'Run 03_PREPARE_CATEGORIES_AND_PV_WINDOWS.bat again '                          '(or 06_PREPARE_DISTRIBUTED_BUSES_WINDOWS.bat for buses). '                          'You do NOT need to rebuild your customer cohort.')
    matrix=[]
    for c in chosen:
        for m,s,source_group in pairs(a.suite,a.include_neural,a.group):
            if a.models and m not in a.models:continue
            if a.seasons and s not in a.seasons:continue
            why=unsupported_reason(m,C.SEASONALITIES[s],meta['train_hours'])
            if m in ('Naive','YearAgoCalendarNaive') and s not in ('daily','yearly_365d'):
                why='Baseline has only one standard configuration'
            # Old classic seasonal restrictions are from prior observed failures.
            matrix.append({'dataset':c['name'],'category':c['category'],'model':m,'seasonality':s,
              'periods_hours':list(C.SEASONALITIES[s]),'reason':why or '',
              'source_group':source_group,'experiment_version':EXPERIMENT_VERSION,
              'dataset_sha256':c.get('dataset_sha256','')})
    C.OUTPUT.mkdir(exist_ok=True)
    pd.DataFrame(matrix).to_csv(C.OUTPUT/f'planned_model_matrix_{a.scope}_{a.group}_{a.suite}.csv',index=False)
    (C.OUTPUT/f'benchmark_settings_{a.scope}_{a.group}_{a.suite}.json').write_text(json.dumps({
        'project':'https://github.com/Islahi/EE499-Team16.git','dataset_preparation':meta,
        'scope':a.scope,'group':a.group,'suite':a.suite,'include_neural':a.include_neural,
        'experiment_version':EXPERIMENT_VERSION,
        'ranked_22': [{'rank':i+1,'model':m,'seasonality':s} for i,(m,s) in enumerate(RANKED_22)],
        'new_optimized_count':len(NEW_OPTIMIZED),'baseline_count':len(BASELINES),
        'save_fitted_models':a.save_fitted_models,'created_utc':datetime.now(timezone.utc).isoformat(),
        'seasonalities':{k:list(v) for k,v in C.SEASONALITIES.items()},
        'tuning':'New candidate hyperparameters selected on last 120 days of training, then refitted; test year 2021 never used for selection',
        'prior_rankings':'Exact prior top20 overall under user ordinal-priority ranking, plus AutoTBATS all four and AutoETS weekly. Previous results were from changing-cohort inputs.'
    },indent=2),encoding='utf-8')
    print('Data:',[x['name'] for x in chosen],flush=True)
    print('Configurations:',len(matrix),'Eligible:',sum(not x['reason'] for x in matrix),flush=True)
    if a.dry_run:return
    nrun=0
    for i,item in enumerate(matrix,1):
        path=C.OUTPUT/item['category']/item['dataset']/(item['model']+'__'+item['seasonality'])
        path.mkdir(parents=True,exist_ok=True)
        rec=path/'run_metrics.json'
        if rec.exists():
            try:old=json.loads(rec.read_text())
            except Exception:old={}
            if (old.get('experiment_version') == EXPERIMENT_VERSION
                    and old.get('dataset_sha256') == item.get('dataset_sha256')
                    and (old.get('status') in ('OK','OK_WITH_WARNINGS','SKIPPED_UNSUPPORTED')
                         or (old.get('status') and not a.retry_failed))):
                print(f'[{i}/{len(matrix)}] RESUME {item["dataset"]} {item["model"]} {item["seasonality"]}',flush=True)
                continue
        if item['reason']:
            rec.write_text(json.dumps({**item,'status':'SKIPPED_UNSUPPORTED','warning_count':0},indent=2))
            continue
        if a.max_jobs is not None and nrun>=a.max_jobs:
            print('MAX JOBS reached; resume later.',flush=True);break
        nrun+=1
        print(f'[{i}/{len(matrix)}] START {item["dataset"]} : {item["model"]} [{item["seasonality"]}]',flush=True)
        cmd=[sys.executable,'-u',str(C.ROOT/'run_single_job.py'),
             '--case',item['dataset'],'--model',item['model'],'--season',item['seasonality'],
             '--out',str(path),'--experiment-version',EXPERIMENT_VERSION,
             '--dataset-sha256',item.get('dataset_sha256',''),
             '--source-group',item['source_group']]
        if a.save_fitted_models:cmd.append('--save-fitted-model')
        try:code,failed,elapsed=run_child(cmd,path/'job_output.log',a.timeout_seconds,a.memory_gb)
        except KeyboardInterrupt:
            print('Interrupted. Previous jobs saved. Run again to resume.',flush=True);break
        if failed or code!=0 or not rec.exists():
            state,reason=failed or ('FAILED',f'Worker exited code {code}; see job_output.log')
            rec.write_text(json.dumps({**item,'status':state,'reason':reason,'wall_seconds':elapsed},indent=2))
        obj=json.loads(rec.read_text())
        print(f'  -> {obj["status"]}, RMSE={obj.get("rmse","-")}, seconds={elapsed:.1f}',flush=True)
    try:
        from report_rankings import build_report
        build_report()
    except Exception as exc:print('Report generation warning:',str(exc))
    print('Completed jobs saved to:',C.OUTPUT)

if __name__=='__main__':main()
