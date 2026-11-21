"""Electrical and stored-output regression tests for the rolling dispatch."""
from dataclasses import replace
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from src_accelerated.bess import BESSConfig
from src_accelerated.data_loader import ProfileData, profile_at
from src_accelerated.fbs import OperatingPoint, run_fbs
from src_accelerated.metrics import EconomicConfig
from src_accelerated.network_loader import load_network
from src_accelerated.network_model import Bus, Line, Load, NetworkModel, PVUnit
from src_accelerated.optimizer import BESSParameters, OptimizationBounds, OptimizerConfig, SimulationEvaluator, optimize
from src_accelerated.simulation import ConstraintAwareDispatch, GridAwareDispatchPolicy, SimulationConfig, simulate_timeseries
from src_accelerated.ui_workflow import PreparedStudy, RunSettings, run_and_export


def feeder(r=0.03, ampacity=None):
    return NetworkModel([Bus(1, "Grid", 12.66, True), Bus(2, "Load", 12.66)],
                        [Line("L1", 1, 2, r, .02, ampacity)],
                        [Load("L2", 2, 100, 0)], [], 1000, 60)


def profiles(values, pv=None, start="2021-01-01"):
    times = pd.date_range(start, periods=len(values), freq="h")
    return ProfileData.from_arrays(times, {2: values}, {2: [0.] * len(times)},
                                   {2: pv or [0.] * len(times)}, {2: [0.] * len(times)})


def battery(**overrides):
    values = dict(bus_id=2, energy_capacity_kwh=160., power_rating_kw=60., soc_min=.1,
                  soc_max=.9, soc_initial=.25, eta_charge=.9, eta_discharge=.9)
    return BESSConfig(**{**values, **overrides})


def test_lookahead_moves_energy_from_calm_hours_to_import_and_voltage_stress():
    network = feeder(r=51.)
    data = profiles([20.] * 17 + [210.] * 2 + [20.] * 17)
    settings = SimulationConfig(reserve_fraction=0, grid_import_limit_kw=100)
    policy = ConstraintAwareDispatch(.1, 0.)
    baseline = simulate_timeseries(network, data, settings)
    previous = simulate_timeseries(network, data, settings, battery(), GridAwareDispatchPolicy())
    run = simulate_timeseries(network, data, settings, battery(), policy)
    assert run.completed and run.feasible
    assert any(step.bess_step.actual_power_kw < 0. for step in run.steps[:17])
    assert not any(step.bess_step.actual_power_kw > 0. for step in run.steps[:17])
    for index in (17, 18):
        step = run.steps[index]
        event = step.dispatch
        assert event.pre.minimum_pu < settings.voltage_min_pu
        assert event.after_bess.minimum_pu > event.pre.minimum_pu
        assert step.shedding_kw < baseline.steps[index].shedding_kw
        assert step.shedding_kw < previous.steps[index].shedding_kw
        assert event.final.minimum_pu == min(step.power_flow.voltage_mag_pu.values())
        assert event.accepted_kw == step.operating_point.p_bess_kw[2]
        assert event.final.import_kw == step.power_flow.slack_p_kw
    for step in run.steps:
        power = step.bess_step.actual_power_kw
        energy = step.bess_step.energy_before_kwh - (power / .9 if power > 0 else power * .9)
        assert step.bess_state.energy_kwh == pytest.approx(energy)
    assert run.steps[0].dispatch.horizon_hours == 24
    assert run.steps[-1].dispatch.horizon_hours == 1
    assert run.dispatch_timing["dispatch_fbs_trials"] >= len(data.timestamps)


def test_reserve_and_terminal_limits_are_enforced():
    data = profiles([99.8] * 23 + [140.])
    settings = SimulationConfig(reserve_fraction=0, grid_import_limit_kw=100., terminal_soc_tolerance=1e-6)
    options = ConstraintAwareDispatch(.1, 0.)
    locked = battery(soc_initial=.9, soc_max=.9)
    run = simulate_timeseries(feeder(), data, settings, locked, options)
    last = run.steps[-1]
    assert last.dispatch.pre.violations["import"] > 0
    assert last.dispatch.accepted_kw == pytest.approx(0.)
    assert last.shedding_kw > 0
    assert abs(last.bess_state.soc - locked.soc_initial) <= settings.terminal_soc_tolerance
    assert "terminal_soc" in last.dispatch.reason_codes
    reserve = replace(settings, reserve_fraction=.5)
    result = simulate_timeseries(feeder(), data, reserve, locked, options)
    assert not result.feasible
    assert "reserve" in result.steps[-1].dispatch.reason_codes
    assert result.steps[-1].reserve_power_shortfall_kw > 0


