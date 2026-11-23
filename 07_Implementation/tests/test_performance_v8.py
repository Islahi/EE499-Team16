"""Performance improvements must not silently change electrical feasibility."""
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.network_model import NetworkModel, Bus, Line, Load
from src.optimizer import (
    BESSCandidate, CandidateEvaluation, OptimizerConfig, OptimizationBounds,
    OptimizationResult, optimize)
from src.fbs import FBSConfig, OperatingPoint, prepare_fbs
from src.sequential_multi import FleetWindowEvaluator, optimize_sequential_multi, annual_fleet
from src.data_loader import ProfileData
from src.feeder_aware import ImprovementRules
from src.metrics import EconomicConfig
from src.simulation import SimulationConfig


def network():
    return NetworkModel([Bus(1, 'slack', 12.66, True), Bus(2, 'near', 12.66),
                         Bus(3, 'far', 12.66)],
                        [Line('a', 1, 2, .1, .06), Line('b', 2, 3, .2, .1)],
                        [Load('l2', 2, 100., 20.), Load('l3', 3, 130., 30.)],
                        [], 10000., 60.)


def profiles(hours=8760):
    hours_index = pd.date_range('2021-01-01', periods=hours, freq='h')
    return ProfileData.from_arrays(hours_index,
        {1: [0.]*hours, 2: [100.]*hours, 3: [130.]*hours},
        {1: [0.]*hours, 2: [20.]*hours, 3: [30.]*hours},
        {1: [0.]*hours, 2: [0.]*hours, 3: [0.]*hours},
        {1: [0.]*hours, 2: [0.]*hours, 3: [0.]*hours})


