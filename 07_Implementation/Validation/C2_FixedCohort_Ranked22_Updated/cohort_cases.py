"""C2 data ingestion: fixed cohort category series and OPTIONAL new distributed buses.

Never treat a historical distributed file as having been regenerated from the new cohort.
The user explicitly supplies it after using the load distributor GUI.
"""
from __future__ import annotations
import argparse,json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd

TRAIN_START=pd.Timestamp('2017-06-01 00:00:00')
TEST_START=pd.Timestamp('2021-01-01 00:00:00')
TEST_END=pd.Timestamp('2021-12-31 23:00:00')
TRAIN=pd.date_range(TRAIN_START, TEST_START-pd.Timedelta(hours=1),freq='h')
TEST=pd.date_range(TEST_START,TEST_END,freq='h')
ALL=TRAIN.append(TEST)
WIDE={'Residential':'Residential-GoiEner-Aggregate','Commercial':'Commercial-GoiEner-Aggregate',
      'Manufacturing':'Industrial-GoiEner-Aggregate'}


def _aligned(df,value,name):
    sub=df[['timestamp',value]].copy()
    sub['timestamp']=pd.to_datetime(sub.timestamp,errors='raise')
    if sub.timestamp.dt.tz is not None:raise ValueError(f'{name}: timezone-aware timestamp; use one consistent source clock')
    if sub.timestamp.duplicated().any():raise ValueError(f'{name}: duplicate timestamp')
    y=sub.set_index('timestamp')[value].reindex(ALL)
    if y.isna().any():
        first=y.index[y.isna()][0]
        raise ValueError(f'{name}: {int(y.isna().sum())} missing hours including {first}; check cohort coverage')
    a=y.to_numpy(float)
    if not np.isfinite(a).all() or np.min(a)<-1e-9:raise ValueError(f'{name}: invalid/nonfinite/negative power')
    return a


def _write(name,category,unit,data,folder,source,notes):
    folder.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(folder/f'{name}.npz',train=data[:len(TRAIN)],actual=data[len(TRAIN):])
    return {'name':name,'category':category,'unit':unit,'source':str(source),
            'dataset_sha256':hashlib.sha256(np.asarray(data,dtype='<f8').tobytes()).hexdigest(),
            'notes':notes,'training_hours':len(TRAIN),'forecast_hours':len(TEST)}


def prepare(cohort:Path,output:Path,pv:Path|None=None,distributed:Path|None=None):
    cases=output/'prepared_cases';cases.mkdir(parents=True,exist_ok=True)
    meta=[]
    wide_file=cohort/'goiener_distributor_ready.csv'
    if not wide_file.exists():raise FileNotFoundError('Run 01_build_common_cohort first: '+str(wide_file))
    wide=pd.read_csv(wide_file)
    for label,col in WIDE.items():
        series=_aligned(wide,col,'Cohort_'+label)
        meta.append(_write('Cohort_'+label,'load','kW/customer',series,cases,wide_file,
          'Mean over available cohort customers; customer ID set fixed, hourly availability may vary'))
    sector_sums=[]
    for sector in ('residential','commercial','manufacturing'):
        src=cohort/f'{sector}.csv'
        df=pd.read_csv(src,usecols=['timestamp','load_kw'])
        y=_aligned(df,'load_kw',sector)
        sector_sums.append(y)
    combined=np.sum(sector_sums,axis=0)
    meta.append(_write('Cohort_SumOfMeterLoads','load','kW',combined,cases,cohort,
      'Sum of available fixed-cohort meter readings; not scaled network demand'))
    if distributed:
        dist=pd.read_csv(distributed,usecols=['timestamp','bus_id','p_kw'])
        if dist.duplicated(['timestamp','bus_id']).any():raise ValueError('Distributed: duplicate (timestamp,bus_id)')
        found=sorted(dist.bus_id.unique())
        if len(found)<2:raise ValueError('Distributed: expected multiple bus IDs')
        allbus=[]
        for bus in found:
            subset=dist[dist.bus_id==bus]
            series=_aligned(subset,'p_kw',f'Bus_{bus}')
            meta.append(_write(f'Bus_{int(bus):02d}','load','kW',series,cases,distributed,
              'Direct bus time series; input MUST come from the new cohort distributor run'))
            allbus.append(series)
        total=np.sum(allbus,axis=0)
        meta.append(_write('Distributed_Total','load','kW',total,cases,distributed,
          'Sum of bus loads in user-supplied DISTRIBUTED file'))
    if pv:
        solar=pd.read_csv(pv)
        if 'p_kw' not in solar.columns:raise ValueError('Solar CSV needs p_kw')
        y=_aligned(solar,'p_kw','Bilbao_PV')
        lat=float(solar.site_lat.iloc[0]) if 'site_lat' in solar else None
        lon=float(solar.site_lon.iloc[0]) if 'site_lon' in solar else None
        row=_write('Bilbao_Modeled_PV','pv','kW',y,cases,pv,
          'NASA POWER solar-derived PV output, not measured PV; source timestamps may be UTC')
        row.update(lat=lat,lon=lon,cap_kw=490.0)  # original C2 illustrative PV rating
        meta.append(row)
    config={'train_start':str(TRAIN[0]),'train_end':str(TRAIN[-1]),'test_start':str(TEST[0]),
      'test_end':str(TEST[-1]),'train_hours':len(TRAIN),'test_hours':len(TEST),
      'cases':meta,'distributed_provenance_warning':'Only specify --distributed when it was regenerated from the NEW cohort profiles',
      'source_clock_warning':'NASA and GoiEner clocks may differ; aligned timestamp labels alone do not establish same physical instant'}
    (cases/'cases.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    print('Prepared:',[(r['name'],r['unit']) for r in meta])
    print(f'Train {len(TRAIN):,} h, forecast {len(TEST):,} h')
    return config

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cohort',type=Path,default=Path('cohort_output'))
    p.add_argument('--output',type=Path,default=Path('.'))
    p.add_argument('--pv',type=Path);p.add_argument('--distributed',type=Path)
    a=p.parse_args();prepare(a.cohort,a.output,a.pv,a.distributed)
