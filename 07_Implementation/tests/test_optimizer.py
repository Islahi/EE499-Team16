"""GWO search checks plus real simulator/metrics integration."""
import sys
import unittest
from io import StringIO
from pathlib import Path
from random import Random

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data_loader import ProfileData
from src.fbs import FBSConfig
from src.metrics import EconomicConfig, evaluate_results
from src.network_model import Bus, Line, Load, NetworkModel, PVUnit
from src.optimizer import (
    BESSCandidate, BESSParameters, CandidateEvaluation, ObjectiveWeights,
    OptimizationBounds, OptimizerConfig, SimulationEvaluator,
    _move_wolves, exhaustive_search, optimize, weighted_sum,
)
from src.simulation import SimulationConfig, simulate_timeseries


def make_network():
    # Zero-impedance branches isolate search/cost behavior from feeder losses.
    return NetworkModel(
        buses=[Bus(2, "Grid", 11, True), Bus(9, "Bus9", 11), Bus(20, "Bus20", 11)],
        lines=[Line("L1", 2, 9, 0, 0), Line("L2", 9, 20, 0, 0)],
        loads=[Load("Load", 2, 200, 0)], pv_units=[PVUnit("PV", 2, 150)],
        base_power_kva=1000, frequency_hz=60,
    )


def make_profiles():
    return ProfileData(
        csv_load=StringIO(
            "timestamp,bus_id,p_kw,q_kvar\n"
            "2026-01-01T00:00:00,2,100,0\n"
            "2026-01-01T01:00:00,2,200,0\n"
        ),
        csv_pv=StringIO(
            "timestamp,bus_id,p_kw,q_kvar\n"
            "2026-01-01T00:00:00,2,150,0\n"
            "2026-01-01T01:00:00,2,50,0\n"
        ),
    )


def dispatch(index, profile, state):
    return sum(profile.p_load_kw.values()) - sum(profile.p_pv_kw.values())


def make_evaluator(settings=None):
    return SimulationEvaluator(
        economic_config=EconomicConfig(cost_per_kwh=2, cost_per_kw=3),
        battery_parameters=BESSParameters(eta_charge=0.9, eta_discharge=0.8),
        dispatch_policy=dispatch,
        simulation_config=settings if settings is not None else SimulationConfig(
            reserve_fraction=0, grid_import_limit_kw=0, grid_export_limit_kw=0
        ),
    )


