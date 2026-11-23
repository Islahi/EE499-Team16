"""V12: SOC warm starts, 72h replan, 24h V11 parity, annual inventory."""
import sys
import unittest
from pathlib import Path
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_v11_predictive_control import example, units
from src.simulation import SimulationConfig, simulate_timeseries
from src.screening_soc import ChronologicalSOCWarmStarts
from src.bess import BESSConfig
from src.metrics import EconomicConfig, evaluate_results
from src.approved_methodology import normalize_settings


class V12Tests(unittest.TestCase):
    def test_v12_72h_plans_daily_and_caches_forecasts(self):
        network, prof = example(96, sunlight=True, stressed=True)
        sim = simulate_timeseries(network,prof,SimulationConfig(),
                                  bess_fleet=units(),capture_dispatch=True)
        self.assertTrue(sim.completed, sim.message)
        self.assertTrue(sim.feasible, sim.message)
        t=sim.dispatch_timing
        self.assertEqual(t['predictive_horizon_hours'],72)
        self.assertEqual(t['predictive_replan_interval_hours'],24)
        self.assertEqual(t['predictive_lp_calls'],4)
        self.assertEqual(t['predictive_lp_failures'],0)
        self.assertEqual(t['predictive_forecast_fbs_calls'],96)
        self.assertGreater(t['predictive_forecast_cache_hits'],0)
        self.assertTrue(t['predictive_shedding_aware'])
        self.assertTrue(all(s.dispatch.horizon_hours == 72 for s in sim.steps))
        self.assertTrue(all(s.feasible for s in sim.steps))

    def test_v11_mode_keeps_24h_planning(self):
        network,prof=example(50,sunlight=True,stressed=True)
        sim=simulate_timeseries(network,prof,
             SimulationConfig(fleet_dispatch_mode='predictive_24h'),
             bess_fleet=units(),capture_dispatch=False)
        self.assertTrue(sim.completed)
        self.assertEqual(sim.dispatch_timing['predictive_horizon_hours'],24)
        self.assertEqual(sim.dispatch_timing['predictive_lp_calls'],3)
        self.assertFalse(sim.dispatch_timing['predictive_shedding_aware'])
        self.assertEqual(normalize_settings({'fleet_dispatch_mode':'predictive_24h'})['fleet_dispatch_mode'], 'predictive_24h')

    def test_candidate_specific_soc_is_not_reset_between_windows(self):
        network,prof=example(96,sunlight=False,stressed=True)
        raw=simulate_timeseries(network,prof,SimulationConfig(),capture_dispatch=True)
        self.assertTrue(raw.completed)
        initial_idx=(tuple(range(0,24)),tuple(range(48,72)),tuple(range(72,96)))
        proxy=ChronologicalSOCWarmStarts.from_annual(network,prof,raw,SimulationConfig(),initial_idx)
        battery=BESSConfig(3,1200.,250.,.2,1.,.5,.9,.9)
        soc=proxy.candidate_energy_at_windows(battery)
        self.assertAlmostEqual(soc[0],600.)
        self.assertNotAlmostEqual(soc[48],600.)
        self.assertGreaterEqual(soc[48],240.-1e-8)
        self.assertLessEqual(soc[72],1200.+1e-7)
        estimates=proxy.window_start_energy(48,(battery,),battery)
        self.assertAlmostEqual(estimates[3],soc[48])

    def test_annual_inventory_deficit_cost_is_reported(self):
        network,prof=example(48,sunlight=False,stressed=True)
        battery=units()[0]
        sim=simulate_timeseries(network,prof,SimulationConfig(),bess_fleet=(battery,),capture_dispatch=False)
        economics=EconomicConfig(grid_import_tariff_per_kwh=.12,grid_export_tariff_per_kwh=0.)
        from unittest.mock import patch
        # The 48h synthetic fixture is intentionally not an annual record.
        with patch('src.metrics.validate_annual_inputs',return_value=None):
            result=evaluate_results(sim,economics,(battery,))
        start=battery.soc_initial*battery.energy_capacity_kwh
        end=sim.final_fleet_states[battery.bus_id].energy_kwh
        expected=max(0.,start-end)/battery.eta_charge*.12
        self.assertAlmostEqual(result.annual_terminal_inventory_adjustment,expected,places=5)
        self.assertTrue(result.annual_total_cost is None or result.annual_total_cost >= 0.)


if __name__=='__main__': unittest.main()
