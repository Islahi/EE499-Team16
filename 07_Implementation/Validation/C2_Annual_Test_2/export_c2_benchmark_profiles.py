"""Export one measured model/season forecast into EE499 project/plotter CSVs.
This is retrospective: selecting a winner by the test-year score is NOT valid model selection.
https://github.com/Islahi/EE499-Team16.git
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import c2_benchmark_settings as S
from c2_benchmark_core import TRAIN_CLOCK, TEST_CLOCK
from c2_inputs import write_profile


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',required=True,help='e.g. B_GoiEner_Distributed_15Bus or PV_040d42N_003d70W')
    p.add_argument('--model',required=True,choices=S.MODELS)
    p.add_argument('--seasonality',required=True,choices=S.SEASONALITIES)
    a=p.parse_args()
    category='pv' if a.dataset.startswith('PV_') else 'load'
    folder=S.OUTPUT/category/a.dataset/f'{a.model}__{a.seasonality}'
    path=folder/'hourly_comparison.csv'
    if not path.exists(): raise FileNotFoundError(f'Run that job first: {path}')
    data=pd.read_csv(path,parse_dates=['timestamp'])
    if not pd.DatetimeIndex(data.timestamp).equals(TEST_CLOCK):
        raise ValueError('Forecast timestamp mismatch')
    output=folder/'project_compatible_profiles'
    output.mkdir(exist_ok=True)
    if category=='pv':
        # PV output is calculated from NASA GHI and a 490 kW reference array, not measured output.
        obs={S.PV_BUS_ID:data.actual_kw.to_numpy(dtype=float)}
        pred={S.PV_BUS_ID:data.forecast_kw.to_numpy(dtype=float)}
        zeros={S.PV_BUS_ID:np.zeros(len(TEST_CLOCK))}
        write_profile(output/'actual_pv_profile.csv',TEST_CLOCK,obs)
        write_profile(output/'forecast_pv_profile.csv',TEST_CLOCK,pred)
        write_profile(output/'actual_load_profile.csv',TEST_CLOCK,zeros)
        write_profile(output/'forecast_load_profile.csv',TEST_CLOCK,zeros)
    else:
        source=S.DATA_LOAD/a.dataset/'load_profile.csv'
        raw=pd.read_csv(source,parse_dates=['timestamp'])
        history=raw[(raw.timestamp>=TRAIN_CLOCK[0])&(raw.timestamp<=TRAIN_CLOCK[-1])]
        observed=raw[(raw.timestamp>=TEST_CLOCK[0])&(raw.timestamp<=TEST_CLOCK[-1])]
        buses=sorted(raw.bus_id.unique())
        # Train-only time-of-day distribution; preserve aggregate predictions exactly.
        history=history.copy()
        history['hour']=history.timestamp.dt.hour
        hp=history.pivot_table(index='bus_id',columns='hour',values='p_kw',aggfunc='mean').reindex(index=buses,columns=range(24)).fillna(0)
        hq=history.pivot_table(index='bus_id',columns='hour',values='q_kvar',aggfunc='mean').reindex(index=buses,columns=range(24)).fillna(0)
        hours=TEST_CLOCK.hour.to_numpy()
        average=hp.to_numpy(float)
        weights=average[:,hours]
        total=weights.sum(axis=0)
        shares=np.divide(weights,total[None,:],out=np.zeros_like(weights),where=total[None,:]>0)
        # For zero-history hour (rare), use each bus's overall mean share.
        zero=total<=0
        if np.any(zero):
            overall=average.mean(axis=1)
            overall=overall/overall.sum()
            shares[:,zero]=overall[:,None]
        expected=np.asarray(data.forecast_kw,dtype=float)
        forecast_p=shares*expected[None,:]
        ratio=np.divide(hq.to_numpy(float),average,out=np.zeros_like(average),where=average>0)
        forecast_q=forecast_p*ratio[:,hours]
        pp={bus:forecast_p[i] for i,bus in enumerate(buses)}
        pq={bus:forecast_q[i] for i,bus in enumerate(buses)}
        write_profile(output/'forecast_load_profile.csv',TEST_CLOCK,pp,pq)
        obs_p,obs_q={},{}
        for b in buses:
            sub=observed[observed.bus_id==b].sort_values('timestamp')
            if not pd.DatetimeIndex(sub.timestamp).equals(TEST_CLOCK):
                raise ValueError(f'Bus {b} missing timestamps')
            obs_p[b]=sub.p_kw.to_numpy(float)
            obs_q[b]=sub.q_kvar.to_numpy(float)
        write_profile(output/'actual_load_profile.csv',TEST_CLOCK,obs_p,obs_q)
        zeros={min(buses):np.zeros(len(TEST_CLOCK))}
        write_profile(output/'actual_pv_profile.csv',TEST_CLOCK,zeros)
        write_profile(output/'forecast_pv_profile.csv',TEST_CLOCK,zeros)
        assert np.allclose(forecast_p.sum(axis=0),expected), 'Bus allocation did not preserve total demand'
    print('Project CSVs exported:',output)
    print('Load and PV profile pairs can be used with the original C2 plot_profiles.py')


if __name__=='__main__':main()
