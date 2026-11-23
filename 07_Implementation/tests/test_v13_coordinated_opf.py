"""V13 functional checks: coordinated P/Q, physical inverter bounds, SOC and UI."""
import sys, unittest, xml.etree.ElementTree as ET
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.network_model import NetworkModel, Bus, Line, Load, PVUnit
from src.bess import BESSConfig
from src.data_loader import ProfileData
from src.simulation import SimulationConfig,simulate_timeseries
from src.approved_methodology import normalize_settings


def stressed_case(hours=12, pv_kw=0.):
    network=NetworkModel([Bus(1,'source',12.66,True),Bus(2,'end',12.66)],
        [Line('12',1,2,6.,5.)], [Load('load',2,1000.,650.)],
        [PVUnit('pv',2,500.)],100000.,60.)
    ts=pd.date_range('2021-01-01',periods=hours,freq='h')
    profile=ProfileData.from_arrays(ts,
        {1:[0.]*hours,2:[1000.]*hours},
        {1:[0.]*hours,2:[650.]*hours},
        {1:[0.]*hours,2:[pv_kw]*hours},
        {1:[0.]*hours,2:[0.]*hours})
    return network,profile


class V13OPFTests(unittest.TestCase):
    def test_settings_and_ui_still_support_v12(self):
        self.assertEqual(SimulationConfig(fleet_dispatch_mode='opf').fleet_dispatch_mode,'opf')
        self.assertEqual(normalize_settings({'fleet_dispatch_mode':'opf'})['fleet_dispatch_mode'],'opf')
        self.assertEqual(normalize_settings({})['fleet_dispatch_mode'],'predictive')
        with self.assertRaises(ValueError):
            SimulationConfig(fleet_dispatch_mode='opf',opf_bess_kva_multiplier=.8)
        xml=ET.parse(ROOT/'src/assets/settings_dialog.ui')
        names={node.get('name') for node in xml.iter('widget')}
        self.assertNotIn('combo_fleet_dispatch_mode',names)
        for label in ('spin_opf_bess_kva_multiplier',
                      'spin_opf_pv_kva_multiplier'):
            self.assertNotIn(label,names)

    def test_q_support_without_battery_energy_discharge(self):
        net,prof=stressed_case(12)
        battery=BESSConfig(2,1000.,500.,.2,1.,.2,.9,.9)
        v12=simulate_timeseries(net,prof,SimulationConfig(fleet_dispatch_mode='predictive'),
                                bess_fleet=(battery,),capture_dispatch=False)
        v13=simulate_timeseries(net,prof,SimulationConfig(fleet_dispatch_mode='opf'),
                                bess_fleet=(battery,),capture_dispatch=False)
        self.assertTrue(v13.completed)
        self.assertTrue(v13.feasible)
        self.assertLessEqual(sum(s.shedding_kw or 0 for s in v13.steps),
                             sum(s.shedding_kw or 0 for s in v12.steps)+1e-5)
        self.assertGreater(max(abs(s.operating_point.q_bess_kvar[2]) for s in v13.steps),10.)
        for s in v13.steps:
            p=s.operating_point.p_bess_kw[2]
            q=s.operating_point.q_bess_kvar[2]
            self.assertLessEqual(p*p+q*q,(1.2*battery.power_rating_kw)**2+1e-4)
            self.assertGreaterEqual(s.fleet_states[2].soc,.2-1e-8)
            self.assertLessEqual(s.fleet_states[2].soc,1.+1e-8)
            for v in s.power_flow.voltage_mag_pu.values():
                self.assertGreaterEqual(v,.95-1e-7)
                self.assertLessEqual(v,1.05+1e-7)
        self.assertGreater(v13.dispatch_timing['opf_lp_calls'],0)

    def test_baseline_no_battery_can_use_pv_reactive_power(self):
        net,prof=stressed_case(10,pv_kw=100.)
        baseline=simulate_timeseries(net,prof,SimulationConfig(fleet_dispatch_mode='predictive'),
                                     capture_dispatch=False)
        new=simulate_timeseries(net,prof,SimulationConfig(fleet_dispatch_mode='opf'),
                                capture_dispatch=False)
        self.assertTrue(new.completed)
        self.assertTrue(new.feasible)
        self.assertLessEqual(sum(s.shedding_kw or 0 for s in new.steps),
                             sum(s.shedding_kw or 0 for s in baseline.steps)+1e-6)
        self.assertTrue(all(s.correction.status in ('verified','not_needed') for s in new.steps))
        self.assertTrue(all(abs(s.operating_point.q_pv_kvar[2]) <= 550.+1e-5 for s in new.steps))
        self.assertGreater(new.dispatch_timing['opf_lp_calls'],0)

    def test_early_out_when_no_constraints_bind(self):
        net,prof=stressed_case(4,pv_kw=500.)
        # Simple safe/low-demand variant should avoid an LP entirely.
        from dataclasses import replace
        net.lines[0]=replace(net.lines[0],r_ohm=.1,x_ohm=.1)
        new=simulate_timeseries(net,prof,SimulationConfig(fleet_dispatch_mode='opf'),capture_dispatch=False)
        self.assertTrue(new.feasible)
        self.assertEqual(new.dispatch_timing['opf_lp_calls'],0)

if __name__=='__main__': unittest.main()
