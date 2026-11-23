"""V11 controller regression: chronological SOC, day-ahead LP and safe FBS."""
import sys
import unittest
from dataclasses import replace
from pathlib import Path
import xml.etree.ElementTree as ET
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.approved_methodology import normalize_settings, methodology_record
from src.bess import BESSConfig
from src.data_loader import ProfileData
from src.network_model import Bus, Line, Load, PVUnit, NetworkModel
from src.simulation import SimulationConfig, simulate_timeseries
from src.metrics import EconomicConfig, with_terminal_policy


def example(hours=48, sunlight=True, stressed=False):
    # Two lateral branches to exercise joint BESS operation.
    network = NetworkModel(
        [Bus(1, 's', 12.66, True), Bus(2, 'a', 12.66), Bus(3, 'b', 12.66), Bus(4, 'c', 12.66)],
        [Line('12', 1, 2, 2.0, .7), Line('23', 2, 3, 3.0, 1.0), Line('24', 2, 4, 2.8, .8)],
        [Load('l3', 3, 450., 100.), Load('l4', 4, 360., 90.)], [PVUnit('p4', 4, 900.)],
        100000., 60.)
    ts = pd.date_range('2021-01-01', periods=hours, freq='h')
    p3 = [(900. if (i%24)>=17 and stressed else 450.) for i in range(hours)]
    p4 = [(750. if (i%24)>=17 and stressed else 360.) for i in range(hours)]
    pv = [(900. if 10 <= (i%24) <= 15 and sunlight else 0.) for i in range(hours)]
    prof = ProfileData.from_arrays(ts,
        {1:[0.]*hours, 2:[0.]*hours, 3:p3, 4:p4},
        {1:[0.]*hours, 2:[0.]*hours, 3:[100.]*hours,4:[90.]*hours},
        {1:[0.]*hours, 2:[0.]*hours, 3:[0.]*hours,4:pv},
        {1:[0.]*hours, 2:[0.]*hours, 3:[0.]*hours,4:[0.]*hours})
    return network, prof


def units():
    return (BESSConfig(3, 1200., 250., .2,1.,.5,.90,.90),
            BESSConfig(4, 1200., 250., .2,1.,.5,.90,.90))


class V11PredictiveTests(unittest.TestCase):
    def test_default_and_legacy_mode_are_explicit(self):
        self.assertEqual(SimulationConfig().fleet_dispatch_mode,'predictive')
        self.assertEqual(normalize_settings({})['fleet_dispatch_mode'],'predictive')
        self.assertEqual(normalize_settings({'fleet_dispatch_mode':'legacy'})['fleet_dispatch_mode'],'legacy')
        with self.assertRaises(ValueError):
            SimulationConfig(fleet_dispatch_mode='invalid')
        self.assertIn('24-hour', methodology_record()['battery_dispatch'])

    def test_multi_bess_plan_is_daily_and_audited(self):
        network, profiles = example(50, sunlight=True, stressed=True)
        sim = simulate_timeseries(network, profiles, SimulationConfig(), bess_fleet=units(),
                                  capture_dispatch=True)
        self.assertTrue(sim.completed, sim.message)
        self.assertTrue(sim.converged, sim.message)
        timing = sim.dispatch_timing
        self.assertEqual(timing['fleet_dispatch_mode'],'predictive')
        self.assertEqual(timing['predictive_horizon_hours'],72)
        self.assertEqual(timing['predictive_days_planned'],3)
        self.assertEqual(timing['predictive_lp_calls'],3)
        self.assertEqual(timing['predictive_lp_failures'],0)
        self.assertEqual(timing['predictive_forecast_fbs_calls'],50)
        self.assertTrue(all(s.dispatch.policy == 'fleet-day-ahead-LP' for s in sim.steps))
        self.assertTrue(all(s.dispatch.horizon_hours == 72 for s in sim.steps))
        self.assertTrue(all(s.feasible for s in sim.steps),sim.message)

    def test_energy_conservation_and_soc_limits(self):
        network, profiles=example(72, sunlight=True, stressed=True)
        fleet=units()
        sim=simulate_timeseries(network, profiles, SimulationConfig(), bess_fleet=fleet,
                                capture_dispatch=False)
        self.assertTrue(sim.completed)
        prev = {c.bus_id:c.energy_capacity_kwh*c.soc_initial for c in fleet}
        for step in sim.steps:
            for c in fleet:
                act = step.fleet_steps[c.bus_id]
                p = act.actual_power_kw
                expected = prev[c.bus_id] - max(0,p)/c.eta_discharge + max(0,-p)*c.eta_charge
                self.assertAlmostEqual(act.energy_after_kwh,expected,places=5)
                self.assertGreaterEqual(act.soc_after,c.soc_min-1e-8)
                self.assertLessEqual(act.soc_after,c.soc_max+1e-8)
                prev[c.bus_id] = act.energy_after_kwh
        for c in fleet:
            self.assertAlmostEqual(prev[c.bus_id],sim.final_fleet_states[c.bus_id].energy_kwh)

    def test_grid_surplus_allows_pv_charging(self):
        network, profiles=example(48, sunlight=True, stressed=False)
        sim=simulate_timeseries(network,profiles,
                    SimulationConfig(grid_export_limit_kw=0.),bess_fleet=units(),capture_dispatch=False)
        self.assertTrue(sim.completed,sim.message)
        self.assertGreater(sum(max(0.,-act.actual_power_kw) for st in sim.steps for act in st.fleet_steps.values()),0.)

    def test_no_extra_load_shedding_for_safe_synthetic_stress(self):
        network, profiles=example(48, sunlight=True, stressed=True)
        results={}
        for mode in ('legacy','predictive'):
            r=simulate_timeseries(network,profiles,SimulationConfig(fleet_dispatch_mode=mode),
                                  bess_fleet=units(),capture_dispatch=False)
            self.assertTrue(r.completed)
            self.assertTrue(r.converged)
            self.assertTrue(all(s.feasible for s in r.steps))
            results[mode]=r
        # Controller quality isn't guaranteed across all networks. This
        # particular scenario is an invariant smoke case, not an annual claim.
        old=sum(s.shedding_kw or 0 for s in results['legacy'].steps)
        new=sum(s.shedding_kw or 0 for s in results['predictive'].steps)
        self.assertLessEqual(new,old+1e-5)


    def test_desktop_uses_active_strict_mode_and_backend_keeps_legacy(self):
        tree=ET.parse(ROOT/'src/assets/settings_dialog.ui')
        self.assertIsNone(tree.find(".//widget[@name='combo_fleet_dispatch_mode']"))
        options=normalize_settings({'fleet_dispatch_mode':'predictive_24h'})
        self.assertEqual(options['fleet_dispatch_mode'],'predictive_24h')

    def test_annual_audit_stays_enabled(self):
        from src.sequential_multi import annual_coverage
        network, prof = example(48)
        result=simulate_timeseries(network,prof,SimulationConfig(),bess_fleet=units(),capture_dispatch=False)
        audit=annual_coverage(result,prof)
        self.assertFalse(audit['complete'])
        self.assertEqual(audit['processed_hours'],48)

if __name__=='__main__': unittest.main()
