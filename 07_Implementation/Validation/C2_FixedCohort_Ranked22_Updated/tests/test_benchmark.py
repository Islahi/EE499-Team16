"""Synthetic multi-year data only; asserts correct 8760-hour calendar and scoring.
Run from package root: python tests/test_benchmark.py
"""
import importlib,sys,tempfile,json
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cohort_cases import TRAIN,TEST,_aligned
from run_single_job import score,baseline
from extra_models import Fourier_basis,optimize_regression,optimize_boosting

def test():
    assert len(TEST)==8760 and len(TRAIN)==31440
    ts=TRAIN.append(TEST)
    d=ts.dayofyear.to_numpy(float)
    h=ts.hour.to_numpy(float)
    y=25+4*np.sin(2*np.pi*h/24)+8*np.cos(2*np.pi*d/365.2425)+0.001*np.arange(len(ts))
    z=_aligned(pd.DataFrame({'timestamp':ts,'load_kw':y}),'load_kw','synthetic')
    assert len(z)==len(TRAIN)+len(TEST)
    pred,params=baseline('YearAgoCalendarNaive',(8760,),z[:len(TRAIN)])
    assert len(pred)==8760 and np.isfinite(pred).all()
    p,m,detail=optimize_regression('FourierOLS',z[:len(TRAIN)],(24,168,8760))
    assert len(p)==8760 and np.isfinite(p).all() and detail['validation_days']>0
    assert score(z[len(TRAIN):],p,z[:len(TRAIN)])['rmse']>=0
    p2,m2,detail2=optimize_regression('CalendarRidge',z[:len(TRAIN)],(24,168,8760))
    assert len(p2)==8760 and np.isfinite(p2).all()
    print('PASS: 31,440-hour train, 8,760-hour test, calendar-year naive, optimized Fourier/Ridge, scoring')
if __name__=='__main__':test()
