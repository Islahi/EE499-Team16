"""Hourly orchestration of profile inputs, BESS operation and FBS power flow."""
from collections.abc import Callable
from copy import copy
from dataclasses import dataclass, field, replace
from math import isfinite

from .fbs import FBSConfig, OperatingPoint, PowerFlowResult, run_fbs
from .bess import BESSConfig, BESSState, BESSStepResult, step_bess
from .network_model import NetworkModel
from .data_loader import ProfileSlice, ProfileData, profile_at
from .progress import ProgressEvent


@dataclass
class SimulationConfig:
    fbs_config: FBSConfig = field(default_factory=FBSConfig)
    voltage_min_pu: float = 0.95
    voltage_max_pu: float = 1.05
    reserve_fraction: float = 0.10
    reserve_duration_hours: float = 1.0
    stop_on_power_flow_failure: bool = True
    allow_pv_curtailment: bool = True
    allow_load_shedding: bool = True
    grid_import_limit_kw: float | None = None
    grid_export_limit_kw: float | None = None
    control_max_iterations: int = 30
    control_tolerance_kw: float = 1e-6

    def __post_init__(self):
        _check_number(self.voltage_min_pu, "voltage_min_pu", positive=True)
        _check_number(self.voltage_max_pu, "voltage_max_pu", positive=True)
        if self.voltage_min_pu >= self.voltage_max_pu:
            raise ValueError("Minimum voltage must be less than maximum voltage")
        _check_number(self.reserve_fraction, "reserve_fraction")
        if not 0 <= self.reserve_fraction <= 1:
            raise ValueError("reserve_fraction must be between zero and one")
        _check_number(self.reserve_duration_hours, "reserve_duration_hours", positive=True)
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
        if (not isinstance(self.control_max_iterations, int)
                or isinstance(self.control_max_iterations, bool) or self.control_max_iterations < 1):
            raise ValueError("control_max_iterations must be a positive integer")
        _check_number(self.control_tolerance_kw, "control_tolerance_kw", positive=True)


@dataclass
class SimulationStepResult:
    timestamp: object
    operating_point: OperatingPoint
    power_flow: PowerFlowResult
    bess_request_kw: float
    bess_step: BESSStepResult | None
    bess_state: BESSState | None
    voltage_violations: dict[int, float]
    reserve_power_kw: float
    reserve_power_shortfall_kw: float
    reserve_energy_shortfall_kwh: float
    feasible: bool
    messages: list[str]
    curtailment_kw: float | None = None
    shedding_kw: float | None = None
    curtailment_by_bus_kw: dict[int, float] | None = None
    shedding_by_bus_kw: dict[int, float] | None = None


@dataclass
class TimeSeriesSimulationResult:
    steps: list[SimulationStepResult]
    dt_hours: float
    completed: bool
    converged: bool
    feasible: bool
    final_bess_state: BESSState | None
    message: str


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


def _run_bess(config, state, request_kw, reserve_kw, reserve_hours):
    """Retain reserve through the existing public BESS step function."""
    discharge_limit_kw = min(
        config.power_rating_kw,
        config.max_discharge_kw if config.max_discharge_kw is not None else config.power_rating_kw,
    )
    minimum_energy = config.soc_min * config.energy_capacity_kwh
    reserve_energy = reserve_kw * reserve_hours / config.eta_discharge
    required_energy = minimum_energy + reserve_energy

    operating_config = copy(config)
    operating_config.soc_min = min(
        config.soc_max, required_energy / config.energy_capacity_kwh
    )
    allowed_discharge_kw = max(0.0, discharge_limit_kw - reserve_kw)
    operating_request_kw = min(request_kw, allowed_discharge_kw)
    result = step_bess(
        config=operating_config,
        state=copy(state),
        requested_power_kw=operating_request_kw,
        dt_hours=1.0,
    )
    # Keep clipping diagnostics relative to the caller's original request.
    if abs(result.actual_power_kw - request_kw) > 1e-9:
        result.limited = True
        if operating_request_kw != request_kw or operating_config.soc_min > config.soc_min:
            result.limit_reason = "Reserve and/or BESS power/SOC limit reached"

    power_shortfall = max(
        0.0, reserve_kw - (discharge_limit_kw - max(result.actual_power_kw, 0.0))
    )
    energy_shortfall = max(
        0.0, required_energy - min(state.energy_kwh, result.energy_after_kwh)
    )
    return result, power_shortfall, energy_shortfall


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


