"""Run all models in separate processes, handle failures / OOM / timeouts, resume jobs.

From C2_FullHistory_2021: python run_c2.py
A short trial: python run_c2.py --models SeasonalNaive --datasets Distributed_15Bus_Load Bilbao_Modelled_PV --seasons daily weekly
Project repository: https://github.com/Islahi/EE499-Team16.git
"""
import argparse,json,os,platform,subprocess,sys,time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import c2_config as C
from c2_data import cases,TRAIN,TEST
from c2_models import unsupported_reason

def options():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--models',nargs='+',choices=C.MODELS,default=list(C.MODELS))
    p.add_argument('--seasons',nargs='+',choices=C.SEASONALITIES,default=list(C.SEASONALITIES))
    p.add_argument('--datasets',nargs='+',help='Case names from 01_CHECK_DATA_WINDOWS.bat; default all')
    p.add_argument('--max-jobs',type=int,help='Execute only N unprocessed fits in this invocation')
    p.add_argument('--retry-failed',action='store_true',help='Retry failed/timed-out runs (otherwise resume skips ALL recorded statuses)')
    p.add_argument('--timeout-seconds',type=int,default=C.DEFAULT_JOB_TIMEOUT_SECONDS)
    p.add_argument('--memory-gb',type=float,default=C.DEFAULT_PROCESS_MEMORY_GB,help='Max worker RSS, 0 disables')
    p.add_argument('--prepare-only',action='store_true',help='Only check source alignment and planned matrix')
    p.add_argument('--no-reports',action='store_true')
    return p.parse_args()

def write_atomic(path,obj):
    temp=path.with_suffix('.json.tmp');temp.write_text(json.dumps(obj,indent=2,allow_nan=False),encoding='utf-8');os.replace(temp,path)

def run_child(cmd,log_path,timeout,mem_limit_gb):
    # psutil is optional but recommended; memory-limits are enforced with psutil if installed.
    try:import psutil
    except ImportError: psutil=None
    start=time.perf_counter();issue=None
    with open(log_path,'w',encoding='utf-8',errors='replace') as stream:
        child=subprocess.Popen(cmd,stdout=stream,stderr=subprocess.STDOUT,cwd=C.ROOT)
        try:
            while child.poll() is None:
                duration=time.perf_counter()-start
                if timeout>0 and duration>timeout:
                    issue=('TIMEOUT',f'Worker exceeded {timeout} seconds');break
                if mem_limit_gb>0 and psutil:
                    try:
                        proc=psutil.Process(child.pid)
                        total=proc.memory_info().rss
                        for desc in proc.children(recursive=True):
                            try:total+=desc.memory_info().rss
                            except psutil.Error:pass
                        if total>mem_limit_gb*(1024**3):
                            issue=('MEMORY_LIMIT',f'Worker RSS exceeded {mem_limit_gb} GiB');break
                    except psutil.Error:pass
                time.sleep(0.5)
        except KeyboardInterrupt:
            child.kill();child.wait();raise
        if issue:
            child.kill();child.wait(timeout=20)
        return child.returncode,issue, time.perf_counter()-start

