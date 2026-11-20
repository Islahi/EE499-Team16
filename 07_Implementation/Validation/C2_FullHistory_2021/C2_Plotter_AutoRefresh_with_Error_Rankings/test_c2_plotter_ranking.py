"""Quick math checks; run with `python test_c2_plotter_ranking.py` (no results folder needed)."""
import math
import numpy as np
from c2_plotter_ranking import _score_hourly,_weekly_denom,RankedRow,SORT_OPTIONS

def check():
    m=_score_hourly(np.array([100.,200.,300.]),np.array([110.,180.,330.]),10.)
    assert math.isclose(m['MAE'],20.)
    assert math.isclose(m['RMSE'],math.sqrt((100+400+900)/3))
    assert math.isclose(m['WAPE'],10.)
    assert math.isclose(m['MASE'],2.)
    assert math.isclose(m['Bias'],(100-110+200-180+300-330)/3)
    assert m['sMAPE']>0
    y=np.arange(300,dtype=float)
    assert math.isclose(_weekly_denom(y),168.)
    r1=RankedRow('A',10,20,15,1.0,-50,8,50,1,51,0)
    r2=RankedRow('B',11,19,16,1.1,2,8,20,1,21,0)
    # Do not accidentally rank large negative bias as a better forecast.
    assert r1.metric('Bias')==50
    assert r2.metric('Bias')==2
    assert r2.metric(SORT_OPTIONS['|Bias| (closest to zero)']) < r1.metric('Bias')
    assert SORT_OPTIONS['RMSE (smallest)']=='RMSE'
    print('C2 plotter ranking math checks passed.')

if __name__=='__main__':check()
