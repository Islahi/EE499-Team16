"""Isolated single model job. All warnings are retained as structured output.
Usage is internal, invoked by run_c2.py.
"""
import argparse, json, traceback, warnings
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
import c2_config as C
from c2_data import cases,TEST
from c2_models import predict
from c2_scoring import save_case

def main():
    p=argparse.ArgumentParser()
    for name in ['dataset','model','seasonality','outdir']:p.add_argument('--'+name,required=True)
    a=p.parse_args()
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    case=next(x for x in cases() if x.name==a.dataset)
    model_seasons=C.SEASONALITIES[a.seasonality]
    t=perf_counter()
    warn=[]
    caught=[]
    record={'dataset':case.name,'category':case.category,'unit':case.unit,
      'model':a.model,'seasonality':a.seasonality,'periods_hours':str(model_seasons),
      'training_hours':len(case.train),'forecast_hours':len(case.actual),
      'training_mean':float(case.train.mean()),'dataset_description':case.note}
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('default')
            raw,fit_s,forecast_s,scale=predict(a.model,model_seasons,case.train,len(TEST))
        record.update(save_case(case,raw,out))
        record.update(status='OK_WITH_WARNINGS' if caught else 'OK',fit_seconds=fit_s,
          forecast_seconds=forecast_s,scale_to_unit_mean=scale,
          model_seconds=fit_s+forecast_s)
    except Exception as exc:
        record.update(status='FAILED',reason=f'{type(exc).__name__}: {exc}',
                      traceback=traceback.format_exc(limit=12))
        # warning records captured before exception may be unavailable; retain exception.
    warn=[{'type':w.category.__name__,'message':str(w.message),'source_file':Path(w.filename).name,'line':w.lineno} for w in caught]
    counts=Counter((x['type'],x['message']) for x in warn)
    record['warning_count']=len(warn)
    record['warning_messages']=[{'type':k[0],'message':k[1],'count':n} for k,n in counts.most_common(25)]
    record['completed_utc']=datetime.now(timezone.utc).isoformat()
    record['wall_seconds']=perf_counter()-t
    (out/'run_metrics.json').write_text(json.dumps(record,indent=2,allow_nan=False),encoding='utf-8')
    (out/'warnings.json').write_text(json.dumps(record['warning_messages'],indent=2),encoding='utf-8')
    print(f"{record['status']} {a.dataset} / {a.model} / {a.seasonality} | "
          f"RMSE {record.get('rmse','n/a')} | {record['wall_seconds']:.2f}s | warnings={len(warn)}",flush=True)
    if record['status']=='FAILED':print(record['reason'],flush=True)

if __name__=='__main__':main()
