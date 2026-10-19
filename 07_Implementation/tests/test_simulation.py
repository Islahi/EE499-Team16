"""Integration checks using the existing loader, BESS model and real FBS."""
import sys
import unittest
from datetime import datetime, timedelta
from dataclasses import replace
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.bess import BESSConfig, BESSState
from src.data_loader import ProfileData, profile_at
from src.fbs import FBSConfig, run_fbs
from src.network_model import Bus, Line, Load, NetworkModel, PVUnit
from src.simulation import SimulationConfig, simulate_step, simulate_timeseries


def make_network(base_kv=11.0, resistance=0.01):
    return NetworkModel(
        buses=[Bus(1, "Grid", base_kv, True), Bus(2, "Load/PV", base_kv)],
        lines=[Line("L1", 1, 2, resistance, 0.01)],
        loads=[Load("Load", 2, 200.0, 40.0)],
        pv_units=[PVUnit("PV", 2, 300.0)],
        base_power_kva=1000.0, frequency_hz=60.0,
    )


def make_profiles(load_values=(200.0, 200.0), pv_values=None):
    if pv_values is None:
        pv_values = [0.0] * len(load_values)
    load_rows = ["timestamp,bus_id,p_kw,q_kvar"]
    pv_rows = ["timestamp,bus_id,p_kw,q_kvar"]
    start = datetime(2026, 1, 1)
    for index, load_kw in enumerate(load_values):
        timestamp = (start + timedelta(hours=index)).isoformat()
        load_rows.append(f"{timestamp},2,{load_kw},0")
        pv_rows.append(f"{timestamp},2,{pv_values[index]},0")
    return ProfileData(
        csv_load=StringIO("\n".join(load_rows)),
        csv_pv=StringIO("\n".join(pv_rows)),
    )


