"""Karve-style sequential-study fleet physics: independent SOC, one joint FBS.

In 'opf' mode, dispatches via Dr. Sindi's SESS coupled P/Q look-ahead LP +
damped sequential linearized AC OPF with nonlinear Numba FBS verification.
"""
from dataclasses import asdict, replace
from math import isfinite
from time import perf_counter

from .bess import BESSConfig, BESSState, step_bess
from .constraint_dispatch import DispatchEvent, admissible, check_flow
from .data_loader import profile_at
from .fbs import prepare_fbs
from .network_control import Correction, NetworkCorrector
from .progress import ProgressEvent
from .voltage_dispatch import VoltageSupport
from .simulation import (_operating_point, SimulationStepResult,
                         TimeSeriesSimulationResult)


def _allocate(configs, states, target_kw):
    """Shared target with separate per-unit SOC/efficiency and redistribution."""
    sign = 1 if target_kw >= 0 else -1
    headrooms = {c.bus_id: abs(step_bess(c, states[c.bus_id], sign * c.power_rating_kw, 1.0).actual_power_kw)
                 for c in configs}
    remaining = min(abs(target_kw), sum(headrooms.values()))
    allocated = {c.bus_id: 0.0 for c in configs}
    free = dict(headrooms)
    for _ in configs:
        cap = sum(free.values())
        if cap <= 1e-10 or remaining <= 1e-10:
            break
        distributed = 0.
        for bus in free:
            amount = min(free[bus], remaining * free[bus] / cap)
            allocated[bus] += amount
            distributed += amount
            free[bus] -= amount
        remaining -= distributed
    return {bus: sign * amount for bus, amount in allocated.items()}


def _target_kw(flow, point, settings, configs, states):
    """Local rule: relieve network stress and opportunistically recharge."""
    if not flow.converged:
        return 0.0
    capacity_kw = sum(c.power_rating_kw for c in configs)
    imports = flow.slack_p_kw
    low = min(flow.voltage_mag_pu.values())
    high = max(flow.voltage_mag_pu.values())
    if settings.grid_import_limit_kw is not None and imports > settings.grid_import_limit_kw:
        return min(capacity_kw, imports - settings.grid_import_limit_kw)
    if low < settings.voltage_min_pu:
        return capacity_kw
    if settings.grid_export_limit_kw is not None and -imports > settings.grid_export_limit_kw:
        return -min(capacity_kw, -imports - settings.grid_export_limit_kw)
    if high > settings.voltage_max_pu:
        return -capacity_kw
    missing_ac_kwh = sum(max(0.0, c.energy_capacity_kwh * c.soc_initial - states[c.bus_id].energy_kwh)
                         / c.eta_charge for c in configs)
    if missing_ac_kwh > 1e-7:
        grid_headroom = (max(0.0, settings.grid_import_limit_kw - max(0., imports))
                         if settings.grid_import_limit_kw is not None else capacity_kw)
        return -min(capacity_kw, grid_headroom, missing_ac_kwh)
    solar_surplus = max(0.0, -imports)
    if solar_surplus > 0:
        return -min(capacity_kw, solar_surplus)
    return 0.0