class OptimizerTests(unittest.TestCase):
    def setUp(self):
        self.network = make_network()
        self.profiles = make_profiles()

    def test_raw_wsm_and_actual_simulation_components(self):
        evaluation = make_evaluator()(self.network, self.profiles, BESSCandidate(9, 100, 500))
        self.assertTrue(evaluation.feasible)
        self.assertEqual(evaluation.metrics.bess_cost, 1300)
        self.assertAlmostEqual(evaluation.metrics.curtailment_energy_kwh, 0, delta=1e-6)
        self.assertAlmostEqual(evaluation.metrics.load_shedding_energy_kwh, 50, delta=2e-6)
        self.assertAlmostEqual(evaluation.objective, 662.5, delta=1e-6)

    def test_generated_battery_limits_follow_each_candidate_rating(self):
        params = BESSParameters(eta_charge=0.9, eta_discharge=0.8)
        for rating in (20, 100, 200):
            config = params.build_config(BESSCandidate(9, rating, 500))
            self.assertEqual(config.max_charge_kw, rating)
            self.assertEqual(config.max_discharge_kw, rating)

    def test_gwo_finds_known_catalog_optimum_and_matches_exhaustive(self):
        bounds = OptimizationBounds((2, 9, 20), (10, 20, 30), (100, 200, 300))

        def objective(network, data, candidate):
            score = (candidate.bus_id - 9) ** 2
            score += (candidate.power_rating_kw - 20) ** 2
            score += (candidate.energy_capacity_kwh - 200) ** 2
            return CandidateEvaluation(candidate, score, True)

        result = optimize(self.network, self.profiles, bounds, objective,
                          OptimizerConfig(population_size=8, max_iterations=15, seed=42))
        reference = exhaustive_search(self.network, self.profiles, bounds, objective)
        self.assertTrue(result.success)
        self.assertEqual(result.best_candidate, BESSCandidate(9, 20, 200))
        self.assertEqual(result.best_objective, 0)
        self.assertEqual(result.best_objective, reference.best_objective)
        self.assertEqual(reference.metadata["evaluations"], 27)
        self.assertEqual(len(result.convergence_history), 15)
        self.assertTrue(all(a >= b for a, b in zip(result.convergence_history,
                                                  result.convergence_history[1:])))

    def test_real_backend_gwo_matches_small_exhaustive_grid(self):
        bounds = OptimizationBounds((2, 9), (50, 100), (500, 1000))
        result = optimize(self.network, self.profiles, bounds, make_evaluator(),
                          OptimizerConfig(population_size=8, max_iterations=10))
        reference = exhaustive_search(self.network, self.profiles, bounds, make_evaluator())
        self.assertTrue(result.success)
        self.assertAlmostEqual(result.best_objective, reference.best_objective)
        self.assertTrue(result.metrics.feasible)
        self.assertEqual(result.metadata["catalog_size"], 8)

    def test_same_seed_reproduces_search_without_changing_global_rng(self):
        import random
        bounds = OptimizationBounds((2, 9), (50, 100), (500, 1000))
        state = random.getstate()
        first = optimize(self.network, self.profiles, bounds, make_evaluator(), OptimizerConfig())
        second = optimize(self.network, self.profiles, bounds, make_evaluator(), OptimizerConfig())
        self.assertEqual(first.best_candidate, second.best_candidate)
        self.assertEqual(first.convergence_history, second.convergence_history)
        self.assertEqual([item.candidate for item in first.evaluations],
                         [item.candidate for item in second.evaluations])
        self.assertEqual(random.getstate(), state)

    def test_single_candidate_is_cached_and_can_fill_all_three_leaders(self):
        calls = []
        bounds = OptimizationBounds((9,), (100,), (500,))

        def objective(network, data, candidate):
            calls.append(candidate)
            return CandidateEvaluation(candidate, 10, True)

        result = optimize(self.network, self.profiles, bounds, objective,
                          OptimizerConfig(population_size=4, max_iterations=5))
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.convergence_history, [10] * 5)
        uncached = optimize(self.network, self.profiles, bounds, objective,
                            OptimizerConfig(population_size=4, max_iterations=5,
                                            cache_evaluations=False))
        self.assertEqual(uncached.metadata["evaluations"], 20)
        self.assertEqual(uncached.best_objective, result.best_objective)

    def test_all_infeasible_returns_no_candidate(self):
        bounds = OptimizationBounds((9,), (10,), (100,))
        result = optimize(self.network, self.profiles, bounds,
                          make_evaluator(SimulationConfig(reserve_fraction=0.1)),
                          OptimizerConfig(max_iterations=3))
        self.assertFalse(result.success)
        self.assertIsNone(result.best_candidate)
        self.assertIsNone(result.metrics)
        self.assertEqual(result.best_objective, float("inf"))

    def test_failed_power_flow_cannot_win(self):
        # A real nonzero-impedance branch requires more than one strict sweep.
        self.network.lines[0] = Line("L1", 2, 9, 0.01, 0.01)
        evaluator = make_evaluator(SimulationConfig(
            reserve_fraction=0, fbs_config=FBSConfig(max_iterations=1, voltage_tolerance_pu=1e-12)
        ))
        result = optimize(self.network, self.profiles,
                          OptimizationBounds((9,), (100,), (500,)), evaluator, OptimizerConfig())
        self.assertFalse(result.success)
        self.assertFalse(result.evaluations[0].feasible)

    def test_infeasible_fake_low_score_is_rejected(self):
        bounds = OptimizationBounds((2,), (50, 100), (500,))

        def objective(network, data, candidate):
            return CandidateEvaluation(candidate, 0 if candidate.power_rating_kw == 50 else 100,
                                       candidate.power_rating_kw == 100)

        result = optimize(self.network, None, bounds, objective, OptimizerConfig())
        self.assertEqual(result.best_candidate.power_rating_kw, 100)
        self.assertEqual(result.best_objective, 100)

    def test_initial_candidates_and_single_iteration(self):
        chosen = BESSCandidate(9, 100, 500)
        result = optimize(
            self.network, self.profiles, OptimizationBounds((2, 9), (50, 100), (500, 1000)),
            make_evaluator(), OptimizerConfig(max_iterations=1, initial_candidates=(chosen,)),
        )
        self.assertEqual(result.iterations, 1)
        self.assertIn(chosen, [item.candidate for item in result.evaluations])

    def test_gwo_zero_exploration_coefficient_moves_to_mean_of_leaders(self):
        bounds = OptimizationBounds((2, 9, 20), (10, 20, 30), (100, 200, 300))
        moved = _move_wolves([[3.0, 1.0, 2.0]],
                             [[1, 1, 1], [2, 2, 2], [3, 3, 3]], bounds, 0, Random(42))
        self.assertEqual(moved, [[2.0, 2.0, 2.0]])

    def test_missing_prices_dispatch_and_wsm_components_raise_errors(self):
        params = BESSParameters(eta_charge=0.9, eta_discharge=0.8)
        with self.assertRaisesRegex(ValueError, "cost_per_kwh"):
            SimulationEvaluator(EconomicConfig(), params, dispatch)
        with self.assertRaisesRegex(ValueError, "dispatch_policy"):
            SimulationEvaluator(EconomicConfig(2, 3), params, None)
        baseline = evaluate_results(simulate_timeseries(self.network, self.profiles,
                                                        SimulationConfig()), EconomicConfig())
        baseline.curtailment_energy_kwh = None
        with self.assertRaisesRegex(ValueError, "WSM needs"):
            weighted_sum(baseline)

    def test_invalid_bounds_settings_and_battery_parameters(self):
        for make_invalid in (
            lambda: OptimizationBounds((), (100,), (500,)),
            lambda: OptimizationBounds((2, 2), (100,), (500,)),
            lambda: OptimizationBounds((2,), (0,), (500,)),
            lambda: OptimizationBounds((True,), (100,), (500,)),
            lambda: OptimizerConfig(population_size=2),
            lambda: OptimizerConfig(max_iterations=0),
            lambda: ObjectiveWeights(cost=1),
            lambda: BESSParameters(eta_charge=1.2, eta_discharge=0.8),
            lambda: BESSParameters(eta_charge=0.9, eta_discharge=0.8, soc_initial=0),
        ):
            with self.subTest(factory=make_invalid):
                with self.assertRaises(ValueError):
                    make_invalid()
        with self.assertRaisesRegex(ValueError, "unknown buses"):
            optimize(self.network, self.profiles, OptimizationBounds((99,), (100,), (500,)),
                     make_evaluator(), OptimizerConfig())

    def test_unexpected_errors_are_not_hidden_as_infeasible_candidates(self):
        def broken_evaluator(network, data, candidate):
            raise RuntimeError("Example programming error")

        with self.assertRaisesRegex(RuntimeError, "programming error"):
            optimize(self.network, None, OptimizationBounds((2,), (100,), (500,)),
                     broken_evaluator, OptimizerConfig())

    def test_bounds_and_profiles_are_preserved(self):
        buses = [9, 2]
        bounds = OptimizationBounds(buses, [100, 50], [1000, 500])
        original_load = list(self.profiles.load_p_kw[2])
        optimize(self.network, self.profiles, bounds, make_evaluator(), OptimizerConfig(max_iterations=2))
        self.assertEqual(buses, [9, 2])
        self.assertEqual(bounds.allowed_bus_ids, (2, 9))
        self.assertEqual(self.profiles.load_p_kw[2], original_load)


if __name__ == "__main__":
    unittest.main()
