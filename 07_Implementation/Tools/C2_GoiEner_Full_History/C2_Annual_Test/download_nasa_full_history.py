"""Optional: obtain matching NASA POWER hourly irradiance for all five C2 PV sites.

NASA data are NOT GoiEner measurements. We convert hourly irradiance (Wh/m2 over
1 hour, numerically W/m2) to a project-modelled PV output (kW, 490kW rating).
The NASA time base is UTC; GoiEner local/DST time and NASA UTC must not be
combined as if they were simultaneous feeder measurements.

Source: https://power.larc.nasa.gov/docs/services/api/temporal/hourly/
Repo: https://github.com/Islahi/EE499-Team16.git
"""
import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd
from c2_benchmark_core import pv_power_from_ghi, daylight_mask_utc

ROOT=Path(__file__).resolve().parent
OUTPUT=ROOT/'C2_full_history_data'
SITES={
    '040d42N_003d70W':(40.42,-3.70),
    '042d81N_001d65W':(42.81,-1.65),
    '042d85N_002d67W':(42.85,-2.67),
    '043d26N_002d94W':(43.26,-2.94),
    '043d32N_001d98W':(43.32,-1.98),
}

def request_year(lat,lon,year,cache):
    if cache.is_file():
        return json.loads(cache.read_text(encoding='utf8'))
    params={'parameters':'ALLSKY_SFC_SW_DWN','community':'RE',
            'longitude':lon,'latitude':lat,'start':f'{year}0101','end':f'{year}1231',
            'format':'JSON','time-standard':'UTC'}
    url='https://power.larc.nasa.gov/api/temporal/hourly/point?'+urlencode(params)
    request=Request(url,headers={'User-Agent':'EE499-Team16-C2-Research/1.0'})
    for n in range(3):
        try:
            with urlopen(request,timeout=120) as response:
                result=json.loads(response.read().decode('utf-8'))
            arr=result.get('properties',{}).get('parameter',{}).get('ALLSKY_SFC_SW_DWN',{})
            if not arr: raise ValueError('NASA POWER returned no irradiance series; check API response')
            cache.parent.mkdir(parents=True,exist_ok=True)
            cache.write_text(json.dumps(result),encoding='utf-8')
            return result
        except Exception as e:
            print(f'NASA download attempt {n+1}/3 for {year}: {e}',flush=True)
            if n==2:raise
            time.sleep(4*(n+1))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--start-year',type=int,default=2017)
    p.add_argument('--end-year',type=int,default=None)
    p.add_argument('--sites',nargs='*',choices=SITES.keys(),default=list(SITES))
    args=p.parse_args()
    if args.end_year is None:
        report=OUTPUT/'goiener_preprocessing_report.json'
        if not report.is_file():raise SystemExit('Prepare GoiEner data first, or set --end-year')
        args.end_year=json.loads(report.read_text())['end_year']
    if args.end_year<=args.start_year:raise ValueError('Need >=2 years for training and evaluation')
    for site in args.sites:
        lat,lon=SITES[site]
        data=[]
        for year in range(args.start_year,args.end_year+1):
            print(f'[NASA] {site} {year}',flush=True)
            result=request_year(lat,lon,year,OUTPUT/'nasa_api_cache'/site/f'{year}.json')
            values=result['properties']['parameter']['ALLSKY_SFC_SW_DWN']
            for stamp,num in values.items():
                data.append((pd.to_datetime(stamp,format='%Y%m%d%H'),float(num)))
        df=pd.DataFrame(data,columns=['timestamp','irradiance_wh_m2'])
        df=df.drop_duplicates('timestamp').set_index('timestamp').sort_index()
        clock=pd.date_range(f'{args.start_year}-01-01',f'{args.end_year}-12-31 23:00',freq='h')
        df=df.reindex(clock)
        missing=(df.irradiance_wh_m2.isna()|(df.irradiance_wh_m2<-100)).to_numpy()
        # NASA could be missing a small number of source measurements; mark them.
        if missing.mean()>0.01:
            raise SystemExit(f'NASA {site}: {missing.sum()} missing of {len(df)} hours; too many to fill')
        ghi=df.irradiance_wh_m2.mask(df.irradiance_wh_m2 < -100)
        ghi=ghi.interpolate(limit_direction='both')
        if ghi.isna().any():raise ValueError('NASA missing data not recoverable')
        power=pv_power_from_ghi(np.maximum(ghi.to_numpy(float),0))
        power[~daylight_mask_utc(clock,lat,lon)]=0.0
        output=OUTPUT/f'nasa_pv_{site}.csv'
        pd.DataFrame({'timestamp':clock,'p_kw':power,'filled_hour':missing.astype(np.int8),
                      'ghi_wh_m2':ghi.to_numpy(),'site_lat':lat,'site_lon':lon}).to_csv(output,index=False)
        print(f'Wrote {output} ({len(clock)} hours; {sum(missing)} NASA gaps)',flush=True)

if __name__=='__main__':main()
