import base64
import csv
from dataclasses import replace
import gzip
import json
from pathlib import Path
import re
from unittest.mock import patch
from zipfile import ZipFile

import pandas as pd
import pytest

from src.bess import BESSConfig
from src.dashboard import package_dashboard, regenerate_dashboard
from src.data_loader import ProfileData, profile_at
from src.metrics import EconomicConfig
from src.network_model import Bus, Line, Load, NetworkModel, PVUnit
from src.progress import RunCancelled
from src.simulation import SimulationConfig, simulate_step, simulate_timeseries
from src.ui_workflow import DataRequest, PreparedStudy, RunSettings, run_and_export, run_study


def study_case(hours=24):
    network = NetworkModel(
        [Bus(1, "Slack", 12.66, True), Bus(2, "PV", 12.66), Bus(3, "Demand", 12.66)],
        [Line("rated", 1, 2, .08, .04, ampacity_a=7.), Line("unrated", 2, 3, .08, .04)],
        [Load("demand", 3, 20., 5.)], [PVUnit("solar", 2, 350.)], 100000., 60.)
    stamps = pd.date_range("2021-01-01", periods=hours, freq="h")
    zeros = [0.] * hours
    profiles = ProfileData.from_arrays(stamps, {1: zeros, 2: zeros, 3: [20.] * hours},
        {1: zeros, 2: zeros, 3: [5.] * hours}, {1: zeros, 2: [350.] * hours, 3: zeros},
        {1: zeros, 2: [10.] * hours, 3: zeros})
    study = PreparedStudy(network, profiles, DataRequest(None, 60., "auto", None, 1, "power", load_source="imported"),
                          {"Clock": "UTC"}, simulation_window={"start": str(stamps[0]),
                            "end_exclusive": str(stamps[-1]+pd.Timedelta(hours=1)), "hours": hours})
    settings = RunSettings(SimulationConfig(grid_export_limit_kw=50., fleet_dispatch_mode="daily_milp_dispatch"),
                           EconomicConfig(grid_import_tariff_per_kwh=.2, grid_export_tariff_per_kwh=.03), None, {})
    return study, settings


def batteries():
    return [BESSConfig(bus, 120., 30., .1, .9, .5, .92, .92) for bus in (2, 3)]


@pytest.mark.parametrize(("mode", "count"), [("daily_milp_dispatch", 2), ("opf", 0), ("predictive", 1)])
def test_uncontrolled_bypasses_all_controllers_and_keeps_prescribed_injections(mode, count):
    study, settings = study_case()
    cfg = replace(settings.simulation, fleet_dispatch_mode=mode, corrective_actions=False)
    units = tuple(batteries()[:count])
    with (
        patch("src.multi_bess.NetworkCorrector", side_effect=AssertionError("corrector called")),
        patch("src.simulation.NetworkCorrector", side_effect=AssertionError("legacy corrector called")),
        patch("src.multi_bess.VoltageSupport", side_effect=AssertionError("voltage support called")),
        patch("src.daily_milp_dispatch.DailyMILPPlanner", side_effect=AssertionError("MILP called")),
        patch("src.joint_opf.JointOPFController", side_effect=AssertionError("OPF called")),
        patch("src.lookahead_dispatch.DayAheadFleetPlanner", side_effect=AssertionError("look-ahead called")),
        patch("src.simulation.RollingDispatch", side_effect=AssertionError("rolling planner called")),
    ):
        series = simulate_timeseries(study.network, study.profiles, cfg,
                                     units[0] if count == 1 else None,
                                     bess_fleet=units if count > 1 else None)
        one = simulate_step(study.network, profile_at(study.profiles, 0), cfg.fbs_config, simulation_config=cfg)
    assert series.completed and series.converged and not series.feasible and len(series.steps) == 24
    assert not one.feasible
    for step in series.steps:
        point = step.operating_point
        assert point.p_pv_kw[2] == 350. and point.q_pv_kvar[2] == 10.
        assert point.p_load_kw[3] == 20. and point.q_load_kvar[3] == 5.
        assert step.curtailment_kw == step.shedding_kw == 0.
        assert sum(point.p_bess_kw.values()) == sum(point.q_bess_kvar.values()) == 0.
        assert step.dispatch.pre == step.dispatch.final
        assert {"export", "ampacity:rated"} <= step.dispatch.final.violations.keys()
        assert "ampacity:unrated" not in step.dispatch.final.violations
        assert step.correction.status == "disabled_by_study_policy"
    assert set(series.final_fleet_states) == {config.bus_id for config in units}
    assert all(state.soc == .5 and state.energy_kwh == 60. for state in series.final_fleet_states.values())


