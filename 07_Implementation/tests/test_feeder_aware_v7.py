"""v7: electrical laterals, sensitivity-directed dispatch, annual gates."""
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.bess import BESSConfig, BESSState
from src.data_loader import ProfileData
from src.feeder_aware import (ImprovementRules, balanced_shortlist,
    lateral_map, technical_improvement)
from src.network_model import Bus, Line, Load, NetworkModel
from src.simulation import SimulationConfig, simulate_timeseries
from src.voltage_dispatch import VoltageSupport
from src.sequential_multi import _diverse_finalists
from src.optimizer import CandidateEvaluation, BESSCandidate


def network33():
    paths = [(i, i + 1) for i in range(1,18)]
    paths += [(2,19),(19,20),(20,21),(21,22)]
    paths += [(3,23),(23,24),(24,25)]
    paths += [(6,26)] + [(i,i+1) for i in range(26,33)]
    return NetworkModel([Bus(i, str(i), 12.66, i==1) for i in range(1,34)],
        [Line(str(i), a,b,.8,.25) for i,(a,b) in enumerate(paths)],
        [Load(str(i), i, 100,10) for i in range(2,34)], [],100000.,60.)


def data_row(label, shedding, deficit):
    return {'lateral':label, 'buses':[1], 'shedding_kwh':shedding,
            'voltage_deficit_pu_hours':deficit}


