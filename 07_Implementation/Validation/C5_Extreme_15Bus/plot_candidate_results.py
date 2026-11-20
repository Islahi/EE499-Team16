"""Visualize results of the actual exhaustive 126-candidate network simulations."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
ROOT=Path(__file__).resolve().parent
RESULTS=ROOT/'C5_results'

def main():
    df=pd.read_csv(RESULTS/'exhaustive_candidates.csv')
    feasible=df[df.feasible == True]
    grouped=feasible.groupby('bess_bus',sort=True).cost_usd_per_year.min()
    fig,ax=plt.subplots(figsize=(10,4.8))
    ax.plot(grouped.index,grouped.values/1e6,'o-',linewidth=1.6,label='Lowest-cost feasible size at each bus')
    ax.scatter([grouped.idxmin()],[grouped.min()/1e6],s=85,marker='*',zorder=5,label='Global optimum')
    ax.legend()
    ax.set_xticks(range(2,16))
    ax.set(title='Best feasible annualized cost by battery location',xlabel='Battery bus',ylabel='Annualized model cost (million USD/year)')
    ax.grid(axis='y',alpha=.2);fig.tight_layout()
    fig.savefig(RESULTS/'best_cost_by_bus.png',dpi=175)
    plt.close(fig)
    counts=feasible.groupby('bess_bus').size().reindex(range(2,16),fill_value=0)
    fig,ax=plt.subplots(figsize=(10,4.8))
    ax.bar(counts.index,counts.values,color='#7092a8')
    ax.axhline(9,color='gray',ls=':',label='9 configurations per location')
    ax.set_xticks(range(2,16));ax.set_ylim(0,10)
    ax.set(title='Feasible configurations by installation bus',xlabel='Battery bus',ylabel='Feasible configurations (out of 9)')
    ax.grid(axis='y',alpha=.2);ax.legend();fig.tight_layout()
    fig.savefig(RESULTS/'feasible_candidates_by_bus.png',dpi=175)
    plt.close(fig)

if __name__=='__main__':main()
