"""Inspect and load new distributed GoiEner, three-category means/sums, NASA PV files."""
from dataclasses import dataclass
import math
import numpy as np
import pandas as pd
import c2_config as C

TRAIN = pd.date_range(C.TRAIN_START, pd.Timestamp(C.TEST_START)-pd.Timedelta(hours=1), freq='h')
TEST = pd.date_range(C.TEST_START, C.TEST_END, freq='h')
ALL = TRAIN.append(TEST)

@dataclass
class Case:
    name: str
    category: str
    unit: str
    train: np.ndarray
    actual: np.ndarray
    source: str
    lat: float | None = None
    lon: float | None = None
    note: str = ''

def _split(frame, col, name):
    frame = frame[['timestamp',col]].copy()
    frame['timestamp'] = pd.to_datetime(frame.timestamp)
    if frame.timestamp.duplicated().any():
        raise ValueError(f'{name}: duplicated hourly timestamps')
    frame = frame.set_index('timestamp').sort_index()
    chosen = frame.reindex(ALL)
    if chosen[col].isna().any():
        bad=chosen.index[chosen[col].isna()]
        raise ValueError(f'{name}: {len(bad)} missing hours, first {bad[0]}')
    y=chosen[col].to_numpy(float)
    if not np.isfinite(y).all() or (y < -1e-8).any():
        raise ValueError(f'{name}: negative/nonfinite observations')
    return y[:len(TRAIN)],y[len(TRAIN):]

def cases():
    result=[]
    dist=pd.read_csv(C.DATA/'distributed_15bus_load.csv', usecols=['timestamp','bus_id','p_kw'])
    if dist.duplicated(['timestamp','bus_id']).any(): raise ValueError('Distributed data: duplicate bus/hour')
    if dist.bus_id.nunique()!=15: raise ValueError('Expected 15 buses')
    count=dist.groupby('timestamp').bus_id.nunique()
    if (count!=15).any():raise ValueError('Distributed data missing buses at some hours')
    byhour=dist.groupby('timestamp',sort=True).p_kw.sum().rename('power').reset_index()
    a,b=_split(byhour,'power','Distributed_15Bus_Load')
    result.append(Case('Distributed_15Bus_Load','load','kW',a,b,'data/distributed_15bus_load.csv',
      note='Constructed 15-bus feeder demand, category profiles scaled to reference bus means'))
    means=pd.read_csv(C.DATA/'goiener_category_means.csv')
    cols=[('Residential','Residential-GoiEner-Aggregate'),('Commercial','Commercial-GoiEner-Aggregate'),
          ('Manufacturing','Industrial-GoiEner-Aggregate')]
    for short,col in cols:
        a,b=_split(means,col,short)
        result.append(Case(f'GoiEner_{short}_PerMeter','load','kW/customer',a,b,
            'data/goiener_category_means.csv', note='Average consumption per active meter, not actual feeder demand'))
    sector_dfs=[]
    for sec,_ in [('residential','Residential'),('commercial','Commercial'),('manufacturing','Manufacturing')]:
        t=pd.read_csv(C.DATA/f'sector_{sec}.csv',usecols=['timestamp','load_kw','active_customers'])
        t=t.rename(columns={'load_kw':f'{sec}_kw','active_customers':f'{sec}_meters'})
        sector_dfs.append(t)
    merged=sector_dfs[0]
    for t in sector_dfs[1:]:merged=merged.merge(t,on='timestamp',how='inner',validate='one_to_one')
    merged['power']=merged[[f'{x}_kw' for x in ('residential','commercial','manufacturing')]].sum(axis=1,min_count=3)
    a,b=_split(merged,'power','GoiEner_ThreeSector_SummedMeters')
    result.append(Case('GoiEner_ThreeSector_SummedMeters','load','kW',a,b,
          'data/sector_{residential,commercial,manufacturing}.csv',
          note='Sum of sector hourly totals; customer population changes over time; not an actual feeder'))
    solar=pd.read_csv(C.DATA/'bilbao_nasa_pv.csv')
    required=['timestamp','p_kw','site_lat','site_lon','filled_hour']
    if not set(required).issubset(solar.columns):raise ValueError('NASA PV CSV missing columns')
    if solar.site_lat.nunique()!=1 or solar.site_lon.nunique()!=1:raise ValueError('Multiple NASA locations')
    a,b=_split(solar,'p_kw','Bilbao_Modelled_PV')
    lat,lon=float(solar.site_lat.iloc[0]),float(solar.site_lon.iloc[0])
    if not (np.max(np.r_[a,b])<=C.PV_RATED_KW + 1e-6):raise ValueError('PV exceeds rated power')
    result.append(Case('Bilbao_Modelled_PV','pv','kW',a,b,'data/bilbao_nasa_pv.csv',lat,lon,
        note='NASA POWER GHI converted to 490-kW illustrative PV, NOT measured PV generation; UTC'))
    return result

def daylight_utc(times, lat, lon):
    """Approximate sun-center-above-horizon (UTC) using known location/date only."""
    ix=pd.DatetimeIndex(times)
    day=ix.dayofyear.to_numpy(float)
    hour=ix.hour.to_numpy(float)+ix.minute.to_numpy(float)/60.0+0.5
    ndays=np.where(ix.is_leap_year,366.0,365.0)
    gamma=2*np.pi/ndays*(day-1+(hour-12)/24)
    eqtime=229.18*(.000075+.001868*np.cos(gamma)-.032077*np.sin(gamma)-.014615*np.cos(2*gamma)-.040849*np.sin(2*gamma))
    decl=(.006918-.399912*np.cos(gamma)+.070257*np.sin(gamma)-.006758*np.cos(2*gamma)+.000907*np.sin(2*gamma)-.002697*np.cos(3*gamma)+.00148*np.sin(3*gamma))
    angle=np.radians((hour*60 +eqtime+4*lon)/4-180)
    return (np.sin(math.radians(lat))*np.sin(decl)+np.cos(math.radians(lat))*np.cos(decl)*np.cos(angle))>0
