#!/usr/bin/env python3
"""Rebuild GoiEner sector profiles from a common 3-archive customer cohort.

Reads original Zenodo 7362094 tar.zst/TZST streams locally; never uploads raw data.
Uses Cleaned.zip *manifests* for the exact membership and original classification.
Processes records customer-by-customer into a disk-backed matrix, handles overlap
by keeping the newer archive's valid measurement, and interpolates only genuine
INTERNAL gaps (never extrapolate before a customer's first / after their last reading).
The cohort ID set is fixed, but available-per-hour customer counts may vary.
"""
from __future__ import annotations
import argparse
import csv
import io
import json
import math
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
import numpy as np
import pandas as pd

SECTORS = ('residential','commercial','manufacturing')
WIDE = {'residential':'Residential-GoiEner-Aggregate',
        'commercial':'Commercial-GoiEner-Aggregate',
        'manufacturing':'Industrial-GoiEner-Aggregate'}
PREFER_NEWER = ('Pre','During','Post')

@contextmanager
def tar_stream(filename:Path):
    name=filename.name.lower()
    if name.endswith(('.zst','.tzst')):
        try:
            import zstandard
        except ImportError:
            zstandard=None
        if zstandard is not None:
            with open(filename,'rb') as fp, zstandard.ZstdDecompressor().stream_reader(fp) as reader:
                with tarfile.open(fileobj=reader,mode='r|') as tar:
                    yield tar
            return
        if shutil.which('zstd'):
            proc=subprocess.Popen(['zstd','-dc',str(filename)],stdout=subprocess.PIPE)
            try:
                with tarfile.open(fileobj=proc.stdout, mode='r|') as tar:
                    yield tar
            finally:
                proc.stdout.close()
                if proc.wait()!=0:raise RuntimeError('zstd decompression failed')
            return
        raise RuntimeError('zstandard is required: python -m pip install zstandard')
    with tarfile.open(filename,mode='r|*') as tar:
        yield tar


def manifest_from_zip(archive:Path, label:str)->pd.DataFrame:
    with zipfile.ZipFile(archive) as z:
        options=[n for n in z.namelist() if n.lower().endswith(f'/{label.lower()}/customer_quality_manifest.csv')]
        if len(options)!=1:
            raise ValueError(f'{archive.name}: expected one {label}/customer_quality_manifest.csv, found {options}')
        content=z.read(options[0])
    df=pd.read_csv(io.BytesIO(content),dtype={'user':'string','sector':'string','classification_basis':'string'})
    req={'user','sector','classification_basis'}
    if not req.issubset(df.columns): raise ValueError(f'{label}: missing manifest columns {req-set(df.columns)}')
    df['user']=df['user'].str.strip().str.lower()
    if df.user.isna().any() or df.user.duplicated().any():raise ValueError(f'{label}: missing/duplicate user IDs')
    return df[df.sector.isin(SECTORS)].copy()


def common_cohort(manifests_zip:Path):
    frames={p:manifest_from_zip(manifests_zip,p) for p in PREFER_NEWER}
    users=set(frames['Pre'].user)&set(frames['During'].user)&set(frames['Post'].user)
    allrows=[];different=[]
    ref={p:df.set_index('user') for p,df in frames.items()}
    for user in sorted(users):
        classes=[ref[p].loc[user,'sector'] for p in PREFER_NEWER]
        if len(set(classes))!=1:
            different.append((user,classes));continue
        allrows.append({'user':user,'sector':classes[0],
            'classification_basis':str(ref['Pre'].loc[user,'classification_basis']),
            'cnae':str(ref['Pre'].loc[user].get('cnae','')),
            'first_pre':str(ref['Pre'].loc[user].get('first','')),
            'last_pre':str(ref['Pre'].loc[user].get('last','')),
            'first_during':str(ref['During'].loc[user].get('first','')),
            'last_during':str(ref['During'].loc[user].get('last','')),
            'first_post':str(ref['Post'].loc[user].get('first','')),
            'last_post':str(ref['Post'].loc[user].get('last',''))})
    if not allrows:raise RuntimeError('No consistently classified customers across all three archives')
    return pd.DataFrame(allrows),{p:len(frames[p]) for p in PREFER_NEWER},different