def test_unresolvable_limits_and_unpriced_charging():
    data = profiles([130.] * 26)
    settings = SimulationConfig(reserve_fraction=0, grid_import_limit_kw=99., allow_load_shedding=False)
    run = simulate_timeseries(feeder(ampacity=4.), data, settings, battery(soc_initial=.1),
                             ConstraintAwareDispatch())
    assert not run.feasible
    assert run.steps[0].dispatch.final.violations
    assert run.steps[0].shedding_kw == 0.
    assert run.steps[0].dispatch.accepted_kw == 0.
    assert "no_energy" in run.steps[0].dispatch.reason_codes
    assert "ampacity:L1" in run.steps[0].dispatch.pre.violations
    calm = simulate_timeseries(feeder(), profiles([40.] * 24 + [130.]), settings,
                              battery(soc_initial=.1), ConstraintAwareDispatch())
    assert "no_charge_headroom" in calm.steps[2].dispatch.reason_codes
    assert not any(step.dispatch.accepted_kw < 0. for step in calm.steps)


def test_pv_absorption_precedes_residual_curtailment():
    network = replace(feeder(), pv_units=[PVUnit("PV", 2, 100)])
    data = profiles([10.], [100.])
    settings = SimulationConfig(reserve_fraction=0, grid_export_limit_kw=0.)
    before = simulate_timeseries(network, data, settings).steps[0]
    after = simulate_timeseries(network, data, settings, battery(), ConstraintAwareDispatch()).steps[0]
    assert after.dispatch.pre.export_kw > 80
    assert after.dispatch.accepted_kw < 0.
    assert 0. < after.curtailment_kw < before.curtailment_kw
    assert after.dispatch.after_bess.export_kw > after.dispatch.final.export_kw


def test_terminal_closure_failure_when_all_later_discharge_is_blocked():
    network = replace(feeder(), pv_units=[PVUnit("PV", 2, 100)])
    data = profiles([0.] * 25, [100.] + [0.] * 24)
    settings = SimulationConfig(reserve_fraction=0, grid_export_limit_kw=0., terminal_soc_tolerance=1e-6)
    run = simulate_timeseries(network, data, settings, battery(), ConstraintAwareDispatch(.1, 0.))
    assert run.steps[0].dispatch.accepted_kw < 0.
    assert run.steps[1].dispatch.terminal_discharge_headroom_kwh == 0.
    assert run.completed and not run.feasible
    assert "Terminal SOC closure failed" in run.message
    assert "terminal_soc" in run.steps[-1].dispatch.reason_codes


def test_forecast_equal_cost_under_serial_and_spawned_gwo():
    data = profiles([40.] * 300 + [120., 130.] + [40.] * (8760 - 302))
    settings = SimulationConfig(reserve_fraction=0, grid_import_limit_kw=100.)
    costs = EconomicConfig(grid_import_tariff_per_kwh=.1, grid_export_tariff_per_kwh=0.)
    evaluator = SimulationEvaluator(costs, BESSParameters(.9, .9),
                                    ConstraintAwareDispatch(.1, 0., source="forecast inputs only"), settings)
    grid = OptimizationBounds((2,), (20., 40.), (150.,))
    first = optimize(feeder(), data, grid, evaluator, OptimizerConfig(3, 1, seed=42))
    second = optimize(feeder(), data, grid, evaluator, OptimizerConfig(3, 1, seed=42, workers=2))
    assert first.success and second.success
    assert first.best_candidate == second.best_candidate
    assert first.best_objective == pytest.approx(second.best_objective)
    assert second.metadata["worker_readiness"]
    assert {item.candidate: item.objective for item in first.evaluations} == pytest.approx(
        {item.candidate: item.objective for item in second.evaluations})


@pytest.fixture(scope="module")
def archive():
    location = os.environ.get("EE499_ARCHIVED_RUN")
    if not location:
        pytest.skip("EE499_ARCHIVED_RUN must point to the archived 2021 15-bus optimization run with inputs")
    root = Path(location) / "inputs"
    for name in ("network.xlsx", "load_profile.csv", "pv_profile.csv"):
        if not (root / name).is_file():
            pytest.skip(f"Archived 15-bus input missing: {root / name}")
    data = ProfileData(root / "load_profile.csv", root / "pv_profile.csv")
    network = load_network(root / "network.xlsx", frequency_hz=60)
    units = [PVUnit(f"PV{bus}", bus, max(values)) for bus, values in data.pv_p_kw.items() if max(values) > 0.]
    return replace(network, pv_units=units), data, root


