"""Hourly orchestration of profile inputs, BESS operation and FBS power flow."""
from collections.abc import Callable
from copy import copy
from dataclasses import asdict, dataclass, field, replace
from math import isfinite
from time import perf_counter

from .fbs import FBSConfig, OperatingPoint, PowerFlowResult, prepare_fbs, validate_config
from .bess import BESSConfig, BESSState, BESSStepResult, step_bess
from .network_model import NetworkModel
from .data_loader import ProfileSlice, ProfileData, profile_at
from .progress import ProgressEvent
from .constraint_dispatch import ConstraintAwareDispatch, DispatchEvent, RollingDispatch, admissible, check_flow
from .network_control import Correction, NetworkCorrector
from .planning_policy import DEFAULT_DISPATCH_HORIZON_HOURS, DEFAULT_MINIMUM_DISCHARGE_PF


@dataclass(frozen=True)
class GridAwareDispatchPolicy:
    """Self-consumption dispatch: store excess PV, discharge to offset grid import.

    Requests charging from solar surplus and discharging against net demand.
    When an import cap is exceeded, requests enough discharge to address
    the cap, subject to BESS power and SOC restrictions. This is rule-based,
    NOT tariff optimization or intertemporal electricity-price arbitrage.
    """
    import_limit_kw: float | None = None
    export_limit_kw: float | None = None

    def __call__(self, index, profile, state):
        net = sum(profile.p_load_kw.values()) - sum(profile.p_pv_kw.values())
        if self.import_limit_kw is not None and net > self.import_limit_kw:
            return net - self.import_limit_kw
        if net < 0:
            # Store otherwise exported PV, especially behind an export limit.
            return net if self.export_limit_kw is None else min(0.0, net + self.export_limit_kw)
        if net > 0:
            # Use previous stored renewable energy against positive demand.
            # The battery's power, SOC and efficiency constraints
            # are enforced by step_bess, not by this request policy.
            return net
        return 0.0


