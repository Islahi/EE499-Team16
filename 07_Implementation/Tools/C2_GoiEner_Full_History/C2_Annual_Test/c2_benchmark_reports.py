"""Summarize independently measured 8,784-hour C2 benchmark results."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import c2_benchmark_settings as S


def build_reports(root=None):
    root=Path(root or S.OUTPUT)
    rows=[]
    for path in sorted(root.glob('*/*/*/run_metrics.json')):
        d=json.loads(path.read_text(encoding='utf-8'))
        d.pop('traceback',None)
        rows.append(d)
    if not rows:
        print('No completed benchmark jobs yet; results tables not generated.')
        return
    all_rows=pd.DataFrame(rows)
    all_rows.to_csv(root/'model_comparison_all_statuses.csv',index=False)
    for category in ('load','pv'):
        sub=all_rows[all_rows.category==category].copy()
        if sub.empty:continue
        sub.to_csv(root/f'{category}_model_comparison_all_statuses.csv',index=False)
        ok=sub[sub.status=='OK'].copy()
        if ok.empty:continue
        ok=ok.sort_values(['dataset','rmse_kw','total_model_seconds'])
        ok.to_csv(root/f'{category}_model_scores.csv',index=False)
        ranked=ok.copy()
        ranked['rank_by_test_rmse_for_analysis_only'] = ranked.groupby('dataset')['rmse_kw'].rank(method='first')
        ranked.to_csv(root/f'{category}_rankings_by_dataset.csv',index=False)
        for ds, subset in ok.groupby('dataset'):
            best=subset.nsmallest(10,'rmse_kw')
            fig,ax=plt.subplots(figsize=(11,5.6))
            labels=[f'{r.model} [{r.seasonality}]' for r in best.itertuples()]
            ax.barh(labels[::-1],best.rmse_kw.to_numpy()[::-1])
            ax.set_xlabel('Full-year RMSE (kW; lower is better)')
            ax.set_title(f'Best measured forecasts — {ds}')
            fig.tight_layout()
            dest=root/category/ds
            fig.savefig(dest/'rmse_top_10.png',dpi=140)
            plt.close(fig)
            fig,ax=plt.subplots(figsize=(9,5.2))
            ax.scatter(subset.total_model_seconds,subset.rmse_kw,alpha=.75)
            for r in subset.itertuples():
                if r.Index in best.index:
                    ax.annotate(f'{r.model} {r.seasonality}',(r.total_model_seconds,r.rmse_kw),fontsize=7)
            ax.set_xlabel('Model fit + forecast time (seconds; lower is faster)')
            ax.set_ylabel('Full-year RMSE (kW; lower is better)')
            ax.set_title(f'Accuracy vs runtime — {ds}')
            fig.tight_layout()
            fig.savefig(dest/'accuracy_vs_time.png',dpi=140)
            plt.close(fig)
            winner=best.iloc[0]
            data_file=dest/f'{winner.model}__{winner.seasonality}'/'hourly_comparison.csv'
            if data_file.exists():
                sample=pd.read_csv(data_file,parse_dates=['timestamp'])
                sample['month']=sample.timestamp.dt.to_period('M')
                monthly=sample.groupby('month',sort=True)[['actual_kw','forecast_kw']].mean()
                fig,ax=plt.subplots(figsize=(12,5))
                ax.plot(monthly.index.astype(str),monthly.actual_kw,marker='o',label='Actual')
                ax.plot(monthly.index.astype(str),monthly.forecast_kw,marker='o',label=f'{winner.model} {winner.seasonality}')
                ax.set_ylabel('Monthly mean power (kW)')
                ax.set_title(f'Annual seasonal shape — {ds} (post-hoc best in held-out test)')
                ax.tick_params(axis='x',rotation=45)
                ax.legend()
                fig.tight_layout()
                fig.savefig(dest/'best_monthly_profile.png',dpi=140)
                plt.close(fig)
    pv=all_rows[(all_rows.category=='pv')&(all_rows.status=='OK')].copy()
    if not pv.empty:
        # Only report category-wide rankings for variants with all 5 solar sites complete.
        nsites=all_rows[all_rows.category=='pv'].dataset.nunique()
        grp=pv.groupby(['model','seasonality'],as_index=False).agg(
            sites_completed=('dataset','nunique'),
            mean_site_mae_kw=('mae_kw','mean'),mean_site_rmse_kw=('rmse_kw','mean'),
            mean_site_wape_percent=('wape_percent','mean'),
            mean_site_mase=('mase_weekly','mean'),mean_site_bias_kw=('bias_kw_actual_minus_forecast','mean'),
            mean_site_fit_seconds=('fit_seconds','mean'),mean_site_forecast_seconds=('forecast_seconds','mean'))
        grp['all_sites_complete']=grp.sites_completed.eq(nsites)
        grp=grp.sort_values(['all_sites_complete','mean_site_rmse_kw'],ascending=[False,True])
        grp.to_csv(root/'pv_models_mean_across_sites.csv',index=False)
    # Simple textual report, explicitly not production model selection.
    lines=['# C2 — full-year benchmark status and comparison','',
           'These results compare full-year forecasts generated once from historical data. '
           'The post-hoc test-year ranking is for evaluation, not production model selection.','',
           'Positive Bias = actual minus predicted: systematic underprediction.','',
           'MASE denominator is the training-only same-hour-previous-week MAE.','',
           'Models unable to fit a long season are marked SKIPPED_UNSUPPORTED; failures remain visible.','']
    if 'status' in all_rows:
        lines.extend(['## Job status','',all_rows.status.value_counts().to_string(),''])
    for cat in ('load','pv'):
        c=all_rows[(all_rows.category==cat)&(all_rows.status=='OK')].copy()
        if c.empty:continue
        lines.extend([f'## {cat.upper()} — best held-out RMSE by dataset',''])
        for ds, g in c.groupby('dataset'):
            w=g.sort_values('rmse_kw').iloc[0]
            lines.append(f'- **{ds}**: {w.model} / {w.seasonality}: RMSE {w.rmse_kw:.3f} kW, '
                         f'MAE {w.mae_kw:.3f} kW, WAPE {w.wape_percent:.2f}%, '
                         f'MASE {w.mase_weekly:.3f}, Bias {w.bias_kw_actual_minus_forecast:+.3f} kW, '
                         f'fit + predict {w.total_model_seconds:.2f} s')
        lines.append('')
    (root/'C2_benchmark_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(f'Comparison reports updated: {root}')


if __name__=='__main__':
    build_reports()
