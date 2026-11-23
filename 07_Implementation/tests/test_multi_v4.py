"""Tests of the barebones Karve-inspired sequential multi-BESS adaptation."""
import math
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.bess import BESSConfig, BESSState
from src.data_loader import ProfileData
from src.metrics import EconomicConfig, evaluate_results, with_terminal_policy
from src.network_model import Bus, Line, Load, NetworkModel
from src.optimizer import (BESSCandidate, BESSParameters, CandidateEvaluation,
                                       OptimizationBounds, OptimizerConfig, SimulationEvaluator,
                                       OptimizationResult)
from src.simulation import SimulationConfig, simulate_timeseries
from src.multi_bess import _target_kw
from src.sequential_multi import optimize_sequential_multi


def make_network():
    return NetworkModel([Bus(1, 'slack', 12.66, True), Bus(2, 'near', 12.66), Bus(3, 'far', 12.66)],
                        [Line('a', 1, 2, .10, .06), Line('b', 2, 3, .2, .1)],
                        [Load('l2', 2, 100., 20.), Load('l3', 3, 130., 30.)], [], 100000., 60.)


def make_profiles(hours):
    ts = pd.date_range('2021-01-01', periods=hours, freq='h')
    return ProfileData.from_arrays(ts, {1: [0.]*hours, 2: [100.]*hours, 3: [130.]*hours},
                    {1: [0.]*hours, 2: [20.]*hours, 3: [30.]*hours},
                    {1: [0.]*hours, 2: [0.]*hours, 3: [0.]*hours},
                    {1: [0.]*hours, 2: [0.]*hours, 3: [0.]*hours})


def battery(bus):
    return BESSConfig(bus, 500., 50., .2, 1., .5, .9, .9)


