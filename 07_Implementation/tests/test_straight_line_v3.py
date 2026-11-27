"""EE499 v2: unit tests requiring no Qt or network access."""
import math
import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.approved_methodology import normalize_settings, methodology_record
from src.metrics import EconomicConfig, evaluate_results
from src.network_model import Bus, Line, Load, NetworkModel
from src.single_bess_search import screen_buses
from src.simulation import SimulationConfig
from src.forecast_accuracy import compare_forecast
from src.data_loader import ProfileData
from src.fbs import OperatingPoint, FBSConfig, run_fbs

class StraightLineAnnualizationTests(unittest.TestCase):
    def test_legacy_assumptions_are_removed(self):
        original={'spin_discount_rate':6,'spin_annual_om_percent':2,'spin_bess_lifetime':10,
                  'spin_fixed_cost':123,'group_reserve':True,'spin_reserve_percent':10,
                  'terminal_policy':'priced_energy','optimizer_algorithm':'GA','spin_grid_import_tariff':.1}
        result=normalize_settings(original,cpu_total=8)
        for field in ('spin_discount_rate','spin_fixed_cost','group_reserve','spin_reserve_percent','terminal_policy'):
            self.assertNotIn(field,result)
        self.assertEqual(result['spin_bess_lifetime'],10)
        self.assertEqual(result['spin_annual_om_percent'],2)
        self.assertEqual(result['optimizer_algorithm'],'GWO')
        self.assertEqual(result['search_mode'],'standard')
        self.assertEqual(result['spin_grid_import_tariff'],.1)
        self.assertIn('weakest',methodology_record()['candidate_screening'])
        for field in ('discount_rate','fixed_installation_cost'):
            self.assertNotIn(field,EconomicConfig.__dataclass_fields__)
        self.assertIn('lifetime_years',EconomicConfig.__dataclass_fields__)
        self.assertIn('annual_om_fraction',EconomicConfig.__dataclass_fields__)
        self.assertNotIn('reserve_fraction',SimulationConfig.__dataclass_fields__)

    def test_33bus_weakest_third_instead_of_fixed_shortlist(self):
        network=NS(buses=[Bus(i,f'B{i}',12.66,i==1) for i in range(1,34)],slack_bus_id=lambda:1)
        eligible=range(2,34)
        steps=[]
        for hour in range(4):
            pre={i:(1.0 if i==2 else .95-(i-2)*.001) for i in range(1,34)}
            steps.append(NS(pre_control_voltage_pu=pre,shedding_by_bus_kw={}))
        base=NS(steps=steps,dt_hours=1.)
        sites,ranking,probes=screen_buses(network,base,eligible,SimulationConfig())
        self.assertEqual(len(sites),11)
        self.assertNotIn(2,sites)
        self.assertIn(33,sites)
        self.assertEqual(probes,0)
        self.assertEqual(ranking[0]['bus'],33)
        self.assertEqual({row['bus'] for row in ranking if row['retained']},set(sites))
        bad=NS(steps=[NS(pre_control_voltage_pu={},shedding_by_bus_kw={})],dt_hours=1.)
        with self.assertRaisesRegex(ValueError,'Pre-correction voltage'):
            screen_buses(network,bad,eligible,SimulationConfig())

    def test_direct_annual_objective_no_capex_ownership(self):
        hours=pd.date_range('2021-01-01',periods=8760,freq='h')
        steps=[]
        for when in hours:
            op=NS(p_load_kw={1:0.,2:196.},p_pv_kw={1:0.,2:50.})
            flow=NS(converged=True,slack_p_kw=100.,total_loss_p_kw=1.,voltage_mag_pu={1:1.,2:.96})
            steps.append(NS(timestamp=when,operating_point=op,power_flow=flow,bess_step=None,
                            voltage_violations={},feasible=True,curtailment_kw=3.,shedding_kw=4.,requested_point=None))
        sim=NS(steps=steps,dt_hours=1.,completed=True,converged=True,feasible=True)
        econ=EconomicConfig(grid_import_tariff_per_kwh=.1,grid_export_tariff_per_kwh=0.,
                            shedding_penalty_per_kwh=12.,curtailment_penalty_per_kwh=.07)
        result=evaluate_results(sim,econ)
        self.assertAlmostEqual(result.requested_load_energy_kwh,(196+4)*8760)
        self.assertAlmostEqual(result.available_pv_energy_kwh,(50+3)*8760)
        self.assertAlmostEqual(result.annual_grid_cost,100*8760*.1)
        self.assertAlmostEqual(result.annual_shedding_cost,4*8760*12.)
        self.assertAlmostEqual(result.annual_curtailment_cost,3*8760*.07)
        self.assertAlmostEqual(result.annual_total_cost,(100*.1+4*12+3*.07)*8760)
        self.assertEqual(result.annualized_bess_cost,0.)
        self.assertAlmostEqual(result.annual_operating_cost,result.annual_total_cost)

    def test_forecasting_scores_only_on_post_training_matched_actuals(self):
        ts=pd.date_range('2021-01-01',periods=48,freq='h')
        hist=ProfileData.from_arrays(ts,{1:[0]*48,2:[10]*48},
             {1:[0]*48,2:[0]*48},{1:[0]*48,2:[6]*48},{1:[0]*48,2:[0]*48})
        future=ProfileData.from_arrays(ts,{1:[0]*48,2:[12]*48},
             {1:[0]*48,2:[0]*48},{1:[0]*48,2:[7]*48},{1:[0]*48,2:[0]*48})
        scores,series=compare_forecast(hist,future,{2:'residential'},'2020-12-31 23:00')
        residential=next(x for x in scores if x['category']=='residential')
        self.assertEqual(residential['hours'],48)
        self.assertAlmostEqual(residential['mae_kw'],2.)
        self.assertAlmostEqual(residential['rmse_kw'],2.)
        self.assertAlmostEqual(residential['wape_percent'],20.)
        # Only categories with genuinely observed-and-forecast buses belong
        # in the holdout display; absent profiles must not become zero-error data.
        self.assertEqual(len(series),48*2)
        self.assertEqual({row['category'] for row in scores}, {'residential', 'solar_pv'})
        with self.assertRaisesRegex(ValueError,'training'):
            compare_forecast(hist,future,{2:'residential'},'2021-01-01')
        missing=ProfileData.from_arrays(pd.date_range('2022-01-01',periods=48,freq='h'),
              future.load_p_kw,future.load_q_kvar,future.pv_p_kw,future.pv_q_kvar)
        scores,series=compare_forecast(hist,missing,{2:'residential'},'2021-12-31')
        self.assertEqual((scores,series),([],[]))

    def test_numba_fbs_unchanged(self):
        buses=[Bus(1,'Slack',12.66,True),Bus(2,'L1',12.66),Bus(3,'L2',12.66)]
        net=NetworkModel(buses,[Line('a',1,2,.1,.06),Line('b',2,3,.15,.09)],
                         [Load('load2',2,100,50),Load('load3',3,50,25)],[],100000,60)
        op=OperatingPoint({1:0,2:100,3:50},{1:0,2:50,3:25},
                          {1:0,2:0,3:0},{1:0,2:0,3:0},{1:0,2:0,3:0},{1:0,2:0,3:0})
        result=run_fbs(net,op,FBSConfig())
        self.assertTrue(result.converged,result.message)
        self.assertGreater(result.voltage_mag_pu[2],result.voltage_mag_pu[3])


    def test_desktop_retains_only_active_ownership_inputs(self):
        source=(ROOT/'src/assets/settings_dialog.ui').read_text(encoding='utf-8')
        for control in ('spin_bess_lifetime', 'spin_annual_om_percent', 'spin_inverter_capex'):
            self.assertIn(f'name="{control}"',source)
        for control in ('combo_optimizer_algorithm', 'spin_discount_rate', 'spin_cost_per_kw'):
            self.assertNotIn(f'name="{control}"',source)

    def test_direct_energy_has_no_representative_day_weights(self):
        for field in ('annual_day_weights', 'annualization_basis', 'annual_hours'):
            self.assertNotIn(field,EconomicConfig.__dataclass_fields__)
        ts=pd.date_range('2021-01-01',periods=8760,freq='h')
        from src.metrics import validate_annual_inputs
        econ=EconomicConfig(grid_import_tariff_per_kwh=.1,grid_export_tariff_per_kwh=0)
        self.assertTrue(validate_annual_inputs(ts,econ))
        with self.assertRaisesRegex(ValueError,'8760/8784'):
            validate_annual_inputs(ts[1:],econ)


    def test_offline_dashboard_displays_relevant_sections_and_cost_basis(self):
        html=(ROOT/'src/assets/dashboard.html').read_text(encoding='utf-8')
        script=(ROOT/'src/assets/dashboard.js').read_text(encoding='utf-8')
        self.assertIn('Study results',html)
        self.assertIn("let run,screen='Summary'",script)
        self.assertIn("if(run.forecast_errors?.length)options.push('Forecast accuracy')",script)
        self.assertIn("labels.push('Compare Runs')",script)
        self.assertIn('Annual capital: initial BESS cost / useful life',script)
        self.assertIn('Annual O&M: initial BESS cost',script)

    def test_straight_line_annual_bess_cost_is_in_annual_objective(self):
        from src.bess import BESSConfig
        from src.optimizer import annual_economic_objective
        hours=pd.date_range('2021-01-01',periods=8760,freq='h')
        battery=BESSConfig(bus_id=2, energy_capacity_kwh=6250., power_rating_kw=1250.,
                           soc_min=.2, soc_max=1., soc_initial=.5, eta_charge=.9, eta_discharge=.9)
        steps=[]
        for t in hours:
            flow=NS(converged=True,slack_p_kw=100.,total_loss_p_kw=1.,voltage_mag_pu={1:1.,2:.97})
            steps.append(NS(timestamp=t,operating_point=NS(p_load_kw={2:100.},p_pv_kw={2:0.}),
                 power_flow=flow,bess_step=NS(actual_power_kw=0.,soc_before=.5),
                 bess_state=NS(soc=.5),voltage_violations={},feasible=True,
                 curtailment_kw=0.,shedding_kw=0.,requested_point=None))
        sim=NS(steps=steps,dt_hours=1.,completed=True,converged=True,feasible=True,
               final_bess_state=NS(energy_kwh=6250.*.5))
        econ=EconomicConfig(grid_import_tariff_per_kwh=.1,grid_export_tariff_per_kwh=0.,
                            lifetime_years=10,annual_om_fraction=.02)
        got=evaluate_results(sim,econ,battery)
        capex=1250*770+6250*385
        self.assertEqual(got.bess_cost,capex)
        self.assertAlmostEqual(got.annual_bess_capital_cost,capex/10)
        self.assertAlmostEqual(got.annual_bess_om_cost,capex*.02)
        self.assertAlmostEqual(got.annualized_bess_cost,404250.)
        self.assertAlmostEqual(got.annual_operating_cost,8760*100*.1)
        self.assertAlmostEqual(got.annual_total_cost,8760*100*.1+404250)
        self.assertEqual(annual_economic_objective(got),got.annual_total_cost)

    def test_bess_lifetime_and_om_are_validated(self):
        with self.assertRaisesRegex(ValueError,'positive integer'):
            EconomicConfig(lifetime_years=0)
        with self.assertRaisesRegex(ValueError,'positive integer'):
            EconomicConfig(lifetime_years=10.5)
        with self.assertRaisesRegex(ValueError,'negative'):
            EconomicConfig(annual_om_fraction=-.01)
        self.assertNotIn('discount_rate', EconomicConfig.__dataclass_fields__)

    def test_screening_evaluator_adds_annual_ownership_once(self):
        from unittest.mock import patch
        from src.single_bess_search import WindowEvaluator
        from src.optimizer import BESSCandidate
        econ=EconomicConfig(grid_import_tariff_per_kwh=.1,grid_export_tariff_per_kwh=0.,
                             lifetime_years=10,annual_om_fraction=.02)
        candidate=BESSCandidate(bus_id=2,power_rating_kw=1250.,energy_capacity_kwh=6250.)
        fake_evaluator=NS(economic_config=econ,simulation_config=SimulationConfig(),
             battery_parameters=NS(build_config=lambda _:NS()),dispatch_policy=None)
        simulation=NS(completed=True,converged=True,steps=[NS(feasible=True,messages=[]) for _ in range(24)])
        sample=NS(load_shedding_energy_kwh=4.,curtailment_energy_kwh=2.,
                  grid_import_energy_kwh=100.,grid_export_energy_kwh=0.)
        with patch('src.single_bess_search.simulate_timeseries',return_value=simulation),\
             patch('src.single_bess_search.evaluate_results',return_value=sample):
            result=WindowEvaluator(fake_evaluator,8760)(None,[NS()],candidate)
        operating_24h=100*.1+4*12+2*.07
        self.assertAlmostEqual(result.objective,operating_24h*(8760/24)+404250.)

    def test_dashboard_and_results_export_include_ownership_components(self):
        source=(ROOT/'src/results.py').read_text(encoding='utf-8')
        js=(ROOT/'src/assets/dashboard.js').read_text(encoding='utf-8')
        for field in ('annual_bess_capital_cost','annual_bess_om_cost','annualized_bess_cost'):
            self.assertIn(field,source)
            self.assertIn(field,js)
        metadata=(ROOT/'src/ui_workflow.py').read_text(encoding='utf-8')
        self.assertIn('annual_om_percent_of_capex',metadata)
        self.assertIn('initial_BESS_cost / lifetime_years',metadata)

if __name__=='__main__':unittest.main()
