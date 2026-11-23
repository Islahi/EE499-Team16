"""V15.5 tests: full allowed-bus search, strict economics and staged verification.

The validation covers individual operations and short representative scenarios;
it does not substitute for the user's 8760-hour Windows verification.
"""
import inspect
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from src.constraint_dispatch import ConstraintAwareDispatch
from src.metrics import EconomicConfig, annual_capital_recovery_factor
from src.optimizer import BESSCandidate, BESSParameters, OptimizationBounds, SimulationEvaluator
from src.simulation import SimulationConfig
from src.fleet_ga_optimizer import (FleetGAConfig, FleetEvaluation,
                                      evaluate_fleet_on_scenarios, run_joint_fleet_ga)
from src.representative_days import build_kmeans_scenarios
from src.sequential_multi import (_optimize_joint_fleet,
    _select_diverse_fleet_finalists, _stress_screen_fleets)
from tests.test_fleet_dispatch_backend import _four_bus_radial_case


def evaluator():
    ec=EconomicConfig(cost_per_kwh=200.,cost_per_kw=175.,power_cost_basis='kva',
        inverter_kva_per_kw=1/.95,annualization_method='real_crf',
        nominal_interest_rate=.05,annual_inflation_rate=.01,
        grid_import_tariff_per_kwh=.10,grid_export_tariff_per_kwh=0.)
    return SimulationEvaluator(ec,BESSParameters(.95,.95),ConstraintAwareDispatch(),
        SimulationConfig(fleet_dispatch_mode='daily_milp_dispatch',minimum_discharge_pf=.95))


class ExpandedSESSUnitTests(unittest.TestCase):
    def test_joint_fleet_path_has_no_initial_ranking_or_lateral_shortlist(self):
        source=inspect.getsource(_optimize_joint_fleet)
        self.assertNotIn('screen_buses(',source)
        self.assertNotIn('balanced_shortlist(',source)
        self.assertIn('sites = list(bounds.allowed_bus_ids)',source)
        self.assertIn('ga_bounds = bounds',source)
        self.assertIn('annual_early_stop_after_first_accepted',source)
        self.assertIn('independent_stress_days',source)

    def test_annual_candidates_are_best_first_without_force_fleet_count(self):
        a=BESSCandidate(2,100,300)
        b=BESSCandidate(3,100,300)
        c=BESSCandidate(4,100,300)
        ranked=[FleetEvaluation((a,b,c),10,True),FleetEvaluation((a,),11,True),
                FleetEvaluation((a,b),12,True)]
        selected=_select_diverse_fleet_finalists(ranked,2)
        self.assertEqual([x.objective for x in selected],[10,11])

    def test_daily_milp_ga_screening_uses_same_kva_and_crf_as_annual(self):
        net,profiles=_four_bus_radial_case(days=2)
        e=evaluator()
        scenarios=build_kmeans_scenarios(profiles,n_clusters=2,seed=7)
        fleet=(BESSCandidate(3,100,300),)
        result=evaluate_fleet_on_scenarios(net,scenarios,e,fleet)
        expected_initial=200*300+175*(100/.95)
        expected_annual=expected_initial*(annual_capital_recovery_factor(e.economic_config)+.02)
        self.assertAlmostEqual(result.annual_fixed_cost,expected_annual,places=5)

    def test_extreme_day_screen_excludes_training_medoids(self):
        net,profiles=_four_bus_radial_case(days=9)
        scenarios=build_kmeans_scenarios(profiles,n_clusters=2,seed=23)
        ev=FleetEvaluation((BESSCandidate(3,100,300),),10.,True)
        _,records,days=_stress_screen_fleets(net,profiles,evaluator(),[ev],scenarios,max_days=4)
        self.assertGreaterEqual(len(days),1)
        self.assertTrue(set(days).isdisjoint({d.day_index for d in scenarios.days}))
        self.assertLessEqual(len(days),4)
        self.assertTrue(all(record['hours']==24 for record in records))

    def test_ga_search_includes_all_bus_choices_without_rank_filter(self):
        net,profiles=_four_bus_radial_case(days=2)
        bounds=OptimizationBounds((2,3,4),(100.,150.),(300.,450.))
        scenarios=build_kmeans_scenarios(profiles,n_clusters=2,seed=7)
        out=run_joint_fleet_ga(net,scenarios,bounds,evaluator(),max_units=1,
            ga_config=FleetGAConfig(population_size=5,max_generations=2,
                                    stall_generation_limit=2,workers=1,seed=2),
            bus_order=(2,3,4))
        self.assertGreaterEqual(out['unique_evaluated'],5)
        tested={u.bus_id for ev in out['ranked'] for u in ev.fleet}
        self.assertTrue(tested.issubset({2,3,4}))
        self.assertGreaterEqual(len(tested),2)

    def test_dashboard_references_kva_and_stress_stage(self):
        js=(ROOT/'src/assets/dashboard.js').read_text(encoding='utf-8')
        self.assertIn('Inverter S (kVA)',js)
        self.assertIn('Installed inverter capacity',js)
        self.assertIn('Search and annual verification',js)
        self.assertIn('BESS inverter apparent power (kVA)',js)
        source=(ROOT/'src/results.py').read_text(encoding='utf-8')
        self.assertIn('inverter_rating_kva',source)


    def test_joint_ga_internal_tuning_reaches_existing_route(self):
        from src.planning_policy import joint_search_policy
        policy = joint_search_policy(32)
        self.assertEqual((policy.crossover,policy.mutation,policy.generations),(0.8,0.2,20))
        workflow=(ROOT/'src/ui_workflow.py').read_text(encoding='utf-8')
        route=(ROOT/'src/sequential_multi.py').read_text(encoding='utf-8')
        self.assertIn("settings.managed_search and joint_sess",workflow)
        self.assertIn("crossover, mutation = policy.crossover, policy.mutation",workflow)
        self.assertIn("crossover_rate=ga_crossover_rate, mutation_rate=ga_mutation_rate",route)


if __name__=='__main__':unittest.main()
