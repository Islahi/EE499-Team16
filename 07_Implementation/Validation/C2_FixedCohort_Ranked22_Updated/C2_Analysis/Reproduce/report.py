from numerical import *
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.utils import simpleSplit
from datetime import date
from textwrap import shorten
import calendar
top=pd.read_csv(O/'10_Recommendations/top_five.csv');overall=pd.read_csv(O/'07_Overall_Rankings/overall.csv');strat=pd.read_csv(O/'08_Strategy_Comparison/strategies.csv');profiles=pd.read_csv(O/'05_15Bus/Dataset_Validation/bus_energy_and_profiles.csv');times=pd.read_csv(O/'07_Overall_Rankings/configuration_rankings.csv')
CATS=['Cohort_Residential','Cohort_Commercial','Cohort_Manufacturing','Cohort_SumOfMeterLoads','Bus_02','Bus_03','Bus_04','Distributed_Total','Bilbao_Modeled_PV']
labels=['Residential cohort','Commercial cohort','Manufacturing cohort','Three-sector meter total','Residential buses','Commercial buses','Manufacturing buses','Direct feeder forecast','Bilbao modeled PV']
notes=['CalendarRidge has the lowest MAE, RMSE, WAPE, MASE and sMAPE. The yearly seasonal baseline ties FourierOLS on the weighted score and requires only a repeated seasonal trace.',
'XGBoost ranks first on all six measures. The calendar-only regression is a much faster fifth option. The source series is mean load per available cohort customer.',
'LightGBM has the lowest MAE, while XGBoost lowers the RMSE. This distinction matters when assigning more importance to larger hourly errors.',
'XGBoost has the lowest hourly MAE and RMSE. Yearly SeasonalNaive has a smaller annual bias. AutoNBEATSx enters the top five here despite its weaker performance elsewhere.',
'Buses 2, 5, 10 and 13 have identical load histories and predictions. The table uses bus 2 timings. Individual timings for all four buses appear in the workbook.',
'Buses 3, 8, 9, 12 and 14 have identical load histories and predictions. The table uses bus 3 timings. XGBoost wins every metric at every commercial bus.',
'Buses 4, 6, 7, 11 and 15 have identical load histories and predictions. Timings below are for bus 4. AutoTBATS took over 16 minutes for this particular fit.',
'MSTL wins the weighted comparison through its low signed bias. LightGBM has smaller MAE, RMSE, WAPE, MASE and sMAPE and runs faster. This direct fit is a separate comparison from the sum of bus forecasts.',
'XGBoost wins four metrics. LightGBM has the lowest sMAPE. All-hour PV sMAPE includes 4,353 zero nighttime hours. XGBoost daylight-only sMAPE is 52.85%.']
dates=pd.date_range('2021-01-01',periods=8760,freq='h')
palette=['#203c4b','#008571','#c05d20','#8267a0','#417ab1','#b04764']
def shortse(s):return {'daily_weekly_monthly_yearly':'D/W/M/Y','daily_weekly_monthly':'D/W/M','daily_weekly':'D/W','monthly_30d':'M','yearly_365d':'Y','weekly':'W','daily':'D'}[s]
def figs():
 for k in CATS:
  z=top.query('dataset==@k');arr=np.load(C/(k+'.npy'));ids=json.loads((C/(k+'.json')).read_text());names=['Actual',*z.config];fig,ax=plt.subplots(2,1,figsize=(8.5,3.65),layout='constrained');u=z.unit.iloc[0]
  for name,c in zip(names,palette):
   v=arr[ids.index(name)];a=pd.Series(v,index=dates);m=a.resample('MS').mean();ax[0].plot(m.index.month,m,color=c,lw=1.4);q=a.loc['2021-07-12':'2021-07-18'];ax[1].plot(q.index,q,color=c,lw=1.05)
  ax[0].set_xticks(range(1,13),[calendar.month_abbr[i] for i in range(1,13)]);ax[1].set_xticks(pd.date_range('2021-07-12',periods=7),['Mon 12','Tue 13','Wed 14','Thu 15','Fri 16','Sat 17','Sun 18'])
  for a,t in zip(ax,['Monthly mean power · full year','Hourly power · July 12–18']):
   a.set_title(t,loc='left',fontsize=10,weight='bold');a.set_ylabel(u,fontsize=8);a.tick_params(labelsize=8);a.grid(axis='y',alpha=.25);a.spines[['right','top']].set_visible(False)
  fp=dest(k)/'Top_five_forecast_review.png';fig.savefig(fp,dpi=140);plt.close(fig)
 raw=pd.read_csv(next(Path('work').rglob('load_profile.csv')));p=raw.pivot(index='timestamp',columns='bus_id',values='p_kw');p.index=pd.to_datetime(p.index);p=p.iloc[:,1:];v=O/'05_15Bus/Dataset_Validation'
 fig,ax=plt.subplots(1,2,figsize=(10,4.6),layout='constrained',gridspec_kw={'width_ratios':[1,1.4]});corr=p.corr();img=ax[0].imshow(corr,vmin=0,vmax=1,cmap='viridis');ax[0].set_xticks(range(0,14,2),list(p.columns[::2]));ax[0].set_yticks(range(0,14,2),list(p.columns[::2]));ax[0].set_xlabel('Bus ID');ax[0].set_ylabel('Bus ID');fig.colorbar(img,ax=ax[0],shrink=.7);ax[0].set_title('Full-history Pearson correlation',fontsize=11)
 for i,lab,col in [(2,'Residential',palette[1]),(3,'Commercial',palette[2]),(4,'Manufacturing',palette[3])]:
  yy=p.loc['2021-07-12':'2021-07-18',i]/p[i].mean();ax[1].plot(yy.values,label=lab,color=col,lw=1.4)
 ax[1].set_xlabel('Hour from July 12, 2021');ax[1].set_ylabel('Load / full-period mean');ax[1].set_title('Three distinct normalized profiles',fontsize=11);ax[1].legend(frameon=False,fontsize=8);ax[1].grid(alpha=.2);fig.savefig(v/'Bus_profile_similarity.png',dpi=150);plt.close(fig)
