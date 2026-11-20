from pathlib import Path
import os,json,shutil
import numpy as np,pandas as pd
SRC=Path('C2_Analysis');OUT=Path('deliver/C2_Analysis');TMP=Path('revcache')
BASE='AutoARIMA__daily'
KEYS=['mae','rmse','wape_percent','mase_weekly','abs_bias','smape_percent']
def folders(root):
 return {pd.read_csv(p,nrows=1).dataset.iloc[0]:p.parent for p in root.rglob('rankings.csv')}
def prepare():
 for p in SRC.rglob('*'):
  if p.is_file() and p.suffix!='.png' and 'PNG' not in p.parts and p.suffix not in ('.html','.pdf') and p.name!='README.md':
   q=OUT/p.relative_to(SRC);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
 lookup=folders(OUT);j=pd.read_csv(SRC/'00_Overview/job_inventory.csv');selections={};ev=[]
 for ds,folder in lookup.items():
  ids=json.loads(Path('cache',ds+'.json').read_text());a=np.load(Path('cache',ds+'.npy'),mmap_mode='r');assert BASE in ids
  z=pd.read_csv(folder/'rankings.csv');z['is_control']=z.config.isin((j[(j.dataset==ds)&(j.source_group=='baseline')].model+'__'+j[(j.dataset==ds)&(j.source_group=='baseline')].seasonality).tolist())|z.model.eq('AutoARIMA')
  zz=z[z.score.notna()&~z.is_control].sort_values(['score','config']).head(3)
  base=z[z.config.eq(BASE)].iloc[0];t=z.copy()
  for key in KEYS:
   t['improvement_'+key+'_pct']=100*(base[key]-t[key])/base[key] if pd.notna(base[key]) and base[key]!=0 else np.nan
  t['score_gain']=base.score-t.score;t['role']=np.select([t.config==BASE,t.config.isin(zz.config)],['ARIMA baseline','Top 3'],default='Other')
  t.to_csv(folder/'arima_comparison.csv',index=False);ev.extend(t[t.role!='Other'].to_dict('records'))
  selections[ds]={'names':['Actual',BASE,*zz.config.tolist()],'folder':str(folder.relative_to(OUT)),'unit':base.unit}
 pd.DataFrame(ev).to_csv(OUT/'10_Recommendations/ARIMA_and_top_three.csv',index=False)
 TMP.mkdir(exist_ok=True);(TMP/'selection.json').write_text(json.dumps(selections))
if __name__=='__main__':prepare()