def _reduce_until_allowed(network, point, flow, fbs_config, settings, curtail_pv, progress=None):
    """Find a proportional reduction that clears the selected network limit."""
    check_index = 0 if curtail_pv else 1
    full_reduction = _scale_operating_power(point, 1.0, curtail_pv)
    full_flow = run_fbs(network, full_reduction, fbs_config, progress=progress)
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
        trial_flow = run_fbs(network, trial_point, fbs_config, progress=progress)
        if trial_flow.converged and not _network_violations(trial_flow, settings)[check_index]:
            upper = fraction
            accepted_point, accepted_flow = trial_point, trial_flow
        else:
            lower = fraction
    if progress is not None:
        progress(ProgressEvent("Control", settings.control_max_iterations, settings.control_max_iterations,
                               "Control trials completed"))
    return accepted_point, accepted_flow


def simulate_step(network: NetworkModel, profile_slice: ProfileSlice,
                  fbs_config: FBSConfig, bess_config: BESSConfig | None = None,
                  bess_state: BESSState | None = None, bess_request_kw: float = 0.0,
                  *, simulation_config: SimulationConfig | None = None,
                  peak_load_kw: float | None = None, progress=None) -> SimulationStepResult:
    """Run one hour. bess_state is accepted only when the power flow converges.

    bess_step retains the attempted energy update for diagnosis on failure.
    Apply configured curtailment/shedding after a converged initial FBS.
    Remaining voltage, grid-cap or reserve violations mark the result infeasible.
    """
    settings = simulation_config if simulation_config is not None else SimulationConfig()
    network.validate()
    bus_ids = [bus.bus_id for bus in network.buses]
    load_ids = {load.bus_id for load in network.loads}
    pv_ids = {pv.bus_id for pv in network.pv_units}
    operating_point = OperatingPoint(
        p_load_kw=_complete_profile(profile_slice.p_load_kw, bus_ids, load_ids, "p_load_kw"),
        q_load_kvar=_complete_profile(profile_slice.q_load_kvar, bus_ids, load_ids, "q_load_kvar"),
        p_pv_kw=_complete_profile(profile_slice.p_pv_kw, bus_ids, pv_ids, "p_pv_kw"),
        q_pv_kvar=_complete_profile(profile_slice.q_pv_kvar, bus_ids, pv_ids, "q_pv_kvar"),
        p_bess_kw={bus_id: 0.0 for bus_id in bus_ids},
        q_bess_kvar={bus_id: 0.0 for bus_id in bus_ids},
    )
    _check_number(bess_request_kw, "bess_request_kw")
    if (bess_config is None) != (bess_state is None):
        raise ValueError("Supply bess_config and bess_state together")
    if bess_config is None and bess_request_kw != 0:
        raise ValueError("A BESS request requires a BESS configuration and state")

    bess_result = None
    reserve_kw = power_shortfall = energy_shortfall = 0.0
    accepted_state = copy(bess_state)
    if bess_config is not None:
        if bess_config.bus_id not in bus_ids:
            raise ValueError("BESS bus is not in the network")
        if peak_load_kw is None:
            peak_load_kw = sum(operating_point.p_load_kw.values())
        _check_number(peak_load_kw, "peak_load_kw")
        if peak_load_kw < sum(operating_point.p_load_kw.values()) - 1e-9:
            raise ValueError("peak_load_kw cannot be less than this hour's total load")
        reserve_kw = settings.reserve_fraction * peak_load_kw
        bess_result, power_shortfall, energy_shortfall = _run_bess(
            config=bess_config, state=bess_state, request_kw=bess_request_kw,
            reserve_kw=reserve_kw, reserve_hours=settings.reserve_duration_hours,
        )
        operating_point.p_bess_kw[bess_config.bus_id] = bess_result.actual_power_kw

    power_flow = run_fbs(network, operating_point, fbs_config, progress=progress)
    original_load = operating_point.p_load_kw.copy()
    original_pv = operating_point.p_pv_kw.copy()
    voltage_violations = {}
    messages = []
    curtailment = shedding = None
    if power_flow.converged:
        excess_generation, excess_demand = _network_violations(power_flow, settings)
        if bess_result is not None:
            actual_kw = bess_result.actual_power_kw
            if (excess_generation and actual_kw > 0) or (excess_demand and actual_kw < 0):
                idle_bess, idle_power_shortfall, idle_energy_shortfall = _run_bess(
                    config=bess_config, state=bess_state, request_kw=0.0,
                    reserve_kw=reserve_kw, reserve_hours=settings.reserve_duration_hours,
                )
                idle_point = replace(operating_point, p_bess_kw=operating_point.p_bess_kw.copy())
                idle_point.p_bess_kw[bess_config.bus_id] = idle_bess.actual_power_kw
                idle_flow = run_fbs(network, idle_point, fbs_config, progress=progress)
                if idle_flow.converged:
                    operating_point, power_flow = idle_point, idle_flow
                    bess_result = idle_bess
                    power_shortfall, energy_shortfall = idle_power_shortfall, idle_energy_shortfall
                    bess_result.limited = True
                    bess_result.limit_reason = "Battery request paused for network limits"
                    messages.append(bess_result.limit_reason)

        excess_generation, _ = _network_violations(power_flow, settings)
        if excess_generation and settings.allow_pv_curtailment:
            operating_point, power_flow = _reduce_until_allowed(
                network, operating_point, power_flow, fbs_config, settings, curtail_pv=True, progress=progress
            )
        _, excess_demand = _network_violations(power_flow, settings)
        if excess_demand and settings.allow_load_shedding:
            operating_point, power_flow = _reduce_until_allowed(
                network, operating_point, power_flow, fbs_config, settings, curtail_pv=False, progress=progress
            )

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
    if power_shortfall > 1e-9 or energy_shortfall > 1e-9:
        messages.append("BESS cannot supply the required power/energy reserve for this hour")
    feasible = power_flow.converged and not voltage_violations
    feasible = feasible and power_shortfall <= 1e-9 and energy_shortfall <= 1e-9
    if power_flow.converged:
        excess_generation, excess_demand = _network_violations(power_flow, settings)
        if excess_generation or excess_demand:
            feasible = False
            messages.append("Network voltage/import/export limits remain violated after controls")
    return SimulationStepResult(
        timestamp=profile_slice.timestamp,
        operating_point=operating_point, power_flow=power_flow,
        bess_request_kw=bess_request_kw, bess_step=bess_result,
        bess_state=accepted_state, voltage_violations=voltage_violations,
        reserve_power_kw=reserve_kw, reserve_power_shortfall_kw=power_shortfall,
        reserve_energy_shortfall_kwh=energy_shortfall,
        feasible=bool(feasible), messages=messages,
        curtailment_kw=sum(curtailment.values()) if curtailment is not None else None,
        shedding_kw=sum(shedding.values()) if shedding is not None else None,
        curtailment_by_bus_kw=curtailment, shedding_by_bus_kw=shedding,
    )