def main():
    a=options()
    available=cases();names=[c.name for c in available]
    if a.datasets:
        unknown=set(a.datasets)-set(names)
        if unknown:raise ValueError(f'Unknown case(s): {unknown}; choices={names}')
        chosen=[c for c in available if c.name in a.datasets]
    else:chosen=available
    C.OUTPUT.mkdir(exist_ok=True)
    plan=[]
    for c in chosen:
        for s in a.seasons:
            periods=C.SEASONALITIES[s]
            for m in a.models:
                why=unsupported_reason(m,periods,len(c.train))
                plan.append({'dataset':c.name,'category':c.category,'model':m,'seasonality':s,
                             'periods':str(periods),'eligibility':'SKIPPED_UNSUPPORTED' if why else 'ELIGIBLE',
                             'reason':why or ''})
    pd.DataFrame(plan).to_csv(C.OUTPUT/'planned_model_matrix.csv',index=False)
    metadata={
     'benchmark':'C2 Full GoiEner + Bilbao NASA PV, 2021 single-shot year-ahead',
     'project_repository':'https://github.com/Islahi/EE499-Team16.git',
     'train_start':str(TRAIN[0]),'train_end':str(TRAIN[-1]),'train_hours':len(TRAIN),
     'test_start':str(TEST[0]),'test_end':str(TEST[-1]),'test_hours':len(TEST),
     'models':a.models,'seasons':{x:list(C.SEASONALITIES[x]) for x in a.seasons},
     'model_setup':{'input_normalized':C.NORMALIZE_INPUTS,'AutoTBATS_use_boxcox':C.TBATS_USE_BOXCOX,
                    'AutoTBATS_use_arma_errors':C.TBATS_USE_ARMA_ERRORS,
                    'max_prediction_to_train_peak':C.UNREALISTIC_MAX_MULTIPLE_OF_TRAIN_PEAK},
     'runtime_guards':{'timeout_seconds':a.timeout_seconds,'max_worker_rss_gib':a.memory_gb},
     'weekly_mase_denominator':'train-only |y[t]-y[t-168]| MAE, same for all models',
     'bias_definition':'actual minus forecast',
     'single_fit_2021':'No future observations are supplied to model fitting or prediction',
     'pv':'490-kW proxy output already calculated from NASA POWER, NOT measured PV output',
     'source_clock_note':'NASA source uses UTC; GoiEner source clock is timezone-naive and not proven UTC. Cases are scored separately.',
     'sector_note':'Per-meter category profiles are averages, summed sector loads have variable meter populations, distributed bus profile is constructed',
     'python_version':platform.python_version(),
     'available_datasets':[{'name':c.name,'category':c.category,'unit':c.unit,'source':c.source,'note':c.note} for c in available],
     'created_utc':datetime.now(timezone.utc).isoformat()}
    write_atomic(C.OUTPUT/'benchmark_settings.json',metadata)
    print(f'TRAIN: {TRAIN[0]} → {TRAIN[-1]} ({len(TRAIN):,} hours)')
    print(f'TEST:  {TEST[0]} → {TEST[-1]} ({len(TEST):,} hours)')
    print('DATASETS:', [(c.name,c.unit) for c in chosen]);print('JOBS:',len(plan),flush=True)
    if a.prepare_only:return
    count=0
    for n,row in enumerate(plan,1):
        out=C.OUTPUT/row['category']/row['dataset']/(row['model']+'__'+row['seasonality']);out.mkdir(parents=True,exist_ok=True)
        record=out/'run_metrics.json'
        if record.exists():
            try: old=json.loads(record.read_text(encoding='utf-8'))
            except (ValueError,OSError):old={}
            if old.get('status') in ('OK','OK_WITH_WARNINGS','SKIPPED_UNSUPPORTED') or (old.get('status') and not a.retry_failed):
                print(f'[{n}/{len(plan)}] RESUME {row["dataset"]} {row["model"]} {row["seasonality"]}',flush=True);continue
        if row['reason']:
            write_atomic(record,{**row,'status':'SKIPPED_UNSUPPORTED',
                         'reason':row['reason'],'warning_count':0,'wall_seconds':0})
            print(f'[{n}/{len(plan)}] SKIP {row["model"]}/{row["seasonality"]}: {row["reason"]}',flush=True)
            continue
        if a.max_jobs is not None and count>=a.max_jobs:print('Max jobs reached; saved progress.');break
        count+=1;print(f'[{n}/{len(plan)}] START {row["dataset"]}: {row["model"]} [{row["seasonality"]}]',flush=True)
        cmd=[sys.executable,'-u',str(C.ROOT/'c2_worker.py'),'--dataset',row['dataset'],
             '--model',row['model'],'--seasonality',row['seasonality'],'--outdir',str(out)]
        try:code,issue,elapsed=run_child(cmd,out/'job_output.log',a.timeout_seconds,a.memory_gb)
        except KeyboardInterrupt:
            print('Interrupted: earlier results remain saved. Run the same command again to resume.')
            break
        if issue or code!=0 or not record.exists():
            status,reason=issue if issue else ('FAILED',f'Worker exited code {code} (see job_output.log)')
            write_atomic(record,{**row,'status':status,'reason':reason,'warning_count':0,
                         'wall_seconds':elapsed,'completed_utc':datetime.now(timezone.utc).isoformat()})
        latest=json.loads(record.read_text(encoding='utf-8'))
        print(f'    -> {latest["status"]}: RMSE={latest.get("rmse", "-")} '
              f'warnings={latest.get("warning_count",0)} wall={elapsed:.1f}s',flush=True)
    if not a.no_reports:
        try:
            from c2_reports import make_reports
            make_reports()
        except Exception as e:print('Reporting error (job results still saved):',str(e))
    print('Results:',C.OUTPUT,flush=True)
if __name__=='__main__':main()