def ingest_member(fileobj, start:pd.Timestamp, end:pd.Timestamp):
    """Original cleaner's UTC-normalization convention; no interpolating yet."""
    try:df=pd.read_csv(io.BytesIO(fileobj.read()),low_memory=False)
    except Exception as exc:return None,{f'parse_failed_{type(exc).__name__}_{str(exc)[:80]}':1}
    cols={str(c).strip().lower():c for c in df.columns}
    if not {'timestamp','kwh'}.issubset(cols):return None,{'invalid_columns':1}
    t=pd.to_datetime(df[cols['timestamp']],utc=True,errors='coerce').dt.tz_localize(None)
    y=pd.to_numeric(df[cols['kwh']],errors='coerce')
    ok=(~t.isna()) & (t>=start) & (t<=end) & (t.dt.minute==0) & (t.dt.second==0)
    bad=(~np.isfinite(y)) | (y<0)
    df2=pd.DataFrame({'time':t[ok],'val':y[ok].where(~bad[ok],np.nan)})
    if df2.empty:return None,{'no_hours_in_range':1}
    duplicate=int(df2.time.duplicated().sum())
    df2=df2.groupby('time',sort=True)['val'].mean().dropna()
    if df2.empty:return None,{'no_valid_measurements':1}
    positions=((df2.index-start)/pd.Timedelta(hours=1)).to_numpy(dtype='int64')
    return (positions,df2.to_numpy('float32')), {'duplicates':duplicate,'invalid_values':int(bad.sum()),'valid_hours':len(df2)}


def fill_inside(values:np.ndarray, max_gap:int):
    """Linear interpolation only between two observed points; no endpoint extrapolation.
    max_gap=0 allows all internal gaps. Returns (number_filled, number_large_gap_hours).
    """
    valid=np.isfinite(values)
    if valid.sum()<2:return 0,int((~valid).sum())
    idx=np.flatnonzero(valid)
    st=idx[:-1];en=idx[1:]
    gap=en-st-1
    selected=np.flatnonzero((gap>0)&((gap<=max_gap) if max_gap>0 else True))
    filled=0
    for k in selected:
        a=int(st[k]);b=int(en[k]);num=b-a-1
        values[a+1:b]=np.linspace(float(values[a]),float(values[b]),num+2,dtype=np.float32)[1:-1]
        filled+=num
    return filled,int(np.sum(gap[gap>max_gap])) if max_gap>0 else 0