figs()
for name,f in [('Body','DejaVuSans.ttf'),('Strong','DejaVuSans-Bold.ttf')]:pdfmetrics.registerFont(TTFont(name,'/usr/share/fonts/truetype/dejavu/'+f))
file=O/'00_Overview/C2_Analysis_Report.pdf';c=Canvas(str(file),pagesize=A4);w,h=A4;c.setTitle('EE499 C2 • Forecast evaluation and model selection');pg=0
def text(x,y,s,size=10,bold=False,color='#1c3441'):
 c.setFillColor(HexColor(color));c.setFont('Strong' if bold else 'Body',size);c.drawString(x,y,str(s))
def page(title):
 global pg
 if pg:c.showPage()
 pg+=1;c.setFillColor(HexColor('#103c49'));c.rect(0,h-79,w,79,fill=1,stroke=0);text(34,h-28,'EE499  /  TEAM 16     •     C2 FORECAST EVALUATION',9,True,'#b9e0d9');text(34,h-60,title,21,True,'#ffffff');text(34,22,'2021 hourly holdout  •  Engineering validation and model selection',8,False,'#546b71');text(w-56,22,str(pg),9,True);return h-104
def para(y,s,size=10,width=w-68,leading=15):
 for l in simpleSplit(s,'Body',size,width):text(34,y,l,size);y-=leading
 return y-9
def heading(y,s):text(34,y,s,13,True,'#00786b');return y-22
def table(y,headers,rows,widths,sz=8.4):
 for i,row in enumerate([headers,*rows]):
  c.setFillColor(HexColor('#e2efec' if i==0 else ('#f3f6f6' if i%2==0 else '#ffffff')));c.rect(34,y-6,sum(widths),20,fill=1,stroke=0);x=39
  for vv,ww in zip(row,widths):text(x,y,str(vv),sz,i==0);x+=ww
  y-=20
 return y-8
def f(x):return f'{x:,.3f}' if abs(x)<1 else f'{x:,.2f}'
def image(y,fp,height):
 c.drawImage(str(fp),34,y-height,w-68,height,preserveAspectRatio=True,anchor='c');return y-height-14
