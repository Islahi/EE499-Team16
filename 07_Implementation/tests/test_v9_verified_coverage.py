"""v9 regression: incremental acceptance, candidate diversity and exact annual coverage."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.feeder_aware import (ImprovementRules,
    incremental_and_cumulative_improvement)
from src.sequential_multi import (_diverse_finalists,
    _full_year_candidate, annual_coverage)
from src.optimizer import CandidateEvaluation, BESSCandidate, OptimizationBounds


def metric(shed, volt):
    return {'shedding_kwh': shed, 'voltage_deficit_pu_hours': volt, 'buses': [2]}


class V9Tests(unittest.TestCase):
    def test_incremental_6_percent_accepted_although_cumulative_10_percent_unmet(self):
        initial = {'A': metric(100, 20), 'B': metric(100, 10)}
        proposed = {'A': metric(94, 19), 'B': metric(100, 10)}
        actual = incremental_and_cumulative_improvement(initial, proposed, initial, 'A', ImprovementRules())
        self.assertTrue(actual['acceptable'])
        self.assertFalse(actual['cumulative_target_met'])
        self.assertAlmostEqual(actual['shedding_improvement_percent'], 6)
        self.assertAlmostEqual(actual['cumulative_shedding_improvement_percent'], 6)

    def test_second_incremental_stage_can_meet_cumulative_target(self):
        initial = {'A': metric(100, 20), 'B': metric(100, 10)}
        current = {'A': metric(94, 19), 'B': metric(100, 10)}
        proposed = {'A': metric(88, 18.8), 'B': metric(100, 10)}
        actual = incremental_and_cumulative_improvement(current, proposed, initial, 'A', ImprovementRules())
        self.assertTrue(actual['acceptable'])
        self.assertTrue(actual['cumulative_target_met'])
        self.assertAlmostEqual(actual['shedding_improvement_percent'], 100*6/94)
        self.assertAlmostEqual(actual['cumulative_shedding_improvement_percent'], 12)

    def test_incremental_acceptance_protects_other_laterals(self):
        initial = {'A': metric(100, 20), 'B': metric(100, 10)}
        proposed = {'A': metric(88, 18), 'B': metric(105, 10)}
        actual = incremental_and_cumulative_improvement(initial, proposed, initial, 'A', ImprovementRules())
        self.assertFalse(actual['acceptable'])
        self.assertIn('worsened', actual['reason'])

    def test_no_false_verified_status_after_partial_year(self):
        times = pd.date_range('2021-01-01', periods=8760, freq='h')
        profile = NS(timestamps=times, dt_hours=1.0)
        short = NS(steps=[NS(timestamp=t) for t in times[:4000]],
                   completed=True, converged=True, feasible=True)
        c = annual_coverage(short, profile)
        self.assertFalse(c['complete'])
        self.assertEqual(c['processed_hours'], 4000)
        self.assertEqual(c['expected_hours'], 8760)
        self.assertEqual(c['status'], 'incomplete_annual')

    def test_all_hours_but_wrong_timestamps_is_not_verified(self):
        times = pd.date_range('2021-01-01', periods=8760, freq='h')
        wrong = times + pd.Timedelta(hours=1)
        profile = NS(timestamps=times, dt_hours=1.0)
        candidate = NS(steps=[NS(timestamp=t) for t in wrong],
                       completed=True, converged=True, feasible=True)
        status = annual_coverage(candidate, profile)
        self.assertFalse(status['complete'])
        self.assertEqual(status['status'], 'timestamp_mismatch')

    def test_incomplete_annual_finalist_rejected_without_false_cost(self):
        times = pd.date_range('2021-01-01', periods=8760, freq='h')
        profile = NS(timestamps=times, dt_hours=1.0)
        short = NS(steps=[NS(timestamp=t) for t in times[:4000]],
                   dispatch_timing={}, completed=True, converged=True, feasible=True,
                   message='Mock incorrectly claims complete')
        c = BESSCandidate(2, 250, 1000)
        fake_metrics = NS(feasible=True, annual_total_cost=0.01)
        with patch('src.sequential_multi.annual_fleet', return_value=(short, fake_metrics)):
            evaluation, _ = _full_year_candidate(None, profile, None, (), c)
        self.assertFalse(evaluation.feasible)
        self.assertEqual(evaluation.execution_metadata['annual_coverage']['processed_hours'], 4000)
        self.assertIsNone(evaluation.metrics)

    def test_complete_hourly_timestamps_qualify_as_complete_coverage(self):
        times = pd.date_range('2021-01-01', periods=8760, freq='h')
        profile = NS(timestamps=times, dt_hours=1.0)
        candidate = NS(steps=[NS(timestamp=t) for t in times],
                       completed=True, converged=True, feasible=True)
        self.assertTrue(annual_coverage(candidate, profile)['complete'])

    def test_power_diversity_in_first_three_finalists(self):
        from src.network_model import NetworkModel, Bus, Line
        net = NetworkModel([Bus(1,'s',12.66,True), Bus(2,'2',12.66),
                            Bus(3,'3',12.66), Bus(4,'4',12.66)],
                           [Line('12',1,2,.1,.1), Line('13',1,3,.1,.1),
                            Line('34',3,4,.1,.1)],[],[],10000.,60.)
        bounds = OptimizationBounds((2,3,4), (250,2500,5000), (1000,10000,50000))
        rows = [CandidateEvaluation(BESSCandidate(b,p,e), cost, True)
                for b,p,e,cost in [(2,250,50000,1), (2,250,10000,2),
                                    (3,250,50000,3), (4,250,10000,4),
                                    (2,5000,10000,7), (3,2500,10000,8),
                                    (3,5000,50000,9)]]
        finalists = _diverse_finalists(rows, 3, net, {'1->3':100,'1->2':40}, bounds)
        self.assertEqual(len(finalists), 3)
        self.assertTrue(any(c.power_rating_kw == 5000 for c in finalists), finalists)
        self.assertEqual({c.bus_id in (3,4) for c in finalists}, {True,False})


if __name__ == '__main__':
    unittest.main()
