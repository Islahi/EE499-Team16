from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src_accelerated.data_loader import ProfileData, profile_at
from src_accelerated.fbs import FBSConfig, prepare_fbs, run_fbs
from src_accelerated.network_control import NetworkCorrector
from src_accelerated.network_loader import load_network
from src_accelerated.network_model import Bus, Line, Load, NetworkModel, PVUnit
from src_accelerated.simulation import SimulationConfig, _operating_point, simulate_timeseries


def case(pv=0., ampacity=None):
    network = NetworkModel(
        [Bus(i, str(i), 12.66, is_slack=(i == 1)) for i in range(1, 5)],
        [Line("short", 1, 2, .03, .02, ampacity), Line("weak", 1, 3, 90., 12.),
         Line("reactive", 2, 4, .1, .1)],
        [Load("fixed_slack", 1, 5., 1.), Load("near", 2, 40., 4.), Load("remote", 3, 250., 50.),
         Load("reactive_only", 4, 0., 10.)], [PVUnit("PV", 2, 300.)], 1000., 60.)
    data = ProfileData.from_arrays([pd.Timestamp("2021-05-27 11:00")],
                                  {1: [5.], 2: [40.], 3: [250.], 4: [0.]},
                                  {1: [1.], 2: [4.], 3: [50.], 4: [10.]},
                                  {2: [pv]}, {2: [pv / 10]})
    return network, data


def test_targeted_shedding_reduces_p_and_q_only_at_the_weak_bus():
    network, data = case()
    settings = SimulationConfig()
    legacy = simulate_timeseries(network, data, replace(settings, legacy_proportional_validation=True)).steps[0]
    step = simulate_timeseries(network, data, settings).steps[0]
    assert legacy.feasible and step.feasible
    assert 0 < step.shedding_kw < legacy.shedding_kw
    assert step.shedding_by_bus_kw[3] == pytest.approx(step.shedding_kw)
    assert step.operating_point.p_load_kw[1] == 5.
    assert step.operating_point.q_load_kvar[4] == 10.
    assert step.operating_point.q_load_kvar[3] == pytest.approx(.2 * step.operating_point.p_load_kw[3])
    assert all(p >= 0 for p in step.operating_point.p_load_kw.values())
    assert data.load_p_kw[3] == [250.]


def test_15_bus_zero_export_failure_reproduced_on_minimized_feeder():
    network, data = case(pv=245.)
    settings = SimulationConfig(grid_export_limit_kw=0., grid_import_limit_kw=500.)
    legacy = simulate_timeseries(network, data, replace(settings, legacy_proportional_validation=True)).steps[0]
    step = simulate_timeseries(network, data, settings).steps[0]
    assert not legacy.feasible and legacy.dispatch.final.violations["export"] > 0
    assert step.feasible and not step.dispatch.final.violations
    assert step.dispatch.after_bess.import_kw > 0
    assert step.dispatch.after_bess.minimum_pu < .95 <= step.dispatch.final.minimum_pu
    assert 0 < step.curtailment_kw < 245. and 0 < step.shedding_kw < 250.
    assert step.dispatch.final.export_kw <= settings.control_tolerance_kw
    assert step.operating_point.q_pv_kvar[2] == pytest.approx(.1 * step.operating_point.p_pv_kw[2])
    assert step.dispatch.correction["status"] == "verified"
    point, flow = step.operating_point, step.power_flow
    assert sum(point.p_load_kw.values()) + flow.total_loss_p_kw == pytest.approx(
        sum(point.p_pv_kw.values()) + flow.slack_p_kw, abs=.002)
    assert sum(point.q_load_kvar.values()) + flow.total_loss_q_kvar == pytest.approx(
        sum(point.q_pv_kvar.values()) + flow.slack_q_kvar, abs=.002)


def test_ampacity_and_disabled_controls_are_checked_with_voltage_and_grid():
    network, data = case(pv=280., ampacity=1.)
    settings = SimulationConfig(grid_export_limit_kw=0., grid_import_limit_kw=500.)
    step = simulate_timeseries(network, data, settings).steps[0]
    assert step.feasible and "ampacity:short" in step.dispatch.pre.violations
    assert step.power_flow.branch_current_a["short"] <= 1.000001
    blocked = simulate_timeseries(network, data, replace(settings, allow_pv_curtailment=False)).steps[0]
    assert not blocked.feasible and blocked.dispatch.final.violations
    assert blocked.dispatch.correction["status"] == "correction_unresolved"
    disabled = replace(settings, allow_load_shedding=False, allow_pv_curtailment=False)
    step = simulate_timeseries(network, data, disabled).steps[0]
    assert not step.feasible and step.dispatch.correction["status"] == "physically_infeasible_no_controls"


def test_nonconvergence_is_diagnostic_only():
    network, data = case()
    settings = SimulationConfig(fbs_config=FBSConfig(max_iterations=1), allow_load_shedding=False)
    step = simulate_timeseries(network, data, settings).steps[0]
    assert not step.feasible and not step.power_flow.converged
    assert step.dispatch.correction["status"] == "fbs_nonconvergence"


def test_implicit_fbs_derivatives_match_power_factor_preserving_probes():
    network, data = case(pv=100., ampacity=100.)
    settings = SimulationConfig(fbs_config=FBSConfig(voltage_tolerance_pu=1e-11))
    solve = prepare_fbs(network, settings.fbs_config)
    point = _operating_point(network, profile_at(data, 0))
    anchor = solve(point)
    corrector = NetworkCorrector(network, settings, solve)
    actions = [(0, 3, 250., 50., 12.), (1, 2, 100., 10., .07)]
    dv, dp, di = corrector.sensitivities(anchor, point, actions)
    h = .001
    for index, (group, bus, p, q, _) in enumerate(actions):
        active = "p_pv_kw" if group else "p_load_kw"
        reactive = "q_pv_kvar" if group else "q_load_kvar"
        changed = solve(replace(point, **{active: {**getattr(point, active), bus: p - h},
                                          reactive: {**getattr(point, reactive), bus: q - h * q / p}}))
        assert dv[:, index] == pytest.approx(np.array([
            changed.voltage_mag_pu[i] - anchor.voltage_mag_pu[i] for i in corrector.buses]) / h, abs=1e-8)
        assert dp[index] == pytest.approx((changed.slack_p_kw - anchor.slack_p_kw) / h, abs=1e-5)
        assert di[0, index] == pytest.approx((changed.branch_current_a["short"] - anchor.branch_current_a["short"]) / h,
                                             abs=1e-6)


def test_ieee33_nominal_numba_reference():
    root = Path(__file__).parents[1] / "Validation/C1_Validation_Test/Working_RDS"
    network = load_network(root / "IEEE_33Bus_Network_Data.xlsx", frequency_hz=60.)
    loads = network.loads_by_bus()
    p = {bus: [sum(load.p_base_kw for load in entries)] for bus, entries in loads.items()}
    q = {bus: [sum(load.q_base_kvar for load in entries)] for bus, entries in loads.items()}
    data = ProfileData.from_arrays([pd.Timestamp("2021-01-01")], p, q, {}, {})
    flow = run_fbs(network, _operating_point(network, profile_at(data, 0)), FBSConfig())
    assert flow.converged and min(flow.voltage_mag_pu, key=flow.voltage_mag_pu.get) == 18
    assert flow.voltage_mag_pu[18] == pytest.approx(.91308, abs=1e-5)
    assert flow.total_loss_p_kw == pytest.approx(202.68, abs=.05)