y=page('Benchmark inventory and decision')
y=table(y,['Archive','Files','Contents'],[['C2 benchmark','8,889','21 datasets · 18 families · 69 configurations'],['15-bus case','10','Load profiles, bus mappings, settings and zero PV placeholder']],[141,47,335]);y=heading(y,'1,444 complete forecasts')
y=para(y,'The archive contains 964 OK jobs, 480 successful jobs with captured warnings, five failures, zero recorded skips and zero incomplete forecasts. All successful exports have exactly 8,760 finite predictions aligned to the hourly calendar. The union of eight plans has 1,447 jobs. Two older failed slack-bus neural records bring the archive-wide count to 1,449.')
y=heading(y,'Provisional selection')
y=para(y,'Use CalendarRidge for residential demand, XGBoost for commercial demand and LightGBM for manufacturing demand. Use XGBoost independently for Bilbao PV. All four choices use the daily/weekly/monthly/yearly configuration. XGBoost leads the overall ranking; LightGBM leads the universal load-only bus comparison.')
y=table(y,['Forecast strategy','Feeder MAE (kW)','Feeder RMSE (kW)','WAPE (%)'],[['Universal LightGBM','144.79','212.63','11.72'],['Three sector winners','139.69','207.33','11.31']],[177,115,125,104])
y=para(y,'The 14 loaded buses contain three distinct time series. Category-specific selections produce the same hourly output as individual bus selection on this case. Independent spatial validation and a strictly prospective preprocessing check remain open. Selections require team approval before integration.')
y=heading(y,'How to use the deliverables')
para(y,'The PDF compares representative forecasts, finalists, runtimes and deployment strategies. The workbook gives the full-precision rankings and per-bus timings. The standalone dashboard supports arbitrary zoom and exact configuration selection. Each dataset folder contains full hourly CSV data and static plot sheets for every available forecast.')
y=page('Protocol, metrics and ranking')
y=para(y,'Training uses 31,440 hourly samples from June 1, 2017 through December 31, 2020. The 2021 target is a fixed-origin 8,760-hour forecast. The 22 retained configurations are joined by 42 additional optimized configurations, three baselines and two neural configurations. Configurations outside the saved design are untested. No missing forecast is imputed.')
for a,b in [('MAE and RMSE','Mean absolute residual and square root of mean squared residual. Residual = actual minus forecast. Both retain target units.'),('WAPE and sMAPE','WAPE = 100 × sum absolute error / sum absolute actual. sMAPE = mean of 200 × absolute error / max(absolute actual + absolute forecast, 1e−8).'),('MASE and bias','MASE = hourly test MAE / mean absolute training difference at lag 168. Signed bias is mean residual. Ranking uses its absolute magnitude. Percent WAPE and MASE are undefined for the zero slack target.'),('Hourly score','Within each dataset, assign ascending average ranks for ties (10 significant digits for numerical equivalence). Weighted score = (5 MAE rank + 5 RMSE rank + 5 WAPE rank + 2 MASE rank + 4 absolute-bias rank + 3 sMAPE rank) / 24. Equal scores share the minimum occupied final rank. Configuration ID orders tied display rows.'),('Overall score','Add the three individual cohort scores, three times the combined-meter score, twice the mean score across 14 loaded buses, and the Bilbao PV score. Divide by nine. Direct feeder total is reported separately. All 69 eligible configurations have full group coverage.'),('Reporting scales','Daily, Monday–Sunday weekly and calendar-month views use hourly means for power or sums × 1 hour for energy. Partial boundary weeks contain 72 and 120 hours. Calendar extremes use complete periods and mean absolute hourly error; equal errors use the first period. Zooms show hourly data.')]:
 y=heading(y,a);y=para(y,b)
y=page('Forecast integrity and neural runs')
y=para(y,'All 12,649,440 forecast rows were checked. No successful file contained an invalid value, duplicate hour or calendar gap. Monthly MAE and RMSE agreed with hourly recomputation. Saved annual MAE, RMSE, signed bias, WAPE and sMAPE agreed with recomputation. Weekly MASE was verified against training histories for the 15 buses, feeder total and separate modeled PV source. The four cohort scores use their archived MASE.')
y=heading(y,'Recursive rollout')
y=para(y,'AutoNHITS and AutoNBEATSx each completed all 20 nonzero cases with C2_NEURAL_RECURSIVE_W168_V1, NeuralForecast 3.1.9 on CPU, 672-hour model input, two Optuna trials, 2,880 training-era validation hours and 53 weekly blocks. Block 53 supplies the last 24 hours. The matching project drop-in appends earlier predictions, and all five causal/configuration tests passed. Future features are calendar coordinates. A source hash linking the local executable to the result files was unavailable.')
for model in ['AutoNHITS','AutoNBEATSx']:
 rr=overall[overall.config.str.startswith(model+'__')].iloc[0];y=para(y,f'{model} placed {int(rr["rank"])} of 69 overall (score {rr.score:.3f}). Full-year recursive performance varied by dataset. The log retained both trials for all 40 jobs, while selected-parameter JSON fields were empty.')
