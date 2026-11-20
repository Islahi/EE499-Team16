"""Smoke checks for exact legacy shortlist and non-leaking seasonal features."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from model_catalog import RANKED_TOP_20,SPECIALISTS,RANKED_22,BASELINES,NEW_OPTIMIZED,select_pairs
from extra_models import calendar_features
from cohort_config import SEASONALITIES,EXTRAS

def test():
    assert len(RANKED_22)==22 and len(set(RANKED_22))==22
    assert RANKED_TOP_20[0]==('MSTL','daily_weekly_monthly_yearly')
    assert SPECIALISTS==(('AutoTBATS','daily_weekly_monthly_yearly'),('AutoETS','weekly'))
    assert ('SeasonalNaive','yearly_365d') in RANKED_TOP_20
    assert len(NEW_OPTIMIZED)==42==len(EXTRAS)*len(SEASONALITIES)
    assert len(select_pairs('all'))==67
    assert len(select_pairs('legacy22'))==22
    assert len(select_pairs('new'))==42
    assert len(select_pairs('baselines'))==3
    assert len(select_pairs('neural',include_neural=True))==2
    assert len(select_pairs('all',include_neural=True))==69
    assert not set((m,s) for m,s,_ in select_pairs('legacy22')).intersection(set(BASELINES))
    hours=pd.date_range('2019-01-01',periods=7*24,freq='h')
    shapes={p: calendar_features(hours,p).shape for p in ((24,),(168,),(720,),(8760,),(24,168,720,8760))}
    assert len(set(shapes.values()))==5
    for dims in shapes.values():assert dims[0]==len(hours)
    # Daily-only calendar features must not encode a separate weekly indicator.
    d1=calendar_features(hours[:24],(24,))
    d2=calendar_features(hours[24:48],(24,))
    diff=d1[0]-d2[0]
    assert np.allclose(diff[2:],0), 'Daily-only seasonal features changed across consecutive days'
    print('PASS: exact 22, 42 optimized new combinations, 3 controls; calendar features respect requested periods')

if __name__=='__main__':test()
