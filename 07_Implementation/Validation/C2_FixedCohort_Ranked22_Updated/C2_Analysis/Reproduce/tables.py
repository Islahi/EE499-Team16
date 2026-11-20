from numerical import *
from itertools import product
J=pd.read_csv(O/'00_Overview/job_inventory.csv');g=pd.read_csv(O/'07_Overall_Rankings/configuration_rankings.csv');t=pd.read_csv(O/'10_Recommendations/top_five.csv')
v=O/'05_15Bus/Dataset_Validation';st=pd.read_csv(O/'08_Strategy_Comparison/strategies.csv');fail=pd.read_csv(O/'09_Failed_and_Incomplete/failed.csv')
units=['dataset','model','seasonality','unit'];metrics=units+['mae','rmse','wape_percent','mase_weekly','bias_actual_minus_forecast','abs_bias','smape_percent','bias_direction']
tim=units+['status','fit_seconds','forecast_seconds','model_seconds','wall_seconds','training_and_tuning_seconds','rollout_seconds','peak_memory_mb','timing_note']
for k,z in g.groupby('dataset'):
 csv(z[metrics],dest(k)/'error_metrics.csv');csv(z[tim],dest(k)/'runtime.csv')
 # Add coverage records for clipped calendar weeks and complete power/energy intervals.
 dates=pd.date_range('2021-01-01',periods=8760,freq='h');periods=[]
 for freq in ['D','W-SUN','M']:
  for p,count in pd.Series(dates.to_period(freq)).value_counts().sort_index().items():
   expected=int((p.end_time.floor('h')-p.start_time)/pd.Timedelta(hours=1))+1
   periods.append(dict(dataset=k,period=str(p),resolution=freq,first_included=max(dates[0],p.start_time),last_included=min(dates[-1],p.end_time.floor('h')),hours=count,calendar_period_hours=expected,coverage_pct=100*count/expected))
 csv(pd.DataFrame(periods),dest(k)/'period_coverage.csv')
overall=pd.read_csv(O/'07_Overall_Rankings/overall.csv')
tested=set(zip(g.model,g.seasonality));untested=[dict(model=m,seasonality=s,status='Outside selected design; no job recorded') for m,s in product(sorted(g.model.unique()),sorted(g.seasonality.unique())) if (m,s) not in tested]
csv(pd.DataFrame(untested),O/'09_Failed_and_Incomplete/outside_selected_grid.csv')
topnotes=[]
for _,row in t.iterrows():
  best=min(row[k+'_rank'] for k in W);worst=max(row[k+'_rank'] for k in W)
  names={'mae':'MAE','rmse':'RMSE','wape_percent':'WAPE','mase_weekly':'MASE','abs_bias':'absolute bias','smape_percent':'sMAPE'}
  topnotes.append({**row.to_dict(),'strength':', '.join(names[k] for k in W if row[k+'_rank']==best)+f' ranked {best:g}/69','weakness':', '.join(names[k] for k in W if row[k+'_rank']==worst)+f' ranked {worst:g}/69' if best!=worst else 'Leads every official metric; one held-out year.'})
t=pd.DataFrame(topnotes);csv(t,O/'10_Recommendations/top_five.csv')
for k,z in t.groupby('dataset'):csv(z,dest(k)/'top_five.csv')
def frame(d):return pd.DataFrame(d)
status=J.groupby(['dataset','status']).size().unstack(fill_value=0).reset_index();status['skipped']=0;status['incomplete']=0
sheets={
'Summary':frame({'Measure':['Successful annual jobs','OK','OK with captured warnings','Failed (all zero-load slack)','Recorded skips','Partial annual traces','Nonzero datasets','Configurations per nonzero target','Forecast rows verified','Overall winner','Approval status'],'Result':[1444,964,480,5,0,0,20,69,12649440,overall.config.iloc[0],'Recommendations pending team approval']}),
'Top five':t[['dataset','rank','config','score','unit','mae','rmse','wape_percent','mase_weekly','bias_actual_minus_forecast','smape_percent','fit_seconds','forecast_seconds','model_seconds','wall_seconds','timing_note']],
'Overall ranking':overall,'Strategy comparison':st,'Recommendations':t[['dataset','rank','config','score','strength','weakness','limitation','bias_direction']],
'Full ranking':g[['dataset','rank','config','unit',*['mae_rank','rmse_rank','wape_percent_rank','mase_weekly_rank','abs_bias_rank','smape_percent_rank'],'score']],
'Error metrics':g[metrics],'Execution times':g[tim],'Bus allocations':pd.read_csv(v/'bus_energy_and_profiles.csv'),'Profile similarity':pd.read_csv(v/'bus_pairs.csv'),'Bus strategy choices':pd.read_csv(O/'08_Strategy_Comparison/bus_selections.csv'),'Completion':status,
'Job inventory':J[['dataset','model','seasonality','status','rows','coverage_pct','correct_calendar','finite','warning_count','dataset_sha256']],
'Failed and incomplete':fail,'Outside selected grid':pd.DataFrame(untested),'Neural rollout':pd.read_csv(O/'00_Overview/neural_rollout.csv')[['dataset','model','neural_strategy_version','forecast_blocks','forecast_horizon_per_block_hours','forecast_context_hours','training_and_tuning_seconds','rollout_seconds','best_logged_parameters']],
'Method':frame({'Topic':['Source archives','Repository','Time interval','Unit','Ranking','Dataset weights','Rank ties','Coverage','Runtime','PV and slack','Load scaling','Strategy convention','Reproducibility'],'Definition':['results_Ranked22(1).7z and 15-Busses Case(3).zip','https://github.com/Islahi/EE499-Team16','31,440 training hours through 2020; all 8,760 hours of 2021 evaluated.','Sector cohorts use kW/customer; other targets use kW.','Metric weights in rank-column order: 5, 5, 5, 2, 4, 3.','Weights 1 each for three sectors and PV, 3 for meter sum and 2 shared equally among 14 loaded buses.','Average metric ranks at 10 significant digits. Equal scores share competition rank.','Blank WAPE/MASE at the zero slack bus; no official score. No partial series.','Blank peak memory means unrecorded. Custom models bundle prediction in fit field.','Separate modeled PV. Feeder PV placeholder is zero.','Sector profile divided by full-period mean, then multiplied by each bus base load.','A universal; B category; C bus-specific; D category defaults, with zero supported exceptions.','Workbook is a fixed-run analysis. Use the packaged scripts to recompute official rankings from changed inputs.']})}
C.mkdir(exist_ok=True)
(C/'workbook.json').write_text(json.dumps({k:[list(d.columns),*json.loads(d.to_json(orient='values',double_precision=15))] for k,d in sheets.items()},allow_nan=False))
