"""Exercise post-GA verification order and acceptance without solving a year."""
from types import SimpleNamespace

import pandas as pd
import pytest

from src import fleet_ga_optimizer, representative_days, sequential_multi
from src.fleet_ga_optimizer import FleetEvaluation
from src.metrics import EconomicConfig
from src.optimizer import BESSCandidate, OptimizationBounds, OptimizerConfig
from src.planning_policy import effective_joint_search
from src.simulation import SimulationConfig
from tests.test_fleet_dispatch_backend import _four_bus_radial_case


@pytest.mark.parametrize(("eligible_count", "outcomes", "expected_attempts", "accepted_rank"), [
    (30, ["accepted"], 1, 1),
    (30, ["infeasible", "accepted"], 2, 2),
    (30, ["incomplete", "infeasible", "expensive", "accepted"], 4, 4),
    (30, ["expensive"] * 9 + ["accepted"], 10, 10),
    (30, ["expensive"] * 10, 10, None),
    (6, ["expensive"] * 6, 6, None),
    (30, ["within_tolerance", "accepted"], 2, 2),
    (0, [], 0, None),
])
def test_joint_annual_verification(monkeypatch, eligible_count, outcomes, expected_attempts, accepted_rank):
    network, _ = _four_bus_radial_case(days=1)
    profiles = SimpleNamespace(timestamps=pd.date_range("2021-01-01", periods=8760, freq="h"), dt_hours=1.)
    bounds = OptimizationBounds((2, 3, 4), (100.,), tuple(float(n) for n in range(200, 240)))
    evaluator = SimpleNamespace(
        economic_config=EconomicConfig(grid_import_tariff_per_kwh=.1, grid_export_tariff_per_kwh=0.),
        simulation_config=SimulationConfig(fleet_dispatch_mode="daily_milp_dispatch"),
    )
    config = OptimizerConfig(population_size=12, max_iterations=20, workers=2, seed=42)
    ga_candidates = [
        FleetEvaluation((BESSCandidate(2, 100., energy),), float(i), True)
        for i, energy in enumerate(bounds.energy_capacities_kwh)
    ]
    # Higher-ranked invalid entries and a duplicate must not take a shortlist slot.
    ranked = [FleetEvaluation((), 0., True), FleetEvaluation((BESSCandidate(3, 100., 200.),), .1, False),
              ga_candidates[0], *ga_candidates]
    scenarios = SimpleNamespace(total_days=365, days=range(12), total_screened_hours=288, metadata=dict)
    baseline_result = SimpleNamespace(dispatch_timing={"no_bess_cache_hit": True})
    baseline_metrics = SimpleNamespace(annual_total_cost=100., feasible=True)
    attempts, messages = [], []

    def run_ga(*args, **kwargs):
        ga_config = kwargs["ga_config"]
        assert (ga_config.seed, ga_config.workers, ga_config.max_generations) == (42, 2, 20)
        return {"ranked": ranked, "history": [1.], "stop_reason": "stall_generation_limit",
                "generations": 9, "unique_evaluated": 42, "visited_bus_ids": [2, 3],
                "elapsed_seconds": 1., "config": {}}

    def screen(*args, max_days):
        pool = args[3]
        assert max_days == 6
        assert pool == ga_candidates[:30]
        return pool[:eligible_count], [], ()

    def verify(_network, annual_profiles, _evaluator, fleet):
        assert annual_profiles is profiles
        outcome = outcomes[len(attempts)]
        cost = {"accepted": 90., "expensive": 110., "within_tolerance": 100. - 5e-7}.get(outcome, 90.)
        result = SimpleNamespace(message="voltage limit exceeded" if outcome == "infeasible" else "finished")
        metrics = SimpleNamespace(annual_total_cost=cost, feasible=outcome != "infeasible")
        complete = outcome != "incomplete"
        coverage = {"complete": complete, "status": "complete_annual" if complete else "incomplete_annual",
                    "processed_hours": 8760 if complete else 8759, "expected_hours": 8760}
        attempts.append((fleet, result))
        return fleet, result, metrics, coverage

    monkeypatch.setattr(representative_days, "build_kmeans_scenarios", lambda *args, **kw: scenarios)
    monkeypatch.setattr(fleet_ga_optimizer, "run_joint_fleet_ga", run_ga)
    monkeypatch.setattr(sequential_multi, "_stress_screen_fleets", screen)
    monkeypatch.setattr(sequential_multi, "_verify_fleet_annual", verify)
    monkeypatch.setattr(sequential_multi, "annual_fleet", lambda *args: (baseline_result, baseline_metrics))
    monkeypatch.setattr(sequential_multi, "summarize_laterals", lambda *args, **kw: {})

    assert effective_joint_search({}).annual_fallbacks == 10
    result, baseline, selected = sequential_multi.optimize_sequential_multi(
        network, profiles, bounds, evaluator, config, stage=messages.append)

    assert baseline is baseline_result
    assert result.metadata["annual_verification_fallback_budget"] == 10
    assert result.metadata["annual_fleet_simulations"] == expected_attempts
    assert result.metadata["stages"][0]["annual_finalists_screened"] == min(10, eligible_count)
    assert [fleet for fleet, _ in attempts] == [candidate.fleet for candidate in ga_candidates[:expected_attempts]]
    assert messages.index(next(msg for msg in messages if msg.startswith("Joint GA stopped"))) < messages.index(
        "SESS independent stress screen: up to 30 candidate fleets")
    if accepted_rank is None:
        assert selected is baseline_result
        assert result.metadata["no_bess_selected"]
        assert any("exhausted" in message and "No-BESS retained" in message for message in messages)
    else:
        assert selected is attempts[accepted_rank - 1][1]
        assert result.best_objective == 90.
        assert any(f"Annual finalist {accepted_rank}/" in message and "accepted" in message for message in messages)
        assert "Adaptive annual verification stopped: acceptable BESS fleet found" in messages
    if "infeasible" in outcomes:
        assert any("voltage limit exceeded" in message for message in messages)
    if "incomplete" in outcomes:
        assert any("8759/8760 hours" in message for message in messages)
    if "expensive" in outcomes:
        assert any("110.00 vs No-BESS 100.00 USD/year" in message for message in messages)