def test_archived_peak_flow(archive):
    network, data, _ = archive
    hours = list(zip(*data.load_p_kw.values()))
    peak = max(range(len(hours)), key=lambda index: sum(hours[index]))
    end = data.timestamps[peak] + pd.Timedelta(hours=1)
    point = data.slice(data.timestamps[peak], end)
    settings = SimulationConfig(reserve_fraction=0, grid_import_limit_kw=2400, grid_export_limit_kw=0)
    baseline = simulate_timeseries(network, point, settings).steps[0]
    ranked = [simulate_timeseries(network, point, settings, battery(bus_id=bus.bus_id, power_rating_kw=400,
                  energy_capacity_kwh=1600, soc_initial=.8), ConstraintAwareDispatch(.1, 0.)).steps[0]
              for bus in network.buses if not bus.is_slack]
    assert all(step.dispatch.pre.minimum_pu == baseline.dispatch.pre.minimum_pu for step in ranked)
    best = min(ranked, key=lambda step: step.shedding_kw)
    sample = profile_at(point, 0)
    zeros = dict.fromkeys((bus.bus_id for bus in network.buses), 0.)
    injected = {**zeros, best.dispatch.bus_id: best.dispatch.accepted_kw}
    check = run_fbs(network, OperatingPoint(sample.p_load_kw, sample.q_load_kvar, sample.p_pv_kw,
                                          sample.q_pv_kvar, injected, zeros), settings.fbs_config)
    assert check.converged
    assert best.dispatch.after_bess.minimum_pu == pytest.approx(min(check.voltage_mag_pu.values()))
    assert best.shedding_kw <= baseline.shedding_kw
    if best.dispatch.accepted_kw:
        assert best.dispatch.after_bess.minimum_pu > best.dispatch.pre.minimum_pu
        assert best.shedding_kw < baseline.shedding_kw


def test_archived_annual_replay(archive, tmp_path):
    network, data, root = archive
    if len(data.timestamps) != 8760 or data.timestamps[0] != pd.Timestamp("2021-01-01"):
        pytest.skip("Archived input does not cover the complete 2021 study")
    study = PreparedStudy(network, data, None, {"Network": "Archived 15-bus 2021", "Clock": "UTC"})
    study.simulation_window = {"mode": "historical", "start": str(data.timestamps[0]), "hours": 8760}
    values = dict(allowed_buses=(2, 15), spin_eta_charge_percent=90, spin_eta_discharge_percent=90,
                  spin_soc_min_percent=20, spin_soc_max_percent=100, spin_soc_initial_percent=50,
                  spin_opt_power_min_kw=100, spin_opt_power_max_kw=100, spin_opt_power_step_kw=100,
                  spin_opt_energy_min_kwh=200, spin_opt_energy_max_kwh=200, spin_opt_energy_step_kwh=200,
                  spin_gwo_population=3, spin_gwo_iterations=1, spin_gwo_seed=42, spin_cpu_workers=2)
    settings = RunSettings(SimulationConfig(reserve_fraction=0, grid_import_limit_kw=2400, grid_export_limit_kw=0),
                           EconomicConfig(grid_import_tariff_per_kwh=.1, grid_export_tariff_per_kwh=0.), None, values)
    report = run_and_export(study, settings, True, tmp_path / "annual",
                            network_snapshot=root / "network.xlsx")
    assert report.result.metadata["no_bess_annual_cost"] == pytest.approx(29266147.66812243, rel=1e-8)
    assert report.result.metadata["best_bess_feasible"]
    assert "best_bess_replay_mismatch" not in report.result.metadata
    assert report.dashboard_path.is_file()
    replay, metrics = report.alternatives["best_bess"]
    assert metrics.annual_total_cost == pytest.approx(report.result.metadata["best_bess_annual_cost"])
    assert replay.completed and replay.feasible
    line = (report.dashboard_path.parent / "best_bess/dispatch_events.jsonl").open(encoding="utf-8")
    with line:
        row = json.loads(next(line))
    assert row["no_bess_shedding_kw"] is not None
    assert row["avoided_shedding_kw"] == pytest.approx(row["no_bess_shedding_kw"] - row["shedding_kw"])
    print("Annual replay:", report.result.message, report.result.metadata["no_bess_annual_cost"],
          metrics.annual_total_cost, replay.dispatch_timing)


@pytest.mark.parametrize("fixture", ["T12_33-Bus.xlsx", "T17_69-Bus.xlsx"])
def test_radial_fixtures(fixture):
    validation = Path(os.environ.get("EE499_VALIDATION_ROOT", Path(__file__).parents[1] / "Validation"))
    workbook = validation / "EE499_C1_Benchmark/C1_Simple_Test/Working_RDS" / fixture
    if not workbook.is_file():
        pytest.skip(f"Archived RDS fixture missing: {workbook}")
    network = load_network(workbook, frequency_hz=60)
    times = pd.date_range("2021-01-01", periods=24, freq="h")
    p = {bus.bus_id: [sum(load.p_base_kw for load in network.loads if load.bus_id == bus.bus_id) / 10] * 24
         for bus in network.buses}
    q = {bus.bus_id: [sum(load.q_base_kvar for load in network.loads if load.bus_id == bus.bus_id) / 10] * 24
         for bus in network.buses}
    data = ProfileData.from_arrays(times, p, q, {}, {})
    result = simulate_timeseries(network, data, SimulationConfig(reserve_fraction=0),
                                 battery(bus_id=network.buses[-1].bus_id))
    assert result.completed and result.converged
    assert len(result.steps[-1].power_flow.voltage_mag_pu) == len(network.buses)
