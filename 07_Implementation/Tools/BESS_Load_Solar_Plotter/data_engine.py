"""Load and group distributed BESS feeder inputs and NASA POWER irradiance CSVs.

No network model is modified. All P/Q values are mean power over 1-hour intervals.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

SECTORS = ('residential', 'commercial', 'manufacturing', 'unclassified')
SOLAR_COLS = ('GHI', 'DHI', 'DNI')


def _category(raw: str) -> str:
    v = str(raw or '').strip().lower()
    if 'residen' in v or 'house' in v: return 'residential'
    if 'commer' in v or 'retail' in v or 'office' in v: return 'commercial'
    if 'manuf' in v or 'industr' in v or 'factory' in v: return 'manufacturing'
    return 'unclassified'


def discover_networks(zippath: str | Path) -> list[dict]:
    """Identify every independently exported feeder in a distributed ZIP."""
    with zipfile.ZipFile(zippath) as z:
        names = set(z.namelist())
        found = []
        for name in sorted(names):
            if not name.endswith('load_profile.csv'): continue
            prefix = name[:-len('load_profile.csv')]
            assignments = prefix + 'bus_assignments_used.csv'
            if assignments not in names:
                # Some archives contain a top-level flat folder
                continue
            found.append({'key':prefix.rstrip('/'), 'prefix':prefix, 'load':name,
                          'assignments': assignments,
                          'manifest':prefix+'manifest.json' if prefix+'manifest.json' in names else None,
                          'summary':prefix+'bus_summary.csv' if prefix+'bus_summary.csv' in names else None,
                          'pv':prefix+'pv_profile.csv' if prefix+'pv_profile.csv' in names else None})
        return found


def aggregate_distributed(zippath: str | Path, entry: dict, *, chunksize: int = 250_000) -> tuple[pd.DataFrame, dict]:
    """Return hourly network-wide P by load category; stream arbitrary feeder sizes."""
    partials: list[pd.DataFrame] = []
    with zipfile.ZipFile(zippath) as z:
        assignments = pd.read_csv(z.open(entry['assignments']), dtype={'bus_id':'string'})
        if not {'bus_id','category'}.issubset(assignments):
            raise ValueError('bus_assignments_used.csv must have bus_id,category columns')
        assignments['bus_id'] = assignments['bus_id'].str.strip()
        if assignments.bus_id.duplicated().any():
            raise ValueError('Duplicate bus_id in assignment CSV')
        cmap = dict(zip(assignments.bus_id, assignments.category.map(_category)))
        unknown_buses = set()
        total_read=0
        with z.open(entry['load']) as stream:
            for chunk in pd.read_csv(stream, usecols=['timestamp','bus_id','p_kw'],
                                     dtype={'bus_id':'string'}, chunksize=chunksize):
                chunk['bus_id'] = chunk['bus_id'].str.strip()
                chunk['timestamp'] = pd.to_datetime(chunk['timestamp'], errors='coerce')
                chunk['p_kw'] = pd.to_numeric(chunk['p_kw'], errors='coerce')
                chunk = chunk.dropna(subset=['timestamp','bus_id','p_kw'])
                chunk['sector'] = chunk['bus_id'].map(cmap).fillna('unclassified')
                unknown_buses.update(set(chunk.loc[(chunk['sector']=='unclassified') & (chunk['p_kw'].abs()>0.000001), 'bus_id']))
                g = chunk.groupby(['timestamp','sector'], observed=True)['p_kw'].sum().unstack(fill_value=0.0)
                partials.append(g)
                total_read+=len(chunk)
        if not partials:
            raise ValueError('No valid distributed load records found')
        # Chunks can split hours: reduce chunk-level totals by the same timestamp.
        hourly = pd.concat(partials).groupby(level=0).sum().sort_index()
        for col in SECTORS:
            if col not in hourly: hourly[col] = 0.0
        hourly = hourly[list(SECTORS)]
        hourly['total'] = hourly[list(SECTORS)].sum(axis=1)
        hourly.index.name = 'timestamp'
        manifest = {}
        if entry.get('manifest'):
            with z.open(entry['manifest']) as f: manifest=json.load(f)
    if unknown_buses:
        manifest['warning_unknown_nonzero_bus_ids'] = sorted(unknown_buses)
    manifest['input_rows_read'] = total_read
    manifest['aggregated_hours'] = len(hourly)
    manifest['load_sectors'] = {k:int(v) for k,v in assignments.category.map(_category).value_counts().items()}
    manifest['start'] = str(hourly.index.min())
    manifest['end'] = str(hourly.index.max())
    return hourly, manifest


def load_aggregated_csv(path: str | Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    data['timestamp']=pd.to_datetime(data['timestamp'])
    data = data.set_index('timestamp').sort_index()
    for col in (*SECTORS,'total'):
        if col not in data: data[col] = 0.0
    return data[list(SECTORS)+['total']]


def _nasa_raw_csv(data: bytes) -> pd.DataFrame:
    text = data.decode('utf-8-sig',errors='replace')
    lines = text.splitlines()
    # NASA POWER puts descriptive text above the actual CSV header.
    start = next((i for i,line in enumerate(lines) if re.match(r'^\s*(?:YEAR|Year)\s*,\s*(?:MO|Month)\s*,\s*(?:DY|Day)\s*,\s*(?:HR|Hour)\s*,',line)),None)
    if start is None:
        start = next((i for i,line in enumerate(lines) if re.match(r'^\s*timestamp\s*,',line,re.I)),None)
    if start is None:
        raise ValueError('Could not find a NASA POWER YEAR,MO,DY,HR header or timestamp column')
    return pd.read_csv(io.StringIO('\n'.join(lines[start:])))


def nasa_power_csv_to_hourly(path: str | Path) -> pd.DataFrame:
    """Read NASA POWER hourly CSV (header preamble accepted). Preserve source timestamps."""
    frame = _nasa_raw_csv(Path(path).read_bytes())
    cmap = {str(c).strip().upper():c for c in frame.columns}
    if {'YEAR','MO','DY','HR'}.issubset(cmap):
        raw = pd.DataFrame({n:pd.to_numeric(frame[cmap[n]],errors='coerce') for n in ['YEAR','MO','DY','HR']})
        times = pd.to_datetime({'year':raw.YEAR,'month':raw.MO,'day':raw.DY,'hour':raw.HR},errors='coerce')
    else:
        ts_col = cmap.get('TIMESTAMP')
        if ts_col is None: raise ValueError('CSV missing date/time fields')
        times = pd.to_datetime(frame[ts_col], errors='coerce')
    rename = {'ALLSKY_SFC_SW_DWN':'GHI','ALLSKY_SFC_SW_DIFF':'DHI',
              'ALLSKY_SFC_SW_DNI':'DNI','T2M':'T2M',
              'GHI':'GHI','DHI':'DHI','DNI':'DNI'}
    out = pd.DataFrame({'timestamp':times})
    for raw_name,target in rename.items():
        if raw_name not in cmap: continue
        vals = pd.to_numeric(frame[cmap[raw_name]],errors='coerce')
        vals = vals.mask(vals<=-900) # NASA missing sentinels
        out[target] = vals.to_numpy()
    if not any(k in out for k in SOLAR_COLS):
        raise ValueError('No GHI, DHI, or DNI column in NASA file')
    return out.dropna(subset=['timestamp']).set_index('timestamp').sort_index()


def merge_nasa_monthly(files: Iterable[str | Path], *, time_mode: str='utc_to_spain') -> pd.DataFrame:
    """Concatenate files for ONE NASA site. utc_to_spain is a declared alignment assumption.

    Duplicated local fall-DST hours are averaged; skipped spring-DST hour is retained missing.
    """
    files = list(files)
    if not files: raise ValueError('Select one or more NASA CSV files')
    frames = [nasa_power_csv_to_hourly(f) for f in files]
    combined = pd.concat(frames).sort_index()
    if time_mode == 'utc_to_spain':
        local = pd.DatetimeIndex(combined.index).tz_localize('UTC').tz_convert('Europe/Madrid').tz_localize(None)
        combined.index=local
    elif time_mode != 'as_is':
        raise ValueError('Unknown time mode: '+time_mode)
    # If monthly imports overlap, repeated timestamp should not add irradiance values.
    combined = combined.groupby(level=0).mean().sort_index()
    combined.index.name='timestamp'
    return combined


def slice_period(frame:pd.DataFrame, period:str, selected:str|pd.Timestamp) -> pd.DataFrame:
    dt=pd.Timestamp(selected).normalize()
    if period == 'Daily': start,end=dt,dt+pd.Timedelta(days=1)
    elif period == 'Weekly':
        start=dt-pd.Timedelta(days=dt.weekday());end=start+pd.Timedelta(days=7)
    elif period == 'Monthly':
        start=dt.replace(day=1);end=start+pd.DateOffset(months=1)
    elif period == 'Yearly':
        start=dt.replace(month=1,day=1);end=start+pd.DateOffset(years=1)
    else: raise ValueError(period)
    return frame.loc[(frame.index>=start) & (frame.index<end)]


def slice_date_range(frame: pd.DataFrame, start: str | pd.Timestamp,
                     end: str | pd.Timestamp) -> pd.DataFrame:
    """Slice inclusive civil dates, with no restriction on the number of years.

    The upper bound is exclusive midnight after the end date, so all hourly
    observations on the end date are retained.
    """
    try:
        first = pd.Timestamp(start).normalize()
        last = pd.Timestamp(end).normalize()
    except (ValueError, TypeError) as exc:
        raise ValueError('Dates must use YYYY-MM-DD') from exc
    if pd.isna(first) or pd.isna(last):
        raise ValueError('Both start and end dates are required (YYYY-MM-DD)')
    if last < first:
        raise ValueError('End date must be on or after start date')
    exclusive = last + pd.Timedelta(days=1)
    return frame.loc[(frame.index >= first) & (frame.index < exclusive)]


def aggregate_period(frame:pd.DataFrame, interval:str, *, quantity:str='load') -> pd.DataFrame:
    """For hourly average power or irradiance, return physically meaningful grouped values.

    load: hourly kW, aggregated interval kWh (sum of hourly kW*1hr).
    irradiance: hourly W/m², aggregated interval kWh/m² (sum W/m²*1hr/1000).
    """
    if frame.empty: return frame.copy()
    if interval == 'Hourly': return frame.copy()
    if interval == 'Daily': key=frame.index.normalize()
    elif interval == 'Weekly':
        key=frame.index.normalize()-pd.to_timedelta(frame.index.weekday,unit='d')
    elif interval == 'Monthly': key=frame.index.to_period('M').to_timestamp()
    else: raise ValueError(interval)
    grouped=frame.groupby(key).sum(min_count=1)
    if quantity=='irradiance':
        cols = [c for c in SOLAR_COLS if c in grouped]
        grouped[cols] /= 1000.0
        if 'T2M' in grouped:
            grouped['T2M'] = frame['T2M'].groupby(key).mean()
    return grouped


def export_prepared_zip(zippath:str|Path, destination:str|Path) -> list[Path]:
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    results=[]
    for item in discover_networks(zippath):
        data,meta=aggregate_distributed(zippath,item)
        dest=destination/(Path(item['key']).name+'_hourly_aggregated.csv')
        data.to_csv(dest, float_format='%.6f')
        (destination/(Path(item['key']).name+'_manifest.json')).write_text(json.dumps(meta,indent=2),encoding='utf8')
        results.append(dest)
    return results
