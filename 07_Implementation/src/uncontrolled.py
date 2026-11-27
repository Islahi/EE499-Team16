"""Raw FBS diagnostics with prescribed P/Q and no automatic dispatch or corrections."""

from dataclasses import asdict
from time import perf_counter

from .bess import BESSState, BESSStepResult
from .constraint_dispatch import DispatchEvent, check_flow
from .control_audit import constraint_evidence
from .data_loader import profile_at
from .fbs import prepare_fbs
from .network_control import Correction
from .optimizer import BESSParameters
from .progress import ProgressEvent
from .simulation import SimulationStepResult, TimeSeriesSimulationResult, _check_number, _operating_point

DISABLED_STATUS = "disabled_by_study_policy"


def idle_states(network, configs):
    eligible = {bus.bus_id for bus in network.buses if not bus.is_slack}
    states = {}
    for unit in configs:
        if unit.bus_id in states or unit.bus_id not in eligible:
            raise ValueError("Use unique existing non-slack BESS buses")
        BESSParameters(unit.eta_charge, unit.eta_discharge, unit.soc_min, unit.soc_max, unit.soc_initial)
        _check_number(unit.energy_capacity_kwh, "Battery energy capacity", positive=True)
        _check_number(unit.power_rating_kw, "Battery power rating", positive=True)
        states[unit.bus_id] = BESSState(unit.energy_capacity_kwh * unit.soc_initial, unit.soc_initial)
    return states


def uncontrolled_step(network, profile, settings, states, solve, capture_dispatch):
    point = _operating_point(network, profile)
    flow = solve(point)
    check = check_flow(flow, network, settings)
    solved = flow.converged
    feasible = solved and not check.violations
    voltages = flow.voltage_mag_pu if solved else None
    violations = {bus: value for bus, value in (voltages or {}).items()
                  if not settings.voltage_min_pu <= value <= settings.voltage_max_pu}
    correction = Correction(status=DISABLED_STATUS)
    reason = [DISABLED_STATUS] + (["nonconvergence"] if not solved else [])
    event = None
    if capture_dispatch:
        event = DispatchEvent("uncontrolled-fbs", "Corrective actions disabled by study policy",
                              None, 0, [], check, after_bess=check, final=check,
                              accepted_kw=0., correction=asdict(correction), reason_codes=reason)
        event.evidence = constraint_evidence(network, settings, (check, check, check), (flow, flow, flow))
    messages = ["Corrective actions disabled by study policy"]
    if not solved:
        messages.append(flow.message)
    elif check.violations:
        messages.append("Prescribed operating point violates network limits")
    # SOC remains known even across a failed solve because no action changes it.
    idle = {bus: BESSStepResult(0., state.energy_kwh, state.energy_kwh, state.soc, state.soc,
                                False, DISABLED_STATUS) for bus, state in states.items()}
    return SimulationStepResult(
        profile.timestamp, point, flow, 0., None, None, violations, feasible, messages,
        curtailment_kw=0. if solved else None, shedding_kw=0. if solved else None,
        curtailment_by_bus_kw=dict.fromkeys(point.p_pv_kw, 0.) if solved else None,
        shedding_by_bus_kw=dict.fromkeys(point.p_load_kw, 0.) if solved else None,
        dispatch=event, requested_point=point, pre_control_voltage_pu=voltages,
        correction=correction, fleet_steps=idle, fleet_states=dict(states),
        uncontrolled_voltage_pu=voltages, before_correction_voltage_pu=voltages)


def simulate_uncontrolled(network, profiles, settings, configs, progress, capture_dispatch):
    started = perf_counter()
    states = idle_states(network, configs)
    solve = prepare_fbs(network, settings.fbs_config)
    steps = []
    total = len(profiles.timestamps)
    for index, stamp in enumerate(profiles.timestamps):
        if progress:
            progress(ProgressEvent("Simulation", index, total, f"Uncontrolled FBS at {stamp}"))
        step = uncontrolled_step(network, profile_at(profiles, index), settings, states, solve, capture_dispatch)
        steps.append(step)
        if progress:
            progress(ProgressEvent("Simulation", index + 1, total, f"{stamp}; converged={step.power_flow.converged}",
                                   hour_finished=True))
    converged = all(step.power_flow.converged for step in steps)
    feasible = converged and all(step.feasible for step in steps)
    message = ("Uncontrolled FBS completed within limits" if feasible else
               "Uncontrolled FBS completed with network violations" if converged else
               "Uncontrolled FBS includes unsolved hours; idle battery SOC is retained")
    return TimeSeriesSimulationResult(
        steps, profiles.dt_hours, True, converged, feasible, None, message,
        dispatch_timing={"control_mode": "uncontrolled", "fleet_dispatch_mode": "idle",
                         "fbs_calls": total, "elapsed_seconds": perf_counter() - started},
        final_fleet_states=states)
