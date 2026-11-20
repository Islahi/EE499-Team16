"""Stream GoiEner v7.1's large annual matrix into consistent hourly load series.

The full compressed matrix is NOT shipped in this test kit; download it from
https://zenodo.org/records/22313409 and place it in Data/GoiEner_v71/.

Default balanced-panel method retains only meters with complete eligible ISO-year
records for the full 2017..last-covered-year interval, avoiding artificial jumps
in total demand when meters join or leave. An all-complete-meter mode is available
for diagnostics, but changes customer composition over time.

Source: https://github.com/Islahi/EE499-Team16.git
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from time import perf_counter
import warnings

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
DEFAULT_SOURCE=ROOT/'Data'/'GoiEner_v71'/'annual_consumption_raw.csv.zst'
DEFAULT_OUTPUT=ROOT/'C2_full_history_data'
COL_PATTERN=re.compile(r'^w(\d\d)_d([1-7])_h(\d\d)$')

@contextmanager
def open_matrix(path):
    """Text stream for very large .csv or .csv.zst, without extracting the 1.4GB archive."""
    if path.suffix.lower()=='.zst':
        try:
            import zstandard as zstd
        except ImportError as e:
            raise SystemExit('Missing zstandard: python -m pip install zstandard') from e
        with path.open('rb') as raw:
            dctx=zstd.ZstdDecompressor()
            with dctx.stream_reader(raw) as dec:
                with io.TextIOWrapper(dec,encoding='utf-8',newline='') as textfile:
                    yield textfile
    else:
        with path.open('r',encoding='utf-8-sig',newline='') as f: yield f


def raw_rows(stream):
    # The matrix has four metadata columns, followed by 8,904 hourly columns.
    header=stream.readline().strip().split(',')
    if [h.strip().lower() for h in header[:4]] != ['file_id','iso_year','full_year','n_imput']:
        raise ValueError('Expected GoiEner v7.1 annual matrix header: file_id,iso_year,full_year,n_imput,...')
    if len(header)<5 or any(COL_PATTERN.fullmatch(c.strip()) is None for c in header[4:]):
        raise ValueError('Invalid wWW_dD_hHH column layout; did you download the v7.1 annual matrix?')
    for line_number,line in enumerate(stream, start=2):
        parts=line.rstrip('\r\n').split(',',4)
        if len(parts)!=5: continue
        try:
            file_id,year,full,n_imput=parts[:4]
            file_id=file_id.strip().strip('"').zfill(5)
            year=int(year)
            full=full.strip().lower() in {'1','true','yes'}
            n_imput=int(float(n_imput))
        except (ValueError, TypeError):
            continue
        yield header,file_id,year,full,n_imput,parts[4],line_number


def positions_for_iso_year(year,cols,clock_start,clock_end):
    """Map ISO week/day/hour into actual calendar hours, dropping invalid week 53."""
    indexes=[]; target=[]
    start_ts=pd.Timestamp(clock_start); end_ts=pd.Timestamp(clock_end)
    for i,col in enumerate(cols):
        match=COL_PATTERN.fullmatch(col)
        week=int(match[1]);weekday=int(match[2]);hour=int(match[3])
        if hour>=24:continue
        try: d=date.fromisocalendar(year,week,weekday)
        except ValueError: continue
        ts=pd.Timestamp(d)+pd.Timedelta(hours=hour)
        if start_ts<=ts<=end_ts:
            indexes.append(i)
            target.append(int((ts-start_ts)/pd.Timedelta(hours=1)))
    return np.asarray(indexes,dtype=np.int32),np.asarray(target,dtype=np.int32)


def parse_numeric(text, count, line_number):
    """Fast numeric parsing with fallback for empty fields or uncommon NA markers."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',DeprecationWarning)
        try:
            values=np.fromstring(text,sep=',',dtype=np.float64)
        except ValueError:
            values=np.empty(0,dtype=np.float64)
    if len(values)!=count:
        tokens=text.strip().split(',')
        if len(tokens)!=count:
            raise ValueError(f'Line {line_number}: expected {count} hourly fields, got {len(tokens)}')
        values=np.array([float(x) if x.strip().lower() not in {'','na','null','none'} else np.nan
                         for x in tokens],dtype=np.float64)
    return values


