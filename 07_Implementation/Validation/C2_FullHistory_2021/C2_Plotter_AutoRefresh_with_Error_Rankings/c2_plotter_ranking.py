"""Rank completed C2 forecasts using saved results; never fit or reforecast.

Repository: https://github.com/Islahi/EE499-Team16.git
- For direct series, read the full-2021 metrics JSON whenever no date filter is set.
- For date-filtered views, recompute metrics on the exact selected hourly interval.
- For reconstructed buses, re-use the completed category forecasts and the
  verified bus multipliers, not an independently fitted per-bus model.
- MASE consistently uses training-period weekly seasonal-naive error (168h).
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
import math
import numpy as np
import pandas as pd
from c2_plotter_core import C2Results, VIRTUAL, TRAIN_START, TRAIN_END, window

# Display label, value-field. Lower is better for every metric except signed Bias;
# choose smallest absolute bias instead of most-negative bias.
SORT_OPTIONS = {
    'RMSE (smallest)': 'RMSE',
    'MAE (smallest)': 'MAE',
    'WAPE (smallest)': 'WAPE',
    'MASE (smallest)': 'MASE',
    '|Bias| (closest to zero)': 'Bias',
    'sMAPE (smallest)': 'sMAPE',
    'Fit time (fastest)': 'Fit',
    'Forecast time (fastest)': 'Predict',
    'Fit + forecast time (fastest)': 'Total',
    'Fewest warnings': 'Warnings',
}

@dataclass(frozen=True)
class RankedRow:
    key: str
    mae: float
    rmse: float
    wape: float
    mase: float
    bias: float
    smape: float
    fit: float
    predict: float
    total: float
    warnings: float

    def metric(self, name: str) -> float:
        value = {
            'MAE': self.mae, 'RMSE':self.rmse, 'WAPE':self.wape,
            'MASE':self.mase, 'Bias':abs(self.bias), 'sMAPE':self.smape,
            'Fit':self.fit, 'Predict':self.predict, 'Total':self.total,
            'Warnings':self.warnings,
        }[name]
        return value if math.isfinite(value) else math.inf


def _num(value) -> float:
    try:
        result=float(value)
        return result if math.isfinite(result) else math.nan
    except (TypeError,ValueError,OverflowError):
        return math.nan


def _weekly_denom(train: np.ndarray) -> float:
    y=np.asarray(train, dtype=float)
    if len(y) <= 168 or not np.isfinite(y).all():
        return math.nan
    den=float(np.mean(np.abs(y[168:]-y[:-168])))
    return den if den > 0 else math.nan


def _score_hourly(actual: np.ndarray, forecast: np.ndarray, mase_denom: float):
    a=np.asarray(actual,dtype=float); f=np.asarray(forecast,dtype=float)
    if len(a)!=len(f) or len(a)==0 or not np.isfinite(a).all() or not np.isfinite(f).all():
        raise ValueError('Invalid actual/forecast values for ranking.')
    diff=a-f; ad=np.abs(diff)
    mae=float(np.mean(ad))
    denom=float(np.sum(np.abs(a)))
    return {
        'MAE':mae,
        'RMSE':float(np.sqrt(np.mean(diff*diff))),
        'WAPE':float(100*np.sum(ad)/denom) if denom>0 else math.nan,
        'MASE':float(mae/mase_denom) if math.isfinite(mase_denom) and mase_denom>0 else math.nan,
        'Bias':float(np.mean(diff)),
        'sMAPE':float(np.mean(200*ad/np.maximum(np.abs(a)+np.abs(f),1e-8))),
    }


class Ranking:
    def __init__(self, db:C2Results):
        self.db=db

    @lru_cache(maxsize=24)
    def _mase_denom_for_virtual(self, bus:str) -> float:
        hist=self.db.distributed().loc[TRAIN_START:TRAIN_END]
        if bus=='Total':
            y=hist.sum(axis=1).to_numpy(float)
        else:
            idx=int(bus.removeprefix('Bus ').strip())
            y=hist[idx].to_numpy(float)
        return _weekly_denom(y)

    @lru_cache(maxsize=256)
    def _direct_metadata(self,dataset:str,key:str) -> dict:
        return self.db.metadata(dataset,key)

    def _model_metadata(self,dataset:str,key:str):
        if dataset==VIRTUAL:
            from c2_plotter_core import CATEGORIES
            meta=[self._direct_metadata(ds,key) for ds in CATEGORIES.values()]
            # All three category forecasts are separate jobs; summed time is
            # total compute expenditure, NOT elapsed wall time if jobs ran in parallel.
            def add(field):
                vals=[_num(item.get(field)) for item in meta]
                return float(sum(vals)) if all(math.isfinite(v) for v in vals) else math.nan
            return add('fit_seconds'),add('forecast_seconds'),add('model_seconds'),add('warning_count')
        m=self._direct_metadata(dataset,key)
        return tuple(_num(m.get(f)) for f in ('fit_seconds','forecast_seconds','model_seconds','warning_count'))

    def _direct_mase_denom(self,dataset:str,key:str)->float:
        m=self._direct_metadata(dataset,key)
        mae=_num(m.get('mae'));mase=_num(m.get('mase_weekly'))
        if math.isfinite(mae) and math.isfinite(mase) and mase>0:
            return mae/mase
        # Exact zero-error model has MAE=MASE=0; its filtered MASE cannot
        # be computed from these summary scores. Leave it as N/A rather
        # than fabricate a denominator.
        return math.nan

    def _full_year_metadata_score(self,dataset:str,key:str):
        m=self._direct_metadata(dataset,key)
        look={'MAE':'mae','RMSE':'rmse','WAPE':'wape_percent',
              'MASE':'mase_weekly','Bias':'bias_actual_minus_forecast',
              'sMAPE':'smape_percent'}
        result={k:_num(m.get(v)) for k,v in look.items()}
        if not (math.isfinite(result['MAE']) and math.isfinite(result['RMSE'])):
            return None
        return result

    def score_one(self,dataset:str,key:str,bus:str,begin:str='',end:str='') -> RankedRow:
        fit,predict,total,warnings=self._model_metadata(dataset,key)
        # For the unfiltered original direct forecast, metrics are already
        # available in JSON and avoid reading entire files to sort the list.
        if dataset!=VIRTUAL and not begin.strip() and not end.strip():
            scores=self._full_year_metadata_score(dataset,key)
        else:
            scores=None
        if scores is None:
            frame=window(self.db.series(dataset,key,bus),begin,end)
            if dataset==VIRTUAL:
                denom=self._mase_denom_for_virtual(bus)
            else:
                denom=self._direct_mase_denom(dataset,key)
            scores=_score_hourly(frame.actual.to_numpy(),frame.forecast.to_numpy(),denom)
        return RankedRow(key=key,mae=scores['MAE'],rmse=scores['RMSE'],
                         wape=scores['WAPE'],mase=scores['MASE'],
                         bias=scores['Bias'],smape=scores['sMAPE'],
                         fit=fit,predict=predict,total=total,warnings=warnings)

    def rank(self,dataset:str,bus:str,by:str,begin:str='',end:str='') -> tuple[list[RankedRow],list[str]]:
        if by not in SORT_OPTIONS:
            raise ValueError(f'Unknown ranking metric {by}')
        # Validate date input even for full-year JSON fast-path; otherwise
        # invalid date text could silently display a full-year ranking.
        from c2_plotter_core import parse_date
        start=parse_date(begin,False)
        stop=parse_date(end,True)
        if start is not None and stop is not None and start>stop:
            raise ValueError('Ranking date range must have From <= To.')
        metric=SORT_OPTIONS[by]
        ranked=[];failures=[]
        for key in self.db.options(dataset):
            try:
                ranked.append(self.score_one(dataset,key,bus,begin,end))
            except (ValueError,KeyError,OSError,RuntimeError,ArithmeticError) as exc:
                failures.append(f'{key}: {str(exc)[:180]}')
        # N/A values always at the bottom. Bias is ranked by magnitude
        # (distance from zero); negative bias is NOT automatically "best".
        ranked.sort(key=lambda item:(item.metric(metric),item.key.casefold()))
        return ranked,failures


def pretty_number(value:float, decimals:int=2) -> str:
    return f'{value:,.{decimals}f}' if math.isfinite(value) else 'N/A'
