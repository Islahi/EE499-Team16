"""CSV values, failure labels, comparisons and non-overwriting export checks."""
import csv
from dataclasses import replace
from pathlib import Path
import pickle
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.fbs import FBSConfig
from src.metrics import EconomicConfig, evaluate_results
from src.optimizer import BESSCandidate, OptimizationBounds, OptimizerConfig, optimize
from src.results import export_results, format_summary
from src.simulation import SimulationConfig, TimeSeriesSimulationResult, simulate_timeseries
from src.uncertainty import Scenario, ScenarioEvaluator, ScenarioSet
from test_optimizer import make_evaluator, make_network, make_profiles


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


class ResultsTests(unittest.TestCase):
    def setUp(self):
        # Keep temporary test files inside the writable workspace, not the user temp folder.
        self.temp = TemporaryDirectory(prefix="results_test_", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "run"
        self.network, self.profiles = make_network(), make_profiles()
        self.settings = SimulationConfig(reserve_fraction=0, grid_import_limit_kw=0, grid_export_limit_kw=0)
        self.economics = EconomicConfig(2, 3)
        self.candidate = BESSCandidate(9, 100, 500)
        self.evaluator = make_evaluator()
        self.battery = self.evaluator.battery_parameters.build_config(self.candidate)
        self.run = simulate_timeseries(self.network, self.profiles, self.settings,
                                       self.battery, self.evaluator.dispatch_policy)
        self.metrics = evaluate_results(self.run, self.economics, self.battery)

    def optimization(self, evaluator=None, data=None):
        return optimize(self.network, self.profiles if data is None else data,
                        OptimizationBounds((9,), (100,), (500,)),
                        self.evaluator if evaluator is None else evaluator, OptimizerConfig(3, 1))

    def test_simulation_tables_and_recorded_values(self):
        paths = export_results(self.run, self.output, metrics=self.metrics)
        self.assertEqual(set(paths), {"summary.md", "metrics.csv", "hourly.csv", "buses.csv", "branches.csv"})
        hourly = read_csv(paths["hourly.csv"])
        self.assertEqual(len(hourly), 2)
        for row, step in zip(hourly, self.run.steps):
            self.assertEqual(row["converged"], "True")
            self.assertEqual(row["diagnostic_only"], "False")
            self.assertAlmostEqual(float(row["curtailment_kw"]), step.curtailment_kw)
            self.assertAlmostEqual(float(row["shedding_kw"]), step.shedding_kw)
            self.assertAlmostEqual(float(row["bess_accepted_soc"]), step.bess_state.soc)
            self.assertAlmostEqual(float(row["bess_trial_power_kw"]), step.bess_step.actual_power_kw)
        self.assertEqual(len(read_csv(paths["buses.csv"])), 6)
        self.assertEqual(len(read_csv(paths["branches.csv"])), 4)
        buses = read_csv(paths["buses.csv"])
        self.assertEqual([int(row["bus_id"]) for row in buses[:3]], [2, 9, 20])
        self.assertEqual(buses[0]["voltage_pu"], "1.0")
        self.assertEqual(float(read_csv(paths["branches.csv"])[0]["current_a"]),
                         self.run.steps[0].power_flow.branch_current_a["L1"])

    def test_metrics_only_and_explicit_units(self):
        paths = export_results(self.metrics, self.output)
        self.assertEqual(set(paths), {"summary.md", "metrics.csv"})
        rows = {row["metric"]: row for row in read_csv(paths["metrics.csv"])}
        self.assertEqual(float(rows["bess_cost"]["value"]), 1300)
        self.assertEqual(rows["bess_cost"]["unit"], "SAR")
        self.assertEqual(rows["bess_soc_min"]["unit"], "fraction")
        self.assertEqual(rows["curtailment_energy_kwh"]["unit"], "kWh")
        self.assertIn("Completion/convergence details were not supplied", paths["summary.md"].read_text())

    def test_missing_values_are_blank_not_zero(self):
        metrics = replace(self.metrics, bess_cost=None, curtailment_energy_kwh=None)
        paths = export_results(metrics, self.output)
        rows = {row["metric"]: row["value"] for row in read_csv(paths["metrics.csv"])}
        self.assertEqual(rows["bess_cost"], "")
        self.assertEqual(rows["curtailment_energy_kwh"], "")
        self.assertIn("bess_cost: unavailable SAR", paths["summary.md"].read_text())

    def test_baseline_without_battery_has_blank_battery_state(self):
        run = simulate_timeseries(self.network, self.profiles, self.settings)
        paths = export_results(run, self.output)
        row = read_csv(paths["hourly.csv"])[0]
        self.assertEqual(row["bess_accepted_soc"], "")
        self.assertEqual(row["bess_trial_power_kw"], "")
        self.assertNotIn("metrics.csv", paths)

    def test_failed_simulation_remains_diagnostic(self):
        # Nonzero line impedance is needed to force a one-sweep convergence failure.
        from src.network_cases import build_guide_5_bus_case
        from src.data_loader import ProfileData
        from io import StringIO
        network = build_guide_5_bus_case()
        load = "timestamp,bus_id,p_kw,q_kvar\n"
        pv = "timestamp,bus_id,p_kw,q_kvar\n"
        for hour in (0, 1):
            timestamp = f"2026-01-01T0{hour}:00:00"
            for bus in (2, 3, 4, 5):
                load += f"{timestamp},{bus},100,30\n"
            pv += f"{timestamp},4,0,0\n"
        profiles = ProfileData(StringIO(load), StringIO(pv))
        failed = simulate_timeseries(network, profiles, SimulationConfig(fbs_config=FBSConfig(max_iterations=1)))
        self.assertFalse(failed.converged)
        paths = export_results(failed, self.output)
        row = read_csv(paths["hourly.csv"])[0]
        self.assertEqual(row["diagnostic_only"], "True")
        self.assertEqual(row["converged"], "False")
        self.assertEqual(row["curtailment_kw"], "")
        self.assertIn("WARNING", paths["summary.md"].read_text())
        self.assertNotIn("metrics.csv", paths)
        with self.assertRaises(ValueError):
            export_results(failed, self.output.parent / "bad", metrics=self.metrics)

    def test_converged_infeasible_metrics_are_retained(self):
        failed_step = replace(self.run.steps[0], feasible=False)
        run = replace(self.run, steps=[failed_step, self.run.steps[1]], feasible=False)
        metrics = replace(self.metrics, feasible=False)
        paths = export_results(run, self.output, metrics=metrics)
        self.assertEqual(read_csv(paths["hourly.csv"])[0]["feasible"], "False")
        self.assertIn("Feasible: False", paths["summary.md"].read_text())

    def test_optimization_candidates_and_history(self):
        result = self.optimization()
        paths = export_results(result, self.output)
        self.assertEqual(len(read_csv(paths["evaluations.csv"])), 1)
        row = read_csv(paths["evaluations.csv"])[0]
        self.assertEqual(row["bus_id"], "9")
        self.assertAlmostEqual(float(row["raw_wsm"]), result.best_objective)
        self.assertEqual(read_csv(paths["convergence.csv"])[0]["axis"], "generation")
        self.assertIn("Selected bus: 9", paths["summary.md"].read_text())

    def test_all_infeasible_optimization_keeps_infinity_and_failure(self):
        from src.optimizer import CandidateEvaluation
        evaluator = lambda network, profiles, candidate: CandidateEvaluation(candidate, float("inf"), False, message="reserve failed")
        result = self.optimization(evaluator=evaluator)
        paths = export_results(result, self.output)
        row = read_csv(paths["evaluations.csv"])[0]
        self.assertEqual(row["feasible"], "False")
        self.assertEqual(row["raw_wsm"], "inf")
        self.assertEqual(row["bess_cost"], "")
        self.assertEqual(read_csv(paths["convergence.csv"])[0]["best_so_far_raw_wsm"], "inf")
        self.assertIn("No feasible battery selected", paths["summary.md"].read_text())
        self.assertNotIn("metrics.csv", paths)

    def test_scenario_results_retain_ids_and_mean_label(self):
        scenarios = ScenarioSet([Scenario("sunny", make_profiles()), Scenario("cloudy", make_profiles())])
        result = self.optimization(ScenarioEvaluator(self.evaluator), scenarios)
        paths = export_results(result, self.output)
        rows = read_csv(paths["scenario_evaluations.csv"])
        self.assertEqual([row["scenario_id"] for row in rows], ["cloudy", "sunny"])
        self.assertTrue(all(row["feasible"] == "True" for row in rows))
        self.assertIn("Equal-weight scenario means", paths["summary.md"].read_text())

    def test_comparison_known_reduction_and_zero_baseline(self):
        baseline = replace(self.metrics, loss_energy_kwh=100, bess_cost=0, curtailment_energy_kwh=None)
        metrics = replace(self.metrics, loss_energy_kwh=80)
        paths = export_results(metrics, self.output, baseline_metrics=baseline)
        rows = {row["metric"]: row for row in read_csv(paths["comparison.csv"])}
        self.assertEqual(float(rows["loss_energy_kwh"]["reduction_percent"]), 20)
        self.assertEqual(rows["bess_cost"]["reduction_percent"], "")
        self.assertEqual(rows["curtailment_energy_kwh"]["baseline"], "")
        self.assertEqual(rows["curtailment_energy_kwh"]["reduction_percent"], "")
        self.assertEqual(rows["loss_energy_kwh"]["baseline_feasible"], "True")

    def test_bad_comparisons_rejected_before_creating_folder(self):
        for baseline in (replace(self.metrics, duration_hours=99), replace(self.metrics, currency="USD"), "bad"):
            with self.subTest(baseline=baseline), self.assertRaises(ValueError):
                export_results(self.metrics, self.output, baseline_metrics=baseline)
            self.assertFalse(self.output.exists())

    def test_metrics_must_match_run_duration_and_feasibility(self):
        for metrics in (replace(self.metrics, duration_hours=99), replace(self.metrics, feasible=False)):
            with self.assertRaises(ValueError):
                export_results(self.run, self.output, metrics=metrics)
            self.assertFalse(self.output.exists())

    def test_existing_directory_is_never_overwritten(self):
        paths = export_results(self.metrics, self.output)
        before = paths["summary.md"].read_bytes()
        with self.assertRaises(FileExistsError):
            export_results(replace(self.metrics, bess_cost=999), self.output)
        self.assertEqual(paths["summary.md"].read_bytes(), before)

    def test_excel_encoding_quoting_and_formula_protection(self):
        metrics = replace(self.metrics, currency="ريال", notes=['=1+1', 'comma, quote " and\nnewline'])
        paths = export_results(metrics, self.output)
        self.assertEqual(paths["metrics.csv"].read_bytes()[:3], b"\xef\xbb\xbf")
        rows = {row["metric"]: row["value"] for row in read_csv(paths["metrics.csv"])}
        self.assertEqual(rows["currency"], "ريال")
        self.assertTrue(rows["notes"].startswith("'=1+1"))
        self.assertIn('comma, quote " and\nnewline', rows["notes"])

    def test_inputs_are_not_mutated(self):
        result = self.optimization()
        before = pickle.dumps((self.run, self.metrics, result))
        export_results(self.run, self.output, metrics=self.metrics)
        export_results(result, self.output.parent / "optimization")
        self.assertEqual(pickle.dumps((self.run, self.metrics, result)), before)

    def test_context_and_unsupported_types(self):
        summary = format_summary(self.metrics, context={"case": "Synthetic unit test", "prices": "Illustrative only"})
        self.assertIn("case: Synthetic unit test", summary)
        for context in ([], {"hours": 24}):
            with self.assertRaises(TypeError):
                export_results(self.metrics, self.output, context=context)
        with self.assertRaises(TypeError):
            export_results({"fake": "result"}, self.output)
        with self.assertRaises(ValueError):
            export_results(self.optimization(), self.output, metrics=self.metrics)
        self.assertFalse(self.output.exists())

    def test_empty_simulation_exports_headers_without_crashing(self):
        empty = TimeSeriesSimulationResult([], 1, False, False, False, None, "No steps")
        paths = export_results(empty, self.output)
        self.assertEqual(read_csv(paths["hourly.csv"]), [])
        self.assertEqual(read_csv(paths["buses.csv"]), [])
        self.assertEqual(read_csv(paths["branches.csv"]), [])
        self.assertIn("Recorded steps: 0", paths["summary.md"].read_text())

    def test_io_failure_does_not_write_completion_summary(self):
        with patch("src.results._write_csv", side_effect=OSError("Disk error")):
            with self.assertRaisesRegex(OSError, "Disk error"):
                export_results(self.metrics, self.output)
        self.assertTrue(self.output.exists())
        self.assertFalse((self.output / "summary.md").exists())

    def test_summary_is_published_only_after_successful_write(self):
        with patch("pathlib.Path.rename", side_effect=OSError("Rename error")):
            with self.assertRaisesRegex(OSError, "Rename error"):
                export_results(self.metrics, self.output)
        self.assertTrue((self.output / "metrics.csv").exists())
        self.assertFalse((self.output / "summary.md").exists())


if __name__ == "__main__":
    unittest.main()
