"""Read the C2_FullHistory_2021 benchmark outputs without rerunning any forecasts.

Project repository: https://github.com/Islahi/EE499-Team16.git
The 15-bus category-derived option is explicitly NOT an independently-fitted bus model.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import json
import numpy as np
import pandas as pd

VIRTUAL = '15-bus network — reconstructed from category forecasts'
CATEGORIES = {
    'residential': 'GoiEner_Residential_PerMeter',
    'commercial': 'GoiEner_Commercial_PerMeter',
    'manufacturing': 'GoiEner_Manufacturing_PerMeter',
}
FORMATS = {
    'Hourly': (None, None),
    'Daily mean': ('D', 'mean'),
    'Daily peak': ('D', 'max'),
    'Weekly mean': ('W', 'mean'),
    'Monthly mean': ('MS', 'mean'),
    'Daily energy (kWh)': ('D', 'sum'),
    'Monthly energy (kWh)': ('MS', 'sum'),
}
TRAIN_START, TRAIN_END = pd.Timestamp('2017-06-01 00:00:00'), pd.Timestamp('2020-12-31 23:00:00')


@dataclass(frozen=True)
class Job:
    dataset: str
    category: str
    model: str
    season: str
    file: Path
    metrics: Path

    @property
    def key(self) -> str:
        return f'{self.model} / {self.season}'


class C2Results:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        if self.root.name.lower() == 'results':
            self.root = self.root.parent
        self.results_dir = self.root / 'results'
        self.data_dir = self.root / 'data'
        if not self.results_dir.is_dir():
            raise FileNotFoundError(f'Cannot find results/ inside {self.root}.\n'
                                    'Choose the extracted C2_FullHistory_2021 folder, NOT a single CSV.')
        self.jobs: dict[str, dict[str, Job]] = {}
        for path in self.results_dir.glob('*/*/*/hourly_comparison.csv'):
            rel = path.relative_to(self.results_dir).parts
            if len(rel) != 4 or rel[0] not in ('load','pv') or '__' not in rel[2]:
                continue
            cat, ds, model_season, _ = rel
            model, season = model_season.split('__', 1)
            metrics = path.parent / 'run_metrics.json'
            if metrics.is_file():
                try:
                    if json.loads(metrics.read_text(encoding='utf-8')).get('status') not in ('OK','OK_WITH_WARNINGS'):
                        continue
                except (json.JSONDecodeError, OSError):
                    continue
            job = Job(ds, cat, model, season, path, metrics)
            self.jobs.setdefault(ds, {})[job.key] = job
        if not self.jobs:
            raise ValueError('No completed forecasts found. Search for '
                             'results/load/<dataset>/<model>__<seasonality>/hourly_comparison.csv.\n'
                             'Keep the entire results folder, not just score summaries.')
        self._common = set.intersection(*(set(self.jobs.get(ds, {})) for ds in CATEGORIES.values()))
        self.has_network_data = (self.data_dir/'distributed_15bus_load.csv').is_file() and \
                                (self.data_dir/'goiener_category_means.csv').is_file() and \
                                (self.data_dir/'bus_assignments_used.csv').is_file()
        if self.has_network_data:
            self.jobs.setdefault(VIRTUAL, {})

    def datasets(self) -> list[str]:
        items = sorted(d for d in self.jobs if d != VIRTUAL)
        if self.has_network_data:
            items.insert(0, VIRTUAL)
        return items

    def options(self, dataset: str) -> list[str]:
        if dataset == VIRTUAL:
            return sorted(self._common)
        return sorted(self.jobs.get(dataset, {}))

    def bus_options(self, dataset: str) -> list[str]:
        if dataset != VIRTUAL:
            return ['Total']
        assignments = self.assignments()
        return ['Total', 'Bus 1'] + [f'Bus {i}' for i in sorted(assignments.index)]

    def category(self, dataset: str) -> str:
        if dataset == VIRTUAL: return 'load'
        if dataset in self.jobs and self.jobs[dataset]:
            return next(iter(self.jobs[dataset].values())).category
        return 'load'

    def unit(self, dataset: str, resolution: str = 'Hourly') -> str:
        if 'energy' in resolution.lower(): return 'kWh'
        if dataset.startswith('GoiEner_') and dataset.endswith('_PerMeter'):
            return 'kW/customer'
        return 'kW'

    @lru_cache(maxsize=24)
    def single(self, dataset: str, key: str) -> pd.DataFrame:
        job = self.jobs[dataset][key]
        frame = pd.read_csv(job.file, usecols=['timestamp','actual','forecast'],parse_dates=['timestamp'])
        if frame['timestamp'].isna().any() or frame['timestamp'].duplicated().any():
            raise ValueError(f'Invalid timestamps in {job.file}')
        if frame[['actual','forecast']].isna().any().any():
            raise ValueError(f'Incomplete actual or forecast data in {job.file}')
        frame = frame.set_index('timestamp').sort_index()
        return frame.astype(float)

    @lru_cache(maxsize=1)
    def assignments(self) -> pd.DataFrame:
        path=self.data_dir/'bus_assignments_used.csv'
        frame=pd.read_csv(path)
        if not {'bus_id','category'}.issubset(frame.columns):
            raise ValueError(f'Invalid bus assignments: {path}')
        frame['category']=frame['category'].astype(str).str.strip().str.lower()
        frame['bus_id']=frame['bus_id'].astype(int)
        if frame.bus_id.duplicated().any():raise ValueError('Duplicate bus IDs in assignments')
        invalid=set(frame.category)-set(CATEGORIES)
        if invalid:raise ValueError(f'Unknown bus categories: {invalid}')
        return frame.set_index('bus_id').sort_index()

    @lru_cache(maxsize=1)
    def distributed(self) -> pd.DataFrame:
        df=pd.read_csv(self.data_dir/'distributed_15bus_load.csv',
                       usecols=['timestamp','bus_id','p_kw'],parse_dates=['timestamp'])
        if df.duplicated(['timestamp','bus_id']).any():raise ValueError('Duplicate distributed bus readings')
        df['bus_id']=df['bus_id'].astype(int)
        return df.pivot(index='timestamp',columns='bus_id',values='p_kw').sort_index()

    @lru_cache(maxsize=1)
    def means(self) -> pd.DataFrame:
        cols=['timestamp','Residential-GoiEner-Aggregate','Commercial-GoiEner-Aggregate',
              'Industrial-GoiEner-Aggregate']
        df=pd.read_csv(self.data_dir/'goiener_category_means.csv',usecols=cols,parse_dates=['timestamp'])
        if df.timestamp.duplicated().any():raise ValueError('Duplicated category timestamps')
        df=df.set_index('timestamp').sort_index().rename(columns={
            'Residential-GoiEner-Aggregate':'residential',
            'Commercial-GoiEner-Aggregate':'commercial',
            'Industrial-GoiEner-Aggregate':'manufacturing'})
        return df

    @lru_cache(maxsize=1)
    def scales(self) -> dict[int, float]:
        """Train-only bus = scale × category mean; verify this is genuinely how inputs were built."""
        bus_data=self.distributed().loc[TRAIN_START:TRAIN_END]
        means=self.means().loc[TRAIN_START:TRAIN_END]
        if len(bus_data)!=len(means) or len(bus_data)!=31440 or not bus_data.index.equals(means.index):
            raise ValueError('Cannot derive bus scale: source training timestamps are incomplete or differ.')
        scales={}
        for bus, row in self.assignments().iterrows():
            cat=row['category']
            x=means[cat].to_numpy(float)
            y=bus_data[bus].to_numpy(float)
            good=np.isfinite(x) & np.isfinite(y)
            xx=float(x[good]@x[good])
            if xx==0:raise ValueError(f'Cannot estimate scale for Bus {bus}: zero category history')
            factor=float(x[good]@y[good]/xx)
            error=float(np.sqrt(np.mean((y[good]-factor*x[good])**2)))
            tolerance=max(1e-4, float(np.mean(np.abs(y[good])))*1e-4)
            if error>tolerance:
                raise ValueError(f'Bus {bus} was not created by a fixed category scaling '
                                 f'(train RMSE {error:.4f} kW). Refusing misleading reconstruction.')
            scales[int(bus)]=factor
        return scales

    @lru_cache(maxsize=1)
    def other_buses(self) -> list[int]:
        df=self.distributed()
        return [int(x) for x in df.columns if x not in self.assignments().index]

    def derived(self, key: str, bus: str = 'Total') -> pd.DataFrame:
        """Re-use saved category predictions, then apply fixed train-only bus factors.
        No per-bus model fitting or new forecasting takes place here.
        """
        if key not in self._common:
            raise ValueError('Reconstruction requires a completed forecast for ALL three GoiEner categories '
                             'using the SAME model and seasonality. This run is not complete yet.')
        cats={c:self.single(ds,key)['forecast'] for c,ds in CATEGORIES.items()}
        times=next(iter(cats.values())).index
        for c,forecast in cats.items():
            if not forecast.index.equals(times):
                raise ValueError(f'Category forecast time mismatch: {c}')
        loads=self.distributed().reindex(times)
        if loads.isna().any().any():raise ValueError('Missing actual per-bus observations for forecast period')
        if bus=='Total':
            actual=loads.sum(axis=1)
            sums={c:0.0 for c in CATEGORIES}
            for i,factor in self.scales().items():
                sums[self.assignments().loc[i,'category']]+=factor
            forecast=sum((cats[c]*s for c,s in sums.items()), pd.Series(0.0,index=times))
        else:
            i=int(bus.removeprefix('Bus ').strip())
            if i not in loads.columns: raise ValueError(f'Unknown bus {i}')
            actual=loads[i]
            if i in self.scales():
                forecast=cats[self.assignments().loc[i,'category']]*self.scales()[i]
            else:
                # Slack bus 1 has no assigned load; verified to be zero throughout training.
                hist=self.distributed()[i].loc[TRAIN_START:TRAIN_END]
                if not np.allclose(hist.to_numpy(float),0,atol=1e-6):
                    raise ValueError('Cannot reconstruct unassigned bus with nonzero training load')
                forecast=pd.Series(0.0,index=times)
        return pd.DataFrame({'actual':actual,'forecast':forecast},index=times)

    def series(self, dataset: str, key: str, bus: str = 'Total') -> pd.DataFrame:
        if dataset==VIRTUAL: return self.derived(key,bus)
        if bus!='Total': raise ValueError('Per-bus data are unavailable for this directly fitted aggregate forecast')
        return self.single(dataset,key)

    def metadata(self, dataset: str, key: str) -> dict:
        if dataset==VIRTUAL:
            return {'method':'Category-derived; NOT independently fitted per bus.',
                    'model':key,'status':'DERIVED FROM THREE COMPLETED CATEGORY FORECASTS'}
        path=self.jobs[dataset][key].metrics
        if path.is_file():
            try:return json.loads(path.read_text(encoding='utf-8'))
            except (OSError,json.JSONDecodeError):pass
        return {}


def parse_date(text: str, ending: bool) -> pd.Timestamp | None:
    text=text.strip()
    if not text:return None
    d=pd.Timestamp(text)
    if len(text)<=10 and ending:
        d+=pd.Timedelta(days=1)-pd.Timedelta(nanoseconds=1)
    return d


def window(frame: pd.DataFrame, begin: str = '', end: str = '') -> pd.DataFrame:
    start=parse_date(begin,False); stop=parse_date(end,True)
    if start is not None:frame=frame.loc[frame.index>=start]
    if stop is not None:frame=frame.loc[frame.index<=stop]
    if frame.empty:raise ValueError('No forecast hours in the selected date range.')
    return frame


def resample(frame: pd.DataFrame, format_name: str) -> pd.DataFrame:
    freq,agg=FORMATS[format_name]
    if freq is None:return frame
    return getattr(frame.resample(freq),agg)().dropna(how='all')


def hourly_metrics(frame: pd.DataFrame) -> dict[str, float]:
    a=frame['actual'].to_numpy(float);p=frame['forecast'].to_numpy(float)
    d=a-p;ad=np.abs(d)
    s=float(np.sum(np.abs(a)))
    return {
        'MAE': float(np.mean(ad)),
        'RMSE':float(np.sqrt(np.mean(d*d))),
        'WAPE (%)':float(100*np.sum(ad)/s) if s>0 else float('nan'),
        'Bias (A−F)':float(np.mean(d)),
        'Hours':len(frame),
    }


def available_root_candidates(here: str | Path) -> list[Path]:
    here=Path(here).resolve()
    c=[here,here.parent,here/'C2_FullHistory_2021',here.parent/'C2_FullHistory_2021']
    return [p for p in c if (p/'results').is_dir()]