y=heading(y,'Warnings and failed records')
y=para(y,'100 AutoTBATS jobs reported overflow; 40 AutoARIMA fits recorded possible convergence and search-limit warnings; 21 FourierSARIMAX fits recorded convergence warnings. All 147 Prophet jobs completed despite missing optional interactive plotting support. Some logs contain general timestamp deprecations outside captured warnings. The common postprocessor recorded negative values in 207 jobs; final saved forecasts are nonnegative.')
y=para(y,'All five failures are at Bus 01. Weekly AutoCES recorded a missing model_ attribute. FourierSARIMAX yearly and four-period recorded unrealistic prediction scale. The two older neural runs recorded an unsupported cpus argument. No failed jobs were rerun. No partial traces exist for a separate partial-coverage comparison.')
y=heading(y,'Separate temporal risks')
para(y,'Full-period distributor normalization uses post-2020 observations. Possible interpolation across the cutoff cannot be resolved from the attachments. The archived worker and tests support causal prediction after the prepared data are supplied. Model selection in this analysis uses 2021 performance and needs confirmation on a later untouched interval.')
for k,label,note in zip(CATS,labels,notes):
 z=top[top.dataset==k];y=page(label);y=para(y,note);u=z.unit.iloc[0];y=heading(y,'Top five hourly configurations')
 y=table(y,['Rank','Configuration','Score','MAE','RMSE','WAPE %','MASE','Bias','sMAPE %'],[[int(v['rank']),v.model+' '+shortse(v.seasonality),f'{v.score:.3f}',f(v.mae),f(v.rmse),f'{v.wape_percent:.2f}',f'{v.mase_weekly:.3f}',f(v.bias_actual_minus_forecast),f'{v.smape_percent:.2f}'] for _,v in z.iterrows()],[28,130,45,51,51,51,43,55,67],7.9)
 y=para(y,'Power errors and bias in '+u+'. D/W/M/Y = daily, weekly, monthly and yearly. Chart colors follow the table order after the dark actual trace.',8.7,leading=12)
 for j,name in enumerate(['Actual',*z.model.tolist()]):text(36+j*86,y,name,8,True,palette[j])
 y=image(y-8,dest(k)/'Top_five_forecast_review.png',210)
 y=heading(y,'Recorded execution time in seconds')
 y=table(y,['Configuration','Fit field','Forecast field','Model total','Job wall'],[[v.model+' '+shortse(v.seasonality),f'{v.fit_seconds:.4f}',f'{v.forecast_seconds:.4f}',f'{v.model_seconds:.4f}',f'{v.wall_seconds:.4f}'] for v in z.itertuples()],[190,78,91,79,83],8)
 para(y,'A zero forecast field for custom optimized models can indicate bundled execution. Neural fit/tuning and rollout times are separately exported. Peak process memory was unavailable.',8.5,leading=12)