@dataclass
class SimulationConfig:
    fbs_config: FBSConfig = field(default_factory=FBSConfig)
    voltage_min_pu: float = 0.95
    voltage_max_pu: float = 1.05
    stop_on_power_flow_failure: bool = True
    allow_pv_curtailment: bool = True
    allow_load_shedding: bool = True
    grid_import_limit_kw: float | None = None
    grid_export_limit_kw: float | None = None
    enforce_line_ampacity: bool = True
    # Legacy fields accepted for older saved settings only; ignored in v5.
    terminal_soc_tolerance: float | None = None
    terminal_cycle_hours: int | None = None
    control_max_iterations: int = 30
    control_tolerance_kw: float = 1e-6
    shedding_penalty_per_kwh: float = 12.0
    curtailment_penalty_per_kwh: float = 0.07
    legacy_proportional_validation: bool = False
    shedding_policy: str = "progressive"
    # V11: mutually exclusive multi-BESS control policies. No new dependencies.
    fleet_dispatch_mode: str = "predictive"
    predictive_grid_tariff_per_kwh: float = 0.10
    # V13: explicit study assumptions, not inverter specifications imported
    # from equipment data sheets. A 1.0 multiplier means no kVA oversizing.
    opf_bess_kva_multiplier: float = 1.00
    opf_pv_kva_multiplier: float = 1.00
    minimum_discharge_pf: float = DEFAULT_MINIMUM_DISCHARGE_PF
    dispatch_horizon_hours: int = DEFAULT_DISPATCH_HORIZON_HOURS
    daily_soc_tolerance_kwh: float = 0.05
    shedding_tier_edges: tuple[float, float] = (0.50, 0.80)
    shedding_tier_weights: tuple[float, float, float] = (1., 3., 10.)

    @classmethod
    def from_saved_settings(cls, values):
        from .saved_schema import upgrade_saved_fields

        settings = upgrade_saved_fields(values)
        if isinstance(settings.get("fbs_config"), dict):
            settings["fbs_config"] = FBSConfig(**settings["fbs_config"])
        if settings.get("dispatch_horizon_hours") in ("24", "48", "72"):
            settings["dispatch_horizon_hours"] = int(settings["dispatch_horizon_hours"])
        return cls(**settings)

    @property
    def effective_bess_inverter_kva_per_kw(self):
        if self.fleet_dispatch_mode == "daily_milp_dispatch":
            return max(self.opf_bess_kva_multiplier, 1.0 / self.minimum_discharge_pf)
        return self.opf_bess_kva_multiplier

    def __post_init__(self):
        from .saved_schema import canonical_dispatch_mode

        self.fleet_dispatch_mode = canonical_dispatch_mode(self.fleet_dispatch_mode)
        if self.terminal_cycle_hours is not None and (type(self.terminal_cycle_hours) is not int or self.terminal_cycle_hours < 1):
            raise ValueError("terminal_cycle_hours must be a positive integer")
        validate_config(self.fbs_config)
        _check_number(self.voltage_min_pu, "voltage_min_pu", positive=True)
        _check_number(self.voltage_max_pu, "voltage_max_pu", positive=True)
        if self.voltage_min_pu >= self.voltage_max_pu:
            raise ValueError("Minimum voltage must be less than maximum voltage")
        if not isinstance(self.stop_on_power_flow_failure, bool):
            raise ValueError("stop_on_power_flow_failure must be True or False")
        for name in ("allow_pv_curtailment", "allow_load_shedding"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be True or False")
        for name in ("grid_import_limit_kw", "grid_export_limit_kw"):
            value = getattr(self, name)
            if value is not None:
                _check_number(value, name)
                if value < 0:
                    raise ValueError(f"{name} cannot be negative")
        if self.terminal_soc_tolerance is not None:
            _check_number(self.terminal_soc_tolerance, "terminal_soc_tolerance")
            if self.terminal_soc_tolerance > 1:
                raise ValueError("terminal_soc_tolerance must be a SOC fraction")
        if not isinstance(self.enforce_line_ampacity, bool):
            raise ValueError("enforce_line_ampacity must be boolean")
        if (not isinstance(self.control_max_iterations, int)
                or isinstance(self.control_max_iterations, bool) or self.control_max_iterations < 1):
            raise ValueError("control_max_iterations must be a positive integer")
        _check_number(self.control_tolerance_kw, "control_tolerance_kw", positive=True)
        for name in ("shedding_penalty_per_kwh", "curtailment_penalty_per_kwh"):
            value = getattr(self, name)
            _check_number(value, name)
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
        if not isinstance(self.legacy_proportional_validation, bool):
            raise ValueError("legacy_proportional_validation must be boolean")
        if self.fleet_dispatch_mode not in ("opf", "daily_milp_dispatch", "predictive", "predictive_24h", "legacy"):
            raise ValueError("fleet_dispatch_mode must be opf, daily_milp_dispatch, predictive, predictive_24h or legacy")
        for field_name in ("opf_bess_kva_multiplier", "opf_pv_kva_multiplier"):
            _check_number(getattr(self, field_name), field_name)
            if getattr(self, field_name) < 1.0:
                raise ValueError(f"{field_name} must be >= 1.0")
        _check_number(self.minimum_discharge_pf, "minimum_discharge_pf", positive=True)
        if self.minimum_discharge_pf > 1.:
            raise ValueError("minimum_discharge_pf must be <= 1")
        if self.dispatch_horizon_hours not in (24, 48, 72):
            raise ValueError("dispatch_horizon_hours must be 24, 48 or 72")
        _check_number(self.daily_soc_tolerance_kwh, "daily_soc_tolerance_kwh", positive=True)
        _check_number(self.predictive_grid_tariff_per_kwh, "predictive_grid_tariff_per_kwh")
        if self.predictive_grid_tariff_per_kwh < 0:
            raise ValueError("predictive_grid_tariff_per_kwh cannot be negative")
        if self.shedding_policy not in ("progressive", "minimum_energy"):
            raise ValueError("Select progressive or minimum_energy shedding")
        edges = tuple(self.shedding_tier_edges)
        weights = tuple(self.shedding_tier_weights)
        for value in (*edges, *weights):
            _check_number(value, "Shedding tier value", positive=True)
        if len(edges) != 2 or not 0 < edges[0] < edges[1] < 1:
            raise ValueError("Shedding tier edges must be two increasing fractions below one")
        if len(weights) != 3 or not weights[0] < weights[1] < weights[2]:
            raise ValueError("Shedding tier weights must be three increasing positive numbers")
        self.shedding_tier_edges = edges
        self.shedding_tier_weights = weights


@dataclass
class SimulationStepResult:
    timestamp: object
    operating_point: OperatingPoint
    power_flow: PowerFlowResult
    bess_request_kw: float
    bess_step: BESSStepResult | None
    bess_state: BESSState | None
    voltage_violations: dict[int, float]
    feasible: bool
    messages: list[str]
    curtailment_kw: float | None = None
    shedding_kw: float | None = None
    curtailment_by_bus_kw: dict[int, float] | None = None
    shedding_by_bus_kw: dict[int, float] | None = None
    dispatch: DispatchEvent | None = None
    requested_point: OperatingPoint | None = None
    pre_control_voltage_pu: dict[int, float] | None = None
    correction: Correction | None = None
    fleet_steps: dict[int, BESSStepResult] | None = None
    fleet_states: dict[int, BESSState] | None = None
    uncontrolled_voltage_pu: dict[int, float] | None = None
    before_correction_voltage_pu: dict[int, float] | None = None


@dataclass
class TimeSeriesSimulationResult:
    steps: list[SimulationStepResult]
    dt_hours: float
    completed: bool
    converged: bool
    feasible: bool
    final_bess_state: BESSState | None
    message: str
    dispatch_timing: dict = field(default_factory=dict)
    final_fleet_states: dict[int, BESSState] | None = None


DispatchPolicy = Callable[[int, ProfileSlice, BESSState], float]


def _check_number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if positive and value <= 0:
        raise ValueError(f"{name} must be greater than zero")


def _complete_profile(values, bus_ids, required_ids, name):
    unknown_ids = set(values) - set(bus_ids)
    if unknown_ids:
        raise ValueError(f"{name} contains unknown buses: {sorted(unknown_ids)}")
    missing_ids = required_ids - set(values)
    if missing_ids:
        raise ValueError(f"{name} is missing configured buses: {sorted(missing_ids)}")
    complete_values = {}
    for bus_id in bus_ids:
        value = values.get(bus_id, 0.0)
        _check_number(value, name)
        if name != "q_pv_kvar" and value < 0:
            raise ValueError(f"{name} cannot contain negative values")
        complete_values[bus_id] = float(value)
    return complete_values


def _run_bess(config, state, request_kw):
    """Apply only physical BESS power, SOC and efficiency limits; no reserve model."""
    return step_bess(config=copy(config), state=copy(state), requested_power_kw=request_kw, dt_hours=1.0)


def _network_violations(flow, settings):
    """Return excess-generation and excess-demand flags for a converged trial."""
    excess_generation = any(v > settings.voltage_max_pu for v in flow.voltage_mag_pu.values())
    excess_demand = any(v < settings.voltage_min_pu for v in flow.voltage_mag_pu.values())
    if settings.grid_export_limit_kw is not None:
        if -flow.slack_p_kw > settings.grid_export_limit_kw + settings.control_tolerance_kw:
            excess_generation = True
    if settings.grid_import_limit_kw is not None:
        if flow.slack_p_kw > settings.grid_import_limit_kw + settings.control_tolerance_kw:
            excess_demand = True
    return excess_generation, excess_demand


def _scale_operating_power(point, fraction_removed, curtail_pv):
    """Build a new trial; reduce P and Q together to preserve power factor."""
    fraction_kept = 1.0 - fraction_removed
    if curtail_pv:
        return replace(
            point,
            p_pv_kw={bus: value * fraction_kept for bus, value in point.p_pv_kw.items()},
            q_pv_kvar={bus: value * fraction_kept for bus, value in point.q_pv_kvar.items()},
        )
    return replace(
        point,
        p_load_kw={bus: value * fraction_kept for bus, value in point.p_load_kw.items()},
        q_load_kvar={bus: value * fraction_kept for bus, value in point.q_load_kvar.items()},
    )


def _reduce_until_allowed(solve, point, flow, settings, curtail_pv, progress=None):
    """Find a proportional reduction that clears the selected network limit."""
    check_index = 0 if curtail_pv else 1
    full_reduction = _scale_operating_power(point, 1.0, curtail_pv)
    full_flow = solve(full_reduction, progress=progress)
    if not full_flow.converged or _network_violations(full_flow, settings)[check_index]:
        return point, flow

    lower, upper = 0.0, 1.0
    accepted_point, accepted_flow = full_reduction, full_flow
    for control_index in range(settings.control_max_iterations):
        if progress is not None:
            progress(ProgressEvent("Control", control_index, settings.control_max_iterations,
                                   "PV curtailment trial" if curtail_pv else "Load shedding trial"))
        fraction = (lower + upper) / 2
        trial_point = _scale_operating_power(point, fraction, curtail_pv)
        trial_flow = solve(trial_point, progress=progress)
        if trial_flow.converged and not _network_violations(trial_flow, settings)[check_index]:
            upper = fraction
            accepted_point, accepted_flow = trial_point, trial_flow
        else:
            lower = fraction
    if progress is not None:
        progress(ProgressEvent("Control", settings.control_max_iterations, settings.control_max_iterations,
                               "Control trials completed"))
    return accepted_point, accepted_flow


def _operating_point(network, profile_slice):
    bus_ids = [bus.bus_id for bus in network.buses]
    load_ids = {load.bus_id for load in network.loads}
    pv_ids = {pv.bus_id for pv in network.pv_units}
    return OperatingPoint(
        p_load_kw=_complete_profile(profile_slice.p_load_kw, bus_ids, load_ids, "p_load_kw"),
        q_load_kvar=_complete_profile(profile_slice.q_load_kvar, bus_ids, load_ids, "q_load_kvar"),
        p_pv_kw=_complete_profile(profile_slice.p_pv_kw, bus_ids, pv_ids, "p_pv_kw"),
        q_pv_kvar=_complete_profile(profile_slice.q_pv_kvar, bus_ids, pv_ids, "q_pv_kvar"),
        p_bess_kw=dict.fromkeys(bus_ids, 0.),
        q_bess_kvar=dict.fromkeys(bus_ids, 0.),
    )


def simulate_step(network: NetworkModel, profile_slice: ProfileSlice,
                  fbs_config: FBSConfig, bess_config: BESSConfig | None = None,
                  bess_state: BESSState | None = None, bess_request_kw: float = 0.0,
                  *, simulation_config: SimulationConfig | None = None,
                  peak_load_kw: float | None = None, progress=None,
                  planner=None, index=None, event=None, capture_dispatch=False,
                  solve_fbs=None, corrector=None) -> SimulationStepResult:
    """Run one hour. bess_state is accepted only when the power flow converges.

    bess_step retains the attempted energy update for diagnosis on failure.
    Apply configured curtailment/shedding after a converged initial FBS.
    Remaining voltage or grid-limit violations mark the result infeasible.
    """
    settings = simulation_config if simulation_config is not None else SimulationConfig()
    if solve_fbs is None:
        network.validate()
        solve_fbs = prepare_fbs(network, fbs_config)
    if planner is None:
        operating_point = _operating_point(network, profile_slice)
    else:
        operating_point, raw_flow, raw_check = planner.uncontrolled(index)
    requested_point = operating_point
    bus_ids = operating_point.p_load_kw
    _check_number(bess_request_kw, "bess_request_kw")
    if (bess_config is None) != (bess_state is None):
        raise ValueError("Supply bess_config and bess_state together")
    if bess_config is None and bess_request_kw != 0:
        raise ValueError("A BESS request requires a BESS configuration and state")

    bess_result = None
    accepted_state = copy(bess_state)
    if bess_config is not None:
        if bess_config.bus_id not in bus_ids:
            raise ValueError("BESS bus is not in the network")
        if peak_load_kw is None:
            peak_load_kw = sum(operating_point.p_load_kw.values())
        _check_number(peak_load_kw, "peak_load_kw")
        if peak_load_kw < sum(operating_point.p_load_kw.values()) - 1e-9:
            raise ValueError("peak_load_kw cannot be less than this hour's total load")
        bess_result = _run_bess(bess_config, bess_state, bess_request_kw)
    if planner is not None:
        power_flow = raw_flow
        after = raw_check
        if capture_dispatch:
            bounds = [_run_bess(bess_config, bess_state, sign * bess_config.power_rating_kw).actual_power_kw
                      for sign in (-1, 1)]
            event.charge_available_kw, event.discharge_available_kw = -bounds[0], bounds[1]
        event.request_kw = bess_request_kw
        corrective = bool(raw_check.violations or not raw_check.converged)
        trial = planner.choose(index, operating_point, raw_check, bess_result.actual_power_kw,
                               corrective=corrective)
        accepted_kw = trial[0] if trial else 0.
        if trial:
            _, power_flow, after = trial
        if abs(accepted_kw - bess_result.actual_power_kw) > 1e-9:
            event.reason_codes.append("no_charge_headroom" if bess_request_kw < 0. and not corrective
                                      else "other_constraint")
            bess_result = _run_bess(bess_config, bess_state, accepted_kw)
            bess_result.limited = True
            bess_result.limit_reason = "Electrical trial limited the battery action"
        elif bess_result.limited:
            power_cap = (min(bess_config.power_rating_kw, bess_config.max_discharge_kw) if bess_request_kw > 0.
                         else min(bess_config.power_rating_kw, bess_config.max_charge_kw))
            if abs(bess_request_kw) > power_cap:
                event.reason_codes.append("power_limit")
            if not set(event.reason_codes).intersection(("power_limit", "no_energy")):
                event.reason_codes.append("soc_limit")
        event.after_bess = after
        event.after_bess_kw = accepted_kw if power_flow.converged else None
    else:
        raw_flow = solve_fbs(requested_point, progress=progress)
        raw_check = check_flow(raw_flow, network, settings)
        power_flow = raw_flow
        if bess_result is not None:
            available_kw = bess_result.actual_power_kw
            if available_kw:
                for fraction in (1., .5, .25, .125, .0625, 0.):
                    power = available_kw * fraction
                    trial = replace(requested_point, p_bess_kw={
                        **requested_point.p_bess_kw, bess_config.bus_id: power})
                    trial_flow = solve_fbs(trial) if power else raw_flow
                    if not power or admissible(raw_check, check_flow(trial_flow, network, settings)):
                        operating_point, power_flow = trial, trial_flow
                        break
                if power != available_kw:
                    bess_result = _run_bess(bess_config, bess_state, power)
                    bess_result.limited = True
                    bess_result.limit_reason = "Electrical trial limited the battery action"
        if capture_dispatch:
            event = DispatchEvent("no-bess" if bess_result is None else "explicit-dispatch",
                                  "", bess_config.bus_id if bess_config else None, 0, [],
                                  raw_check, request_kw=bess_request_kw)
    if planner is not None:
        operating_point = replace(operating_point, p_bess_kw={
            **operating_point.p_bess_kw, bess_config.bus_id: bess_result.actual_power_kw})
    original_load = requested_point.p_load_kw
    original_pv = requested_point.p_pv_kw
    voltage_violations = {}
    messages = []
    curtailment = shedding = None
    after_bess_check = (event.after_bess if event is not None and event.after_bess is not None
                        else raw_check if power_flow is raw_flow else check_flow(power_flow, network, settings))
    reference_flow = power_flow
    if capture_dispatch and event is not None:
        event.after_bess = after_bess_check
        event.after_bess_kw = bess_result.actual_power_kw if bess_result is not None and power_flow.converged else None
    correction = Correction(status="legacy_proportional_validation")
    if not settings.legacy_proportional_validation:
        if after_bess_check.violations or not power_flow.converged:
            if corrector is None:
                corrector = NetworkCorrector(network, settings, solve_fbs)
            operating_point, power_flow, correction = corrector.correct(operating_point, power_flow, after_bess_check)
        else:
            correction = Correction()
    elif power_flow.converged:
        excess_generation, _ = _network_violations(power_flow, settings)
        if excess_generation and settings.allow_pv_curtailment:
            operating_point, power_flow = _reduce_until_allowed(
                solve_fbs, operating_point, power_flow, settings, curtail_pv=True, progress=progress
            )
        _, excess_demand = _network_violations(power_flow, settings)
        if excess_demand and settings.allow_load_shedding:
            operating_point, power_flow = _reduce_until_allowed(
                solve_fbs, operating_point, power_flow, settings, curtail_pv=False, progress=progress
            )
    if correction.status not in ("legacy_proportional_validation", "not_needed", "verified"):
        messages.append(f"Corrective control unresolved ({correction.status})")
    if power_flow.converged:
        curtailment = {}
        shedding = {}
        for bus_id in bus_ids:
            curtailment[bus_id] = max(0.0, original_pv[bus_id] - operating_point.p_pv_kw[bus_id])
            shedding[bus_id] = max(0.0, original_load[bus_id] - operating_point.p_load_kw[bus_id])
        if sum(curtailment.values()) > 1e-9:
            messages.append(f"Curtailed {sum(curtailment.values()):.6f} kW of available PV")
        if sum(shedding.values()) > 1e-9:
            messages.append(f"Shed {sum(shedding.values()):.6f} kW of requested demand")
        for bus_id, voltage in power_flow.voltage_mag_pu.items():
            if voltage < settings.voltage_min_pu or voltage > settings.voltage_max_pu:
                voltage_violations[bus_id] = voltage
        if bess_result is not None:
            accepted_state = BESSState(
                energy_kwh=bess_result.energy_after_kwh, soc=bess_result.soc_after
            )
    else:
        messages.append(f"Power flow failed: {power_flow.message}")
    if voltage_violations:
        messages.append(f"Voltage limits violated at buses {sorted(voltage_violations)}")
    line_overloads = []
    if power_flow.converged and settings.enforce_line_ampacity:
        for line in network.lines:
            if (line.ampacity_a is not None
                and power_flow.branch_current_a.get(line.line_id, 0.0) > line.ampacity_a + 1e-6):
                line_overloads.append(line.line_id)
        if line_overloads:
            messages.append(f"Line ampacity exceeded: {line_overloads}")
    feasible = power_flow.converged and not voltage_violations and not line_overloads
    if power_flow.converged:
        excess_generation, excess_demand = _network_violations(power_flow, settings)
        if excess_generation or excess_demand:
            feasible = False
            messages.append("Network voltage/import/export limits remain violated after controls")
    if capture_dispatch and event is not None:
        event.final = check_flow(power_flow, network, settings)
        from .control_audit import constraint_evidence
        event.evidence = constraint_evidence(network, settings, (event.pre, event.after_bess, event.final),
                                             (raw_flow, reference_flow, power_flow))
        event.correction = asdict(correction)
        event.accepted_kw = (bess_result.actual_power_kw if bess_result is not None and power_flow.converged
                             else None)
        if not power_flow.converged and "nonconvergence" not in event.reason_codes:
            event.reason_codes.append("nonconvergence")
        if power_flow.converged:
            excess_generation, excess_demand = _network_violations(power_flow, settings)
            if excess_generation:
                event.reason_codes.append("curtailment_unresolved" if settings.allow_pv_curtailment
                                          else "pv_curtailment_disabled")
            if excess_demand:
                event.reason_codes.append("shedding_unresolved" if settings.allow_load_shedding
                                          else "load_shedding_disabled")
            if line_overloads:
                event.reason_codes.append("ampacity_unresolved")
            if curtailment is not None and sum(curtailment.values()) > 1e-9:
                event.reason_codes.append("pv_curtailed")
            if shedding is not None and sum(shedding.values()) > 1e-9:
                event.reason_codes.append("load_shed")
    return SimulationStepResult(
        timestamp=profile_slice.timestamp,
        operating_point=operating_point, power_flow=power_flow,
        bess_request_kw=bess_request_kw, bess_step=bess_result,
        bess_state=accepted_state, voltage_violations=voltage_violations,
        feasible=bool(feasible), messages=messages,
        curtailment_kw=sum(curtailment.values()) if curtailment is not None else None,
        shedding_kw=sum(shedding.values()) if shedding is not None else None,
        curtailment_by_bus_kw=curtailment, shedding_by_bus_kw=shedding,
        dispatch=event if capture_dispatch else None,
        requested_point=requested_point if capture_dispatch else None,
        pre_control_voltage_pu=raw_flow.voltage_mag_pu if capture_dispatch and raw_flow.converged else None,
        uncontrolled_voltage_pu=raw_flow.voltage_mag_pu if capture_dispatch and raw_flow.converged else None,
        before_correction_voltage_pu=reference_flow.voltage_mag_pu if capture_dispatch and reference_flow.converged else None,
        correction=correction,
    )


_DEFAULT_DISPATCH = ConstraintAwareDispatch()


def simulate_timeseries(network: NetworkModel, profiles: ProfileData,
                        simulation_config: SimulationConfig,
                        bess_config: BESSConfig | None = None,
                        dispatch_policy: DispatchPolicy | ConstraintAwareDispatch | None = _DEFAULT_DISPATCH,
                        *, progress=None, hourly_progress_only=False, capture_dispatch=True,
                        bess_fleet=None) -> TimeSeriesSimulationResult:
    """Run all supplied hourly profiles, starting from config.soc_initial.

    An explicit None requests idle diagnostic dispatch. A callable is supported
    for engineering validation and receives its own copy of the battery state.
    completed describes processing coverage; feasible includes all constraints.
    """
    if (bess_fleet is not None or simulation_config.fleet_dispatch_mode == 'daily_milp_dispatch'
            or (bess_config is None and simulation_config.fleet_dispatch_mode == 'opf')):
        from .multi_bess import simulate_timeseries_fleet
        fleet = tuple(bess_fleet) if bess_fleet is not None else ((bess_config,) if bess_config is not None else ())
        return simulate_timeseries_fleet(network, profiles, simulation_config,
                                         fleet, progress=progress, capture_dispatch=capture_dispatch)
    started = perf_counter()
    network.validate()
    if not profiles.timestamps:
        raise ValueError("The simulation requires at least one timestamp")
    if profiles.dt_hours != 1.0:
        raise ValueError("The simulation currently requires hourly profiles")
    if bess_config is None and dispatch_policy is _DEFAULT_DISPATCH:
        dispatch_policy = None
    if dispatch_policy is not None and bess_config is None:
        raise ValueError("A dispatch policy requires a BESS configuration")
    if dispatch_policy is not None and not (callable(dispatch_policy) or isinstance(dispatch_policy, ConstraintAwareDispatch)):
        raise ValueError("dispatch_policy must be callable")
    count = len(profiles.timestamps)
    for name in ("load_p_kw", "load_q_kvar", "pv_p_kw", "pv_q_kvar"):
        for bus_id, values in getattr(profiles, name).items():
            if len(values) != count:
                raise ValueError(f"{name} at bus {bus_id} must have a value for every timestamp")
    for index in range(1, count):
        difference = profiles.timestamps[index] - profiles.timestamps[index - 1]
        if difference.total_seconds() != 3600:
            raise ValueError("Profile timestamps must be consecutive hours")

    peak_load_kw = 0.0
    for index in range(count):
        total_load_kw = 0.0
        for values in profiles.load_p_kw.values():
            value = values[index]
            _check_number(value, "load_p_kw")
            if value < 0:
                raise ValueError("Load power cannot be negative")
            total_load_kw += value
        peak_load_kw = max(peak_load_kw, total_load_kw)

    state = None
    if bess_config is not None:
        state = BESSState(
            energy_kwh=bess_config.energy_capacity_kwh * bess_config.soc_initial,
            soc=bess_config.soc_initial,
        )
    prepared_fbs = prepare_fbs(network, simulation_config.fbs_config)
    fbs_calls = 0
    fbs_seconds = 0.

    def solve_fbs(point, progress=None):
        nonlocal fbs_calls, fbs_seconds
        start = perf_counter()
        flow = prepared_fbs(point, progress=progress)
        fbs_calls += 1
        fbs_seconds += perf_counter() - start
        return flow

    corrector = NetworkCorrector(network, simulation_config, solve_fbs)
    planner = None
    if isinstance(dispatch_policy, ConstraintAwareDispatch):
        planner = RollingDispatch(network, simulation_config, bess_config, dispatch_policy,
                                  profiles.timestamps,
                                  lambda index: _operating_point(network, profile_at(profiles, index)),
                                  solve_fbs)
    preparation_seconds = perf_counter() - started
    steps = []
    for index in range(count):
        if progress is not None:
            progress(ProgressEvent("Simulation", index, count,
                                   f"processing hour {index + 1}; source time {profiles.timestamps[index]}"))
        profile_slice = profile_at(profiles, index)
        request_kw = 0.0
        event = None
        if planner is not None:
            request_kw, event = planner.plan(index, state, capture=capture_dispatch)
        elif dispatch_policy is not None:
            request_kw = dispatch_policy(index, profile_slice, copy(state))
        step = simulate_step(
            network=network, profile_slice=profile_slice,
            fbs_config=simulation_config.fbs_config,
            bess_config=bess_config, bess_state=state, bess_request_kw=request_kw,
            simulation_config=simulation_config, peak_load_kw=peak_load_kw,
            progress=None if hourly_progress_only else progress,
            planner=planner, index=index, event=event, capture_dispatch=capture_dispatch, solve_fbs=solve_fbs,
            corrector=corrector,
        )
        steps.append(step)
        state = copy(step.bess_state)
        if progress is not None:
            progress(ProgressEvent("Simulation", index + 1, count,
                                   f"{step.timestamp} | FBS converged={step.power_flow.converged}",
                                   hour_finished=True))
        if not step.power_flow.converged and simulation_config.stop_on_power_flow_failure:
            break

    completed = len(steps) == count
    converged = all(step.power_flow.converged for step in steps)
    feasible = all(step.feasible for step in steps)
    if not converged:
        message = "Power-flow failure; inspect step messages."
    elif not feasible:
        message = "Completed with voltage or grid-limit violations."
    else:
        message = "Completed successfully."
    return TimeSeriesSimulationResult(
        steps=steps, dt_hours=1.0, completed=completed, converged=converged,
        feasible=feasible, final_bess_state=copy(state), message=message,
        dispatch_timing={"planning_seconds": planner.plan_seconds if planner else 0.,
                         "dispatch_fbs_seconds": planner.flow_seconds if planner else 0.,
                         "dispatch_fbs_trials": planner.flow_trials if planner else 0,
                         "correction_seconds": corrector.seconds, "correction_fbs_trials": corrector.trials,
                         "correction_hours": corrector.evaluations, "correction_unresolved_hours": corrector.unresolved,
                         "fbs_calls": fbs_calls, "fbs_seconds": fbs_seconds,
                         "sensitivity_calls": corrector.sensitivity_calls, "sensitivity_seconds": corrector.sensitivity_seconds,
                         "lp_calls": corrector.lp_calls, "lp_seconds": corrector.lp_seconds,
                         "lp_redundant_rows": corrector.lp_redundant_rows,
                         "verified_linear_shortcuts": corrector.verified_linear_shortcuts,
                         "sensitivity_probe_trials": corrector.probe_trials,
                         "preparation_seconds": preparation_seconds, "elapsed_seconds": perf_counter() - started},
    )