class SequentialMultiTests(unittest.TestCase):
    def test_joint_fbs_and_independent_soc(self):
        configs = (battery(2), battery(3))
        econ = EconomicConfig(grid_import_tariff_per_kwh=.1, grid_export_tariff_per_kwh=0.)
        simulation = simulate_timeseries(make_network(), make_profiles(24),
                                         SimulationConfig(), bess_fleet=configs)
        self.assertTrue(simulation.completed)
        self.assertTrue(simulation.converged)
        self.assertEqual(set(simulation.final_fleet_states), {2, 3})
        self.assertEqual(set(simulation.steps[0].fleet_steps), {2, 3})
        for step in simulation.steps:
            self.assertAlmostEqual(sum(step.operating_point.p_bess_kw.values()),
                                   sum(x.actual_power_kw for x in step.fleet_steps.values()))
            self.assertTrue(step.power_flow.converged)
        metrics = evaluate_results(simulation, econ, configs)
        installation = 2 * (500 * 385 + 50 * 770)
        self.assertEqual(metrics.bess_cost, installation)
        self.assertEqual(metrics.annualized_bess_cost, installation / 10 + installation * .02)
        self.assertIsNone(metrics.annual_total_cost, 'Short technical runs are not annual financial claims')
        with self.assertRaisesRegex(ValueError, 'same installation bus twice'):
            simulate_timeseries(make_network(), make_profiles(24),
                                SimulationConfig(), bess_fleet=(battery(2), battery(2)))

    def test_simple_dispatch_responds_to_constraint_not_normal_demand(self):
        c = battery(2)
        states = {2: BESSState(250., .5)}
        point = NS(p_load_kw={1:0.,2:100.},p_pv_kw={1:0.,2:0.})
        normal = NS(converged=True,slack_p_kw=120.,voltage_mag_pu={1:1.,2:.98})
        config = SimulationConfig(grid_import_limit_kw=200.)
        self.assertEqual(_target_kw(normal,point,config,(c,),states),0.)
        stressed = NS(converged=True,slack_p_kw=300.,voltage_mag_pu={1:1.,2:.98})
        self.assertEqual(_target_kw(stressed,point,config,(c,),states),50.)
        depleted = {2: BESSState(180., .36)}
        self.assertLess(_target_kw(normal,point,config,(c,),depleted),0.)
        undervoltage = NS(converged=True,slack_p_kw=120.,voltage_mag_pu={1:1.,2:.94})
        self.assertEqual(_target_kw(undervoltage,point,config,(c,),states),50.)

    def test_yearly_fleet_cost_and_terminal_soc(self):
        configs = (battery(2),battery(3))
        econ = EconomicConfig(grid_import_tariff_per_kwh=.1, grid_export_tariff_per_kwh=0.)
        run = simulate_timeseries(make_network(),make_profiles(8760),
                 with_terminal_policy(SimulationConfig(),econ),bess_fleet=configs,
                 capture_dispatch=False)
        self.assertTrue(run.feasible)
        for battery_id in (2,3):
            # v7 deliberately recharges toward SOC MAX in safe hours; it no
            # longer tries to maintain the initial 50% inventory.
            self.assertGreaterEqual(run.final_fleet_states[battery_id].soc, .5)
            self.assertLessEqual(run.final_fleet_states[battery_id].soc, 1.0)
        metrics = evaluate_results(run,econ,configs)
        self.assertTrue(metrics.feasible)
        self.assertAlmostEqual(metrics.annual_total_cost, metrics.annual_operating_cost + metrics.annualized_bess_cost)
        self.assertGreaterEqual(metrics.final_soc_deviation,0.)

    def test_sequential_reranks_and_stops_when_unhelpful(self):
        econ=EconomicConfig(grid_import_tariff_per_kwh=.1,grid_export_tariff_per_kwh=0.)
        evaluator=SimulationEvaluator(econ,BESSParameters(.9,.9),
                                      __import__('src.constraint_dispatch',fromlist=['ConstraintAwareDispatch']).ConstraintAwareDispatch(),SimulationConfig())
        network=make_network()
        profiles=make_profiles(8760)
        bounds=OptimizationBounds((2,3), (50.,), (500.,))
        optimizer_config=OptimizerConfig(population_size=3,max_iterations=1,workers=1)
        ranking_inputs=[]
        def screen(net, baseline, eligible, sim, **kwargs):
            ranking_inputs.append(tuple(eligible))
            return (min(eligible),), [{'bus': min(eligible), 'rank':1, 'retained':True}], 0
        def yearly(net, pr, ev, fleet, **kwargs):
            n=len(fleet)
            score=[1000.,850.,700.][min(n,2)]
            return NS(steps=[NS()],completed=True,converged=True,feasible=True), NS(feasible=True,annual_total_cost=score)
        def screened(net, windows, stage_bounds, trial, cfg, **kwargs):
            candidate=BESSCandidate(stage_bounds.allowed_bus_ids[0],50.,500.)
            ev=CandidateEvaluation(candidate,100.,True)
            return OptimizationResult(candidate,100.,None,[100.],1,True,'test',[ev],{})
        def yearly_candidate(net, pr, ev, installed, candidate, **kwargs):
            stage=len(installed)+1
            score=(850. if stage==1 else 700.)
            group='trunk:2'
            return CandidateEvaluation(candidate,score,True,
                execution_metadata={'technical_check': {
                   'acceptable': True, 'reason': 'mock technical pass',
                   'target': group, 'shedding_improvement_percent': 15.,
                   'voltage_improvement_percent': 11.}})
        with patch('src.sequential_multi.annual_fleet',side_effect=yearly),\
             patch('src.sequential_multi.screen_buses',side_effect=screen),\
             patch('src.sequential_multi.representative_lateral_windows',return_value=[[0,1]]),\
             patch('src.sequential_multi.summarize_laterals',return_value={}),\
             patch('src.sequential_multi.balanced_shortlist',side_effect=lambda net, evidence, remaining, **kw:(min(remaining),)),\
             patch('src.sequential_multi._reference_window_metrics',return_value=(1.,1.)),\
             patch('src.sequential_multi._probe_lateral_candidates',return_value=[]),\
             patch('src.sequential_multi.optimize',side_effect=screened),\
             patch('src.sequential_multi._full_year_candidate',side_effect=yearly_candidate):
            result, baseline, selected=optimize_sequential_multi(network,profiles,bounds,evaluator,
                                                                  optimizer_config,max_units=3,finalists_per_stage=1)
        self.assertEqual(ranking_inputs,[(2,3),(3,)])
        self.assertEqual([c['bus_id'] for c in result.metadata['fleet']],[2,3])
        self.assertEqual(result.metadata['installed_bess_count'],2)
        self.assertEqual(result.metadata['stages'][1]['candidate_count'],1)
        self.assertTrue(result.success)
        self.assertEqual(result.best_objective,700.)

    def test_gui_and_dashboard_fleet_outputs_present(self):
        ui=(ROOT/'src/assets/settings_dialog.ui').read_text()
        self.assertIn('spin_bess_units',ui)
        self.assertIn('>3</number>',ui)
        for file, expected in [('src/results.py','fleet_hourly.csv'),
                               ('src/results.py','sequential_stages.csv'),
                               ('src/assets/dashboard.js','Battery SOC per installation'),
                               ('src/ui_workflow.py','optimize_sequential_multi')]:
            self.assertIn(expected,(ROOT/file).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
