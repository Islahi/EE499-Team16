"""Physical PV bounds at the OPF-to-FBS handoff."""
from dataclasses import replace
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src import app_log
from src import joint_opf
from src.bess import BESSConfig, BESSState
from src.fbs import OperatingPoint, prepare_fbs
from src.network_model import Bus, Line, NetworkModel, PVUnit
from src.simulation import SimulationConfig


def opf_case(available, *, export_limit=0.):
    network = NetworkModel(
        [Bus(1, "Slack", 12.66, True), Bus(2, "PV", 12.66)],
        [Line("1-2", 1, 2, .12, .05)], [], [PVUnit("PV2", 2, 10.375)], 1000., 60.,
    )
    settings = SimulationConfig(fleet_dispatch_mode="daily_milp_dispatch",
                                allow_load_shedding=False, grid_export_limit_kw=export_limit)
    zeros = {1: 0., 2: 0.}
    point = OperatingPoint(zeros, zeros, {1: 0., 2: available}, zeros, zeros, zeros)
    solve = prepare_fbs(network, settings.fbs_config)
    return network, settings, point, solve


def proposal(monkeypatch, curtailment, available):
    def solver(cost, **kwargs):
        assert kwargs["bounds"][0] == (0., available)
        x = np.zeros(len(cost))
        x[0] = curtailment
        return SimpleNamespace(success=True, x=x, message="supplied solver result")
    monkeypatch.setattr(joint_opf, "linprog", solver)


@pytest.mark.parametrize(("curtailment", "remaining", "event"), [
    (3.125, 0., False),
    (3.125 + 5e-8, 0., True),
    (1.0625, 2.0625, False),
    (-5e-8, 3.125, True),
])
def test_fractional_pv_boundaries(monkeypatch, curtailment, remaining, event):
    available = 3.125
    # Force dispatch into OPF through the export constraint. Use a direct OPF
    # proposal for lower-bound cases, where leaving PV online violates export.
    network, settings, point, solve = opf_case(available)
    controller = joint_opf.JointOPFController(network, settings, solve)
    recorded = []
    monkeypatch.setattr(joint_opf, "record_opf_pv_boundary", recorded.append)
    proposal(monkeypatch, curtailment, available)
    result = controller._optimize(point, solve(point), (), {}, {})
    assert result.p_pv_kw[2] == remaining
    assert point.p_pv_kw[2] == available
    assert network.pv_units[0].p_rated_kw == 10.375
    assert solve(result).converged
    assert bool(recorded) == event
    if event:
        assert recorded[0]["action"] == "clamped"
        assert recorded[0]["resulting_pv_kw"] == available - curtailment


@pytest.mark.parametrize("curtailment", [3.125 + 1e-5, -1e-5, np.nan])
def test_material_or_nonfinite_pv_proposal_uses_existing_fallback(tmp_path, monkeypatch, curtailment):
    available = 3.125
    network, settings, point, solve = opf_case(available)
    timestamp = pd.Timestamp("2021-07-02 12:00")
    day = {"day_index": 182, "cluster_id": 3, "start": "2021-07-02 00:00:00"}
    # Keep the production diagnostic writer active with a temporary target.
    monkeypatch.setattr(app_log, "__file__", str(tmp_path / "app_log.py"))
    battery = BESSConfig(2, 10., 5., .20, 1., .50, .95, .95)
    controller = joint_opf.JointOPFController(network, settings, solve)

    def solver(cost, **kwargs):
        x = np.zeros(len(cost))
        # Four BESS variables precede the PV curtailment variable.
        assert kwargs["bounds"][4] == (0., available)
        x[4] = curtailment
        return SimpleNamespace(success=True, x=x, message="supplied solver result")

    monkeypatch.setattr(joint_opf, "linprog", solver)
    final, flow, _, _, audit = controller.dispatch(
        point, solve(point), [battery], {2: BESSState(5., .5)}, {2: 0.},
        timestamp=timestamp, representative_day=day)
    assert flow.converged
    assert 0. <= final.p_pv_kw[2] <= available
    assert controller.opf_lp_failures == 1
    assert controller.opf_fallbacks == 1
    assert audit["status"].startswith(("opf_corrective_fallback", "opf_failed_fallback:"))
    [log] = (tmp_path / "Results" / "Diagnostics").glob("opf_pv_boundary_*.jsonl")
    record = json.loads(log.read_text(encoding="utf-8"))
    assert record["action"] == "fallback"
    assert record["fleet"] == [{"bus": 2, "power_kw": 5., "energy_kwh": 10.}]
    assert record["representative_day"] == day
    assert record["timestamp"] == str(timestamp)
    assert record["bus"] == 2
    assert record["available_pv_kw"] == available
    if np.isfinite(curtailment):
        assert record["proposed_curtailment_kw"] == curtailment
        assert record["resulting_pv_kw"] == available - curtailment
    else:
        assert record["proposed_curtailment_kw"] == record["resulting_pv_kw"] == "nan"


def test_zero_generation_leaves_zero_and_fbs_remains_strict(monkeypatch):
    network, settings, point, solve = opf_case(0.)
    controller = joint_opf.JointOPFController(network, settings, solve)
    monkeypatch.setattr(joint_opf, "linprog", lambda *a, **kw: pytest.fail("LP called at zero PV"))
    final, flow, _, _, audit = controller.dispatch(point, solve(point), (), {}, {})
    assert final.p_pv_kw[2] == 0.
    assert flow.converged
    assert audit["status"] == "no_opf_needed"
    with pytest.raises(ValueError, match="p_pv_kw is outside its physical range"):
        solve(replace(point, p_pv_kw={1: 0., 2: -1e-12}))


def test_real_highs_export_constraint_at_full_curtailment(monkeypatch):
    available = 3.125
    network, settings, point, solve = opf_case(available)
    network.pv_units[0] = replace(network.pv_units[0], q_capability_kvar=0.)
    raw = solve(point)
    controller = joint_opf.JointOPFController(network, settings, solve)
    _, dp, _ = controller.corrector.sensitivities(raw, point, [(2, 2, -1., 0., 0.)])
    # Set the linearized export constraint just beyond the curtailment bound.
    # The nonlinear operating point with zero PV still meets the export limit.
    export_limit = float(-dp[0] * (available + 5e-8) - raw.slack_p_kw + 1e-4)
    controller.settings = replace(settings, grid_export_limit_kw=export_limit)
    records = []
    monkeypatch.setattr(joint_opf, "record_opf_pv_boundary", records.append)
    final, flow, _, _, _ = controller.dispatch(point, raw, (), {}, {})
    assert flow.converged
    assert final.p_pv_kw[2] == pytest.approx(0., abs=1e-7)
    if records:
        [record] = records
        assert record["action"] == "clamped"
        assert record["proposed_curtailment_kw"] == pytest.approx(3.12500005, abs=1e-10)