def simulate_timeseries(network: NetworkModel, profiles: ProfileData,
                        simulation_config: SimulationConfig,
                        bess_config: BESSConfig | None = None,
                        dispatch_policy: DispatchPolicy | None = None, *, progress=None) -> TimeSeriesSimulationResult:
    """Run all supplied hourly profiles, starting from config.soc_initial.

    dispatch_policy(index, profile_slice, state) returns requested kW. With no
    policy, the BESS stays idle. Each policy receives its own state copy.
    completed describes processing coverage; feasible includes all constraints.
    """
    network.validate()
    if not profiles.timestamps:
        raise ValueError("The simulation requires at least one timestamp")
    if profiles.dt_hours != 1.0:
        raise ValueError("The simulation currently requires hourly profiles")
    if dispatch_policy is not None and bess_config is None:
        raise ValueError("A dispatch policy requires a BESS configuration")
    if dispatch_policy is not None and not callable(dispatch_policy):
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
    steps = []
    for index in range(count):
        if progress is not None:
            progress(ProgressEvent("Simulation", index, count,
                                   f"processing hour {index + 1}; source time {profiles.timestamps[index]}"))
        profile_slice = profile_at(profiles, index)
        request_kw = 0.0
        if dispatch_policy is not None:
            request_kw = dispatch_policy(index, profile_slice, copy(state))
        step = simulate_step(
            network=network, profile_slice=profile_slice,
            fbs_config=simulation_config.fbs_config,
            bess_config=bess_config, bess_state=state, bess_request_kw=request_kw,
            simulation_config=simulation_config, peak_load_kw=peak_load_kw, progress=progress,
        )
        steps.append(step)
        state = copy(step.bess_state)
        if progress is not None:
            progress(ProgressEvent("Simulation", index + 1, count,
                                   f"hour completed; source time {step.timestamp}; FBS converged={step.power_flow.converged}"))
        if not step.power_flow.converged and simulation_config.stop_on_power_flow_failure:
            break

    completed = len(steps) == count
    converged = all(step.power_flow.converged for step in steps)
    feasible = all(step.feasible for step in steps)
    if not converged:
        message = "Power-flow failure; inspect step messages."
    elif not feasible:
        message = "Completed with voltage, grid-limit or reserve violations."
    else:
        message = "Completed successfully."
    return TimeSeriesSimulationResult(
        steps=steps, dt_hours=1.0, completed=completed, converged=converged,
        feasible=feasible, final_bess_state=copy(state), message=message,
    )
