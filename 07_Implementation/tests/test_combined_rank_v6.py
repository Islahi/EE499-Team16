"""Regression tests for combined-rank placement and dashboard forecast aggregation."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_loader import ProfileData
from src.forecast_accuracy import compare_forecast
from src.single_bess_search import screen_buses
from src.optimizer import OptimizationResult
from src.results import export_results


def trial_network():
    return NS(buses=[NS(bus_id=i) for i in range(1, 8)], slack_bus_id=lambda: 1)


def trial_result(voltages, shedding):
    return NS(dt_hours=1.0, steps=[NS(pre_control_voltage_pu=voltages,
                                       shedding_by_bus_kw=shedding)])


class CombinedRankingTests(unittest.TestCase):
    def test_equal_weighting_can_promote_high_shedding_bus(self):
        voltages = {1: 1., 2: .90, 3: .91, 4: .92, 5: .93, 6: .94, 7: .96}
        shed = {2: 0., 3: 0., 4: 15., 5: 12., 6: 10., 7: 0.}
        sites, rows, probes = screen_buses(trial_network(), trial_result(voltages, shed),
                                           (2, 3, 4, 5, 6, 7), NS(voltage_min_pu=.95))
        self.assertEqual(probes, 0)
        self.assertEqual(sites, (4, 2), 'Two of six buses must pass')
        self.assertEqual([r['bus'] for r in rows[:2]], [4, 2])
        bus2 = next(r for r in rows if r['bus'] == 2)
        bus4 = next(r for r in rows if r['bus'] == 4)
        self.assertEqual((bus2['voltage_rank'], bus2['shedding_rank']), (1, 4))
        self.assertEqual((bus4['voltage_rank'], bus4['shedding_rank']), (3, 1))
        self.assertEqual(bus4['combined_score'], 2.)
        self.assertEqual(bus2['combined_score'], 2.5)
        self.assertTrue(all(r['retained'] == (r['rank'] <= 2) for r in rows))
        self.assertEqual([r['shedding_rank'] for r in rows if r['local_baseline_shedding_kwh'] == 0.], [4, 4, 4])

    def test_rerank_uses_updated_voltages_and_shedding_and_excludes_installed(self):
        first = trial_result({1:1.,2:.9,3:.91,4:.92,5:.93,6:.94,7:.96},
                             {2:0.,3:0.,4:15.,5:12.,6:10.,7:0.})
        second = trial_result({1:1.,2:.97,3:.94,4:.98,5:.95,6:.89,7:.88},
                              {2:0.,3:0.,4:0.,5:0.,6:50.,7:30.})
        initial, _, _ = screen_buses(trial_network(), first, range(2,8), NS(voltage_min_pu=.95))
        after, ranking, _ = screen_buses(trial_network(), second,
                                         tuple(bus for bus in range(2,8) if bus != 4), NS(voltage_min_pu=.95))
        self.assertEqual(initial,(4,2))
        self.assertEqual(after,(7,6))
        self.assertEqual(len(after),2)
        self.assertTrue(all(r['bus'] != 4 for r in ranking))
        self.assertAlmostEqual(next(r for r in ranking if r['bus'] == 6)['local_baseline_shedding_kwh'],50.)

    def test_ieee33_shortlist_counts_are_dynamic(self):
        network=NS(buses=[NS(bus_id=i) for i in range(1,34)], slack_bus_id=lambda:1)
        flows=trial_result({i:1.-0.002*i for i in range(1,34)},
                           {i:float(i % 9) for i in range(2,34)})
        for excluded, expected in [((),11), ((33,),11), ((33,32),10)]:
            eligible=tuple(i for i in range(2,34) if i not in excluded)
            sites, evidence, _=screen_buses(network,flows,eligible,NS(voltage_min_pu=.95))
            self.assertEqual(len(sites),expected)
            self.assertEqual(len(evidence),len(eligible))
            self.assertTrue(set(sites).isdisjoint(excluded))

    def test_missing_shedding_must_not_be_silently_treated_as_no_shedding(self):
        bad = trial_result({i:.91 for i in range(1,8)}, {})
        bad.steps[0].shedding_by_bus_kw = None
        with self.assertRaisesRegex(ValueError, 'Per-bus load shedding'):
            screen_buses(trial_network(),bad,range(2,8),NS(voltage_min_pu=.95))

    def test_export_all_buses_of_each_stage(self):
        first, evidence, _ = screen_buses(trial_network(),
             trial_result({1:1.,2:.9,3:.91,4:.92,5:.93,6:.94,7:.96},
                          {2:0.,3:0.,4:15.,5:12.,6:10.,7:0.}),range(2,8),NS(voltage_min_pu=.95))
        stages=[{'index': 1, 'status':'installed', 'selected':{'bus_id': 4},
                 'candidate_count':2,'weakness_ranking':evidence, 'shortlist':list(first)}]
        result=OptimizationResult(None,0.,None,[],0,True,'test',[],{'stages':stages,'no_bess_selected':True})
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'run'
            export_results(result,path)
            with (path/'bus_ranking_by_stage.csv').open(encoding='utf-8-sig',newline='') as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),6)
            self.assertEqual([int(r['bus_id']) for r in rows[:2]],[4,2])
            self.assertEqual(sum(r['retained']=='True' for r in rows),2)
            self.assertEqual(sum(r['selected_for_installation']=='True' for r in rows),1)
            self.assertEqual(rows[0]['voltage_rank'],'3')
            self.assertEqual(rows[0]['shedding_rank'],'1')

    def test_forecast_errors_are_mean_per_bus_not_aggregate(self):
        times=pd.date_range('2021-01-01',periods=2,freq='h')
        original=ProfileData.from_arrays(times,
                 {1:[0.,0.],2:[10.,10.],3:[20.,20.]},
                 {1:[0.,0.],2:[0.,0.],3:[0.,0.]},
                 {1:[0.,0.],2:[5.,5.],3:[0.,0.]},
                 {1:[0.,0.],2:[0.,0.],3:[0.,0.]})
        predicted=ProfileData.from_arrays(times,
                 {1:[0.,0.],2:[13.,13.],3:[18.,18.]},
                 {1:[0.,0.],2:[0.,0.],3:[0.,0.]},
                 {1:[0.,0.],2:[6.,6.],3:[0.,0.]},
                 {1:[0.,0.],2:[0.,0.],3:[0.,0.]})
        scores, series=compare_forecast(original,predicted,{2:'residential',3:'residential'},'2020-12-31 23:00')
        residential=next(row for row in scores if row['category']=='residential')
        self.assertEqual(residential['bus_count'],2)
        self.assertAlmostEqual(residential['mae_kw'],2.5)  # (3 + 2) / 2
        self.assertAlmostEqual(residential['rmse_kw'],2.5)
        self.assertAlmostEqual(residential['aggregate_mae_kw'],1.)  # cancellations
        self.assertAlmostEqual(residential['wape_percent'],20.)  # (30% + 10%)/2
        self.assertAlmostEqual(residential['pooled_wape_percent'],100*5/30)
        pv=next(row for row in scores if row['category']=='solar_pv')
        self.assertEqual(pv['bus_count'],1)  # zero-PV buses excluded
        self.assertAlmostEqual(pv['mae_kw'],1.)
        plot=next(row for row in series if row['category']=='residential')
        self.assertEqual((plot['actual_kw'],plot['forecast_kw']), (30.,31.))

    def test_dashboard_has_stage_tables_and_correct_forecast_labels(self):
        script=(ROOT/'src/assets/dashboard.js').read_text(encoding='utf-8')
        for text in ('After BESS ', 'Before BESS 1', 'Voltage rank', 'Shedding rank',
                     'bus_ranking_by_stage.csv','Avg bus MAE (kW)','Avg bus RMSE (kW)'):
            self.assertIn(text,script)


if __name__=='__main__':
    unittest.main()
