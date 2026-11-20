"""Rebuild the analysis inputs from the two extracted archives. Optional historical checks are retained in a separate evidence file."""
from pathlib import Path
import pandas as pd,numpy as np,json,hashlib,shutil,re,ast,sys
from numerical import A,O,R,C
A.mkdir(exist_ok=True);C.mkdir(exist_ok=True);(O/'00_Overview').mkdir(exist_ok=True,parents=True)
# This audit calculates row-level checks and reconciles each job to its measurements.
exec(compile(Path(__file__).with_name('hourly_audit.py').read_text(),'hourly_audit.py','exec'))
keys=['dataset','model','seasonality'];S=pd.read_csv(R/'all_model_statuses.csv')
J=pd.read_csv(A/'job_audit.csv');J=J.merge(S[keys+['unit','reason','dataset_sha256','fit_seconds','forecast_seconds','source_group']],on=keys,validate='one_to_one');J.to_csv(A/'job_audit.csv',index=False)
plan=pd.concat([pd.read_csv(p)[keys] for p in R.glob('planned*')]).drop_duplicates()
S[keys+['status','reason']].merge(plan,on=keys,how='outer',indicator=True).to_csv(A/'plan_reconciliation.csv',index=False)
file=next(Path('work').rglob('bus_summary.csv'));bus=pd.read_csv(file);p=pd.read_csv(file.with_name('load_profile.csv')).pivot(index='timestamp',columns='bus_id',values='p_kw').loc[:'2021-12-31 23:00:00'];t=p.iloc[:31440]
bus['training_mean_kw']=bus.bus_id.map(t.mean());bus['train_only_reanchor_factor']=bus.base_p_kw/bus.training_mean_kw.replace(0,np.nan);bus.to_csv(A/'bus_profiles.csv',index=False)
series={f'Bus_{i:02}':p[i].to_numpy().copy() for i in p};series['Distributed_Total']=np.sum(list(series.values()),axis=0)
sh=S.groupby('dataset').dataset_sha256.first();rows=[]
for k,v in series.items():
 h=hashlib.sha256(np.asarray(v,dtype='<f8').tobytes()).hexdigest();a=pd.read_csv(next(R.glob('*/'+k+'/*/hourly_comparison.csv'))).actual.to_numpy();vtrain=v[:31440];rows.append(dict(dataset=k,recorded_sha256=sh[k],computed_sha256=h,match=h==sh[k],training_weekly_mae=np.abs(vtrain[168:]-vtrain[:-168]).mean(),holdout_max_abs_diff=abs(v[31440:]-a).max()))
# Independent evidence for the separate modeled PV file is bundled for replay without the supplementary source kit.
prev=pd.read_csv(Path(__file__).with_name('supplementary_pv_hash.csv'));pd.concat([pd.DataFrame(rows),prev],ignore_index=True).to_csv(A/'source_fingerprints.csv',index=False)
N=pd.read_csv(A/'neural_rollout.csv')
for i,row in N.iterrows():
 log=next(R.glob(f'*/{row.dataset}/{row.model}*/job_output.log')).read_text(errors='replace')
 trials=re.findall(r'Trial (\d+) finished with value: ([\d.eE+\-]+) and parameters: (\{[^}]+\})',log)
 if trials:
  b=min(trials,key=lambda x:float(x[1]));N.at[i,'best_logged_trial']=int(b[0]);N.at[i,'best_logged_validation_loss']=float(b[1]);N.at[i,'best_logged_parameters']=json.dumps(ast.literal_eval(b[2]))
N.to_csv(A/'neural_rollout.csv',index=False)
inv=[]
for f in sorted(Path('work').rglob('*')):
 if f.is_file():inv.append((str(f.relative_to('work')),f.stat().st_size,hashlib.sha256(f.read_bytes()).hexdigest()))
pd.DataFrame(inv,columns=['archive_member','uncompressed_bytes','sha256']).to_csv(A/'inventory.csv',index=False)