def run(args):
    t0=time.perf_counter()
    for f in [args.manifests_zip,args.pre,args.during,args.post]:
        if not f.is_file():raise FileNotFoundError(f)
    args.out.mkdir(parents=True,exist_ok=True)
    if args.work_dir is not None:args.work_dir.mkdir(parents=True,exist_ok=True)
    cohort,source_counts,different=common_cohort(args.manifests_zip)
    cohort.to_csv(args.out/'cohort_customer_manifest.csv',index=False)
    start=pd.Timestamp(args.start);end=pd.Timestamp(args.end)
    if start.tzinfo or end.tzinfo:raise ValueError('Use source-clock timestamps without timezone (see README)')
    if end<=start:raise ValueError('End must be after start')
    all_hours=pd.date_range(start,end,freq='h')
    n=len(cohort);h=len(all_hours)
    disk_gib=n*h*4/(1024**3)
    print(f'Cohort: {n:,} customers; {h:,} hourly timestamps; disk-backed cache {disk_gib:.2f} GiB',flush=True)
    print('By category:',cohort.sector.value_counts().to_dict(),flush=True)
    if shutil.disk_usage(args.work_dir or args.out).free < n*h*4*1.15:
        raise OSError(f'Not enough free disk for {disk_gib:.2f} GiB temporary customer matrix')
    rowmap={str(row.user):i for i,row in cohort.iterrows()}
    categories=cohort.sector.to_numpy()
    tempdir=Path(tempfile.mkdtemp(prefix='goiener_cohort_',dir=args.work_dir or args.out))
    cache=tempdir/'customer_hourly_float32.dat'
    counts={}; statistics={}
    try:
        matrix=np.memmap(cache,dtype='float32',mode='w+',shape=(n,h))
        for sl in range(0,n,64): matrix[sl:min(n,sl+64),:]=np.nan
        matrix.flush()
        print(f'Temporary cache: {cache}',flush=True)
        for label,path in [('Pre',args.pre),('During',args.during),('Post',args.post)]:
            started=time.perf_counter();record=Counter();found=set()
            with tar_stream(path) as tar:
                for entry in tar:
                    if not entry.isfile() or not entry.name.lower().endswith('.csv'):continue
                    uid=Path(entry.name).stem.strip().lower()
                    if uid not in rowmap:continue
                    fp=tar.extractfile(entry)
                    if fp is None:continue
                    with fp:got,quality=ingest_member(fp,start,end)
                    record.update(quality)
                    if got is None:continue
                    pos,vals=got
                    row=matrix[rowmap[uid]]
                    # Only valid new measurements replace old ones. Archive precedence: Post > During > Pre.
                    row[pos]=vals
                    found.add(uid)
                    record['customer_files_read']+=1
                    if record['customer_files_read']%1000==0:
                        print(f'  {label}: {record["customer_files_read"]:,} cohort customer files',flush=True)
            matrix.flush()
            record['unique_customer_ids_found']=len(found)
            record['cohort_ids_not_found']=n-len(found)
            record['seconds']=round(time.perf_counter()-started,2)
            statistics[label]=dict(record)
            print(f'{label} complete: {len(found):,}/{n:,} customers, {record["seconds"]}s',flush=True)
        # Stream over customers to calculate aggregate sector series and preserve gap counts.
        total={s:np.zeros(h,dtype=np.float64) for s in SECTORS}
        active={s:np.zeros(h,dtype=np.int32) for s in SECTORS}
        interpolated={s:np.zeros(h,dtype=np.int32) for s in SECTORS}
        user_quality=[]
        for k,user in enumerate(cohort.user):
            row=matrix[k];before=np.isfinite(row).copy()
            filled,long_gap=fill_inside(row,args.max_gap_hours)
            new=np.isfinite(row)
            sector=str(categories[k])
            if new.any():
                total[sector][new]+=row[new].astype('float64')
                active[sector][new]+=1
                interp_mask=new & ~before
                interpolated[sector][interp_mask]+=1
            user_quality.append({'user':user,'sector':sector,'observed_hours':int(before.sum()),
                'interpolated_hours':filled,'unresolved_hours':int((~new).sum()),
                'long_internal_missing_hours':long_gap,
                'first_observed':str(all_hours[np.flatnonzero(before)[0]]) if before.any() else '',
                'last_observed':str(all_hours[np.flatnonzero(before)[-1]]) if before.any() else ''})
            if (k+1)%1000==0: print(f'Aggregated {k+1:,}/{n:,} customers',flush=True)
        pd.DataFrame(user_quality).to_csv(args.out/'customer_interpolation_report.csv',index=False)
        wide=pd.DataFrame({'timestamp':all_hours})
        quality={}
        for s in SECTORS:
            cnt=active[s];sz=int((categories==s).sum())
            mean=np.divide(total[s],cnt,out=np.full(h,np.nan),where=cnt>0)
            # This is average of available members of the fixed ID cohort, not a fixed-N aggregate.
            pd.DataFrame({'timestamp':all_hours,'load_kw':np.where(cnt>0,total[s],np.nan),
                'average_customer_kw':mean,'active_customers':cnt,
                'selected_customers':sz,'coverage_fraction':cnt/sz,
                'interpolated_customer_hours':interpolated[s]}).to_csv(
                    args.out/(s+'.csv'),index=False,float_format='%.7f')
            wide[WIDE[s]]=mean
            q={'selected_common_customer_ids':sz,'max_active_customers':int(cnt.max()),
                'min_active_customers':int(cnt.min()),'average_hourly_coverage_percent':round(100*cnt.mean()/sz,3),
                'hours_below_80_percent_coverage':int((cnt<0.8*sz).sum()),
                'customer_hours_interpolated':int(interpolated[s].sum()),
                'hours_with_zero_available_customers':int((cnt==0).sum())}
            quality[s]=q
        wide.to_csv(args.out/'goiener_three_profiles.csv',index=False,float_format='%.7f')
        mandatory=wide[list(WIDE.values())]
        complete=mandatory.notna().all(axis=1)
        ready=wide.loc[complete].copy()
        contiguous=(ready.timestamp.diff().dropna()==pd.Timedelta(hours=1)).all()
        if not contiguous:
            # Don't silently drop missing hours and pretend it's continuous.
            wide.to_csv(args.out/'goiener_distributor_ready_with_gaps.csv',index=False,float_format='%.7f')
            print('WARNING: some category hours have no observations. Distributor-ready file not produced.',flush=True)
        else:
            ready.to_csv(args.out/'goiener_distributor_ready.csv',index=False,float_format='%.7f')
        pd.DataFrame({'timestamp':all_hours,**{s:active[s] for s in SECTORS}}).to_csv(
            args.out/'hourly_cohort_coverage.csv',index=False)
        report={
          'source_dataset':'GoiEner original Zenodo https://zenodo.org/records/7362094',
          'method':'Intersection of classified customer IDs across Pre, During, Post manifests; per-customer hourly reconstruction',
          'archive_priority':'Post over During over Pre for overlapping valid observations',
          'clock_note':'Uses original cleaner convention: parse timestamps with utc=True, return timezone-naive; not proof of real UTC alignment',
          'interpolation':'Only internal gaps between two valid readings; no first/last extrapolation',
          'max_gap_hours':args.max_gap_hours,'period':[str(start),str(end)],'hours':h,
          'manifest_classification':'Preserved from uploaded cleaned metadata; residential tariff proxies remain UNVERIFIED',
          'selected_customers':len(cohort),'source_classified_counts':source_counts,
          'inconsistent_sector_ids_excluded':len(different),
          'category_quality':quality,'archive_reading':statistics,
          'limitations':['Common ID membership does not imply every meter was active for every hour',
            'Interpolation within a large gap can conceal actual demand changes; adjust max-gap-hours and review coverage',
            'Per-meter averages use available cohort members, not a fixed denominator during missing periods',
            'Changing per-hour coverage or changes to the underlying consumer behavior can still affect trends'],
          'runtime_seconds':round(time.perf_counter()-t0,2)}
        (args.out/'cohort_quality_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('Finished:',args.out,flush=True)
        return report
    finally:
        # Cache is disposable and large. Do not remove if explicitly requested for debugging.
        # Drop row views too; Windows otherwise may keep the very large mmap open.
        try:del row
        except UnboundLocalError:pass
        try:
            matrix.flush()
            matrix._mmap.close()
            del matrix
        except (UnboundLocalError,AttributeError):pass
        import gc;gc.collect()
        if not args.keep_cache:shutil.rmtree(tempdir,ignore_errors=True)
        else:print('Preserved disk-backed cache:',tempdir)


def parse():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('--manifests-zip',type=Path,required=True,help='Previously uploaded Cleaned.zip with Pre/During/Post customer manifests')
    for label in ('pre','during','post'):
        p.add_argument('--'+label,type=Path,required=True,help=f'Original imp-{label if label!="during" else "in"}.tzst archive')
    p.add_argument('--out',type=Path,default=Path('cohort_output'))
    p.add_argument('--start',default='2017-06-01 00:00:00')
    p.add_argument('--end',default='2022-06-08 00:00:00')
    p.add_argument('--max-gap-hours',type=int,default=168,help='Only interpolate missing internal runs <= this length; 0 means unlimited')
    p.add_argument('--work-dir',type=Path,help='Directory for temporary large disk-backed cache')
    p.add_argument('--keep-cache',action='store_true')
    return p.parse_args()

if __name__=='__main__':run(parse())
