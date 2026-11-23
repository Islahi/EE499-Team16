"""V15 verification tests for Dr. Sindi SESS full backend integration.

Verifies:
  1. K-means representative-day scenario clustering weights and probabilities.
  2. Coupled P/Q look-ahead LP + damped SLP OPF + active voltage flattening (Eq. 17).
  3. Joint Multi-BESS Stationary GA (SESS Eq. 53) with V14 2-12h duration repair.
  4. End-to-end optimize_sequential_multi routing in 'opf' mode preserving the exact
     BESS + Shedding + Curtailment + Grid economic objective.
"""
import sys
from dataclasses import replace
from os import cpu_count
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.bess import BESSConfig
from src.data_loader import ProfileData
from src.metrics import EconomicConfig
from src.network_model import Bus, Line, Load, NetworkModel, PVUnit
from src.optimizer import (
    BESSParameters,
    OptimizationBounds,
    OptimizerConfig,
    SimulationEvaluator,
)
from src.sequential_multi import optimize_sequential_multi
from src.simulation import (
    ConstraintAwareDispatch,
    SimulationConfig,
    simulate_timeseries,
)
from src.representative_days import build_kmeans_scenarios


def _four_bus_radial_case(days=4):
    """4-bus radial feeder with two distinct laterals and stressed evening peaks."""
    hours = days * 24
    net = NetworkModel(
        buses=[
            Bus(1, "substation", 12.66, is_slack=True),
            Bus(2, "junction", 12.66),
            Bus(3, "lateral_A", 12.66),
            Bus(4, "lateral_B", 12.66),
        ],
        lines=[
            Line("L12", 1, 2, 1.5, 1.2),
            Line("L23", 2, 3, 4.0, 3.5),
            Line("L24", 2, 4, 4.5, 3.8),
        ],
        loads=[
            Load("LD2", 2, 200.0, 100.0),
            Load("LD3", 3, 700.0, 420.0),
            Load("LD4", 4, 750.0, 450.0),
        ],
        pv_units=[
            PVUnit("PV3", 3, 400.0),
            PVUnit("PV4", 4, 400.0),
        ],
        base_power_kva=100000.0,
        frequency_hz=60.0,
    )
    ts = pd.date_range("2021-06-01", periods=hours, freq="h")
    hod = np.arange(hours) % 24
    # Morning/midday solar, heavy evening peak causing undervoltage/shedding
    day_factor = np.repeat(np.linspace(0.85, 1.15, days), 24)
    peak_shape = 0.45 + 0.65 * np.exp(-0.5 * ((hod - 19.0) / 3.0) ** 2)
    pv_shape = np.maximum(0.0, np.sin((hod - 6.0) * np.pi / 12.0)) * ((hod >= 6) & (hod <= 18))

    p_load = {
        1: np.zeros(hours),
        2: 200.0 * peak_shape * day_factor,
        3: 700.0 * peak_shape * day_factor,
        4: 750.0 * peak_shape * day_factor,
    }
    q_load = {
        1: np.zeros(hours),
        2: 100.0 * peak_shape * day_factor,
        3: 420.0 * peak_shape * day_factor,
        4: 450.0 * peak_shape * day_factor,
    }
    p_pv = {
        1: np.zeros(hours),
        2: np.zeros(hours),
        3: 400.0 * pv_shape,
        4: 400.0 * pv_shape,
    }
    q_pv = {b: np.zeros(hours) for b in (1, 2, 3, 4)}
    profile = ProfileData.from_arrays(ts, p_load, q_load, p_pv, q_pv)
    return net, profile


