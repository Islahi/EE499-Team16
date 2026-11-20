"""Create separate load/PV score rankings, run status summaries, charts."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import c2_config as C

def make_reports():
    root=C.OUTPUT
    rows=[]
    for file in sorted(root.glob('*/*/*/run_metrics.json')):
        r=json.loads(file.read_text(encoding='utf-8'))
        r.pop('traceback',None)
        r['relative_result_path']=str(file.parent.relative_to(root))
        rows.append(r)
    if not rows:print('No job records');return
    df=pd.DataFrame(rows)
    df.to_csv(root/'model_comparison_all_statuses.csv',index=False)
    status=df.status.value_counts()
    lines=['# C2 full-history, annual 2021 benchmark','',
       'One forecast of 8,760 hours for 2021 from 2017-06-01 through 2020-12-31 training.',
       'Results are after nonnegative and (for PV) physical night/rating constraints. Warning-containing results remain visible.',
       'Model fits were normalized to mean≈1; AutoTBATS used Box-Cox=False and ARMA errors=False for stability.',
       'NASA PV output is modeled, GoiEner sector load profiles are per-customer or variable-cohort totals, and the 15-bus profile is constructed.',
       'All results are exploratory test-year comparisons. Do not choose a model on this test year then claim independent accuracy.','',
       '## Status counts','',status.to_string(),'']
    for category in ('load','pv'):
        section=df[df.category==category].copy()
        if section.empty:continue
        section.to_csv(root/f'{category}_all_statuses.csv',index=False)
        good=section[section.status.isin(['OK','OK_WITH_WARNINGS'])].copy()
        if good.empty:continue
        good=good.sort_values(['dataset','rmse','model_seconds'])
        good.to_csv(root/f'{category}_model_scores.csv',index=False)
        good['rank_by_rmse']=good.groupby('dataset').rmse.rank(method='first')
        good.to_csv(root/f'{category}_rankings.csv',index=False)
        lines.extend([f'## {category.upper()} best recorded runs (lowest RMSE)',''])
        for name,group in good.groupby('dataset'):
            winner=group.iloc[0]
            lines.append(f'- {name}: {winner.model} / {winner.seasonality}: RMSE={winner.rmse:.3f} {winner.unit}; '
               f'MAE={winner.mae:.3f}; WAPE={winner.wape_percent:.2f}%; '
               f'fit+forecast={winner.model_seconds:.2f}s; warnings={winner.warning_count}.')
            top=group.head(12)
            fig,ax=plt.subplots(figsize=(10,5))
            ax.barh([f'{r.model} {r.seasonality}' for r in top.itertuples()][::-1],top.rmse.iloc[::-1]);
            ax.set_xlabel(f'Full-year RMSE ({winner.unit})');ax.set_title(f'C2 model comparison — {name}')
            fig.tight_layout()
            dest=root/category/name/'rmse_top_models.png';fig.savefig(dest,dpi=140);plt.close(fig)
            best_file=root/category/name/(winner.model+'__'+winner.seasonality)/'hourly_comparison.csv'
            if best_file.exists():
                h=pd.read_csv(best_file,parse_dates=['timestamp'])
                mon=h.groupby(h.timestamp.dt.to_period('M'))[['actual','forecast']].mean()
                fig,ax=plt.subplots(figsize=(11,4.5))
                ax.plot(mon.index.astype(str),mon.actual.values,marker='o',label='Actual')
                ax.plot(mon.index.astype(str),mon.forecast.values,marker='o',label='Forecast')
                ax.set_ylabel(f'Monthly mean ({winner.unit})');ax.legend();ax.tick_params(axis='x',rotation=45)
                fig.tight_layout();fig.savefig(root/category/name/'monthly_means_best.png',dpi=140);plt.close(fig)
        lines.append('')
    (root/'benchmark_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Saved load/PV score tables, statuses, plots:',root)
if __name__=='__main__':make_reports()
