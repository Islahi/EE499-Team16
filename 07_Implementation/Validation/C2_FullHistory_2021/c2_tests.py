"""Offline smoke-checks for source data + scoring + model configuration.
StatsForecast API-only checks are optional with --live-api (requires installed package).
"""
import sys
import math
import numpy as np
import c2_config as C
from c2_data import TRAIN,TEST,cases
from c2_models import unsupported_reason,make_model
from c2_scoring import scores,postprocess,save_case
from tempfile import TemporaryDirectory
from pathlib import Path

def main():
    cs=cases();assert len(cs)==6
    assert len(TRAIN)>3*8760, len(TRAIN)
    assert len(TEST)==8760,len(TEST)
    for c in cs:
        assert len(c.train)==len(TRAIN) and len(c.actual)==len(TEST),c.name
        assert np.isfinite(c.train).all() and np.isfinite(c.actual).all(),c.name
        assert (c.train>=0).all() and (c.actual>=0).all(),c.name
        assert c.train.mean()>0,c.name
    assert unsupported_reason('AutoARIMA',(720,),len(TRAIN))
    assert unsupported_reason('AutoETS',(720,),len(TRAIN))
    assert unsupported_reason('HoltWinters',(720,),len(TRAIN))
    assert unsupported_reason('AutoARIMA',(24,),len(TRAIN)) is None
    assert unsupported_reason('AutoTBATS',(24,168,720,8760),len(TRAIN)) is None
    m=scores([90.,180.,270.],[100.,200.,300.],np.arange(1000.)+1)
    assert np.isclose(m['mae'],20.)
    assert np.isclose(m['rmse'],math.sqrt((100+400+900)/3))
    with TemporaryDirectory() as d:
        c=cs[0]
        out=Path(d)
        guess=np.resize(c.train[-168:],len(TEST))
        r=save_case(c,guess,out)
        assert (out/'hourly_comparison.csv').is_file() and (out/'monthly_metrics.csv').is_file()
        assert np.isfinite(r['rmse'])
    print('PASS: 6 input cases (5 LOAD, 1 PV), full-year 2021, metrics, adapters and safety skips.')
    if '--live-api' in sys.argv:
        import statsforecast
        from time import perf_counter
        x=100+20*np.sin(2*np.pi*np.arange(24*140)/24)
        for name in C.MODELS:
            model=make_model(name,(24,))
            begin=perf_counter()
            model.fit(x/x.mean())
            pred=model.predict(h=48)['mean']
            assert np.isfinite(pred).all() and len(pred)==48,name
            print(f'LIVE API OK: {name:15s} {perf_counter()-begin:.2f}s')
if __name__=='__main__':main()
