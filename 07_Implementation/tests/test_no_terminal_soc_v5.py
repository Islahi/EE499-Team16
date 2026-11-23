"""Regression tests: terminal SOC closure is fully disabled, not just hidden in the UI."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.approved_methodology import normalize_settings, methodology_record
from src.metrics import EconomicConfig, evaluate_results, with_terminal_policy
from src.simulation import (GridAwareDispatchPolicy, SimulationConfig,
                                         simulate_timeseries)
from tests.test_multi_v4 import make_network, make_profiles, battery


class NoTerminalClosureTests(unittest.TestCase):
    def test_single_bess_finishes_below_initial_without_terminal_failure(self):
        source = SimulationConfig(terminal_soc_tolerance=1e-12, terminal_cycle_hours=4)
        run = simulate_timeseries(make_network(), make_profiles(24), source,
                                  bess_config=battery(3),
                                  dispatch_policy=GridAwareDispatchPolicy(),
                                  capture_dispatch=False)
        self.assertTrue(run.feasible, run.message)
        self.assertTrue(run.completed)
        self.assertAlmostEqual(run.final_bess_state.soc, 0.2)
        self.assertTrue(all('Terminal SOC' not in msg for step in run.steps for msg in step.messages))
        for step in run.steps:
            self.assertGreaterEqual(step.bess_state.soc, 0.2 - 1e-10)
            self.assertLessEqual(step.bess_state.soc, 1.0 + 1e-10)

    def test_two_bess_independent_energy_bounds_without_final_equality(self):
        source = SimulationConfig(terminal_soc_tolerance=1e-12, terminal_cycle_hours=4, fleet_dispatch_mode="legacy")
        with patch('src.voltage_dispatch.VoltageSupport.dispatch',
                   side_effect=lambda flow,configs,states,settings:
                      ({c.bus_id:c.power_rating_kw for c in configs}, 'forced discharge')):
            run = simulate_timeseries(make_network(), make_profiles(24), source,
                                      bess_fleet=(battery(2), battery(3)), capture_dispatch=False)
        self.assertTrue(run.feasible, run.message)
        self.assertTrue(run.completed)
        self.assertAlmostEqual(run.final_fleet_states[2].soc, 0.2)
        self.assertAlmostEqual(run.final_fleet_states[3].soc, 0.2)
        self.assertTrue(all(step.feasible for step in run.steps))

    def test_old_saved_terminal_settings_cannot_reenable_closure(self):
        saved = normalize_settings({'group_terminal_soc': True,
                                    'spin_terminal_soc_percent': .0001,
                                    'terminal_policy': 'equal_soc'})
        self.assertNotIn('group_terminal_soc', saved)
        self.assertNotIn('spin_terminal_soc_percent', saved)
        self.assertEqual(methodology_record()['terminal_soc_closure'].split(';')[0], 'disabled')
        econ = EconomicConfig(grid_import_tariff_per_kwh=.1, grid_export_tariff_per_kwh=0.)
        applied = with_terminal_policy(SimulationConfig(terminal_soc_tolerance=1e-12,
                                                        terminal_cycle_hours=2), econ)
        self.assertIsNone(applied.terminal_soc_tolerance)
        self.assertIsNone(applied.terminal_cycle_hours)

    def test_annual_cost_and_final_inventory_reported_even_when_unbalanced(self):
        c = battery(3)
        econ = EconomicConfig(grid_import_tariff_per_kwh=.1, grid_export_tariff_per_kwh=0.)
        with patch('src.voltage_dispatch.VoltageSupport.dispatch',
                   side_effect=lambda flow,configs,states,settings:
                      ({c.bus_id:c.power_rating_kw for c in configs}, 'forced discharge')):
            run = simulate_timeseries(make_network(), make_profiles(8760),
                                      with_terminal_policy(SimulationConfig(fleet_dispatch_mode="legacy"), econ),
                                      bess_fleet=(c,), capture_dispatch=False)
        self.assertTrue(run.feasible, run.message)
        self.assertAlmostEqual(run.final_fleet_states[3].soc, 0.2)
        result = evaluate_results(run, econ, (c,))
        self.assertTrue(result.feasible, result.notes)
        self.assertIsNotNone(result.annual_total_cost)
        self.assertAlmostEqual(result.final_soc_deviation, -.3)
        self.assertAlmostEqual(result.terminal_energy_change_kwh, -150.)
        self.assertIn('Bus 3:', result.terminal_soc_details[0])
        self.assertIn('No terminal SOC closure', result.notes[-1])
        self.assertAlmostEqual(result.annual_total_cost,
                               result.annual_operating_cost + result.annualized_bess_cost)

    def test_dashboard_explicitly_discloses_end_of_study_energy(self):
        script = (ROOT / 'src/assets/dashboard.js').read_text(encoding='utf8')
        for name in ('terminal_energy_change_kwh', 'terminal_soc_details',
                     'No terminal SOC closure is required'):
            self.assertIn(name, script)


if __name__ == '__main__':
    unittest.main()
