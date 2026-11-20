from prepare import *
from charts import render,D,S,E,time_ticks
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
V=OUT/'05_15Bus/Dataset_Validation'
raw=pd.read_csv(next(Path('work').rglob('load_profile.csv')));p=raw.pivot(index='timestamp',columns='bus_id',values='p_kw');p.index=pd.to_datetime(p.index);p=p.drop(columns=1)
fig,ax=plt.subplots(figsize=(10,6),layout='constrained');img=ax.imshow(p.corr(),vmin=0,vmax=1,cmap='viridis');ax.set_xticks(range(14),p.columns);ax.set_yticks(range(14),p.columns);ax.set_xlabel('Bus ID');ax.set_ylabel('Bus ID');fig.colorbar(img,ax=ax,label='Pearson correlation');ax.set_title('Pairwise load correlation across the 14 loaded buses\nJune 2017 – June 2022');fig.savefig(V/'Bus_Pearson_Correlation.png',dpi=170);plt.close(fig)
q=p.loc['2021-07-01 00:00:00':'2021-07-14 23:00:00'];vs=(q[[2,3,4]]/p[[2,3,4]].mean()).to_numpy().T
render(V/'Bus_Normalized_Load_Hourly_14Days.png','15-bus feeder','Three sector demand profiles','01–14 July 2021   /   336 observations   /   normalized by full-period bus mean',vs,['Residential / bus 2','Commercial / bus 3','Manufacturing / bus 4'],'Load / mean load','Date in 2021',time_ticks(np.arange(S,E)),dict(axes=1,chart='normalized_load',input_hours=336,start=str(D[S]),end=str(D[E-1])),colors=[2,3,4])
# Retain the factual report sections and replace its display-specific sections and sources.
src=Path('scripts/report.py').read_text();src=src.replace('from numerical import *','from prepare import *\nO=OUT\nC=Path("cache")\nselected=json.loads((TMP/"selection.json").read_text())\ndef dest(k):return OUT/selected[k]["folder"]')
src=src[:src.index('def figs():')]+src[src.index("for name,f in [('Body'"):]
src=src.replace("'00_Overview/C2_Analysis_Report.pdf'","'00_Overview/C2_Analysis_Report.pdf'")
src=src.replace('and static plot sheets for every available forecast.','and separate single-chart PNGs for every available forecast. The standard hourly windows all span July 1–14, 2021. Start with README_DASHBOARD.md or START_DASHBOARD.bat.')
src=src.replace('Zooms show hourly data.', 'Standard hourly plots show the same July 1–14 interval (336 hours). Additional error-selected zooms carry their own dates.')
src=src.replace("z=top[top.dataset==k];y=page(label);y=para(y,note);u=z.unit.iloc[0];y=heading(y,'Top five hourly configurations')","z=pd.read_csv(dest(k)/'arima_comparison.csv').set_index('config',drop=False).loc[selected[k]['names'][1:]];y=page(label);y=para(y,note);u=z.unit.iloc[0];y=heading(y,'Design baseline and three leading candidates')")
src=src.replace('Chart colors follow the table order after the dark actual trace.','Ranks and errors use all 8,760 hours. AutoARIMA D is the design baseline.')
a=src.index(' for j,name in enumerate(');b=src.index(" y=heading(y,'Recorded execution",a)
src=src[:a]+""" y=image(y,dest(k)/'PNG/Main_Comparison/Forecast_Hourly_14Days.png',211)
 gain=z.iloc[1];y=para(y,f'The leading candidate reduces full-year MAE by {gain.improvement_mae_pct:.1f}% and RMSE by {gain.improvement_rmse_pct:.1f}% relative to daily AutoARIMA.',9.1)
"""+src[b:]
src=src.replace("y=image(y,O/'05_15Bus/Dataset_Validation/Bus_profile_similarity.png',216)","y=image(y,O/'05_15Bus/Dataset_Validation/Bus_Pearson_Correlation.png',216)")
src=src.replace('All 69 eligible configurations have full group coverage.', 'All 69 have full group coverage. The main figures reserve one trace for AutoARIMA__daily, which matches the repository’s 24-hour default. The three candidate slots exclude AutoARIMA variants and jobs explicitly tagged as baseline controls. Official ranks retain every eligible configuration.')
exec(compile(src,'revised_report','exec'))
