"""Create readable separate load/PV ranking and seasonal accuracy charts.
https://github.com/Islahi/EE499-Team16.git
"""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,default=ROOT/'C2_full_history_results')
    args=p.parse_args()
    result=args.results
    if not (result/'all_model_scores.csv').is_file():
        raise SystemExit('Benchmark metrics unavailable: run run_c2_full_history.py first')
    scores=pd.read_csv(result/'all_model_scores.csv')
    scores=scores[scores.status=='OK']
    plotdir=result/'plots';plotdir.mkdir(exist_ok=True)
    for (category,dataset),group in scores.groupby(['category','dataset']):
        g=group.copy().sort_values('rmse_kw')
        if g.empty:continue
        label=(category+'_'+dataset).replace('/','_')
        short=g.head(15).copy()
        names=[f'{r.model} / {r.seasonality}' for r in short.itertuples()]
        fig,ax=plt.subplots(figsize=(11,max(5,len(short)*.35)))
        ax.barh(np.arange(len(short)),short.rmse_kw.to_numpy())
        ax.set_yticks(np.arange(len(short)),names,fontsize=8)
        ax.invert_yaxis();ax.set_xlabel('RMSE (kW), lower is better')
        ax.set_title(f'{dataset}: 15 lowest-RMSE configurations')
        fig.tight_layout();fig.savefig(plotdir/f'{label}_rmse_ranking.png',dpi=165);plt.close(fig)
        short=g.head(15).copy()
        names=[f'{r.model} / {r.seasonality}' for r in short.itertuples()]
        fig,ax=plt.subplots(figsize=(11,max(5,len(short)*.35)))
        ax.barh(np.arange(len(short)),short.total_model_seconds.to_numpy()/60)
        ax.set_yticks(np.arange(len(short)),names,fontsize=8)
        ax.invert_yaxis();ax.set_xlabel('Model fit + forecast time (minutes)')
        ax.set_title(f'{dataset}: timing of 15 most accurate configurations')
        fig.tight_layout();fig.savefig(plotdir/f'{label}_runtime.png',dpi=165);plt.close(fig)
        winner=g.iloc[0]
        result_path=result/category/dataset/f'{winner.model}__{winner.seasonality}'
        csv=result_path/'hourly_comparison.csv'
        if not csv.is_file():continue
        hourly=pd.read_csv(csv,parse_dates=['timestamp'])
        by_month=hourly.set_index('timestamp').resample('MS')[['actual_kw','forecast_kw']].mean()
        fig,ax=plt.subplots(figsize=(12,5))
        ax.plot(by_month.index,by_month.actual_kw,label='Actual')
        ax.plot(by_month.index,by_month.forecast_kw,label=f'{winner.model} / {winner.seasonality}')
        ax.set_ylabel('Mean hourly demand / modelled PV power (kW)')
        ax.set_title(f'{dataset}: monthly means (best RMSE configuration)')
        ax.legend();ax.grid(alpha=.25);fig.tight_layout()
        fig.savefig(plotdir/f'{label}_monthly_actual_vs_forecast.png',dpi=165);plt.close(fig)
        print(f'Plots: {label}; best RMSE={winner.rmse_kw:.2f} kW',flush=True)

if __name__=='__main__':main()