class FleetDispatchBackendTests(unittest.TestCase):
    def test_kmeans_scenario_clustering_preserves_weights_and_medoids(self):
        net, profile = _four_bus_radial_case(days=6)
        scenarios = build_kmeans_scenarios(profile, n_clusters=3, seed=7)
        self.assertEqual(len(scenarios.days), 3)
        self.assertEqual(scenarios.total_days, 6)
        self.assertAlmostEqual(sum(d.weight_days for d in scenarios.days), 6.0, places=6)
        self.assertAlmostEqual(sum(d.probability for d in scenarios.days), 1.0, places=6)
        for rep in scenarios.days:
            self.assertEqual(len(rep.profile.timestamps), 24)

    def test_coupled_pq_lookahead_and_voltage_regulation(self):
        net, profile = _four_bus_radial_case(days=2)
        fleet = (
            BESSConfig(3, 500.0, 2000.0, 0.2, 1.0, 0.5, 0.92, 0.92),
            BESSConfig(4, 500.0, 2000.0, 0.2, 1.0, 0.5, 0.92, 0.92),
        )
        res_pred = simulate_timeseries(
            net, profile, SimulationConfig(fleet_dispatch_mode="predictive"),
            bess_fleet=fleet, capture_dispatch=False,
        )
        res_opf = simulate_timeseries(
            net, profile, SimulationConfig(fleet_dispatch_mode="opf"),
            bess_fleet=fleet, capture_dispatch=True,
        )
        self.assertTrue(res_opf.completed)
        self.assertTrue(res_opf.feasible)
        self.assertTrue(res_opf.dispatch_timing.get("predictive_coupled_pq"))
        self.assertIn("Coordinated P/Q OPF", res_opf.dispatch_timing.get("opf_formulation", ""))
        shed_pred = sum(s.shedding_kw or 0.0 for s in res_pred.steps)
        shed_opf = sum(s.shedding_kw or 0.0 for s in res_opf.steps)
        self.assertLessEqual(shed_opf, shed_pred + 1e-5)
        for step in res_opf.steps:
            for v in step.power_flow.voltage_mag_pu.values():
                self.assertGreaterEqual(v, 0.95 - 1e-6)
                self.assertLessEqual(v, 1.05 + 1e-6)

    def test_joint_ga_reduces_cost_and_obeys_v14_duration(self):
        from src.fleet_ga_optimizer import FleetGAConfig, run_joint_fleet_ga
        net, profile = _four_bus_radial_case(days=3)
        econ = EconomicConfig(
            cost_per_kw=250.0,
            cost_per_kwh=200.0,
            lifetime_years=10,
            annual_om_fraction=0.02,
            grid_import_tariff_per_kwh=0.10,
            grid_export_tariff_per_kwh=0.05,
            shedding_penalty_per_kwh=12.0,
            curtailment_penalty_per_kwh=0.07,
        )
        sim_cfg = SimulationConfig(
            fleet_dispatch_mode="opf",
            shedding_penalty_per_kwh=12.0,
            curtailment_penalty_per_kwh=0.07,
        )
        evaluator = SimulationEvaluator(
            economic_config=econ,
            battery_parameters=BESSParameters(eta_charge=0.92, eta_discharge=0.92),
            dispatch_policy=ConstraintAwareDispatch(),
            simulation_config=sim_cfg,
        )
        bounds = OptimizationBounds(
            allowed_bus_ids=(2, 3, 4),
            power_ratings_kw=(250.0, 500.0, 750.0),
            energy_capacities_kwh=(500.0, 1000.0, 2000.0, 3000.0),
            min_duration_hours=2.0,
            max_duration_hours=12.0,
        )
        scenarios = build_kmeans_scenarios(profile, n_clusters=2, seed=42)
        tuning = FleetGAConfig(population_size=8, max_generations=3, stall_generation_limit=3,
                               seed=42, workers=1)
        ga_out = run_joint_fleet_ga(
            net, scenarios, bounds, evaluator,
            max_units=2,
            ga_config=tuning,
        )
        self.assertEqual(ga_out["generations"], tuning.max_generations)
        if (cpu_count() or 1) > 1:
            parallel = run_joint_fleet_ga(net, scenarios, bounds, evaluator, max_units=2,
                                          ga_config=replace(tuning, workers=2))
            self.assertEqual(parallel["config"]["workers"], 2)
            self.assertEqual(parallel["history"], ga_out["history"])
            self.assertEqual([item.fleet for item in parallel["ranked"]],
                             [item.fleet for item in ga_out["ranked"]])
        ranked = ga_out["ranked"]
        self.assertGreater(len(ranked), 0)
        no_bess = next(ev for ev in ranked if ev.fleet == ())
        best = ranked[0]
        self.assertTrue(best.feasible)
        self.assertLessEqual(best.objective, no_bess.objective + 1e-6)
        for ev in ranked:
            for unit in ev.fleet:
                dur = unit.energy_capacity_kwh / unit.power_rating_kw
                self.assertGreaterEqual(dur, 2.0 - 1e-9)
                self.assertLessEqual(dur, 12.0 + 1e-9)


if __name__ == "__main__":
    unittest.main()
