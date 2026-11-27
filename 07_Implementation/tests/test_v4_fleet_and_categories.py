from dataclasses import replace

import pandas as pd
import pytest

from src.bess import BESSConfig
from src.dashboard_series import csv_series, load_categories
from src.data_loader import ProfileData
from src.fbs import FBSConfig
from src.manual_fleet import manual_rows, validate_manual_fleet
from src.metrics import EconomicConfig, with_terminal_policy
from src.network_model import Bus, Line, Load, NetworkModel, PVUnit
from src.optimizer import BESSParameters, OptimizationBounds, OptimizerConfig, SimulationEvaluator
from src.sequential_multi import optimize_sequential_multi
from src.simulation import ConstraintAwareDispatch, SimulationConfig
from src.ui_workflow import PreparedStudy, RunSettings, run_study


def case(hours):
    buses = tuple(range(2, 6))
    network = NetworkModel([Bus(1, "Slack", 12.66, True), *(Bus(b, f"B{b}", 12.66) for b in buses)],
                           [Line(str(b), 1, b, .08, .04) for b in buses],
                           [Load(f"L{b}", b, 15., 2.) for b in buses],
                           [PVUnit(f"PV{b}", b, 30.) for b in buses], 100000., 60.)
    stamps = pd.date_range("2021-01-01", periods=hours, freq="h")
    zero = [0.] * hours
    p = [15. if 17 <= stamp.hour < 21 else 6. for stamp in stamps]
    pv = [30. if 10 <= stamp.hour < 15 else 0. for stamp in stamps]
    profiles = ProfileData.from_arrays(stamps, {1: zero, **{b: p for b in buses}},
                                       {1: zero, **{b: [2.] * hours for b in buses}},
                                       {1: zero, **{b: pv for b in buses}},
                                       {b: zero for b in (1, *buses)})
    cfg = SimulationConfig(fleet_dispatch_mode="daily_milp_dispatch",
                           grid_export_limit_kw=0., fbs_config=FBSConfig(backend="numba"))
    economics = EconomicConfig(cost_per_kwh=.1, cost_per_kw=.1, grid_import_tariff_per_kwh=.2,
                               grid_export_tariff_per_kwh=0., curtailment_penalty_per_kwh=.01)
    return network, profiles, cfg, economics


def test_legacy_single_and_four_manual_units_use_coupled_workflow():
    network, profiles, cfg, economics = case(24)
    study = PreparedStudy(network, profiles, None, {})
    # Workflow information reads the request sources.
    from src.ui_workflow import DataRequest
    from pathlib import Path
    study.request = DataRequest(Path("fixture.xlsx"), None, "auto", None, 1, "power", load_source="imported")
    units = tuple(BESSConfig(bus, 9., 3., .1, .9, .5, .92, .92) for bus in range(2, 6))
    initial = RunSettings(cfg, economics, units[0], {})
    legacy = run_study(study, initial)
    single = run_study(study, replace(initial, manual_bess=None, manual_bess_fleet=units[:1]))
    assert legacy.context["Manual BESS"] == single.context["Manual BESS"]
    assert [step.power_flow.slack_p_kw for step in legacy.result.steps] == [
        step.power_flow.slack_p_kw for step in single.result.steps]
    result = run_study(study, replace(initial, manual_bess=None, manual_bess_fleet=units))
    assert result.context["Fleet count"] == 4
    assert "Manual BESS" not in result.context
    assert result.result.feasible
    assert result.metrics.bess_cost == pytest.approx(4.8)
    for step in result.result.steps:
        assert set(step.fleet_states) == {2, 3, 4, 5}
        assert sum(event.actual_power_kw for event in step.fleet_steps.values()) == pytest.approx(
            sum(step.operating_point.p_bess_kw.values()))


@pytest.mark.parametrize(("edit", "message"), [
    ({"bus_id": 1}, "non-slack"), ({"bus_id": 99}, "non-slack"),
    ({"power_kw": "NaN"}, "finite positive"), ({"energy_kwh": -1}, "finite positive"),
    ({"power_kw": 0}, "finite positive"), ({"energy_kwh": 1}, "duration"),
])
def test_manual_legacy_rows_and_invalid_ratings(edit, message):
    values = {"group_manual_bess": True, "bess_bus": 2, "spin_bess_power_kw": 3, "spin_bess_energy_kwh": 9,
              "spin_opt_duration_min_hours": 2., "spin_opt_duration_max_hours": 5.}
    assert validate_manual_fleet(values, {2}, BESSParameters(.9, .9))[0].energy_capacity_kwh == 9
    row = manual_rows(values)[0]
    values["manual_bess_rows"] = [{**row, **edit}]
    with pytest.raises(ValueError, match="row 1.*" + message):
        validate_manual_fleet(values, {2}, BESSParameters(.9, .9))


@pytest.mark.parametrize("maximum", [1, 2, 3, 4])
def test_coupled_ga_annual_fleet_limits(maximum):
    network, profiles, cfg, economics = case(8760)
    evaluator = SimulationEvaluator(economics, BESSParameters(.92, .92, .1, .9, .5),
                                    ConstraintAwareDispatch(), with_terminal_policy(cfg, economics))
    bounds = OptimizationBounds((2, 3, 4, 5), (3.,), (9.,), min_duration_hours=3., max_duration_hours=3.)
    config = OptimizerConfig(population_size=8, max_iterations=4, seed=27, workers=1)
    if maximum == 4:
        with pytest.raises(ValueError, match="Enable experimental"):
            optimize_sequential_multi(network, profiles, bounds, evaluator, config, max_units=maximum)
    result, baseline, selected = optimize_sequential_multi(
        network, profiles, bounds, evaluator, config, max_units=maximum,
        experimental_multi_bess=maximum == 4, finalists_per_stage=1)
    assert len(baseline.steps) == len(selected.steps) == 8760
    meta = result.metadata
    assert meta["experimental_enabled"] == (maximum == 4)
    assert meta["requested_max_units"] == maximum
    assert meta["selected_fleet_count"] <= maximum
    if maximum == 4:
        checked = meta["stages"][0]["full_year_candidates"]
        assert any(row["unit_count"] == 4 and row["annual_processed_hours"] == 8760 and row["feasible"] for row in checked)
        assert meta["selected_fleet_count"] == 4
        assert set(selected.final_fleet_states) == {2, 3, 4, 5}


def test_category_aggregation_counts_only_complete_unique_bus_samples(tmp_path):
    path = tmp_path / "load.csv"
    path.write_text("timestamp,bus_id,p_kw,q_kvar\na,1,5,2\na,2,6,3\na,3,2,1\na,4,0,0\n"
                    "b,1,5,2\nb,1,5,2\nb,3,2,1\nb,4,1,0\n"
                    "c,1,5,2\nc,2,6,3\nc,3,2,1\nc,4,0,0\n")
    categories = load_categories({1: " Residential ", 2: "RESIDENTIAL", 3: "Total"}, ["1", "2", "3", "4"])
    blocks = []

    def add(block):
        blocks.append(block)
        return len(blocks) - 1

    data = csv_series(path, "bus_id", {"a": 0, "b": 1, "c": 2}, add, categories=categories, aggregate=True)
    assert data["categories"]["category:total"]["source_defined"]
    assert data["categories"]["unclassified"]["buses"] == ["4"]

    def values(entity, field):
        return blocks[data["entities"][entity][0][2]][1][field]

    assert values("Total", "p_kw") == [13., None, 13.]
    assert values("residential", "q_kvar") == [5., None, 5.]
    assert values("unclassified", "p_kw") == [0., 1., 0.]