def make_bess():
    # Explicit test coefficients: 80% discharge, 90% charge efficiency.
    return BESSConfig(
        bus_id=2, energy_capacity_kwh=500.0, power_rating_kw=100.0,
        soc_min=0.1, soc_max=0.9, soc_initial=0.5,
        eta_charge=0.9, eta_discharge=0.8,
    )


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.network = make_network()
        self.profiles = make_profiles()
        self.bess = make_bess()

    def test_baseline_matches_direct_fbs(self):
        result = simulate_step(self.network, profile_at(self.profiles, 0), FBSConfig())
        reference = run_fbs(self.network, result.operating_point, FBSConfig())
        self.assertEqual(result.power_flow.voltage_mag_pu, reference.voltage_mag_pu)
        self.assertEqual(result.operating_point.p_load_kw, {1: 0.0, 2: 200.0})
        self.assertEqual(result.operating_point.q_bess_kvar, {1: 0.0, 2: 0.0})
        self.assertTrue(result.feasible)
        self.assertIsNone(result.bess_state)
        self.assertEqual(result.reserve_power_kw, 0)

    def test_charge_discharge_and_state_carryover(self):
        requests = [40.0, -20.0]
        result = simulate_timeseries(
            self.network, self.profiles, SimulationConfig(reserve_fraction=0),
            self.bess, lambda index, profile, state: requests[index],
        )
        self.assertTrue(result.completed)
        self.assertTrue(result.feasible)
        self.assertAlmostEqual(result.steps[0].bess_state.energy_kwh, 200)
        self.assertAlmostEqual(result.steps[1].bess_step.energy_before_kwh, 200)
        self.assertAlmostEqual(result.final_bess_state.energy_kwh, 218)
        self.assertEqual(result.steps[1].operating_point.p_bess_kw[2], -20)
        self.assertGreater(result.steps[1].power_flow.slack_p_kw, 200)

    def test_missing_policy_means_idle_bess(self):
        result = simulate_timeseries(self.network, self.profiles, SimulationConfig(), self.bess)
        self.assertEqual(result.final_bess_state.energy_kwh, 250)
        self.assertTrue(result.feasible)
        self.assertEqual(result.steps[0].bess_step.actual_power_kw, 0)

    def test_power_and_soc_clipping_are_retained(self):
        profiles = make_profiles(load_values=[200.0] * 4)
        result = simulate_timeseries(
            self.network, profiles, SimulationConfig(reserve_fraction=0), self.bess,
            lambda index, profile, state: 500,
        )
        self.assertEqual(result.steps[0].bess_step.actual_power_kw, 100)
        self.assertAlmostEqual(result.steps[1].bess_step.actual_power_kw, 60)
        self.assertEqual(result.steps[2].bess_step.actual_power_kw, 0)
        self.assertAlmostEqual(result.final_bess_state.soc, 0.1)

    def test_reserve_holds_power_and_energy_using_horizon_peak(self):
        profiles = make_profiles(load_values=[100.0, 200.0, 100.0, 100.0])
        original_config = self.bess.__dict__.copy()
        result = simulate_timeseries(
            self.network, profiles, SimulationConfig(), self.bess,
            lambda index, profile, state: 100,
        )
        self.assertEqual(result.steps[0].reserve_power_kw, 20)
        self.assertEqual(result.steps[0].bess_step.actual_power_kw, 80)
        self.assertAlmostEqual(result.final_bess_state.energy_kwh, 50 + 20 / 0.8)
        self.assertEqual(result.steps[-1].bess_step.actual_power_kw, 0)
        self.assertTrue(result.feasible)
        self.assertEqual(self.bess.__dict__, original_config)
        self.assertTrue(result.steps[0].bess_step.limited)
        self.assertIn("Reserve", result.steps[0].bess_step.limit_reason)

    def test_insufficient_power_reserve_is_infeasible(self):
        self.bess.power_rating_kw = 10
        result = simulate_timeseries(self.network, self.profiles, SimulationConfig(), self.bess)
        self.assertTrue(result.completed)
        self.assertTrue(result.converged)
        self.assertFalse(result.feasible)
        self.assertEqual(result.steps[0].reserve_power_shortfall_kw, 10)

    def test_insufficient_initial_energy_can_charge_toward_reserve(self):
        self.bess.soc_initial = 0.1
        result = simulate_timeseries(
            self.network, self.profiles, SimulationConfig(), self.bess,
            lambda index, profile, state: -50,
        )
        self.assertFalse(result.steps[0].feasible)
        self.assertAlmostEqual(result.steps[0].reserve_energy_shortfall_kwh, 25)
        self.assertTrue(result.steps[1].feasible)
        self.assertAlmostEqual(result.final_bess_state.energy_kwh, 140)

    def test_voltage_violations_mark_converged_run_infeasible(self):
        network = make_network(base_kv=1.0, resistance=0.1)
        profiles = make_profiles(load_values=[600.0, 0.0], pv_values=[0.0, 600.0])
        result = simulate_timeseries(network, profiles, SimulationConfig(
            allow_pv_curtailment=False, allow_load_shedding=False
        ))
        self.assertTrue(result.completed)
        self.assertTrue(result.converged)
        self.assertFalse(result.feasible)
        self.assertLess(result.steps[0].voltage_violations[2], 0.95)
        self.assertGreater(result.steps[1].voltage_violations[2], 1.05)

    def test_failure_stops_and_does_not_advance_soc(self):
        settings = SimulationConfig(
            fbs_config=FBSConfig(max_iterations=1, voltage_tolerance_pu=1e-12),
            reserve_fraction=0,
        )
        result = simulate_timeseries(
            self.network, self.profiles, settings, self.bess,
            lambda index, profile, state: 50,
        )
        self.assertFalse(result.completed)
        self.assertFalse(result.converged)
        self.assertFalse(result.feasible)
        self.assertEqual(len(result.steps), 1)
        self.assertEqual(result.final_bess_state.energy_kwh, 250)
        self.assertLess(result.steps[0].bess_step.energy_after_kwh, 250)
        self.assertIsNone(result.steps[0].shedding_kw)
        self.assertIsNone(result.steps[0].curtailment_kw)

    def test_voltage_controls_record_actual_pv_and_load_reductions(self):
        network = make_network(base_kv=1.0, resistance=0.1)
        profiles = make_profiles(load_values=[600.0, 0.0], pv_values=[0.0, 600.0])
        result = simulate_timeseries(network, profiles, SimulationConfig())
        self.assertTrue(result.feasible)
        self.assertGreater(result.steps[0].shedding_kw, 0)
        self.assertGreater(result.steps[1].curtailment_kw, 0)
        self.assertAlmostEqual(result.steps[0].power_flow.voltage_mag_pu[2], 0.95, places=7)
        self.assertAlmostEqual(result.steps[1].power_flow.voltage_mag_pu[2], 1.05, places=7)
        self.assertEqual(profiles.load_p_kw[2], [600, 0])
        self.assertEqual(profiles.pv_p_kw[2], [0, 600])

    def test_import_cap_shedding_preserves_load_power_factor_and_balance(self):
        self.profiles.load_q_kvar[2] = [100, 100]
        result = simulate_timeseries(
            self.network, self.profiles, SimulationConfig(grid_import_limit_kw=100)
        )
        self.assertTrue(result.feasible)
        for step in result.steps:
            point = step.operating_point
            self.assertLessEqual(step.power_flow.slack_p_kw, 100 + 1e-6)
            self.assertAlmostEqual(point.q_load_kvar[2], point.p_load_kw[2] * 0.5)
            self.assertAlmostEqual(point.p_load_kw[2] + step.shedding_by_bus_kw[2], 200)
            self.assertAlmostEqual(sum(step.shedding_by_bus_kw.values()), step.shedding_kw)
            self.assertAlmostEqual(
                step.power_flow.slack_p_kw,
                point.p_load_kw[2] + step.power_flow.total_loss_p_kw,
                delta=1e-5,
            )

    def test_export_cap_curtails_pv_and_preserves_pv_power_factor(self):
        profiles = make_profiles(load_values=[100, 100], pv_values=[300, 300])
        profiles.pv_q_kvar[2] = [30, 30]
        result = simulate_timeseries(
            self.network, profiles, SimulationConfig(grid_export_limit_kw=0)
        )
        self.assertTrue(result.feasible)
        for step in result.steps:
            point = step.operating_point
            self.assertGreater(step.curtailment_kw, 190)
            self.assertGreaterEqual(step.power_flow.slack_p_kw, -1e-6)
            self.assertAlmostEqual(point.q_pv_kvar[2], point.p_pv_kw[2] * 0.1)
            self.assertAlmostEqual(point.p_pv_kw[2] + step.curtailment_by_bus_kw[2], 300)
            self.assertEqual(step.shedding_kw, 0)

    def test_bess_can_reduce_actual_shedding(self):
        settings = SimulationConfig(grid_import_limit_kw=100, reserve_fraction=0)
        baseline = simulate_timeseries(self.network, self.profiles, settings)
        with_bess = simulate_timeseries(
            self.network, self.profiles, settings, self.bess,
            lambda index, profile, state: 50,
        )
        self.assertTrue(with_bess.feasible)
        self.assertLess(with_bess.steps[0].shedding_kw, baseline.steps[0].shedding_kw - 49)
        self.assertAlmostEqual(with_bess.final_bess_state.energy_kwh, 125)

    def test_charging_can_reduce_actual_curtailment(self):
        profiles = make_profiles(load_values=[100, 100], pv_values=[300, 300])
        settings = SimulationConfig(grid_export_limit_kw=0, reserve_fraction=0)
        baseline = simulate_timeseries(self.network, profiles, settings)
        with_bess = simulate_timeseries(
            self.network, profiles, settings, self.bess,
            lambda index, profile, state: -50,
        )
        self.assertTrue(with_bess.feasible)
        self.assertLess(with_bess.steps[0].curtailment_kw, baseline.steps[0].curtailment_kw - 49)
        self.assertAlmostEqual(with_bess.final_bess_state.energy_kwh, 340)

    def test_network_limited_bess_trial_does_not_double_advance_soc(self):
        result = simulate_timeseries(
            self.network, self.profiles,
            SimulationConfig(grid_import_limit_kw=100, reserve_fraction=0),
            self.bess, lambda index, profile, state: -50,
        )
        self.assertTrue(result.feasible)
        self.assertEqual(result.final_bess_state.energy_kwh, 250)
        self.assertGreater(result.steps[0].shedding_kw, 99)
        self.assertEqual(result.steps[0].bess_request_kw, -50)
        self.assertEqual(result.steps[0].bess_step.actual_power_kw, 0)
        result = simulate_timeseries(
            self.network, make_profiles([100, 100], [300, 300]),
            SimulationConfig(grid_export_limit_kw=0, reserve_fraction=0),
            self.bess, lambda index, profile, state: 50,
        )
        self.assertEqual(result.final_bess_state.energy_kwh, 250)
        self.assertEqual(result.steps[0].bess_step.actual_power_kw, 0)
        self.assertGreater(result.steps[0].curtailment_kw, 190)

    def test_uncontrollable_slack_voltage_remains_infeasible(self):
        self.network.buses[0] = replace(self.network.buses[0], v_set_pu=1.1)
        result = simulate_timeseries(self.network, self.profiles, SimulationConfig())
        self.assertTrue(result.converged)
        self.assertFalse(result.feasible)
        self.assertEqual(result.steps[0].curtailment_kw, 0)
        self.assertEqual(result.steps[0].shedding_kw, 0)

    def test_shedding_is_proportional_across_load_buses(self):
        self.network.buses.append(Bus(3, "Second load", 11))
        self.network.lines.append(Line("L2", 1, 3, 0, 0))
        self.network.loads.append(Load("Load3", 3, 300, 150))
        profiles = make_profiles([100, 100])
        profiles.load_p_kw[3] = [300, 300]
        profiles.load_q_kvar[2] = [50, 50]
        profiles.load_q_kvar[3] = [150, 150]
        result = simulate_timeseries(
            self.network, profiles, SimulationConfig(grid_import_limit_kw=200)
        )
        self.assertTrue(result.feasible)
        for step in result.steps:
            self.assertAlmostEqual(step.shedding_by_bus_kw[3] / step.shedding_by_bus_kw[2], 3)
            self.assertAlmostEqual(step.operating_point.q_load_kvar[3],
                                   step.operating_point.p_load_kw[3] * 0.5)

    def test_disabled_controls_preserve_grid_limit_violation(self):
        settings = SimulationConfig(grid_import_limit_kw=100, allow_load_shedding=False)
        result = simulate_timeseries(self.network, self.profiles, settings)
        self.assertFalse(result.feasible)
        self.assertEqual(result.steps[0].shedding_kw, 0)
        self.assertGreater(result.steps[0].power_flow.slack_p_kw, 100)

    def test_invalid_control_settings_are_rejected(self):
        invalid_settings = [
            {"grid_import_limit_kw": -1}, {"grid_export_limit_kw": float("nan")},
            {"control_max_iterations": 0}, {"control_max_iterations": True},
            {"control_tolerance_kw": 0}, {"allow_load_shedding": "yes"},
        ]
        for values in invalid_settings:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    SimulationConfig(**values)

    def test_optional_continuation_keeps_failure_visible(self):
        settings = SimulationConfig(
            fbs_config=FBSConfig(max_iterations=1, voltage_tolerance_pu=1e-12),
            stop_on_power_flow_failure=False, reserve_fraction=0,
        )
        result = simulate_timeseries(
            self.network, self.profiles, settings, self.bess,
            lambda index, profile, state: 50,
        )
        self.assertTrue(result.completed)
        self.assertFalse(result.converged)
        self.assertFalse(result.feasible)
        self.assertEqual(result.steps[1].bess_step.energy_before_kwh, 250)
        self.assertEqual(result.final_bess_state.energy_kwh, 250)

    def test_inputs_and_stored_states_are_not_changed_by_policy(self):
        def dispatch(index, profile, state):
            state.energy_kwh = 0
            state.soc = 0
            return 40

        result = simulate_timeseries(
            self.network, self.profiles, SimulationConfig(reserve_fraction=0), self.bess, dispatch
        )
        self.assertAlmostEqual(result.final_bess_state.energy_kwh, 150)
        self.assertEqual(result.steps[0].bess_state.energy_kwh, 200)

    def test_rejects_unknown_and_missing_bus_profiles(self):
        for mode in ("unknown", "missing"):
            with self.subTest(mode=mode):
                profile = profile_at(self.profiles, 0)
                if mode == "unknown":
                    profile.p_load_kw[99] = 0
                else:
                    del profile.p_load_kw[2]
                with self.assertRaises(ValueError):
                    simulate_step(self.network, profile, FBSConfig())

    def test_rejects_misaligned_series_and_non_hourly_times(self):
        self.profiles.load_p_kw[2].pop()
        with self.assertRaisesRegex(ValueError, "every timestamp"):
            simulate_timeseries(self.network, self.profiles, SimulationConfig())
        profiles = make_profiles()
        profiles.timestamps[1] += timedelta(hours=1)
        with self.assertRaisesRegex(ValueError, "consecutive hours"):
            simulate_timeseries(self.network, profiles, SimulationConfig())

    def test_rejects_dispatch_without_bess_and_nonfinite_request(self):
        with self.assertRaisesRegex(ValueError, "requires a BESS"):
            simulate_timeseries(
                self.network, self.profiles, SimulationConfig(), dispatch_policy=lambda i, p, s: 0
            )
        with self.assertRaisesRegex(ValueError, "finite"):
            simulate_step(self.network, profile_at(self.profiles, 0), FBSConfig(),
                          self.bess, BESSState(250, 0.5), float("nan"))

    def test_three_month_hourly_horizon(self):
        # January through March 2026: 90 days, each including all 24 hourly rows.
        profiles = make_profiles(load_values=[200.0] * (90 * 24))
        result = simulate_timeseries(self.network, profiles, SimulationConfig())
        self.assertTrue(result.completed)
        self.assertTrue(result.feasible)
        self.assertEqual(len(result.steps), 2160)
        self.assertEqual(str(result.steps[-1].timestamp), "2026-03-31 23:00:00")


if __name__ == "__main__":
    unittest.main()
