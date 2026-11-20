"""Produce a focused view of the artificially stressed PV/load profiles.

Called from run_c5.py, or independently after prepare_c5_inputs.py.
"""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parent
INPUT=ROOT/'inputs'/'hourly_input_summary.csv'
OUT=ROOT/'C5_results'


def main():
    OUT.mkdir(exist_ok=True)
    df=pd.read_csv(INPUT,parse_dates=['timestamp']).sort_values('timestamp')
    sample=df.iloc[:min(72,len(df))]
    fig,ax=plt.subplots(figsize=(11,4.6))
    ax.plot(sample.timestamp,sample.load_kw,label='Synthetic demand (160% of source)',linewidth=1.8)
    ax.plot(sample.timestamp,sample.pv_kw,label='Modeled PV (2MW nameplate)',linewidth=1.8)
    ax.fill_between(sample.timestamp,sample.pv_kw,sample.load_kw,
                    where=(sample.pv_kw.to_numpy()>sample.load_kw.to_numpy()),
                    alpha=.18,color='orange',label='PV exceeds total demand')
    ax.set(title='Extreme C5: hourly supply and demand (first 72 hours)',xlabel='Time',ylabel='Power (kW)')
    ax.legend();ax.grid(alpha=.2);fig.autofmt_xdate();fig.tight_layout()
    fig.savefig(OUT/'solar_surplus_first_72h.png',dpi=175)
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,4.6))
    ax.plot(df.timestamp,df.net_load_kw,lw=.9,label='Net demand = load − PV')
    ax.axhline(0,color='black',linewidth=.9)
    ax.fill_between(df.timestamp,0,df.net_load_kw,where=(df.net_load_kw.to_numpy()<0),
                    color='orange',alpha=.18,label='Aggregate solar surplus')
    ax.set(title='Extreme C5: signed net demand over the full horizon',xlabel='Time',ylabel='Net demand (kW)')
    ax.grid(alpha=.2);ax.legend();fig.autofmt_xdate();fig.tight_layout()
    fig.savefig(OUT/'net_load_and_surplus_full_horizon.png',dpi=175)
    plt.close(fig)
    print('Saved solar surplus plots under',OUT)

if __name__=='__main__':main()
