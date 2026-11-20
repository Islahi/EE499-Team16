"""Run from the analysis workspace. Read extracted archives under work/ and audited CSVs under audit_tables/."""
from pathlib import Path
import pandas as pd,numpy as np,json,shutil
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor
R=Path('work/results');O=Path('C2_Analysis');C=Path('cache');A=Path('audit_tables')
W={'mae':5,'rmse':5,'wape_percent':5,'mase_weekly':2,'abs_bias':4,'smape_percent':3}
fields=list(W);rk=[x+'_rank' for x in W]
def dest(k):
 return O/({'Cohort_Residential':'01_Residential','Cohort_Commercial':'02_Commercial','Cohort_Manufacturing':'03_Manufacturing','Cohort_SumOfMeterLoads':'04_Aggregate_Load','Bilbao_Modeled_PV':'06_Bilbao_PV'}.get(k,'05_15Bus/'+k))
def csv(df,path):
 path.parent.mkdir(parents=True,exist_ok=True);df.to_csv(path,index=False)
def main():
 J=pd.read_csv(A/'job_audit.csv');r=pd.read_csv(R/'all_model_statuses.csv')
 df=pd.DataFrame()
 df=J[J.has_forecast & J.correct_calendar.eq(True) & J.finite.eq(True) & J.rows.eq(8760)].copy()
 df['config']=df.model+'__'+df.seasonality;df['abs_bias']=df.bias_actual_minus_forecast.abs()
 for m in W:df[m+'_rank']=df.groupby('dataset')[m].transform(lambda a:a.map(lambda x:float(f'{x:.10g}')).rank())
 df['score']=sum(w*df[m+'_rank'] for m,w in W.items())/24
 df['rank']=df.groupby('dataset').score.rank(method='min');df=df.sort_values(['dataset','score','config'])
 df['bias_direction']=np.select([df.bias_actual_minus_forecast>1e-12,df.bias_actual_minus_forecast< -1e-12],['underforecast','overforecast'],default='balanced')
 df['peak_memory_mb']=np.nan
 neural=pd.read_csv(A/'neural_rollout.csv')[['dataset','model','training_and_tuning_seconds','rollout_seconds']]
 df=df.merge(neural,on=['dataset','model'],how='left');df['timing_note']=np.where(df.training_and_tuning_seconds.notna(),'Fit field bundles prediction; see neural stage times',np.where(df.source_group=='new_optimized','Fit field bundles tuning, fitting and prediction','Recorded stage timings'))
 cols=['dataset','rank','config','model','seasonality','unit','score',*W,'bias_actual_minus_forecast','bias_direction',*rk,'fit_seconds','forecast_seconds','model_seconds','wall_seconds','peak_memory_mb','training_and_tuning_seconds','rollout_seconds','timing_note','status','warning_count']
 df=df[cols];D=df.dropna(subset=['score']).copy();T=D.groupby('dataset').head(5).copy()
 def candidate(x):
  ranks=x[rk].to_numpy(float);lo=int(ranks.argmin());hi=int(ranks.argmax());return f'{fields[lo]} rank {ranks[lo]:g}; {fields[hi]} rank {ranks[hi]:g}; {x.bias_direction}.'
 T['evidence']=T.apply(candidate,axis=1);T['limitation']=T.dataset.map(lambda s:'One of three shared sector shapes; full-period feeder scaling.' if s.startswith('Bus') or s=='Distributed_Total' else ('Modeled PV, with zero-output nighttime hours.' if s.startswith('Bilbao') else 'Retrospective 2021 selection; fixed cohort and variable meter availability.'))
 F=O/'07_Overall_Rankings';csv(df,F/'configuration_rankings.csv');csv(T,O/'10_Recommendations/top_five.csv')
 b=D.pivot(index='config',columns='dataset',values='score')
 G=b.filter(regex='^Bus_').mean(axis=1); overall=pd.DataFrame({'bus_mean':G,'residential':b.Cohort_Residential,'commercial':b.Cohort_Commercial,'manufacturing':b.Cohort_Manufacturing,'aggregate':b.Cohort_SumOfMeterLoads,'pv':b.Bilbao_Modeled_PV})
 overall['score']=(overall.residential+overall.commercial+overall.manufacturing+3*overall['aggregate']+2*G+overall.pv)/9
 overall['rank']=overall.score.rank(method='min');overall=overall.sort_values('score').reset_index();csv(overall,F/'overall.csv')
 for k,z in df.groupby('dataset'):
  csv(z,dest(k)/'rankings.csv');csv(T[T.dataset==k],dest(k)/'top_five.csv')
 J['coverage_pct']=J.rows.fillna(0)*100/8760;csv(J,O/'00_Overview/job_inventory.csv')
 csv(J[~J.has_forecast][['dataset','model','seasonality','status','reason','coverage_pct']],O/'09_Failed_and_Incomplete/failed.csv')
 csv(J[J.has_forecast & (J.rows<8760)][['dataset','model','seasonality','rows','coverage_pct']],O/'09_Failed_and_Incomplete/partial_coverage.csv')
 for f in ['inventory','plan_reconciliation','warnings','neural_rollout','source_fingerprints']:shutil.copyfile(A/(f+'.csv'),O/'00_Overview'/(f+'.csv'))
 bus=pd.read_csv(A/'bus_profiles.csv');raw=pd.read_csv(next(Path('work').rglob('load_profile.csv')));year=raw[raw.timestamp.str.startswith('2021')];P=year.pivot(index='timestamp',columns='bus_id',values='p_kw');E=P.sum()
 for i,row in bus.iterrows():
  v=int(row.bus_id);bus.loc[i,['energy_2021_kwh','energy_share_pct','min_kw','max_kw','min_kvar','max_kvar']]=[E[v],100*E[v]/E.sum(),raw.loc[raw.bus_id==v,'p_kw'].min(),raw.loc[raw.bus_id==v,'p_kw'].max(),raw.loc[raw.bus_id==v,'q_kvar'].min(),raw.loc[raw.bus_id==v,'q_kvar'].max()]
 V=O/'05_15Bus/Dataset_Validation';csv(bus,V/'bus_energy_and_profiles.csv')
 pairs=pd.read_csv(A/'bus_pair_comparisons.csv');full=raw.pivot(index='timestamp',columns='bus_id',values='p_kw')
 for i,row in pairs.iterrows():
  aa=full[int(row.bus_a)].to_numpy();bb=full[int(row.bus_b)].to_numpy()
  if np.any(aa):
   factor=np.sum(aa*bb)/np.sum(aa*aa);pairs.loc[i,['factor_b_from_a','max_abs_scaled_residual_kw']]=[factor,abs(bb-aa*factor).max()]
 csv(pairs,V/'bus_pairs.csv')
 # Full numeric exports and cached arrays for figures. Give each target a single actual column.
 def prepare(y):
  k,z=y;z=z.sort_values('config');arr=[];ids=z.config.tolist()
  for cfg in ids:
   file=next(R.glob('*/'+k+'/'+cfg+'/hourly_comparison.csv'));f=pd.read_csv(file);arr.append(f.forecast.values)
  values=np.vstack([f.actual.values,*arr]);np.save(C/(k+'.npy'),values);(C/(k+'.json')).write_text(json.dumps(['Actual',*ids]))
  wide=pd.DataFrame(values.T,columns=['actual',*ids]);wide.insert(0,'dataset',k);wide.insert(0,'timestamp',f.timestamp);csv(wide,dest(k)/'hourly_forecasts.csv')
 with ThreadPoolExecutor(max_workers=5) as pool:list(pool.map(prepare,df.groupby('dataset')))
 def yhat(k,cfg):
  return np.load(C/(k+'.npy'),mmap_mode='r')[json.loads((C/(k+'.json')).read_text()).index(cfg)]
 universal=G.idxmin();sectors={'residential':'Cohort_Residential','commercial':'Cohort_Commercial','manufacturing':'Cohort_Manufacturing'};winners=T.groupby('dataset').first().config
 tt=np.load(C/'Distributed_Total.npy')[0];den=pd.read_csv(A/'source_fingerprints.csv').set_index('dataset').at['Distributed_Total','training_weekly_mae']
 sr=[];detail=[]
 for strategy in 'ABCD':
  forecasts=[];score=[];times=[];dedup={}
  for row in bus[bus.bus_id!=1].itertuples():
   k=f'Bus_{row.bus_id:02}';cfg=universal if strategy=='A' else (winners[k] if strategy=='C' else winners[sectors[row.category]])
   cc=D[(D.dataset==k)&(D.config==cfg)].iloc[0];forecasts.append(yhat(k,cfg));score.append(cc.score);times.append(cc.model_seconds);dedup.setdefault((row.category,cfg),cc.model_seconds);detail.append(dict(strategy=strategy,dataset=k,category=row.category,config=cfg,bus_score=cc.score,bus_rank=cc['rank'],model_seconds=cc.model_seconds))
  ff=np.sum(forecasts,axis=0);e=tt-ff;ab=abs(e);sr.append(dict(strategy=strategy,mean_bus_score=np.mean(score),mae=ab.mean(),rmse=np.sqrt(np.mean(e**2)),wape_percent=100*ab.sum()/abs(tt).sum(),mase_weekly=ab.mean()/den,bias_actual_minus_forecast=e.mean(),smape_percent=200*np.mean(ab/(abs(tt)+abs(ff))),all_bus_model_seconds=sum(times),three_representative_job_seconds=sum(dedup.values()),configuration_count=len(set(x['config'] for x in detail if x['strategy']==strategy))))
 csv(pd.DataFrame(sr),O/'08_Strategy_Comparison/strategies.csv');csv(pd.DataFrame(detail),O/'08_Strategy_Comparison/bus_selections.csv')
 print(overall.head().to_string(index=False));print(T.groupby('dataset').config.apply(list).to_string());print(pd.DataFrame(sr).to_string(index=False))
if __name__=='__main__':main()