def inspect(path,year_start,max_imputed_fraction):
    """Pass one: find year coverage and eligible meter IDs, without loading hourly values."""
    full_year_counts=Counter(); eligible=defaultdict(set); total_year_counts=Counter()
    num_rows=0; start=perf_counter()
    with open_matrix(path) as f:
        for header,ident,year,full,imputed,values,line_no in raw_rows(f):
            num_rows+=1; total_year_counts[year]+=1
            if full:
                full_year_counts[year]+=1
            if full and imputed <= max_imputed_fraction*len(header[4:]):
                eligible[ident].add(year)
            if num_rows%30000==0:
                print(f'  first pass: {num_rows:,} customer-year rows scanned',flush=True)
    print(f'First pass: {num_rows:,} records in {perf_counter()-start:.1f}s',flush=True)
    print('ISO-year coverage (total / complete records):')
    for year in sorted(total_year_counts):
        print(f'  {year}: {total_year_counts[year]:,} / {full_year_counts[year]:,}',flush=True)
    return full_year_counts,eligible,total_year_counts


def contiguous_panel(eligible,start_year,end_year):
    needed=set(range(start_year,end_year+1))
    return {ident for ident,years in eligible.items() if needed.issubset(years)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=DEFAULT_SOURCE)
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--start-year',type=int,default=2017)
    parser.add_argument('--end-year',type=int,default=None,help='Default: newest year with enough complete records')
    parser.add_argument('--population',choices=('balanced','all_complete'),default='balanced')
    parser.add_argument('--min-panel',type=int,default=20,
                        help='Minimum constant meter count for auto end-year selection')
    parser.add_argument('--max-imputed-fraction',type=float,default=0.10,
                        help='Exclude annual meter records with excessive imputed hourly samples')
    parser.add_argument('--max-filled-hours',type=int,default=168,
                        help='Maximum hours in aggregated result that may be missing and imputed')
    args=parser.parse_args()
    if not args.source.is_file():
        raise SystemExit(f'GoiEner file not found: {args.source}\n'
                         'Download annual_consumption_raw.csv.zst from https://zenodo.org/records/22313409')
    if not 0<=args.max_imputed_fraction<=1:raise ValueError('Imputation fraction must lie in [0,1]')
    year_counts,eligible,all_year_counts=inspect(args.source,args.start_year,args.max_imputed_fraction)
    candidates=[y for y in sorted(year_counts,reverse=True) if y>=args.start_year+2 and year_counts[y]>=args.min_panel]
    if not candidates:raise SystemExit('No full-year test period with at least two previous years of training')
    if args.end_year is not None:
        end_year=args.end_year
        if end_year not in candidates:
            raise SystemExit(f'--end-year {end_year} is not eligible; eligible end years: {candidates}')
        panel=contiguous_panel(eligible,args.start_year,end_year)
    elif args.population=='balanced':
        # Prefer the most recent reliable year, without silently using an unstable panel.
        options=[(year,contiguous_panel(eligible,args.start_year,year)) for year in candidates]
        possible=[(y,p) for y,p in options if len(p)>=args.min_panel]
        if not possible:
            print('Balanced panel sizes for candidate test years:',[(y,len(p)) for y,p in options])
            raise SystemExit('Too few meters with continuous full-year records since start year. '
                             'Try --min-panel 5, a later --start-year, or --population all_complete.')
        end_year,panel=possible[0]
    else:
        end_year=candidates[0]
        panel=set()
    if args.population=='balanced' and len(panel)<args.min_panel:
        raise SystemExit(f'Only {len(panel)} complete meters in {args.start_year}..{end_year}; '
                         'use another end year, --min-panel, or --population all_complete.')
    print(f'Selected ISO years {args.start_year}..{end_year}; mode={args.population}; '
          f'constant eligible meters={len(panel) if panel else "not applicable"}',flush=True)
    clock=pd.date_range(f'{args.start_year}-01-01',f'{end_year}-12-31 23:00',freq='h')
    sum_kw=np.zeros(len(clock),dtype=np.float64)
    n_meters=np.zeros(len(clock),dtype=np.int32)
    imputed_contributions=0
    seen_rows=0; accepted_rows=0
    cache={}
    start=perf_counter()
    with open_matrix(args.source) as f:
        for header,ident,iso_year,full,n_imput,raw,line_no in raw_rows(f):
            seen_rows+=1
            if not (args.start_year-1 <= iso_year <= end_year+1):continue
            if not full or n_imput>args.max_imputed_fraction*len(header[4:]):continue
            if args.population=='balanced' and ident not in panel:continue
            if iso_year not in cache:
                cache[iso_year]=positions_for_iso_year(iso_year,header[4:],clock[0],clock[-1])
            src_idxs,dest_idxs=cache[iso_year]
            if not len(src_idxs):continue
            series=parse_numeric(raw,len(header)-4,line_no)
            values=series[src_idxs]
            valid=np.isfinite(values)&(values>=0)
            if np.any(valid):
                # Each hourly kWh measurement is numerically the average kW for that hour.
                np.add.at(sum_kw,dest_idxs[valid],values[valid]);np.add.at(n_meters,dest_idxs[valid],1)
            imputed_contributions+=n_imput
            accepted_rows+=1
            if accepted_rows%10000==0:
                print(f'  second pass: {accepted_rows:,} accepted customer-year rows',flush=True)
    missing=n_meters==0
    missing_count=int(missing.sum())
    if missing_count>args.max_filled_hours:
        raise SystemExit(f'{missing_count:,} timestamps have no data; max allowed is '
                         f'{args.max_filled_hours}. Lower --end-year or adjust panel filters.')
    if args.population=='balanced' and len(panel)>0:
        # All selected meters should contribute every hour; disclose partial coverage.
        coverage_min=int(n_meters.min())
        print(f'Balanced panel coverage: min {coverage_min}/{len(panel)} meters per hour',flush=True)
    # Only hours with no eligible observations are filled, using a past-year/week same-hour
    # lookup or adjacent observed values. Result distinguishes imputed hours from observed.
    values=sum_kw.copy()
    if missing_count:
        ser=pd.Series(values,index=clock,dtype=float)
        ser.iloc[np.where(missing)[0]]=np.nan
        week=ser.shift(168)
        ser=ser.fillna(week)
        ser=ser.ffill().bfill()
        if ser.isna().any():raise SystemExit('Cannot fill calendar gaps in the aggregated source')
        values=ser.to_numpy()
    args.output.mkdir(parents=True,exist_ok=True)
    source_path=args.output/'goiener_hourly_load.csv'
    pd.DataFrame({'timestamp':clock,'p_kw':values,'n_meters':n_meters,
                  'filled_hour':missing.astype(np.int8)}).to_csv(source_path,index=False)
    report={
        'source':'GoiEner v7.1 annual_consumption_raw.csv.zst',
        'source_url':'https://zenodo.org/records/22313409',
        'repo':'https://github.com/Islahi/EE499-Team16.git',
        'source_file':str(args.source),
        'source_size_bytes':args.source.stat().st_size,
        'source_mtime_ns':args.source.stat().st_mtime_ns,
        'max_imputed_fraction':args.max_imputed_fraction,
        'start_year':args.start_year,'end_year':end_year,'population':args.population,
        'selected_meter_count':len(panel) if args.population=='balanced' else None,
        'records_examined':seen_rows,'annual_records_accepted':accepted_rows,
        'available_full_year_counts':dict(sorted(year_counts.items())),
        'available_annual_row_counts':dict(sorted(all_year_counts.items())),
        'hours':len(clock),'missing_hours_filled':missing_count,
        'min_hourly_meter_count':int(n_meters.min()),'max_hourly_meter_count':int(n_meters.max()),
        'mean_hourly_meter_count':float(n_meters.mean()),
        'annual_profile_imputed_samples_sum':imputed_contributions,
        'note':'Consumer composition can change in all_complete; balanced is fixed-meter cohort.',
        'units':'One-hour kWh corresponds to kW average during the hourly interval.',
        'processing_seconds_second_pass':perf_counter()-start,
    }
    (args.output/'goiener_preprocessing_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f'Wrote {source_path} ({len(clock):,} hours); {missing_count} gap hours filled',flush=True)
    print('Annual forecast year:',end_year,'| prior training:',args.start_year,'through',end_year-1,flush=True)

if __name__=='__main__':main()