def simulate_timeseries_fleet(network, profiles, settings, configs, *, progress=None,
                              capture_dispatch=True, representative_day=None):
    """Dispatch distinct batteries and run a single coupled feeder solve per trial."""
    started = perf_counter()
    configs = tuple(configs)
    if settings.corrective_actions and not configs and settings.fleet_dispatch_mode not in ('opf', 'daily_milp_dispatch'):
        from .simulation import simulate_timeseries
        return simulate_timeseries(network, profiles, settings, dispatch_policy=None,
                                   progress=progress, capture_dispatch=capture_dispatch)
    network.validate()
    if profiles.dt_hours != 1.0 or not profiles.timestamps:
        raise ValueError('Fleet simulation requires consecutive hourly profiles')
    if len(configs) != len({c.bus_id for c in configs}):
        raise ValueError('Multi-BESS cannot use the same installation bus twice')
    eligible = {bus.bus_id for bus in network.buses if not bus.is_slack}
    if any(c.bus_id not in eligible for c in configs):
        raise ValueError('Fleet BESS locations must be unique, existing non-slack buses')
    from datetime import timedelta
    for previous, current in zip(profiles.timestamps, profiles.timestamps[1:]):
        if current - previous != timedelta(hours=1):
            raise ValueError('Fleet simulation requires continuous hourly timestamps')
    n = len(profiles.timestamps)
    for name in ('load_p_kw','load_q_kvar','pv_p_kw','pv_q_kvar'):
        if any(len(values) != n for values in getattr(profiles, name).values()):
            raise ValueError(f'Incomplete {name} profile in fleet study')
    if not settings.corrective_actions:
        from .uncontrolled import simulate_uncontrolled
        return simulate_uncontrolled(network, profiles, settings, configs, progress, capture_dispatch)
    states = {c.bus_id: BESSState(c.energy_capacity_kwh * c.soc_initial,c.soc_initial) for c in configs}
    solve = prepare_fbs(network, settings.fbs_config)
    counter = [0, 0.0]
    def traced(point, progress=None):
        begun = perf_counter()
        result = solve(point, progress=progress)
        counter[0] += 1
        counter[1] += perf_counter() - begun
        return result
    corrector = NetworkCorrector(network, settings, traced)
    voltage_support = VoltageSupport(network)
    planner = None
    if settings.fleet_dispatch_mode == 'daily_milp_dispatch' and configs:
        from .daily_milp_dispatch import DailyMILPPlanner
        planner = DailyMILPPlanner(network, profiles, settings, configs, traced)
    if settings.fleet_dispatch_mode in ('predictive', 'predictive_24h', 'opf') and configs:
        from .lookahead_dispatch import DayAheadFleetPlanner, PredictiveSettings
        is_opf = settings.fleet_dispatch_mode == 'opf'
        planner = DayAheadFleetPlanner(network, profiles, settings, configs,
                    voltage_support, traced,
                    PredictiveSettings(
                        horizon_hours=24 if settings.fleet_dispatch_mode == 'predictive_24h' else 72,
                        monitored_buses=8 if settings.fleet_dispatch_mode == 'predictive_24h' else 12,
                        shedding_aware=settings.fleet_dispatch_mode != 'predictive_24h',
                        shedding_penalty_per_kwh=settings.shedding_penalty_per_kwh,
                        grid_purchase_tariff_per_kwh=settings.predictive_grid_tariff_per_kwh,
                        coupled_pq=is_opf,
                        bess_kva_multiplier=settings.opf_bess_kva_multiplier,
                        pv_kva_multiplier=settings.opf_pv_kva_multiplier))
    opf_controller = None
    if settings.fleet_dispatch_mode in ('opf', 'daily_milp_dispatch'):
        from .joint_opf import JointOPFController
        opf_controller = JointOPFController(network, settings, traced, corrector)
    steps = []
    strict_day_start = {bus: state.energy_kwh for bus, state in states.items()}
    strict_failures = []
    for i, timestamp in enumerate(profiles.timestamps):
        if progress:
            progress(ProgressEvent('Simulation', i, n, f'Fleet step {i+1}/{n}'))
        point = _operating_point(network, profile_at(profiles, i))
        raw = traced(point)
        check = check_flow(raw, network, settings)
        if planner is not None:
            requests, control_reason = planner.request(i, states, raw)
            q_requests = (planner.planned_q(i) if hasattr(planner, 'planned_q') else planner.q_schedule.get(i, {})) if opf_controller is not None else None
        else:
            requests, control_reason = voltage_support.dispatch(raw, configs, states, settings)
            q_requests = None
        total_target = sum(requests.values())
        if opf_controller is not None:
            served, flow, actions, correction, opf_audit = opf_controller.dispatch(
                point, raw, configs, states, requests, q_requests=q_requests,
                timestamp=timestamp, representative_day=representative_day)
            before_correction = opf_controller.last_reference_point
            reference_flow = opf_controller.last_reference_flow
            accepted = (before_correction, reference_flow, actions)
            before_check = check_flow(reference_flow, network, settings)
        else:
            total_target = sum(requests.values())
            attempted = {c.bus_id: step_bess(c, states[c.bus_id], requests[c.bus_id], 1.0)
                         for c in configs}
            injection = {bus: attempt.actual_power_kw for bus, attempt in attempted.items()}
            accepted = None
            for factor in (1., .5, .25, .125, .0625, 0.):
                adjusted = {c.bus_id: step_bess(c, states[c.bus_id],
                                              injection[c.bus_id] * factor, 1.0)
                            for c in configs}
                trial_point = replace(point, p_bess_kw={**point.p_bess_kw,
                    **{bus: action.actual_power_kw for bus,action in adjusted.items()}})
                trial_flow = traced(trial_point) if factor else raw
                if factor == 0 or admissible(check, check_flow(trial_flow, network, settings)):
                    accepted = (trial_point,trial_flow,adjusted)
                    break
            before_correction, flow, actions = accepted
            before_check = check_flow(flow, network, settings)
            correction = Correction()
            served = before_correction
            if before_check.violations or not flow.converged:
                served, flow, correction = corrector.correct(before_correction, flow, before_check)
        converged = flow.converged
        voltage_violations = ({bus:v for bus,v in flow.voltage_mag_pu.items()
                               if v < settings.voltage_min_pu or v > settings.voltage_max_pu}
                              if converged else {})
        final_check = check_flow(flow, network, settings)
        feasible = converged and not final_check.violations
        messages = []
        if settings.fleet_dispatch_mode == 'daily_milp_dispatch' and planner is not None and 'no feasible schedule' in control_reason:
            # Safe idle is a physical fallback, NOT a validated optimal schedule.
            # Do not let an optimizer accept a run that relied on a failed MILP.
            feasible = False
            messages.append('Daily MILP dispatch schedule UNAVAILABLE: ' + control_reason)
        if correction.status not in ('not_needed','verified'):
            messages.append(f'Corrective control unresolved ({correction.status})')
        if final_check.violations:
            messages.append('Network voltage/import/export/ampacity violations remain after controls')
        shed = ({bus:max(0., point.p_load_kw[bus]-served.p_load_kw[bus])
                 for bus in point.p_load_kw} if converged else None)
        curtailed = ({bus:max(0., point.p_pv_kw[bus]-served.p_pv_kw[bus])
                      for bus in point.p_pv_kw} if converged else None)
        if converged:
            for bus, action in actions.items():
                states[bus] = BESSState(action.energy_after_kwh, action.soc_after)
        if settings.fleet_dispatch_mode == 'daily_milp_dispatch' and ((i + 1) % 24 == 0 or i + 1 == n):
            for bus, initial in strict_day_start.items():
                residual = states[bus].energy_kwh - initial
                if abs(residual) > settings.daily_soc_tolerance_kwh:
                    strict_failures.append({'hour': i+1, 'bus': bus, 'energy_error_kwh': residual})
                    feasible = False
                    messages.append(f'Daily SOC restoration failed at bus {bus}: {residual:+.5f} kWh')
            strict_day_start = {bus: state.energy_kwh for bus, state in states.items()}
        event = None
        if capture_dispatch:
            event = DispatchEvent(('daily-milp-verified-opf' if settings.fleet_dispatch_mode == 'daily_milp_dispatch' else 'coordinated-pq-opf') if opf_controller is not None else
                                  ('fleet-day-ahead-LP' if planner else 'fleet-sequential-rule'),
                                  ('Daily MILP dispatch day-ahead P/Q MILP + discharge-linked PF + daily SOC closure + FBS verification'
                                    if settings.fleet_dispatch_mode == 'daily_milp_dispatch' else
                                    'SESS independent P/Q MPC + damped SLP OPF + FBS verification') if opf_controller is not None else
                                  ('72h daily-replanned supplied-profile forecast + joint FBS safeguard' if settings.fleet_dispatch_mode == 'predictive' else
                                   '24h supplied-profile forecast + joint nonlinear FBS safeguard' if planner else
                                   'multi-BESS joint network feasibility'),
                                  None, planner.parameters.horizon_hours if planner else 1, [], check, after_bess=before_check, final=final_check,
                                  planned_kw=total_target, request_kw=sum(requests.values()),
                                  accepted_kw=sum(action.actual_power_kw for action in actions.values()),
                                  correction=asdict(correction),
                                  reason_codes=[control_reason, f'{len(configs)} distinct battery injections'] +
                                  ([opf_audit['status']] if opf_controller is not None else []))
            from .control_audit import constraint_evidence
            event.requested_p_by_bus = dict(requests)
            event.requested_q_by_bus = dict(q_requests or {})
            event.evidence = constraint_evidence(network, settings, (check, before_check, final_check),
                                                 (raw, accepted[1], flow))
        steps.append(SimulationStepResult(
            timestamp=timestamp, operating_point=served, power_flow=flow,
            bess_request_kw=sum(requests.values()), bess_step=None, bess_state=None,
            voltage_violations=voltage_violations, feasible=feasible,
            messages=messages, curtailment_kw=sum(curtailed.values()) if curtailed is not None else None,
            shedding_kw=sum(shed.values()) if shed is not None else None,
            curtailment_by_bus_kw=curtailed, shedding_by_bus_kw=shed,
            dispatch=event, requested_point=point if capture_dispatch else None,
            uncontrolled_voltage_pu=raw.voltage_mag_pu if capture_dispatch and raw.converged else None,
            before_correction_voltage_pu=accepted[1].voltage_mag_pu if capture_dispatch and accepted[1].converged else None,
            pre_control_voltage_pu=(dict(accepted[1].voltage_mag_pu) if accepted[1].converged else None),
            correction=correction, fleet_steps=actions,
            fleet_states={bus:BESSState(state.energy_kwh,state.soc) for bus,state in states.items()},
        ))
        if progress:
            progress(ProgressEvent('Simulation', i+1, n, f'{timestamp}; feasible={feasible}',hour_finished=True))
        if not converged and settings.stop_on_power_flow_failure:
            break
    complete=len(steps)==n
    conv=all(step.power_flow.converged for step in steps)
    feasible=complete and conv and all(step.feasible for step in steps)
    return TimeSeriesSimulationResult(
        steps,1.0,complete,conv,feasible,None,
        'Completed successfully' if feasible else 'Fleet completed with unresolved power flow or network constraints',
        dispatch_timing={'fleet_dispatch_mode':settings.fleet_dispatch_mode,
                         **(planner.summary() if planner is not None else {}),
                         'daily_soc_failures': strict_failures,
                         'daily_soc_tolerance_kwh': settings.daily_soc_tolerance_kwh,
                         'daily_soc_restored': not bool(strict_failures) if settings.fleet_dispatch_mode == 'daily_milp_dispatch' else None,
                         **(opf_controller.summary() if opf_controller is not None else {}),
                         'fbs_calls':counter[0],'fbs_seconds':counter[1],
                         'correction_seconds':corrector.seconds,'correction_fbs_trials':corrector.trials,
                         'correction_hours':corrector.evaluations,'correction_unresolved_hours':corrector.unresolved,
                         'elapsed_seconds':perf_counter()-started},
        final_fleet_states={bus:BESSState(state.energy_kwh,state.soc) for bus,state in states.items()},
    )