class PerformanceV8Tests(unittest.TestCase):
    def test_gwo_stops_on_feasible_stagnation_and_records_reason(self):
        b = OptimizationBounds((2, 3), (250., 500.), (1000., 2000.))
        def evaluator(net, pr, c):
            return CandidateEvaluation(c, 10.0, True)
        cfg = OptimizerConfig(population_size=8, max_iterations=30,
                              convergence_min_iterations=8,
                              convergence_patience=6,
                              convergence_relative_tolerance=.001)
        result = optimize(network(), None, b, evaluator, cfg)
        self.assertTrue(result.success)
        self.assertEqual(result.iterations, 8)
        self.assertEqual(result.metadata['stop_reason'], 'converged_no_meaningful_improvement')
        self.assertEqual(result.metadata['convergence_patience'], 6)

    def test_gwo_does_not_report_convergence_with_only_infeasible_candidates(self):
        b = OptimizationBounds((2, 3), (250.,), (1000.,))
        cfg = OptimizerConfig(population_size=4, max_iterations=10)
        result = optimize(network(), None, b,
                          lambda net, pr, c: CandidateEvaluation(c, float('inf'), False), cfg)
        self.assertEqual(result.iterations, 10)
        self.assertEqual(result.metadata['stop_reason'], 'maximum_iterations')
        self.assertFalse(result.success)

    def test_screening_cache_only_reuses_equivalent_fleet_context(self):
        candidate = BESSCandidate(2, 250., 1000.)
        evaluation = CandidateEvaluation(candidate, 1.0, True)
        first = FleetWindowEvaluator(NS(), (), 8760)
        second = FleetWindowEvaluator(NS(), (candidate,), 8760)
        with patch.object(FleetWindowEvaluator, '_evaluate_uncached', return_value=evaluation) as underlying:
            self.assertIs(first(None, None, candidate), evaluation)
            self.assertIs(first(None, None, candidate), evaluation)
            self.assertEqual(first.cache_hits, 1)
            self.assertIs(second(None, None, candidate), evaluation)
            self.assertEqual(underlying.call_count, 2)
        self.assertIsNot(first.evaluation_cache, second.evaluation_cache)

    def test_accepted_annual_finalist_is_reused_as_next_stage_assessment(self):
        baseline = NS(steps=[NS()], completed=True, converged=True, feasible=True,
                      dispatch_timing={})
        accepted = NS(steps=[NS()], completed=True, converged=True, feasible=True,
                      dispatch_timing={'fbs_calls': 20})
        old_metrics = NS(feasible=True, annual_total_cost=1000.)
        new_metrics = NS(feasible=True, annual_total_cost=950.)
        candidate = BESSCandidate(2, 250., 1000.)
        ranking = [{'bus': 2, 'voltage_deficit_pu_hours': 10.,
                    'local_baseline_shedding_kwh': 100.}]
        lateral = {'trunk:2': {'shedding_kwh': 100., 'voltage_deficit_pu_hours': 10.,
                               'buses': [2, 3]}}
        evaluation = CandidateEvaluation(candidate, 950., True, metrics=new_metrics,
            execution_metadata={'technical_check': {'acceptable': True, 'target': 'trunk:2',
                'shedding_improvement_percent': 20., 'voltage_improvement_percent': 15.},
                'lateral_metrics_after': lateral})
        search_result = OptimizationResult(candidate, 1., None, [1.], 1, True, '',
                                           [CandidateEvaluation(candidate,1.,True)],
                                           {'stop_reason': 'maximum_iterations', 'evaluations': 1})
        cfg = OptimizerConfig(population_size=3, max_iterations=1)
        with (patch('src.sequential_multi.annual_fleet', return_value=(baseline,old_metrics)) as yearly,
              patch('src.sequential_multi.screen_buses', return_value=((2,),ranking,0)),
              patch('src.sequential_multi.summarize_laterals', return_value=lateral),
              patch('src.sequential_multi.balanced_shortlist', return_value=(2,)),
              patch('src.sequential_multi.representative_lateral_windows', return_value=[[0,1]]),
              patch('src.sequential_multi._reference_window_metrics', return_value=(1.,1.)),
              patch('src.sequential_multi._probe_lateral_candidates', return_value=[]),
              patch('src.sequential_multi.optimize', return_value=search_result),
              patch('src.sequential_multi._full_year_candidate', return_value=(evaluation,accepted))):
            run, baseline_result, chosen = optimize_sequential_multi(
                network(), profiles(), OptimizationBounds((2,3), (250.,), (1000.,)),
                NS(economic_config=EconomicConfig(grid_import_tariff_per_kwh=.1,grid_export_tariff_per_kwh=0.), simulation_config=SimulationConfig()),
                cfg, max_units=1, finalists_per_stage=1)
        self.assertEqual(yearly.call_count, 1, 'One baseline; no duplicate accepted annual replay')
        self.assertIs(chosen, accepted)
        self.assertEqual(run.metadata['annual_fleet_simulations'], 2)
        self.assertEqual(run.metadata['accepted_annual_results_reused'], 1)
        self.assertEqual(run.best_candidate, candidate)

    def test_no_bess_annual_baseline_cache_invalidates_when_prices_change(self):
        study = profiles(24)
        economic = EconomicConfig(grid_import_tariff_per_kwh=.1,
                                  grid_export_tariff_per_kwh=0.)
        evaluator = NS(economic_config=economic, simulation_config=SimulationConfig())
        with patch('src.single_bess_search._baseline', None):
            first, _ = annual_fleet(network(), study, evaluator, ())
            self.assertFalse(first.dispatch_timing['no_bess_cache_hit'])
            second, _ = annual_fleet(network(), study, evaluator, ())
            self.assertIs(first, second)
            self.assertTrue(second.dispatch_timing['no_bess_cache_hit'])
            evaluator.economic_config = EconomicConfig(grid_import_tariff_per_kwh=.11,
                                                       grid_export_tariff_per_kwh=0.)
            third, _ = annual_fleet(network(), study, evaluator, ())
            self.assertIsNot(second, third)
            self.assertFalse(third.dispatch_timing['no_bess_cache_hit'])

    def test_numba_fbs_history_switch_preserves_results(self):
        net = network()
        point = OperatingPoint({1:0.,2:100.,3:130.}, {1:0.,2:20.,3:30.},
                               {1:0.,2:0.,3:0.}, {1:0.,2:0.,3:0.},
                               {1:0.,2:0.,3:100.}, {1:0.,2:0.,3:0.})
        unrecorded = prepare_fbs(net, FBSConfig(record_history=False))(point)
        recorded = prepare_fbs(net, FBSConfig(record_history=True))(point)
        self.assertTrue(unrecorded.converged and recorded.converged)
        self.assertEqual(unrecorded.iterations, recorded.iterations)
        for b in (1,2,3):
            self.assertAlmostEqual(unrecorded.voltage_mag_pu[b],recorded.voltage_mag_pu[b],places=12)
        self.assertAlmostEqual(unrecorded.slack_p_kw, recorded.slack_p_kw, places=10)
        self.assertEqual(len(unrecorded.voltage_history),0)
        self.assertEqual(len(recorded.voltage_history),recorded.iterations+1)

if __name__ == '__main__':
    unittest.main()
