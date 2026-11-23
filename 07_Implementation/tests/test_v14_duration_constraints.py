"""V14: no under/oversized E/P pair may reach expensive power-flow simulation."""
import sys
import unittest
from multiprocessing import get_context
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.optimizer import (
    BESSCandidate, CandidateEvaluation, OptimizationBounds, OptimizerConfig,
    _candidate_from_position, _evaluate, exhaustive_search, genetic_optimize, optimize,
)
from src.sequential_multi import _probe_lateral_candidates, _refine_annual_energy
from src.approved_methodology import normalize_settings
from src.network_model import NetworkModel, Bus, Line


def network():
    return NetworkModel([Bus(1, "Slack", 12.66, True), Bus(2, "B2", 12.66), Bus(3, "B3", 12.66)],
                        [Line("L12", 1, 2, .1, .1), Line("L13", 1, 3, .1, .1)],
                        [], [], 10000., 60.)


class CountingEvaluator:
    def __init__(self):
        self.visited = []

    def __call__(self, network_obj, profiles, candidate):
        self.visited.append(candidate)
        return CandidateEvaluation(candidate, candidate.power_rating_kw + .01*candidate.energy_capacity_kwh, True)


class DurationBoundsTests(unittest.TestCase):
    def setUp(self):
        self.bounds = OptimizationBounds((2, 3), (250., 500., 1000., 3000., 5000.),
                                         (250., 500., 1000., 2000., 5250., 6000., 10000., 15000., 50000.))

    def test_unrealistic_combinations_are_rejected(self):
        for power, energy in [(5000., 5250.), (3000., 250.), (250., 50000.), (250., 250.)]:
            with self.subTest(power=power, energy=energy), self.assertRaises(ValueError):
                self.bounds.validate_candidate(BESSCandidate(2, power, energy))
        for power, energy in [(250., 500.), (1000., 2000.), (5000., 10000.), (5000., 50000.)]:
            with self.subTest(power=power, energy=energy):
                if energy / power > self.bounds.max_duration_hours:
                    with self.assertRaises(ValueError):
                        self.bounds.validate_candidate(BESSCandidate(2, power, energy))
                else:
                    self.bounds.validate_candidate(BESSCandidate(2, power, energy))

    def test_2_and_12_hour_boundaries(self):
        bounds = OptimizationBounds((2,), (250.,), (250., 500., 3000., 3250.))
        self.assertEqual(bounds.energies_for_power(250.), (500., 3000.))
        self.assertEqual(bounds.feasible_design_count(), 2)

    def test_reject_bad_duration_parameters_and_disjoint_grids(self):
        for low, high in [(0, 12), (2, 0), (12, 2), (-1, 2)]:
            with self.subTest(low=low, high=high), self.assertRaises(ValueError):
                OptimizationBounds((2,), (500.,), (1000.,), low, high)
        with self.assertRaisesRegex(ValueError, 'No battery power/energy catalog pair'):
            OptimizationBounds((2,), (3000.,), (250.,))

    def test_projection_of_every_wolf_is_feasible(self):
        for p in range(-2, len(self.bounds.power_ratings_kw)+5):
            for e in range(-2, len(self.bounds.energy_capacities_kwh)+5):
                candidate = _candidate_from_position((1.5, p + 1., e + 1.), self.bounds)
                self.bounds.validate_candidate(candidate)

    def test_strict_evaluation_guard_rejects_before_dispatch(self):
        evaluator = CountingEvaluator()
        with self.assertRaisesRegex(ValueError, 'duration'):
            _evaluate(network(), None, self.bounds, evaluator, BESSCandidate(2, 5000., 5250.))
        self.assertEqual(evaluator.visited, [])

    def test_gwo_only_simulates_valid_pairs(self):
        evaluator = CountingEvaluator()
        result = optimize(network(), None, self.bounds, evaluator,
                          OptimizerConfig(population_size=15, max_iterations=5, workers=1))
        self.assertTrue(result.success)
        self.assertGreater(len(evaluator.visited), 0)
        self.assertEqual(result.metadata['catalog_size'], 2*self.bounds.feasible_design_count())
        self.assertEqual(result.metadata['duration_limits_hours'], [2., 12.])
        for candidate in evaluator.visited:
            self.bounds.validate_candidate(candidate)
        with self.assertRaises(ValueError):
            optimize(network(), None, self.bounds, CountingEvaluator(), OptimizerConfig(
                initial_candidates=(BESSCandidate(2, 5000., 5250.),)))

    def test_ga_repairs_invalid_children_after_crossover(self):
        evaluator = CountingEvaluator()
        result = genetic_optimize(network(), None, self.bounds, evaluator,
                                  OptimizerConfig(population_size=12, max_iterations=7),
                                  crossover_rate=1., mutation_rate=.8)
        self.assertTrue(result.success)
        for candidate in evaluator.visited:
            self.bounds.validate_candidate(candidate)

    def test_spawned_parallel_gwo_preserves_duration_gate(self):
        # Spawn is used on Windows, so do not rely on Linux-only fork semantics.
        with patch('src.optimizer.get_context', return_value=get_context('spawn')):
            result = optimize(network(), None, self.bounds, CountingEvaluator(),
                              OptimizerConfig(population_size=8, max_iterations=2, workers=2))
        self.assertTrue(result.success)
        self.assertEqual(result.metadata['workers'], 2)
        self.assertTrue(any(item.execution_metadata.get('worker_pid')
                            for item in result.evaluations))
        for item in result.evaluations:
            self.bounds.validate_candidate(item.candidate)

    def test_exhaustive_skips_invalid_pairs(self):
        evaluator = CountingEvaluator()
        result = exhaustive_search(network(), None, self.bounds, evaluator)
        self.assertEqual(len(evaluator.visited), 2*self.bounds.feasible_design_count())
        self.assertEqual(result.metadata['catalog_size'], len(evaluator.visited))

    def test_lateral_probes_never_evaluate_invalid_designs(self):
        evaluator = CountingEvaluator()
        with patch('src.sequential_multi.lateral_map', return_value={2: 'A', 3: 'B'}):
            _probe_lateral_candidates(None, network(), None, (2,3),
                [{'bus':2}, {'bus':3}], self.bounds, (), 8760, (0,0,1),
                trial_evaluator=evaluator, limit_per_lateral=7)
        self.assertEqual(len(evaluator.visited), 14)
        self.assertEqual(set(item.bus_id for item in evaluator.visited), {2,3})
        self.assertIn(5000., {item.power_rating_kw for item in evaluator.visited})
        for item in evaluator.visited:
            self.bounds.validate_candidate(item)

    def test_energy_refinement_filters_unrealistic_smaller_batteries(self):
        bounds = OptimizationBounds((2,), (1000.,), (250., 1000., 2000., 3000., 6000., 9000., 15000.))
        incumbent = BESSCandidate(2, 1000., 9000.)
        winner = CandidateEvaluation(incumbent, 50., True, execution_metadata={
            'annual_technical_remaining_ratio': .4, 'technical_check': {'acceptable': True},
            'annual_coverage': {'complete': True}})
        # Avoid synthetic simulation: verify the candidate list passed to the annual batch.
        visited = []
        def verify(*args, **kwargs):
            candidates = args[4]
            visited.extend(candidates)
            return {c: (CandidateEvaluation(c, 40., True, execution_metadata={
                'annual_technical_remaining_ratio': .4,
                'technical_check': {'acceptable': True},
                'annual_coverage': {'complete': True}}), object()) for c in candidates}
        with patch('src.sequential_multi._verify_annual_batch', side_effect=verify):
            _refine_annual_energy(None, None, None, (), winner, object(), bounds, {}, {}, None, 1)
        self.assertTrue(visited)
        for item in visited:
            bounds.validate_candidate(item)
        self.assertNotIn(250., [c.energy_capacity_kwh for c in visited])
        self.assertNotIn(1000., [c.energy_capacity_kwh for c in visited])

    def test_ui_exposes_duration_and_legacy_saves_receive_defaults(self):
        from xml.etree import ElementTree
        root = ElementTree.parse(ROOT/'src/assets/settings_dialog.ui').getroot()
        for name in ('spin_opt_duration_min_hours', 'spin_opt_duration_max_hours'):
            self.assertIsNotNone(root.find(f'.//widget[@name="{name}"]'))
        values = normalize_settings({'chk_auto_cpu_workers': True}, cpu_total=8)
        self.assertEqual((values['spin_opt_duration_min_hours'], values['spin_opt_duration_max_hours']), (2.,12.))


if __name__ == '__main__':
    unittest.main()
