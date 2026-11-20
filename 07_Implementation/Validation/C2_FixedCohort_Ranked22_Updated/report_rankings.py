"""Build independent per-dataset rankings for all error metrics and timings."""
from pathlib import Path
import json
import pandas as pd
import cohort_config as C
METRICS={
 'rmse':'asc','mae':'asc','wape_percent':'asc','mase_weekly':'asc',
 'smape_percent':'asc','abs_bias':'asc','model_seconds':'asc',
 'fit_seconds':'asc','forecast_seconds':'asc'}

def build_report():
    rows=[]
    for p in C.OUTPUT.glob('*/*/*/run_metrics.json'):
        x=json.loads(p.read_text(encoding='utf-8'))
        x.pop('traceback',None);x.pop('warnings',None)
        x['result_path']=str(p.parent.relative_to(C.OUTPUT))
        rows.append(x)
    if not rows:return print('No results yet.')
    data=pd.DataFrame(rows)
    data['current_experiment']=data.get('experiment_version',pd.Series(index=data.index,dtype=str)).eq(C.EXPERIMENT_VERSION)
    meta_path=C.DATA/'cases.json'
    if meta_path.exists():
        case_hash={c['name']:c.get('dataset_sha256','') for c in json.loads(meta_path.read_text()).get('cases',[])}
        data['current_data']=data.apply(lambda r: r.get('dataset_sha256','')==case_hash.get(r.get('dataset'),None),axis=1)
    else:data['current_data']=False
    data.to_csv(C.OUTPUT/'all_model_statuses.csv',index=False)
    good=data[(data.current_experiment)&(data.current_data)&(data.status.isin(('OK','OK_WITH_WARNINGS')))].copy()
    if good.empty:return print('No successful models for CURRENT experiment + data hash yet.')
    good['abs_bias']=good.bias_actual_minus_forecast.abs()
    good.to_csv(C.OUTPUT/'successful_model_scores.csv',index=False)
    for category,g in good.groupby('category'):
        g.to_csv(C.OUTPUT/f'{category}_model_scores.csv',index=False)
    for dataset,g in good.groupby('dataset'):
        dest=C.OUTPUT/'rankings'/dataset;dest.mkdir(parents=True,exist_ok=True)
        for metric in METRICS:
            if metric not in g.columns:continue
            sort=g.sort_values(metric,na_position='last')
            sort.insert(0,'rank',range(1,len(sort)+1))
            sort.to_csv(dest/f'ranked_{metric}.csv',index=False)
    print(f'Saved {len(good)} successful results; rankings by dataset and metric.')
if __name__=='__main__':build_report()
