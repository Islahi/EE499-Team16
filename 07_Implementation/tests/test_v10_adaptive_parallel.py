"""V10 physical voltage gate, annual-aware sampling, and worker safety."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.network_model import NetworkModel, Bus, Line
from src.feeder_aware import (ImprovementRules,
    incremental_and_cumulative_improvement, representative_lateral_windows)
from src.optimizer import _without_progress, BESSCandidate
from src.sequential_multi import _verify_annual_batch


def item(shed, volt):
    return {'shedding_kwh':shed, 'voltage_deficit_pu_hours':volt, 'buses':[2]}


class V10Tests(unittest.TestCase):
    def test_small_voltage_correction_meeting_095_is_enough(self):
        # From 0.946 pu to 0.951 pu can correct a violation with <10% voltage rise.
        old={'A':item(0., .004), 'B':item(50.,2.)}
        new={'A':item(0.,0.),'B':item(50.,2.)}
        result=incremental_and_cumulative_improvement(old,new,old,'A',ImprovementRules())
        self.assertTrue(result['acceptable'],result)
        self.assertTrue(result['voltage_compliant_before_shedding'])
        self.assertTrue(result['cumulative_target_met'])

    def test_measurable_shedding_relief_below_ten_percent_can_pass(self):
        old={'A':item(100.,10.),'B':item(50.,5.)}
        new={'A':item(99.9,9.999),'B':item(50.,5.)}
        self.assertTrue(incremental_and_cumulative_improvement(old,new,old,'A',ImprovementRules())['acceptable'])

    def test_voltage_cannot_be_gained_by_shedding_more_demand(self):
        old={'A':item(100.,10.),'B':item(50.,5.)}
        new={'A':item(100.001,0.),'B':item(50.,5.)}
        result=incremental_and_cumulative_improvement(old,new,old,'A',ImprovementRules())
        self.assertFalse(result['acceptable'])
        self.assertIn('target shedding increased',result['reason'])

    def test_no_incremental_improvement_is_rejected(self):
        old={'A':item(100.,10.)}
        result=incremental_and_cumulative_improvement(old,old,old,'A',ImprovementRules())
        self.assertFalse(result['acceptable'])

    def test_sampling_spans_seasons_and_severe_laterals_with_same_hour_budget(self):
        net=NetworkModel([Bus(1,'slack',12.66,True),Bus(2,'2',12.66),
                          Bus(3,'3',12.66),Bus(4,'4',12.66)],
                         [Line('1-2',1,2,.1,.1),Line('2-3',2,3,.1,.1),
                          Line('1-4',1,4,.1,.1)],[],[],10000.,60.)
        times=pd.date_range('2021-01-01',periods=8760,freq='h')
        steps=[]
        for hour in range(8760):
            # Two different high-risk electrical laterals in different seasons.
            a = 300. if 220<=hour<268 else 0.
            b = 600. if 5300<=hour<5350 else 0.
            steps.append(NS(pre_control_voltage_pu={1:1.,2:1.,3:.92 if a else 1.,
                                                     4:.90 if b else 1.},
                            shedding_by_bus_kw={2:0.,3:a,4:b}))
        baseline=NS(steps=steps)
        profile=NS(timestamps=times,
                   load_p_kw={3:[200.] *8760, 4:[250.] *8760},
                   pv_p_kw={3:[0.] *8760,4:[0.] *8760})
        groups=representative_lateral_windows(net,baseline,profile,2,.95)
        self.assertEqual(len(groups),7)
        self.assertEqual(sum(map(len,groups)),336)
        self.assertTrue(all(len(g)==48 and all(b==a+1 for a,b in zip(g,g[1:])) for g in groups))
        dates=[times[g[0]] for g in groups]
        quarters={date.quarter for date in dates}
        self.assertEqual(quarters,{1,2,3,4})
        self.assertTrue(any(set(g).intersection(range(220,268)) for g in groups))
        self.assertTrue(any(set(g).intersection(range(5300,5350)) for g in groups))
        taken=[i for g in groups for i in g]
        self.assertEqual(len(taken),len(set(taken)))

    def test_nested_progress_callback_is_removed_for_worker_pickling(self):
        callback=lambda x: x
        original=NS(progress=callback)
        nested=NS(original_evaluator=original,progress=callback)
        cleaned=_without_progress(nested)
        self.assertIsNone(cleaned.progress)
        self.assertIsNone(cleaned.original_evaluator.progress)
        self.assertIs(nested.progress,callback)
        self.assertIs(original.progress,callback)

    def test_sequential_screening_can_prioritize_shedding_over_voltage_rank(self):
        from src.single_bess_search import screen_buses
        net=NetworkModel([Bus(1,'s',12.66,True),Bus(2,'2',12.66),
                          Bus(3,'3',12.66),Bus(4,'4',12.66)],
                         [Line('12',1,2,.1,.1),Line('13',1,3,.1,.1),
                          Line('14',1,4,.1,.1)],[],[],10000.,60.)
        step=NS(pre_control_voltage_pu={1:1.,2:.949,3:.85,4:.98},
                shedding_by_bus_kw={2:100.,3:0.,4:0.})
        baseline=NS(steps=[step]*24,dt_hours=1.)
        equal,_,_=screen_buses(net,baseline,(2,3,4),NS(voltage_min_pu=.95))
        weighted,_,_=screen_buses(net,baseline,(2,3,4),NS(voltage_min_pu=.95),shedding_weight=.8)
        self.assertEqual(equal,(3,))
        self.assertEqual(weighted,(2,))

    def test_parallel_annual_batch_retains_candidate_order(self):
        # Synthetic small chronological tasks can run as separate processes,
        # while keeping result order deterministic.
        from src.data_loader import ProfileData
        from src.simulation import SimulationConfig
        from src.metrics import EconomicConfig
        from src.optimizer import SimulationEvaluator, BESSParameters
        from src.constraint_dispatch import ConstraintAwareDispatch
        hours=24
        times=pd.date_range('2021-01-01',periods=hours,freq='h')
        net=NetworkModel([Bus(1,'s',12.66,True),Bus(2,'2',12.66)],
                         [Line('12',1,2,.1,.1)],[],[],10000.,60.)
        profiles=ProfileData.from_arrays(times,{2:[0.]*hours},{2:[0.]*hours},{},{})
        ev=SimulationEvaluator(EconomicConfig(grid_import_tariff_per_kwh=.1,
                 grid_export_tariff_per_kwh=0.), BESSParameters(.9,.9),
                 ConstraintAwareDispatch(),SimulationConfig())
        a,b=BESSCandidate(2,250.,1000.),BESSCandidate(2,500.,1000.)
        result=_verify_annual_batch(net,profiles,ev,(),(a,b),None,None,ImprovementRules(),workers=2)
        self.assertEqual(list(result),[a,b])
        for candidate,(evaluation,series) in result.items():
            self.assertFalse(evaluation.feasible, 'Short periods must not count as annual verification')
            self.assertEqual(evaluation.execution_metadata['annual_coverage']['processed_hours'],hours)
            self.assertEqual(len(series.steps),hours)


if __name__=='__main__': unittest.main()