class FeederAwareTests(unittest.TestCase):
    def test_ieee33_grouping_uses_electrical_lateral_not_bus_number(self):
        groups = lateral_map(network33())
        self.assertEqual(groups[14], groups[17])
        self.assertEqual(groups[14], '6->7')
        self.assertEqual(groups[32], '6->26')
        self.assertNotEqual(groups[14], groups[32])

    def test_battery_near_problem_bus_has_stronger_sensitivity(self):
        support = VoltageSupport(network33())
        self.assertGreater(support.sensitivity[17][18], support.sensitivity[32][18])
        self.assertGreater(support.sensitivity[32][32], support.sensitivity[17][32])
        c17 = BESSConfig(17, 5000, 100, .2,1.,.9,.95,.95)
        c32 = BESSConfig(32, 5000, 100, .2,1.,.9,.95,.95)
        states = {c.bus_id:BESSState(4500,.9) for c in (c17,c32)}
        flow = NS(converged=True, slack_p_kw=500,
                  voltage_mag_pu={i:(.947 if i==18 else .98) for i in range(1,34)})
        requested, reason = support.dispatch(flow,(c17,c32),states,SimulationConfig())
        self.assertGreater(requested[17], requested[32])
        self.assertGreater(requested[17], 0)
        self.assertIn('voltage',reason)

    def test_charging_only_when_voltage_safe(self):
        support = VoltageSupport(network33())
        c = BESSConfig(17, 1000, 200,.2,1.,.5,.9,.9)
        states = {17:BESSState(500,.5)}
        unsafe = NS(converged=True, slack_p_kw=50,
                    voltage_mag_pu={i:.956 for i in range(1,34)})
        safe = NS(converged=True, slack_p_kw=50,
                  voltage_mag_pu={i:.99 for i in range(1,34)})
        self.assertEqual(support.dispatch(unsafe,(c,),states,SimulationConfig())[0][17],0.)
        self.assertLess(support.dispatch(safe,(c,),states,SimulationConfig())[0][17],0.)

    def test_acceptance_requires_gain_and_no_other_lateral_harm(self):
        rules=ImprovementRules(10,10,1)
        before={'A':data_row('A',100,10),'B':data_row('B',200,20)}
        better={'A':data_row('A',85,9.2),'B':data_row('B',199,19.9)}
        result=technical_improvement(before,better,'A',rules)
        self.assertTrue(result['acceptable'],result)
        self.assertAlmostEqual(result['shedding_improvement_percent'],15)
        weak={'A':data_row('A',95,9.5),'B':data_row('B',200,20)}
        self.assertFalse(technical_improvement(before,weak,'A',rules)['acceptable'])
        harmful={'A':data_row('A',80,8),'B':data_row('B',205,20)}
        self.assertFalse(technical_improvement(before,harmful,'A',rules)['acceptable'])

    def test_shortlist_diversity_and_optional_exclusion(self):
        network=network33()
        ordered=[17,14,18,16,15,32,31,30,33,23,24,20]
        ranking=[{'bus': bus, 'rank':i,'voltage_deficit_pu_hours':100-i,
                  'local_baseline_shedding_kwh':1000-i*2}
                 for i,bus in enumerate(ordered,1)]
        selected=balanced_shortlist(network,ranking,ordered,installed=(),rules=ImprovementRules())
        groups=lateral_map(network)
        self.assertIn('6->26',{groups[b] for b in selected})
        self.assertIn('6->7',{groups[b] for b in selected})
        reranked=[dict(row) for row in ranking if row['bus']!=17]
        forced=balanced_shortlist(network,reranked,[b for b in ordered if b!=17],
                                  installed=(BESSCandidate(17,100,1000),),
                                  rules=ImprovementRules(exclude_installed_laterals=True))
        self.assertTrue(forced)
        self.assertNotIn('6->7',{groups[b] for b in forced})

    def test_diverse_finalists_include_other_affected_lateral(self):
        net=network33()
        evals=[CandidateEvaluation(BESSCandidate(bus,250,10000),float(i),True)
               for i,bus in enumerate((17,14,16,18,32,31),1)]
        finalists=_diverse_finalists(evals,2,net,{'6->26':3000,'6->7':1000})
        self.assertEqual({lateral_map(net)[c.bus_id] for c in finalists},{'6->26','6->7'})

    def test_real_fbs_voltage_and_shedding_improve_when_discharge_available(self):
        net=NetworkModel([Bus(1,'S',12.66,True),Bus(2,'2',12.66),Bus(3,'3',12.66)],
                         [Line('12',1,2,4.,1.),Line('23',2,3,5.,1.5)],
                         [Load('L',3,1000,200)],[],100000,60)
        h=4
        prof=ProfileData.from_arrays(pd.date_range('2021-01-01',periods=h,freq='h'),
                                     {1:[0]*h,2:[0]*h,3:[1000]*h},
                                     {1:[0]*h,2:[0]*h,3:[200]*h},
                                     {1:[0]*h,2:[0]*h,3:[0]*h},
                                     {1:[0]*h,2:[0]*h,3:[0]*h})
        baseline=simulate_timeseries(net,prof,SimulationConfig(),capture_dispatch=True)
        c=BESSConfig(3,3000,300,.2,1.,.95,.9,.9)
        battery=simulate_timeseries(net,prof,SimulationConfig(),bess_fleet=(c,),capture_dispatch=True)
        self.assertTrue(baseline.completed)
        self.assertTrue(battery.completed)
        self.assertGreater(battery.steps[0].pre_control_voltage_pu[3],baseline.steps[0].pre_control_voltage_pu[3])
        self.assertLessEqual(sum(s.shedding_kw for s in battery.steps),sum(s.shedding_kw for s in baseline.steps)+1e-6)
        self.assertGreater(battery.steps[0].fleet_steps[3].actual_power_kw,0)

    def test_v7_technical_csv_exports(self):
        import tempfile
        import csv
        from src.results import export_results
        from src.optimizer import OptimizationResult
        before=data_row('A',100,10)
        after=data_row('A',80,8)
        stage={'index':1, 'status':'installed','selected':{'bus_id':17},
               'selected_lateral':'A','shortlist':[17],
               'weakness_ranking':[],
               'lateral_metrics_before':{'A':before},
               'lateral_metrics_after':{'A':after},
               'full_year_candidates':[{'bus':17,'lateral':'A',
                   'power_kw':250,'energy_kwh':10000,'annual_cost':100000,
                   'feasible':True,'technical_acceptable':True,
                   'technical_reason':'annual pass',
                   'shedding_improvement_percent':20,
                   'voltage_improvement_percent':20}]}
        run=OptimizationResult(None,0,None,[],0,True,'test',[],{'stages':[stage], 'no_bess_selected':True})
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'results'
            export_results(run,target)
            with (target/'lateral_improvement_by_stage.csv').open(encoding='utf-8-sig') as stream:
                rows=list(csv.DictReader(stream))
            self.assertEqual(rows[0]['lateral'],'A')
            self.assertEqual(float(rows[0]['shedding_improvement_percent']),20.)
            with (target/'annual_finalist_checks.csv').open(encoding='utf-8-sig') as stream:
                rows=list(csv.DictReader(stream))
            self.assertEqual(rows[0]['technical_acceptable'],'True')


if __name__ == '__main__':
    unittest.main()