def readings(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_paired_export_regenerates_and_matches_independent_runs(tmp_path):
    study, settings = study_case()
    path = tmp_path / "pair"
    report = run_and_export(study, replace(settings, compare_corrective_actions=True), False, path)
    assert report.dashboard_path and not (path / "hourly.csv").exists()
    assert set(report.alternatives) == {"uncontrolled", "controlled"}
    for name, (result, metrics) in report.alternatives.items():
        independent = run_study(study, replace(settings, simulation=replace(settings.simulation,
                               corrective_actions=name == "controlled")))
        assert result.steps == independent.result.steps and metrics == independent.metrics
        assert len(readings(path / name / "hourly.csv")) == 24
    off, on = (report.alternatives[key][1] for key in ("uncontrolled", "controlled"))
    assert off.curtailment_energy_kwh == 0. and not off.feasible
    assert on.curtailment_energy_kwh > 0. and on.feasible
    ledger = (path / "uncontrolled" / "control_decisions.jsonl").read_text().splitlines()
    assert all(not (row := json.loads(line))["actions"] and row["reason_codes"] ==
               ["disabled_by_study_policy"] for line in ledger)
    html = regenerate_dashboard(path).read_text(encoding="utf-8")
    encoded = re.search(r'<script id="report-data"[^>]*>([^<]+)</script>', html)[1]
    payload = json.loads(gzip.decompress(base64.b64decode(encoded)))
    assert "time-navigator" not in html
    assert payload["scenarios"]["uncontrolled"]["comparison"]["export_violation_hours"] == 24
    assert payload["scenarios"]["controlled"]["comparison"]["overload_hours"] == 0
    assert payload["scenarios"]["controlled"]["descriptor"]["limits"] == payload["scenarios"]["uncontrolled"]["descriptor"]["limits"]
    assert payload["scenarios"]["uncontrolled"]["descriptor"]["dispatch_mode"] == "idle"
    assert payload["scenarios"]["uncontrolled"]["descriptor"]["processed_hours"] == 24
    with ZipFile(package_dashboard(path, tmp_path / "pair.zip")) as archive:
        assert archive.testzip() is None
        assert {"controlled/hourly.csv", "uncontrolled/hourly.csv", "inputs/load_profile.csv"} <= set(archive.namelist())


def test_unsolved_uncontrolled_hours_keep_inputs_and_idle_states(tmp_path):
    study, settings = study_case(3)
    from src.fbs import prepare_fbs
    solver = prepare_fbs(study.network, settings.simulation.fbs_config)
    count = 0

    def solve(point):
        nonlocal count
        count += 1
        flow = solver(point)
        return replace(flow, converged=False, message="Injected failure") if count == 2 else flow

    path = tmp_path / "failed"
    settings = replace(settings, simulation=replace(settings.simulation, corrective_actions=False),
                       manual_bess_fleet=tuple(batteries()))
    with patch("src.uncontrolled.prepare_fbs", return_value=solve):
        report = run_and_export(study, settings, False, path)
    assert report.result.completed and not report.result.converged
    assert report.metrics is None
    assert report.context["Scenario descriptors"]["."]["converged_hours"] == 2
    assert all(state.soc == .5 for state in report.result.final_fleet_states.values())
    failed = readings(path / "hourly.csv")[1]
    assert failed["fbs_message"] == "Injected failure"
    assert failed["requested_load_kw"] == "20.0"
    for field in ("voltage_min_pu", "slack_p_kw", "served_load_kwh", "shed_kwh", "curtailed_kwh"):
        assert failed[field] == ""


def test_cancelled_comparison_is_not_published(tmp_path):
    study, settings = study_case()
    path = tmp_path / "cancelled"

    def cancel_before_controlled(message):
        if message == "With corrective actions":
            raise RunCancelled

    with pytest.raises(RunCancelled):
        run_and_export(study, replace(settings, compare_corrective_actions=True), False, path, cancel_before_controlled)
    assert not path.exists()


def test_infeasible_full_year_uncontrolled_cost_is_diagnostic():
    study, settings = study_case(8760)
    settings.simulation = replace(settings.simulation, corrective_actions=False)
    report = run_study(study, settings)
    assert report.result.completed and report.result.converged and not report.result.feasible
    assert report.metrics.annual_total_cost is None
    assert report.metrics.annual_operating_cost is not None
    assert any("diagnostic" in note for note in report.metrics.notes)


@pytest.mark.parametrize("count", [1, 2])
def test_paired_manual_installations_keep_independent_soc_and_active_dispatch(count):
    study, settings = study_case()
    profiles = study.profiles
    study.profiles = ProfileData.from_arrays(
        profiles.timestamps, profiles.load_p_kw, profiles.load_q_kvar,
        {**profiles.pv_p_kw, 2: [350.] * 12 + [0.] * 12},
        {**profiles.pv_q_kvar, 2: [10.] * 12 + [0.] * 12})
    fleet = tuple(batteries()[:count])
    report = run_study(study, replace(settings, manual_bess_fleet=fleet, compare_corrective_actions=True))
    off, on = (report.alternatives[name][0] for name in ("uncontrolled", "controlled"))
    assert all(unit.actual_power_kw == 0. for step in off.steps for unit in step.fleet_steps.values())
    assert any(abs(unit.actual_power_kw) > 1e-5 for step in on.steps for unit in step.fleet_steps.values())
    assert set(on.final_fleet_states) == set(off.final_fleet_states) == {config.bus_id for config in fleet}
    assert all(state.soc == .5 for state in off.final_fleet_states.values())
    assert on.dispatch_timing["daily_soc_restored"]