y=page('Overall ranking and practicality')
y=para(y,'The comparison uses the requested dataset weights and hourly metric weights. The first three configurations are boosted trees and Prophet. The best seasonal control is yearly SeasonalNaive. Runtime is secondary; no minimum gain or maximum duration was imposed.')
y=table(y,['Rank','Exact model and seasonality','Weighted score'],[[int(v['rank']),v.config,f'{v.score:.4f}'] for _,v in overall.head(15).iterrows()],[53,341,127],8.3)
y=heading(y,'Computational interpretation')
y=para(y,'At the cohort winners, model time was 1.75 s for residential CalendarRidge, 10.76 s for commercial XGBoost and 8.17 s for manufacturing LightGBM. The combined-meter and PV XGBoost fits took 13.43 s and 13.42 s. Four-period MSTL took 455.36 s on the direct feeder total. Neural families had median model times near 52 s. These machine-specific measures include fitting where recorded; they are not online inference benchmarks.')
para(y,'The exact stage times, wall time and warning counts are available per dataset and configuration. All successful model times sum to 21.52 job-hours, including 11.80 job-hours on the 11 repeated same-sector buses beyond one representative per sector.')
y=page('Feeder data and cross-archive evidence')
y=para(y,'The exporter produced 658,815 rows on 15 buses over 43,921 uninterrupted hours, June 1, 2017 through June 5, 2022. No missing values or duplicated bus–timestamp pairs were found. Load exports are byte-identical. Each row has timestamp, bus ID, P (kW) and Q (kvar). The PV file is a 43,921-row aligned zero placeholder at bus 1.')
y=table(y,['Group','Bus IDs','Base P / Q','2021 energy share'],[[a,ids,f'{bp:g} kW / {bq:g} kvar',f'{profiles[profiles.bus_id.isin(ii)].energy_share_pct.sum():.2f}%'] for a,ids,bp,bq,ii in [('Slack','1',0,0,[1]),('Residential','2, 5, 10, 13',44.1,45,[2,5,10,13]),('Commercial','3, 8, 9, 12, 14',70,71.4,[3,8,9,12,14]),('Manufacturing','4, 6, 7, 11, 15',140,142.8,[4,6,7,11,15])]],[100,142,143,136])
y=image(y,O/'05_15Bus/Dataset_Validation/Bus_profile_similarity.png',216)
y=para(y,'All 26 same-category active-bus pairs have zero raw and normalized differences. Cross-category correlations are 0.3201 residential/commercial, 0.2752 residential/manufacturing and 0.6941 commercial/manufacturing. Corresponding mean-normalized RMSE values are 0.5626, 0.6536 and 0.4972. The 105-pair CSV includes proportional-fit factors and maximum residuals. Slack correlation is undefined.')
y=para(y,'Input SHA-256 values reproduce all 40,200 training and test samples per bus and for the summed feeder. Actuals match each bus exactly. Each category cohort is proportional to its bus counterpart in 2021 to within 5.1e−9 kW. Every same-sector pair produced the same hourly output under all 69 configurations.')
para(y,'The feeder data validate the forecast pipeline and a three-template scenario. For distinct bus forecasting, use disjoint customer groups and fit scales using training data only. Distinct topology alone cannot establish independent demand shapes.')
y=page('Deployment comparison and decision')
y=para(y,'Strategy A chooses the single configuration with the lowest mean bus score. B selects the winner on each per-customer category and applies its configuration at mapped buses. C selects separately at each bus. D follows category defaults where no distinct bus evidence supports an exception. Each aggregate below sums the saved bus predictions before scoring.')
y=table(y,['Strategy','Bus score','MAE kW','RMSE kW','WAPE %','Bias kW','All fits s'],[[v.strategy,f'{v.mean_bus_score:.3f}',f'{v.mae:.2f}',f'{v.rmse:.2f}',f'{v.wape_percent:.2f}',f'{v.bias_actual_minus_forecast:.2f}',f'{v.all_bus_model_seconds:.2f}'] for v in strat.itertuples()],[77,72,81,89,76,62,64])
y=heading(y,'Prefer category-specific forecasting, subject to approval')
y=para(y,'Universal LightGBM is the simplest one-configuration option. Category-specific forecasting reduced feeder MAE by 5.10 kW and RMSE by 5.31 kW. It lowered absolute bias from 11.81 to 0.52 kW. Individual and hybrid choices produced exactly the same hourly totals as the category strategy. Additional per-bus model selection would add complexity without improving this case.')
y=para(y,'If identical inputs are reused, the three representative measured model times sum to 20.28 s for B versus 23.35 s for A. These are sums of exemplar job times, not measured end-to-end cached application performance. The full 14-bus job totals are in the table. The experiment stored no peak-memory telemetry.')
y=heading(y,'Conditions for final validation')
for txt in ['1. Freeze normalization and any interpolation at the forecast origin. Full-history scaling changes residential, commercial and manufacturing training means to 44.078, 68.926 and 137.148 kW relative to the full-period targets of 44.1, 70 and 140 kW.',
'2. Report three independent sector shapes for this case. Evaluate a disjoint-meter bus allocation if independent bus behavior is a required claim. Retain current profiles as the documented scenario.',
'3. Keep the Bilbao PV selection separate. The feeder file has no installed PV, and timestamp labels alone cannot establish the same physical clock for load and irradiance.',
'4. Freeze a shortlist before evaluating an untouched interval. Report failures, stage timings, raw and corrected outputs, and neural trial parameters with the next run. No deployment or simulation was performed.']:
 y=para(y,txt,9.3,leading=13)
y=heading(y,'Evidence')
para(y,'Primary evidence: both attached archives. Project source: github.com/Islahi/EE499-Team16, GoiEner_Load_Distributor_Simple/distribution_engine.py. The matching fixed-cohort worker kit and recursive drop-in supported the source checks; the results archive supplies the measurements.',8.7,leading=12)
c.save()
