"""Metrics checked against hand-calculated two-hour runs and energy balance."""
import sys
import unittest
from dataclasses import replace
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.bess import BESSConfig
from src.fbs import FBSConfig
from src.data_loader import ProfileData
from src.metrics import EconomicConfig, evaluate_results, percentage_reduction
from src.network_model import Bus, Line, Load, NetworkModel, PVUnit
from src.simulation import SimulationConfig, simulate_timeseries


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


def make_network(with_line=False):
    buses = [Bus(2, "Grid", 1.0, True)]
    lines = []
    if with_line:
        buses = [Bus(1, "Grid", 1.0, True), Bus(2, "Load/PV", 1.0)]
        lines = [Line("L1", 1, 2, 0.05, 0.02)]
    return NetworkModel(
        buses=buses, lines=lines,
        loads=[Load("Load", 2, 200, 0)], pv_units=[PVUnit("PV", 2, 150)],
        base_power_kva=1000, frequency_hz=60,
    )


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.network = make_network()
        self.profiles = make_profiles()
        self.settings = SimulationConfig(reserve_fraction=0)
        self.bess = BESSConfig(
            bus_id=2, energy_capacity_kwh=500, power_rating_kw=100,
            soc_min=0.1, soc_max=0.9, soc_initial=0.5,
            eta_charge=0.9, eta_discharge=0.8,
        )

    def simulate(self, with_bess=False):
        if with_bess:
            requests = [40, -20]
            return simulate_timeseries(
                self.network, self.profiles, self.settings, self.bess,
                lambda index, profile, state: requests[index],
            )
        return simulate_timeseries(self.network, self.profiles, self.settings)

    def test_hand_calculated_baseline_and_recorded_zero_controls(self):
        metrics = evaluate_results(self.simulate(), EconomicConfig())
        self.assertEqual(metrics.duration_hours, 2)
        self.assertEqual(metrics.served_load_energy_kwh, 300)
        self.assertEqual(metrics.pv_generation_energy_kwh, 200)
        self.assertEqual(metrics.grid_import_energy_kwh, 150)
        self.assertEqual(metrics.grid_export_energy_kwh, 50)
        self.assertEqual(metrics.peak_grid_import_kw, 150)
        self.assertEqual(metrics.loss_energy_kwh, 0)
        self.assertEqual(metrics.voltage_min_pu, 1)
        self.assertEqual(metrics.voltage_max_pu, 1)
        self.assertEqual(metrics.bess_cost, 0)
        self.assertIsNone(metrics.bess_soc_min)
        self.assertEqual(metrics.curtailment_energy_kwh, 0)
        self.assertEqual(metrics.load_shedding_energy_kwh, 0)
        self.assertTrue(metrics.feasible)

    def test_bess_cost_charge_discharge_and_soc(self):
        metrics = evaluate_results(
            self.simulate(with_bess=True), EconomicConfig(cost_per_kwh=2, cost_per_kw=3), self.bess
        )
        self.assertEqual(metrics.bess_cost, 1300)
        self.assertEqual(metrics.currency, "SAR")
        self.assertEqual(metrics.bess_charge_energy_kwh, 20)
        self.assertEqual(metrics.bess_discharge_energy_kwh, 40)
        self.assertAlmostEqual(metrics.bess_soc_min, 0.4)
        self.assertAlmostEqual(metrics.bess_soc_max, 0.5)
        self.assertEqual(metrics.grid_export_energy_kwh, 90)
        self.assertEqual(metrics.grid_import_energy_kwh, 170)

    def test_cost_is_unavailable_until_both_coefficients_exist(self):
        for config in (EconomicConfig(), EconomicConfig(cost_per_kwh=2), EconomicConfig(cost_per_kw=3)):
            with self.subTest(config=config):
                metrics = evaluate_results(self.simulate(True), config, self.bess)
                self.assertIsNone(metrics.bess_cost)
                self.assertTrue(any("coefficients" in note for note in metrics.notes))

    def test_explicit_zero_coefficients_are_distinct_from_missing_values(self):
        metrics = evaluate_results(self.simulate(True), EconomicConfig(0, 0), self.bess)
        self.assertEqual(metrics.bess_cost, 0)

    def test_optional_curtailed_and_shed_power_are_integrated(self):
        # Older results may use external action records if none were recorded.
        result = self.simulate()
        for step in result.steps:
            step.curtailment_kw = None
            step.shedding_kw = None
        metrics = evaluate_results(
            result, EconomicConfig(), curtailment_kw=[10, 20], shedding_kw=[2, 3]
        )
        self.assertEqual(metrics.curtailment_energy_kwh, 30)
        self.assertEqual(metrics.load_shedding_energy_kwh, 5)
        self.assertEqual(metrics.served_load_energy_kwh, 300)
        self.assertEqual(metrics.notes, [])

    def test_automatic_control_totals_and_original_energy(self):
        result = simulate_timeseries(
            self.network, self.profiles,
            SimulationConfig(grid_import_limit_kw=100, grid_export_limit_kw=0),
        )
        metrics = evaluate_results(result, EconomicConfig())
        self.assertAlmostEqual(metrics.curtailment_energy_kwh, 50, delta=2e-6)
        self.assertAlmostEqual(metrics.load_shedding_energy_kwh, 50, delta=2e-6)
        self.assertAlmostEqual(metrics.requested_load_energy_kwh, 300)
        self.assertAlmostEqual(metrics.available_pv_energy_kwh, 200)
        self.assertAlmostEqual(metrics.served_load_energy_kwh, 250, delta=2e-6)
        self.assertAlmostEqual(metrics.pv_generation_energy_kwh, 150, delta=2e-6)
        self.assertTrue(metrics.feasible)

    def test_external_records_cannot_overwrite_automatic_actions(self):
        with self.assertRaisesRegex(ValueError, "contradicts"):
            evaluate_results(self.simulate(), EconomicConfig(), curtailment_kw=[10, 0])

    def test_legacy_unrecorded_controls_remain_unknown(self):
        result = self.simulate()
        for step in result.steps:
            step.curtailment_kw = None
            step.shedding_kw = None
        metrics = evaluate_results(result, EconomicConfig())
        self.assertIsNone(metrics.curtailment_energy_kwh)
        self.assertIsNone(metrics.load_shedding_energy_kwh)
        self.assertIsNone(metrics.requested_load_energy_kwh)
        self.assertIsNone(metrics.available_pv_energy_kwh)

    def test_voltage_counts_distinguish_hours_and_bus_hours(self):
        result = self.simulate()
        # Controlled violation records to check counting, not a second voltage rule.
        result.steps[0].voltage_violations = {1: 0.94, 2: 0.93}
        result.steps[0].feasible = False
        result.feasible = False
        metrics = evaluate_results(result, EconomicConfig())
        self.assertEqual(metrics.voltage_violation_hours, 1)
        self.assertEqual(metrics.voltage_violation_bus_hours, 2)
        self.assertFalse(metrics.feasible)

    def test_reserve_violations_count_hours_once(self):
        self.bess.power_rating_kw = 10
        result = simulate_timeseries(
            self.network, self.profiles, SimulationConfig(), self.bess
        )
        metrics = evaluate_results(result, EconomicConfig(), self.bess)
        self.assertEqual(metrics.reserve_violation_hours, 2)
        self.assertFalse(metrics.feasible)

    def test_loss_energy_matches_network_energy_balance(self):
        result = simulate_timeseries(
            make_network(with_line=True), self.profiles,
            SimulationConfig(fbs_config=FBSConfig(voltage_tolerance_pu=1e-12)),
        )
        metrics = evaluate_results(result, EconomicConfig())
        balance = (
            metrics.grid_import_energy_kwh - metrics.grid_export_energy_kwh
            + metrics.pv_generation_energy_kwh - metrics.served_load_energy_kwh
        )
        self.assertGreater(metrics.loss_energy_kwh, 0)
        self.assertAlmostEqual(metrics.loss_energy_kwh, balance, delta=1e-8)

    def test_rejects_empty_partial_and_failed_runs(self):
        result = self.simulate()
        bad_results = [
            replace(result, steps=[]), replace(result, completed=False),
            replace(result, converged=False),
        ]
        for bad_result in bad_results:
            with self.subTest(result=bad_result.message):
                with self.assertRaises(ValueError):
                    evaluate_results(bad_result, EconomicConfig())
        result.steps[0].power_flow.converged = False
        with self.assertRaisesRegex(ValueError, "non-converged"):
            evaluate_results(result, EconomicConfig())

    def test_rejects_missing_or_unrelated_bess_configuration(self):
        with self.assertRaisesRegex(ValueError, "Supply the BESS"):
            evaluate_results(self.simulate(True), EconomicConfig())
        with self.assertRaisesRegex(ValueError, "without a BESS"):
            evaluate_results(self.simulate(), EconomicConfig(), self.bess)

    def test_rejects_invalid_coefficients_and_optional_series(self):
        for value in (-1, float("nan"), float("inf"), True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    EconomicConfig(cost_per_kw=value)
        for series in ([1], [1, -2], [1, float("nan")]):
            with self.subTest(series=series):
                with self.assertRaises(ValueError):
                    evaluate_results(self.simulate(), EconomicConfig(), shedding_kw=series)

    def test_evaluation_does_not_change_input_state(self):
        result = self.simulate(True)
        config_before = self.bess.__dict__.copy()
        energy_before = result.final_bess_state.energy_kwh
        powers_before = result.steps[0].operating_point.p_bess_kw.copy()
        evaluate_results(result, EconomicConfig(2, 3), self.bess)
        self.assertEqual(self.bess.__dict__, config_before)
        self.assertEqual(result.final_bess_state.energy_kwh, energy_before)
        self.assertEqual(result.steps[0].operating_point.p_bess_kw, powers_before)

    def test_percentage_reduction_and_undefined_baselines(self):
        self.assertEqual(percentage_reduction(100, 75), 25)
        self.assertEqual(percentage_reduction(100, 125), -25)
        self.assertEqual(percentage_reduction(0, 0), 0)
        self.assertIsNone(percentage_reduction(0, 20))
        self.assertIsNone(percentage_reduction(None, 20))


if __name__ == "__main__":
    unittest.main()
