"""Offline checks for data, metrics, model coverage, seasonality, output schemas and leakage.
Does not claim to test StatsForecast fitting without StatsForecast installed.
"""
from pathlib import Path
import sys
import types
import os
from tempfile import TemporaryDirectory
import numpy as np
import pandas as pd

import c2_benchmark_settings as S
from c2_benchmark_core import (
    TRAIN_CLOCK,TEST_CLOCK,SeriesCase,load_cases,daylight_mask_utc,pv_power_from_ghi,
    scoring,monthly_scores,postprocess,seasonal_naive_numpy,unsupported_reason,
    score_and_save,make_model,predict_model
)
from src_accelerated.pv_model import PVModelConfig, irradiance_to_power


def main():
    assert len(TRAIN_CLOCK)==15312,len(TRAIN_CLOCK)
    assert len(TEST_CLOCK)==8784,len(TEST_CLOCK)
    assert TEST_CLOCK[0]==TRAIN_CLOCK[-1]+pd.Timedelta(hours=1)
    assert len(S.MODELS)==9 and len(S.SEASONALITIES)==7
    for period in [0,5,100,150,500,1000,1200]:
        official=irradiance_to_power(period,S.PV_RATED_KW,
            PVModelConfig(S.PV_CRITICAL_IRRADIANCE_W_M2,S.PV_STANDARD_IRRADIANCE_W_M2))
        assert np.isclose(pv_power_from_ghi([period])[0],official)
    cases=load_cases()
    assert len(cases)==7,f'Expected 2 load + 5 PV cases; got {len(cases)}'
    assert sum(c.category=='load' for c in cases)==2
    assert sum(c.category=='pv' for c in cases)==5
    tr=np.ones(200)*100
    tr[168:]=110
    scores=scoring([100,200],[90,180],tr)
    assert np.isclose(scores['mae_kw'],15)
    assert np.isclose(scores['rmse_kw'],np.sqrt(250))
    assert np.isclose(scores['wape_percent'],10)
    assert np.isclose(scores['bias_kw_actual_minus_forecast'],15)
    assert np.isclose(scores['mase_weekly'],1.5)
    for c in cases:
        assert c.y_train.shape==(15312,)
        assert c.y_test.shape==(8784,)
        assert c.y_train.min()>=0 and c.y_test.min()>=0
        assert np.isfinite(c.y_train).all() and np.isfinite(c.y_test).all()
        if c.category=='pv':
            assert c.y_train.max()<=S.PV_RATED_KW+1e-8
            assert c.y_test.max()<=S.PV_RATED_KW+1e-8
            mask=daylight_mask_utc(TEST_CLOCK,c.site_lat,c.site_lon)
            assert 0.4<np.mean(mask)<0.65
        naive=seasonal_naive_numpy(c.y_train,168,len(TEST_CLOCK))
        p,_=postprocess(naive,c)
        assert len(p)==8784 and p.min()>=0
        s,monthly=monthly_scores(c.y_test,p,c.y_train)
        assert len(monthly)==12 and np.isfinite(s['rmse_kw'])
    assert unsupported_reason('MSTL',(24,168,720,8760),15312)
    assert unsupported_reason('AutoETS',(8760,),15312)
    assert unsupported_reason('AutoETS',(24,168),15312)
    assert not unsupported_reason('AutoTBATS',(24,168,720),15312)
    with TemporaryDirectory() as d:
        c=cases[0]
        fake=np.ones(len(TEST_CLOCK))*100
        info=score_and_save(c,'SeasonalNaive','daily',fake,Path(d),0,0.01,'unit_test_stub')
        assert info['status']=='OK'
        assert len(pd.read_csv(Path(d)/'hourly_comparison.csv'))==8784
        assert len(pd.read_csv(Path(d)/'monthly_metrics.csv'))==12
    # Validate all nine constructor keyword arguments without the external package.
    # This catches accidental use of obsolete parameter names (e.g. seasonal_periods).
    from unittest.mock import patch
    from inspect import signature
    class FakeModel:
        def __init__(self, **kwargs): self.kwargs = kwargs
        def __repr__(self): return 'AutoETS'
    model_names=['AutoARIMA','AutoETS','AutoCES','AutoTheta','MSTL','AutoTBATS','AutoMFLES','SeasonalNaive','HoltWinters']
    fake=types.SimpleNamespace(**{n:FakeModel for n in model_names})
    with patch.dict(sys.modules, {'statsforecast':types.SimpleNamespace(models=fake),
                                  'statsforecast.models':fake}):
        for name in S.MODELS:
            length=(24,168) if name in S.MULTI_SEASON_MODELS else (24,)
            o=make_model(name,length,15312)
            assert isinstance(o,FakeModel)
            if name=='AutoTBATS': assert o.kwargs['season_length']==[24,168]
            if name=='AutoMFLES': assert o.kwargs['metric']=='mae'
    # Optional integration test: fit selected models on short synthetic series only.
    try: import statsforecast
    except ImportError:
        print('StatsForecast unavailable here: model API integration not executed; offline tests passed.')
    else:
        if os.environ.get("C2_MODEL_API_TEST") != "1":
            print("StatsForecast detected; set C2_MODEL_API_TEST=1 for slow live model smoke tests.")
            print("ALL C2 benchmark offline tests passed")
            return
        import warnings
        x=np.array([80+20*np.sin(i*2*np.pi/24) for i in range(24*100)],dtype=float)
        for name in S.MODELS:
            if name in ('MSTL','AutoMFLES','AutoTBATS'):
                lengths=(24,168)
            else: lengths=(24,)
            try:
                mdl=make_model(name,lengths,len(x))
                forecast,fit_s,pred_s=predict_model(mdl,x,48)
                assert len(forecast)==48 and np.isfinite(forecast).all()
                print('API OK:',name,fit_s,pred_s)
            except Exception as exc:
                raise AssertionError(f'Nixtla model API test failed for {name}: {exc}') from exc
    print('ALL C2 benchmark tests passed: 7 datasets, yearly clocks, metrics, project PV model, output files')


if __name__=='__main__':
    main()
