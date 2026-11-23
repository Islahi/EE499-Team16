"""Guarantee that V12 does not automatically force undersized batteries."""
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.optimizer import BESSCandidate,CandidateEvaluation,OptimizationBounds
from src.sequential_multi import _refine_annual_energy


class EnergyRefinementTests(TestCase):
    def _check(self, ratios):
        original=BESSCandidate(17,500.,50000.)
        win=CandidateEvaluation(original,10000.,True,execution_metadata={
            'annual_technical_remaining_ratio':.95,
            'technical_check':{'acceptable':True},
            'annual_coverage':{'complete':True}})
        cache={}
        for size,ratio in ratios.items():
            candidate=BESSCandidate(17,500.,float(size))
            item=CandidateEvaluation(candidate,1000.+size/10,True,execution_metadata={
                'annual_technical_remaining_ratio':ratio,
                'technical_check':{'acceptable':True},
                'annual_coverage':{'complete':True}})
            cache[candidate]=(item,object())
        # This regression intentionally tests the historical V12 100-hour
        # battery. V14's production study uses a tighter 2–12 h default;
        # explicitly widen the bounds here to preserve the old scenario.
        bounds=OptimizationBounds((17,), (500.,),tuple(ratios)+(50000.,),
                                  min_duration_hours=2., max_duration_hours=100.)
        with patch('src.sequential_multi._verify_annual_batch',return_value=cache):
            selected,simulation,details,count=_refine_annual_energy(
                None,None,None,(),win,object(),bounds,{}, {},None,1)
        self.assertEqual(count,len(ratios))
        self.assertEqual(len(details),len(ratios))
        return selected

    def test_cheaper_near_equal_capacity_wins(self):
        item=self._check({5000:.965,10000:.954,25000:.952})
        self.assertEqual(item.candidate.energy_capacity_kwh,10000)

    def test_large_capacity_kept_when_small_options_lose_reliability(self):
        item=self._check({5000:.97,10000:.963,25000:.96})
        self.assertEqual(item.candidate.energy_capacity_kwh,50000)
