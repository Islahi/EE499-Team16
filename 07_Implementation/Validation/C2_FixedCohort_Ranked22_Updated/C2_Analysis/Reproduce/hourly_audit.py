from pathlib import Path
import numpy as np,pandas as pd,json,collections,hashlib,zipfile, re
r=Path('work/results'); out=Path('audit_tables');out.mkdir(exist_ok=True)
root=next(Path('work').rglob('bus_summary.csv')).parent
s=pd.read_csv(r/'all_model_statuses.csv')
h=pd.date_range('2021-01-01',periods=8760,freq='h');H=h.astype(str).to_numpy()
l=pd.read_csv(root/'load_profile.csv');p=l.pivot(index='timestamp',columns='bus_id',values='p_kw');q=l.pivot(index='timestamp',columns='bus_id',values='q_kvar');pv=pd.read_csv(root/'pv_profile.csv')
train=p.loc[:'2020-12-31 23:00:00']; T=p.loc[H]; summary=pd.read_csv(root/'bus_summary.csv').set_index('bus_id')
def sha(x):return hashlib.sha256(x.read_bytes()).hexdigest()
print('load extent',len(p),p.index[[0,-1]],len(l),l.isna().sum().to_dict(),l.duplicated(['timestamp','bus_id']).sum(),p.isna().sum().sum(),len(pd.date_range(p.index[0],p.index[-1],freq='h').difference(pd.to_datetime(p.index))))
print('train',len(train),'pv',pv.shape,pv.bus_id.unique(),pv.isna().sum().sum(),pv.duplicated(['bus_id','timestamp']).sum(),np.array_equal(pv.timestamp.to_numpy(),p.index.to_numpy()),pv[['p_kw','q_kvar']].abs().max().to_dict())
print('duplicate load',sha(root/'load_profile.csv')==sha(root/'distributed_load_from_NEW_cohort.csv'))
print('means',train[[2,3,4]].mean(),p[[2,3,4]].mean());print('Q diff', (q - p.mul(summary.base_q_kvar.div(summary.base_p_kw).fillna(0))).abs().max().max())
busdat={f'Bus_{j:02}':T[j].to_numpy() for j in T};busdat['Distributed_Total']=T.sum(axis=1).to_numpy()
tr={f'Bus_{j:02}':train[j].to_numpy() for j in train};tr['Distributed_Total']=train.sum(axis=1).to_numpy()
allactual={}; ref_pred={}; summary_metrics=[]; warnings=[]; logkeys=collections.Counter(); monthlybad=[]; rankbad=[]; metadataerrors=[]; recursive=[]
mw={'mae':1,'rmse':1,'wape_percent':2,'mase_weekly':3,'abs_bias':2,'smape_percent':1}
def errmet(a,f):
 e=a-f; ab=np.abs(e); tot=np.abs(a).sum();den=np.abs(a)+np.abs(f)
 return dict(mae=ab.mean(),rmse=np.sqrt(np.mean(e*e)),wape_percent=100*ab.sum()/tot if tot else np.nan,bias_actual_minus_forecast=e.mean(),smape_percent=200*np.divide(ab,den,out=np.zeros_like(a),where=den!=0).mean())
