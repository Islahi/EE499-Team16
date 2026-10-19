"""ARIMA, scenario selection and real simulation/GWO integration checks."""
import copy
from dataclasses import replace
from io import StringIO
from math import pi, sin
from pathlib import Path
from random import Random
import sys
import unittest
from unittest.mock import patch

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data_loader import ProfileData, profile_at
from src.optimizer import BESSCandidate, OptimizationBounds, OptimizerConfig, optimize, weighted_sum
from src.uncertainty import (
    Scenario, ScenarioEvaluator, ScenarioSet, SelectionConfig, UncertaintyConfig,
    _SeriesModel, _forecast_errors, generate_scenarios, scenario_features, select_scenarios,
)
from test_optimizer import make_evaluator, make_network, make_profiles


def make_history(hours=168, noisy=True, zero_pv=False):
    rng = Random(15)
    load_rows = ["timestamp,bus_id,p_kw,q_kvar"]
    pv_rows = ["timestamp,bus_id,p_kw,q_kvar"]
    error = 0.0
    for index, timestamp in enumerate(pd.date_range("2026-01-01", periods=hours, freq="h")):
        hour = timestamp.hour
        error = 0.6 * error + rng.uniform(-4, 4) if noisy else 0
        load = 100 + 10 * sin(hour * pi / 12) + error
        pv = 0.0
        if not zero_pv and 7 <= hour <= 17:
            pv = 60 * sin((hour - 6) * pi / 12)
            if noisy:
                pv *= rng.uniform(0.8, 1.0)
        load_rows.append(f"{timestamp.isoformat()},2,{load},{load * 0.3}")
        pv_rows.append(f"{timestamp.isoformat()},2,{pv},{-pv * 0.1}")
    return ProfileData(StringIO("\n".join(load_rows)), StringIO("\n".join(pv_rows)))


def make_ranked_set(count=100):
    scenarios = []
    for index in range(count):
        profiles = make_profiles()
        profiles.load_p_kw[2] = [float(index + 1), float(index + 1)]
        profiles.pv_p_kw[2] = [0.0, 0.0]
        scenarios.append(Scenario(f"case_{index:03d}", profiles, 1 / count))
    return ScenarioSet(scenarios)


class UncertaintyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history = make_history()
        cls.config = UncertaintyConfig(forecast_hours=24, pv_capacity_kw={2: 100})
        cls.generated = generate_scenarios(cls.history, cls.config)

    def test_generate_100_compatible_future_profiles(self):
        self.assertEqual(len(self.generated.scenarios), 100)
        self.generated.validate()
        profiles = self.generated.scenarios[0].profiles
        self.assertIsInstance(profiles, ProfileData)
        self.assertEqual(len(profiles.timestamps), 24)
        self.assertEqual(profiles.timestamps[0], pd.Timestamp(self.history.timestamps[-1]) + pd.Timedelta(hours=1))
        self.assertEqual(profiles.dt_hours, 1)
        self.assertAlmostEqual(sum(item.probability for item in self.generated.scenarios), 1)
        self.assertEqual(profile_at(profiles, 0).p_load_kw[2], profiles.load_p_kw[2][0])

    def test_actual_arima_used_for_nonconstant_data(self):
        self.assertEqual(self.generated.metadata["models"]["load"][2]["model"], "ARIMA")
        self.assertEqual(self.generated.metadata["models"]["pv"][2]["model"], "ARIMA")
        self.assertNotEqual(self.generated.scenarios[0].profiles.load_p_kw,
                            self.generated.scenarios[1].profiles.load_p_kw)

    def test_seed_repeats_paths_and_different_seed_changes_them(self):
        config = replace(self.config, scenario_count=3)
        first = generate_scenarios(self.history, config)
        events = []
        again = generate_scenarios(self.history, config, progress=events.append)
        different = generate_scenarios(self.history, replace(config, seed=43))
        self.assertEqual(first.scenarios[0].profiles.load_p_kw, again.scenarios[0].profiles.load_p_kw)
        self.assertEqual(first.scenarios[0].profiles.pv_p_kw, again.scenarios[0].profiles.pv_p_kw)
        self.assertNotEqual(first.scenarios[0].profiles.load_p_kw, different.scenarios[0].profiles.load_p_kw)
        fits = [event for event in events if event.phase == "ARIMA"]
        self.assertEqual((fits[-1].completed, fits[-1].total), (4, 4))
        self.assertEqual((events[-1].phase, events[-1].completed), ("Scenarios", 3))

    def test_physical_limits_nighttime_and_signed_q_ratios(self):
        for scenario in self.generated.scenarios:
            profiles = scenario.profiles
            for index, timestamp in enumerate(profiles.timestamps):
                self.assertGreaterEqual(profiles.load_p_kw[2][index], 0)
                pv = profiles.pv_p_kw[2][index]
                self.assertGreaterEqual(pv, 0)
                self.assertLessEqual(pv, 100)
                if not 7 <= pd.Timestamp(timestamp).hour <= 17:
                    self.assertEqual(pv, 0)
                self.assertAlmostEqual(profiles.load_q_kvar[2][index], profiles.load_p_kw[2][index] * 0.3)
                self.assertAlmostEqual(profiles.pv_q_kvar[2][index], -pv * 0.1)

    def test_deterministic_history_does_not_get_invented_noise(self):
        generated = generate_scenarios(make_history(noisy=False), replace(self.config, scenario_count=2))
        self.assertEqual(generated.metadata["models"]["load"][2]["model"], "deterministic_hourly_pattern")
        self.assertEqual(generated.scenarios[0].profiles.load_p_kw, generated.scenarios[1].profiles.load_p_kw)
        self.assertAlmostEqual(generated.metadata["validation"]["load"][2]["arima"]["rmse_kw"], 0)

    def test_zero_pv_mape_is_unavailable_not_division_by_zero(self):
        generated = generate_scenarios(make_history(zero_pv=True), replace(self.config, scenario_count=1))
        score = generated.metadata["validation"]["pv"][2]["arima"]
        self.assertIsNone(score["mape_percent"])
        self.assertEqual(score["mape_sample_count"], 0)
        self.assertEqual(score["rmse_kw"], 0)
        self.assertEqual(max(generated.scenarios[0].profiles.pv_p_kw[2]), 0)

    def test_error_metrics_known_numbers(self):
        errors = _forecast_errors([0, 10, 20], [2, 8, 24])
        self.assertAlmostEqual(errors["rmse_kw"], (24 / 3) ** 0.5)
        self.assertAlmostEqual(errors["mape_percent"], 20)
        self.assertEqual(errors["mape_sample_count"], 2)
        tiny_zero = _forecast_errors([1e-13, 10], [0, 8])
        self.assertEqual(tiny_zero["mape_sample_count"], 1)
        self.assertAlmostEqual(tiny_zero["mape_percent"], 20)

    def test_clipping_and_numerical_nighttime_zero(self):
        baseline = np.full(24, 10.0)
        baseline[18] = 1e-13
        model = _SeriesModel(baseline, np.zeros(24), 1, None, 20, [])
        times = pd.date_range("2026-01-01T16:00:00", periods=3, freq="h")
        result = model.restore(np.array([-100.0, 100.0, 100.0]), times)
        self.assertEqual(result.tolist(), [0, 20, 0])

    def test_holdout_fit_does_not_see_future_data(self):
        from src import uncertainty
        with patch.object(uncertainty, "_fit_series", wraps=uncertainty._fit_series) as fitting:
            generate_scenarios(self.history, replace(self.config, scenario_count=1))
        self.assertEqual([len(call.args[0]) for call in fitting.call_args_list], [144, 168, 144, 168])
        self.assertIn("repeat_last_day", self.generated.metadata["validation"]["load"][2])

    def test_history_unchanged(self):
        history = make_history()
        before = copy.deepcopy(history.__dict__)
        generate_scenarios(history, replace(self.config, scenario_count=1))
        self.assertEqual(history.__dict__, before)

    def test_capacity_and_short_history_errors(self):
        for capacities in ({}, {3: 100}, {2: 1}):
            with self.subTest(capacities=capacities), self.assertRaises(ValueError):
                generate_scenarios(self.history, replace(self.config, pv_capacity_kw=capacities))
        with self.assertRaisesRegex(ValueError, "training hours"):
            generate_scenarios(make_history(48), self.config)

    def test_bad_config_values(self):
        for settings in ({"forecast_hours": 1}, {"scenario_count": 0}, {"seed": -1},
                         {"arima_order": (1, -1, 0)}, {"arima_order": (1, 0)},
                         {"validation_hours": 0}, {"pv_capacity_kw": {2: float("nan")}}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                replace(self.config, **settings)

    def test_malformed_profile_series_rejected(self):
        for defect in ("length", "nan", "negative", "q_without_p", "time"):
            history = make_history()
            if defect == "length":
                history.load_p_kw[2].pop()
            elif defect == "nan":
                history.load_p_kw[2][0] = float("nan")
            elif defect == "negative":
                history.load_p_kw[2][0] = -1
            elif defect == "q_without_p":
                history.pv_q_kvar[2][0] = 1
            else:
                history.timestamps[1] = history.timestamps[0]
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                generate_scenarios(history, self.config)

    def test_nonconverged_fit_not_silently_replaced(self):
        with patch("src.uncertainty.ARIMA") as arima:
            arima.return_value.fit.return_value.mle_retvals = {"converged": False}
            with self.assertRaisesRegex(ValueError, "did not converge"):
                generate_scenarios(self.history, self.config)

    def test_features_known_values_including_negative_peak(self):
        features = scenario_features(make_profiles())  # net [-50, 150]
        self.assertEqual(features, {"net_energy_kwh": 150, "peak_net_kw": 150,
                                    "surplus_energy_kwh": 50, "ramp_kw": 200})
        profiles = make_profiles()
        profiles.load_p_kw[2] = [0, 0]
        profiles.pv_p_kw[2] = [20, 30]
        self.assertEqual(scenario_features(profiles)["peak_net_kw"], -20)

    def test_select_45_disjoint_extremes_and_random(self):
        scenarios = make_ranked_set()
        selected = select_scenarios(scenarios)
        self.assertEqual(len(selected.scenarios), 45)
        ids = [item.scenario_id for item in selected.scenarios]
        self.assertEqual(len(set(ids)), 45)
        self.assertEqual(ids[:15], [f"case_{i:03d}" for i in range(15)])
        self.assertEqual(ids[15:30], [f"case_{i:03d}" for i in range(85, 100)])
        self.assertTrue(all(15 <= int(value[-3:]) < 85 for value in ids[30:]))
        scores = selected.metadata["stress_scores"]
        self.assertAlmostEqual(scores["case_000"], 0)
        self.assertAlmostEqual(scores["case_099"], 0.65)
        self.assertTrue(all(item.probability is None for item in selected.scenarios))
        self.assertTrue(all(item.metadata == {} and item.probability == 0.01 for item in scenarios.scenarios))

    def test_selection_seed_stability_and_different_random_group(self):
        scenarios = make_ranked_set()
        first = select_scenarios(scenarios)
        again = select_scenarios(scenarios)
        different = select_scenarios(scenarios, SelectionConfig(seed=43))
        ids = lambda values: [item.scenario_id for item in values.scenarios]
        self.assertEqual(ids(first), ids(again))
        self.assertEqual(ids(first)[:30], ids(different)[:30])
        self.assertNotEqual(ids(first)[30:], ids(different)[30:])

    def test_tied_scores_and_zero_counts(self):
        scenarios = ScenarioSet([Scenario(str(i), make_profiles()) for i in range(6)])
        selected = select_scenarios(scenarios, SelectionConfig(2, 2, 2))
        self.assertEqual(len({item.scenario_id for item in selected.scenarios}), 6)
        self.assertTrue(all(value == 0 for value in selected.metadata["stress_scores"].values()))
        selected = select_scenarios(scenarios, SelectionConfig(0, 0, 2))
        self.assertEqual(len(selected.scenarios), 2)
        with self.assertRaises(ValueError):
            select_scenarios(scenarios)
        with self.assertRaises(ValueError):
            SelectionConfig(0, 0, 0)

    def test_scenario_set_rejects_empty_duplicate_or_different_horizon(self):
        with self.assertRaises(ValueError):
            ScenarioSet([]).validate()
        with self.assertRaises(ValueError):
            ScenarioSet([Scenario("same", make_profiles()), Scenario("same", make_profiles())]).validate()
        different = make_profiles()
        different.timestamps = [pd.Timestamp(time) + pd.Timedelta(hours=1) for time in different.timestamps]
        with self.assertRaises(ValueError):
            ScenarioSet([Scenario("a", make_profiles()), Scenario("b", different)]).validate()

    def test_real_evaluator_mean_cost_once_and_independent_soc(self):
        network = make_network()
        candidate = BESSCandidate(9, 100, 500)
        first, second = make_profiles(), make_profiles()
        second.load_p_kw[2] = [150, 250]
        cases = ScenarioSet([Scenario("a", first), Scenario("b", second)])
        evaluator = make_evaluator()
        expected = [evaluator(network, item.profiles, candidate) for item in cases.scenarios]
        result = ScenarioEvaluator(evaluator)(network, cases, candidate)
        self.assertTrue(result.feasible)
        self.assertEqual(len(result.scenario_evaluations), 2)
        self.assertAlmostEqual(result.objective, sum(item.objective for item in expected) / 2)
        self.assertEqual(result.metrics.bess_cost, 1300)
        self.assertAlmostEqual(result.objective, weighted_sum(result.metrics))
        self.assertEqual(result.metrics.voltage_min_pu, min(item.metrics.voltage_min_pu for item in expected))
        for scenario_id, single in zip(("a", "b"), expected):
            self.assertEqual(result.scenario_evaluations[scenario_id].metrics, single.metrics)

    def test_one_failed_case_rejects_candidate(self):
        from src.optimizer import CandidateEvaluation
        candidate = BESSCandidate(9, 100, 500)
        cases = ScenarioSet([Scenario("failed_case", make_profiles())])
        evaluator = lambda network, profiles, battery: CandidateEvaluation(battery, float("inf"), False, message="failure")
        result = ScenarioEvaluator(evaluator)(make_network(), cases, candidate)
        self.assertFalse(result.feasible)
        self.assertEqual(result.objective, float("inf"))
        self.assertIn("failed_case", result.message)

    def test_generated_selected_profiles_connect_to_real_gwo(self):
        selected = select_scenarios(self.generated, SelectionConfig(1, 1, 1))
        result = optimize(make_network(), selected, OptimizationBounds((9,), (100,), (500,)),
                          ScenarioEvaluator(make_evaluator()), OptimizerConfig(3, 1))
        self.assertTrue(result.success)
        self.assertEqual(result.best_candidate, BESSCandidate(9, 100, 500))
        self.assertEqual(len(result.evaluations[0].scenario_evaluations), 3)
        self.assertIsNotNone(result.metrics.curtailment_energy_kwh)
        self.assertIsNotNone(result.metrics.load_shedding_energy_kwh)


if __name__ == "__main__":
    unittest.main()
