"""Executed-hour validation for strict Ahmed/Sindi static adaptation.

These tests do not claim a reproduction of mobile MESS or the paper's GRG MINLP.
"""
import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.simulation import simulate_timeseries, SimulationConfig
from src.bess import BESSConfig
from src.metrics import EconomicConfig, evaluate_results
from src.daily_milp_dispatch import DailyMILPPlanner, q_per_kw_at_min_pf
from tests.test_fleet_dispatch_backend import _four_bus_radial_case


class StrictOperationTests(unittest.TestCase):
    def setUp(self):
        self.network, self.profiles = _four_bus_radial_case(days=2)
        self.fleet=(BESSConfig(3, 2000, 500, .2, 1., .5, .95, .95),
                    BESSConfig(4, 2000, 500, .2, 1., .5, .95, .95))

    def test_daily_restoration_and_pf_for_every_executed_step(self):
        config=SimulationConfig(fleet_dispatch_mode='daily_milp_dispatch',minimum_discharge_pf=.95)
        result=simulate_timeseries(self.network,self.profiles,config,bess_fleet=self.fleet)
        self.assertTrue(result.completed)
        self.assertTrue(result.feasible,result.message)
        self.assertEqual(result.dispatch_timing['daily_soc_failures'],[])
        self.assertAlmostEqual(result.dispatch_timing['opf_bess_plan_adjustment_abs_kwh'],0,places=6)
        for i, step in enumerate(result.steps):
            for conf in self.fleet:
                power=step.operating_point.p_bess_kw.get(conf.bus_id,0.)
                reactive=step.operating_point.q_bess_kvar.get(conf.bus_id,0.)
                self.assertGreaterEqual(reactive,-1e-6)
                self.assertLessEqual(reactive,max(0.,power)*q_per_kw_at_min_pf(.95)+1e-5)
                self.assertLessEqual(power*power+reactive*reactive,(conf.power_rating_kw/.95)**2+1e-4)
                self.assertGreaterEqual(step.fleet_states[conf.bus_id].soc, conf.soc_min-1e-7)
                self.assertLessEqual(step.fleet_states[conf.bus_id].soc, conf.soc_max+1e-7)
            if (i+1)%24 == 0:
                for c in self.fleet:
                    self.assertAlmostEqual(step.fleet_states[c.bus_id].soc,.5,places=5)

    def test_48_and_72_hour_horizons(self):
        for horizon in (48,72):
            with self.subTest(horizon=horizon):
                cfg=SimulationConfig(fleet_dispatch_mode='daily_milp_dispatch',dispatch_horizon_hours=horizon)
                r=simulate_timeseries(self.network,self.profiles,cfg,bess_fleet=(self.fleet[0],),capture_dispatch=False)
                self.assertTrue(r.feasible,r.message)
                self.assertTrue(r.dispatch_timing['daily_soc_restored'])

    def test_manual_single_battery_uses_strict_not_legacy_dispatch(self):
        r=simulate_timeseries(self.network,self.profiles,
            SimulationConfig(fleet_dispatch_mode='daily_milp_dispatch'),bess_config=self.fleet[0])
        self.assertTrue(r.feasible)
        self.assertEqual(r.dispatch_timing['fleet_dispatch_mode'],'daily_milp_dispatch')

    def test_baseline_empty_fleet_avoids_recursive_dispatch(self):
        r=simulate_timeseries(self.network,self.profiles,
            SimulationConfig(fleet_dispatch_mode='daily_milp_dispatch'),bess_fleet=())
        self.assertTrue(r.completed)
        self.assertEqual(len(r.steps),48)

    def test_failing_actual_soc_restoration_is_not_marked_feasible(self):
        def faulty(self,index,states,flow):
            self.last_reason='injected regression fault'
            return ({self.configs[0].bus_id: 10. if index == 23 else 0.},'forced')
        with patch.object(DailyMILPPlanner,'request',faulty):
            r=simulate_timeseries(self.network,self.profiles,
                SimulationConfig(fleet_dispatch_mode='daily_milp_dispatch'),bess_fleet=(self.fleet[0],),capture_dispatch=False)
        self.assertFalse(r.feasible)
        self.assertTrue(r.dispatch_timing['daily_soc_failures'])

    def test_failed_milp_is_reported_infeasible_not_silent_success(self):
        with patch.object(DailyMILPPlanner, '_plan', side_effect=ValueError('forced infeasible schedule')):
            r=simulate_timeseries(self.network,self.profiles,
                SimulationConfig(fleet_dispatch_mode='daily_milp_dispatch'),
                bess_fleet=(self.fleet[0],),capture_dispatch=False)
        self.assertFalse(r.feasible)
        self.assertGreater(r.dispatch_timing['daily_milp_failures'],0)
        self.assertTrue(any('Daily MILP dispatch schedule UNAVAILABLE' in message
                            for step in r.steps for message in step.messages))

    def test_complete_manual_gui_workflow_uses_strict_dispatch_counters(self):
        # Qt is not installed here; run_study is the pure-Python business logic
        # used by the GUI worker and must not assume legacy timing keys.
        from src.ui_workflow import PreparedStudy, RunSettings, run_study
        from src.constraint_dispatch import ConstraintAwareDispatch
        study=PreparedStudy(self.network,self.profiles,None,{'Network':'4-bus test'})
        economic=EconomicConfig(cost_per_kwh=200,cost_per_kw=175,
           grid_import_tariff_per_kwh=.1,grid_export_tariff_per_kwh=0,
           power_cost_basis='kva',inverter_kva_per_kw=1/.95)
        settings=RunSettings(SimulationConfig(fleet_dispatch_mode='daily_milp_dispatch'),
                             economic,self.fleet[0],values={},dispatch=ConstraintAwareDispatch())
        messages=[]
        report=run_study(study,settings,optimization=False,stage=messages.append)
        self.assertTrue(report.result.completed)
        self.assertTrue(report.result.feasible)
        self.assertIn('daily_milp_days_planned',report.result.dispatch_timing)
        self.assertTrue(any('Dispatch scheduling' in m for m in messages))

    def test_power_inverter_cost_basis_kva(self):
        cfg=SimulationConfig(fleet_dispatch_mode='daily_milp_dispatch')
        r=simulate_timeseries(self.network,self.profiles,cfg,bess_fleet=(self.fleet[0],),capture_dispatch=False)
        econ=EconomicConfig(cost_per_kwh=200,cost_per_kw=175,power_cost_basis='kva',inverter_kva_per_kw=1/.95,
                            grid_import_tariff_per_kwh=.1,grid_export_tariff_per_kwh=0)
        metrics=evaluate_results(r,econ,(self.fleet[0],))
        self.assertAlmostEqual(metrics.bess_cost,2000*200+500*175/.95,places=4)
        self.assertEqual(econ.power_cost_basis,'kva')

if __name__=='__main__':unittest.main()