for i,x in s.iterrows():
 folder=r/x.result_path.replace('\\','/');j=json.loads((folder/'run_metrics.json').read_text());log=(folder/'job_output.log').read_text(errors='replace');ws=json.loads((folder/'warnings.json').read_text())
 for w in ws:warnings.append(dict(dataset=x.dataset,model=x.model,seasonality=x.seasonality,**w))
 for word in ['error','failed','traceback','warning','abnormal','fallback','non-finite','terminated','converg','overflow','stopped early','singular','deprecated']:
  if word in log.lower(): logkeys[word]+=1
 if x.status!=j['status']:metadataerrors.append((x.result_path,'status'))
 d=dict(dataset=x.dataset,model=x.model,seasonality=x.seasonality,status=x.status,warning_count=x.warning_count)
 if x.status=='FAILED':
  d.update(has_forecast=(folder/'hourly_comparison.csv').exists());summary_metrics.append(d);continue
 z=pd.read_csv(folder/'hourly_comparison.csv');a=z.actual.to_numpy();f=z.forecast.to_numpy();e=a-f;n=len(a); dt=z.timestamp.to_numpy()
 config=json.loads((folder/'fitted_configuration.json').read_text());info=config['auto_fit_info']
 if x.model in ('AutoNHITS','AutoNBEATSx'):
  recursive.append(dict(dataset=x.dataset,model=x.model,**{k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in info.items()},logged_trials=log.count(' finished with value:')))
 m=errmet(a,f)
 if x.dataset in tr:
  b=tr[x.dataset];den=np.mean(np.abs(b[168:]-b[:-168]));m['mase_weekly']=m['mae']/den if den else np.nan
 mx=max(abs(m[k]-x[k])/max(1,abs(x[k])) for k in m if np.isfinite(x[k]))
 same=np.max(np.abs(a-allactual.setdefault(x.dataset,a)));external=np.max(np.abs(a-busdat[x.dataset])) if x.dataset in busdat else np.nan
 d.update(has_forecast=True,rows=n,correct_calendar=np.array_equal(dt,H),finite=np.isfinite(z.iloc[:,1:]).all().all(),actual_drift=same,actual_vs_bus_kw=external,metric_max_relative_discrepancy=mx,error_column_max_difference=np.abs(e-z.actual_minus_forecast).max(),forecast_min=f.min(),forecast_max=f.max(),actual_max=a.max(),negative_saved=(f<0).sum(),negative_reported=x.negative_forecast_values,above_cap_reported=x.above_pv_cap,night_reset_reported=x.nighttime_predictions_set_zero,unique_forecasts=len(np.unique(f)),forecast_std=f.std(),actual_std=a.std(),first_week_forecast_mean=f[:168].mean(),last_week_forecast_mean=f[-168:].mean(),last_week_rmse=np.sqrt(np.mean(e[-168:]**2)),first_week_rmse=np.sqrt(np.mean(e[:168]**2)),peak_ratio=f.max()/a.max() if a.max() else np.nan,model_seconds=x.model_seconds,wall_seconds=x.wall_seconds,**{k:x[k] for k in ['mae','rmse','wape_percent','mase_weekly','bias_actual_minus_forecast','smape_percent','annual_energy_error_percent','peak_error_kw']})
 if x.dataset.startswith('Bus_') and x.dataset!='Bus_01':
  cat=summary.at[int(x.dataset[-2:]),'category'];key=(cat,x.model,x.seasonality);d['forecast_diff_from_first_peer_kw']=np.max(abs(f-ref_pred.setdefault(key,f)))
 if x.dataset=='Bilbao_Modeled_PV':d.update(positive_forecasts_on_actual_zero=((f>0)&(a==0)).sum(),positive_forecasts_on_actual_positive=((f>0)&(a>0)).sum())
 mon=pd.read_csv(folder/'monthly_metrics.csv')
 if len(mon)!=12 or list(mon.month)!=[f'2021-{v:02}' for v in range(1,13)]:monthlybad.append(x.result_path)
 else:
  for k,ar in [('rmse',e*e),('mae',abs(e))]:
   vals=np.add.reduceat(ar,(h.dayofyear[(h.day==1)&(h.hour==0)].to_numpy()-1)*24)/(h.days_in_month[(h.day==1)&(h.hour==0)].to_numpy()*24)
   if k=='rmse':vals=np.sqrt(vals)
   if not np.allclose(vals,mon[k],rtol=1e-8,atol=1e-8):monthlybad.append((x.result_path,k))
 summary_metrics.append(d)
D=pd.DataFrame(summary_metrics);D.to_csv(out/'job_audit.csv',index=False);pd.DataFrame(warnings).to_csv(out/'warnings.csv',index=False);pd.DataFrame(recursive).to_csv(out/'neural_rollout.csv',index=False)
g=D[D.has_forecast].copy()
print('audit',g.correct_calendar.value_counts(),g.finite.value_counts(),g[['actual_drift','actual_vs_bus_kw','error_column_max_difference','metric_max_relative_discrepancy']].max(), 'monthly errors',len(monthlybad),'meta',metadataerrors,'logkeys',logkeys)
print('metric issues',g.nlargest(10,'metric_max_relative_discrepancy')[['dataset','model','seasonality','metric_max_relative_discrepancy']])
# verify scores/prerank/plan indexes
key=['dataset','model','seasonality']
for fp in list(r.glob('*scores.csv'))+list(r.glob('rankings/*/*.csv')):
 zz=pd.read_csv(fp);joined=zz.merge(s,on=key,suffixes=('','_global'),how='left',validate='one_to_one')
 for k in ['mae','rmse','wape_percent','mase_weekly','bias_actual_minus_forecast','smape_percent']:
  if k in zz and not np.allclose(joined[k],joined[k+'_global'],equal_nan=True):rankbad.append((str(fp),k))
print('score inconsistent',rankbad[:10])
# pair differences full horizon
pairs=[]
for i in range(1,16):
 for j in range(i+1,16):
  aa=p[i].to_numpy();bb=p[j].to_numpy();row=dict(bus_a=i,bus_b=j,category_a=summary.at[i,'category'],category_b=summary.at[j,'category'],max_abs_kw=np.abs(aa-bb).max())
  if i!=1:
   xx=aa/aa.mean()-bb/bb.mean();row.update(pearson=np.corrcoef(aa,bb)[0,1],normalized_rmse=np.sqrt(np.mean(xx**2)),normalized_max_abs=np.abs(xx).max())
  pairs.append(row)
P=pd.DataFrame(pairs);P.to_csv(out/'bus_pair_comparisons.csv',index=False)
print(P[P.bus_a.isin([2,3,4])&P.bus_b.isin([3,4,5])].to_string(index=False))
for c,bus in [('Residential',2),('Commercial',3),('Manufacturing',4)]:
 a=allactual['Cohort_'+c]; y=T[bus].to_numpy();factor=np.dot(a,y)/np.dot(a,a);print(c,'factor',factor,'maxerr',abs(factor*a-y).max(),'2021 corr',np.corrcoef(a,y)[0,1])
pvactual=allactual['Bilbao_Modeled_PV'];print('pv zeros',sum(pvactual==0),'peak',pvactual.max())
