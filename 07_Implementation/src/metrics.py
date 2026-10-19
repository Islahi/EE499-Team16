"""Summarize simulation performance and the agreed two-coefficient BESS cost."""
from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite

from .bess import BESSConfig
from .simulation import TimeSeriesSimulationResult


@dataclass
class EconomicConfig:
    cost_per_kwh: float | None = None
    cost_per_kw: float | None = None
    currency: str = "SAR"

    def __post_init__(self):
        for name in ("cost_per_kwh", "cost_per_kw"):
            value = getattr(self, name)
            if value is not None:
                _check_nonnegative(value, name)
        if not isinstance(self.currency, str) or not self.currency.strip():
            raise ValueError("currency must be a nonempty label")


@dataclass
class PerformanceMetrics:
    duration_hours: float
    served_load_energy_kwh: float
    pv_generation_energy_kwh: float
    grid_import_energy_kwh: float
    grid_export_energy_kwh: float
    loss_energy_kwh: float
    peak_grid_import_kw: float
    voltage_min_pu: float
    voltage_max_pu: float
    voltage_violation_hours: float
    voltage_violation_bus_hours: float
    reserve_violation_hours: float
    bess_charge_energy_kwh: float
    bess_discharge_energy_kwh: float
    bess_soc_min: float | None
    bess_soc_max: float | None
    bess_cost: float | None
    currency: str
    curtailment_energy_kwh: float | None
    load_shedding_energy_kwh: float | None
    feasible: bool
    notes: list[str]
    requested_load_energy_kwh: float | None = None
    available_pv_energy_kwh: float | None = None


def _check_nonnegative(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < 0:
        raise ValueError(f"{name} cannot be negative")


def _sum_optional_energy(values, step_count, dt_hours, name):
    if values is None:
        return None
    if len(values) != step_count:
        raise ValueError(f"{name} must contain one power value per simulation step")
    energy_kwh = 0.0
    for value in values:
        _check_nonnegative(value, name)
        energy_kwh += value * dt_hours
    return energy_kwh


def _control_values(steps, supplied_values, name):
    """Prefer actual operating records; external values cannot contradict them."""
    recorded_values = [getattr(step, name, None) for step in steps]
    if supplied_values is not None:
        if len(supplied_values) != len(steps):
            raise ValueError(f"{name} must contain one power value per simulation step")
        for supplied, recorded in zip(supplied_values, recorded_values):
            _check_nonnegative(supplied, name)
            if recorded is not None and abs(supplied - recorded) > 1e-6:
                raise ValueError(f"{name} contradicts the simulation's recorded control action")
        return supplied_values
    if any(value is None for value in recorded_values):
        return None
    return recorded_values


def evaluate_results(simulation_result: TimeSeriesSimulationResult,
                     economic_config: EconomicConfig,
                     bess_config: BESSConfig | None = None,
                     *, curtailment_kw: Sequence[float] | None = None,
                     shedding_kw: Sequence[float] | None = None) -> PerformanceMetrics:
    """Summarize a completed, converged run without changing engineering state.

    Supply the same bess_config used by the simulator. Optional curtailment and
    shedding series are optional legacy inputs. Normally the simulator's own
    per-step action records provide these values automatically.
    """
    steps = simulation_result.steps
    if not steps:
        raise ValueError("Cannot evaluate an empty simulation")
    if not simulation_result.completed or not simulation_result.converged:
        raise ValueError("Metrics require a completed, converged simulation")
    for step in steps:
        if not step.power_flow.converged:
            raise ValueError("Cannot evaluate non-converged power-flow steps")
    dt_hours = simulation_result.dt_hours
    _check_nonnegative(dt_hours, "dt_hours")
    if dt_hours == 0:
        raise ValueError("dt_hours must be greater than zero")

    has_bess = any(step.bess_step is not None for step in steps)
    if has_bess and bess_config is None:
        raise ValueError("Supply the BESS configuration used for this simulation")
    if not has_bess and bess_config is not None:
        raise ValueError("BESS configuration supplied for a simulation without a BESS")
    curtailment_kw = _control_values(steps, curtailment_kw, "curtailment_kw")
    shedding_kw = _control_values(steps, shedding_kw, "shedding_kw")

    metrics = PerformanceMetrics(
        duration_hours=len(steps) * dt_hours,
        served_load_energy_kwh=0.0, pv_generation_energy_kwh=0.0,
        grid_import_energy_kwh=0.0, grid_export_energy_kwh=0.0,
        loss_energy_kwh=0.0, peak_grid_import_kw=0.0,
        voltage_min_pu=float("inf"), voltage_max_pu=0.0,
        voltage_violation_hours=0.0, voltage_violation_bus_hours=0.0,
        reserve_violation_hours=0.0,
        bess_charge_energy_kwh=0.0, bess_discharge_energy_kwh=0.0,
        bess_soc_min=None, bess_soc_max=None,
        bess_cost=0.0, currency=economic_config.currency,
        curtailment_energy_kwh=_sum_optional_energy(
            curtailment_kw, len(steps), dt_hours, "curtailment_kw"
        ),
        load_shedding_energy_kwh=_sum_optional_energy(
            shedding_kw, len(steps), dt_hours, "shedding_kw"
        ),
        feasible=simulation_result.feasible and all(step.feasible for step in steps),
        notes=[],
    )
    for step in steps:
        point = step.operating_point
        flow = step.power_flow
        metrics.served_load_energy_kwh += sum(point.p_load_kw.values()) * dt_hours
        metrics.pv_generation_energy_kwh += sum(point.p_pv_kw.values()) * dt_hours
        metrics.grid_import_energy_kwh += max(flow.slack_p_kw, 0.0) * dt_hours
        metrics.grid_export_energy_kwh += max(-flow.slack_p_kw, 0.0) * dt_hours
        metrics.loss_energy_kwh += flow.total_loss_p_kw * dt_hours
        metrics.peak_grid_import_kw = max(metrics.peak_grid_import_kw, flow.slack_p_kw)
        metrics.voltage_min_pu = min(metrics.voltage_min_pu, min(flow.voltage_mag_pu.values()))
        metrics.voltage_max_pu = max(metrics.voltage_max_pu, max(flow.voltage_mag_pu.values()))
        if step.voltage_violations:
            metrics.voltage_violation_hours += dt_hours
            metrics.voltage_violation_bus_hours += len(step.voltage_violations) * dt_hours
        if step.reserve_power_shortfall_kw > 1e-9 or step.reserve_energy_shortfall_kwh > 1e-9:
            metrics.reserve_violation_hours += dt_hours
        if step.bess_step is not None:
            actual_kw = step.bess_step.actual_power_kw
            metrics.bess_charge_energy_kwh += max(-actual_kw, 0.0) * dt_hours
            metrics.bess_discharge_energy_kwh += max(actual_kw, 0.0) * dt_hours
            hour_soc_min = min(step.bess_step.soc_before, step.bess_state.soc)
            hour_soc_max = max(step.bess_step.soc_before, step.bess_state.soc)
            if metrics.bess_soc_min is None:
                metrics.bess_soc_min = hour_soc_min
                metrics.bess_soc_max = hour_soc_max
            else:
                metrics.bess_soc_min = min(metrics.bess_soc_min, hour_soc_min)
                metrics.bess_soc_max = max(metrics.bess_soc_max, hour_soc_max)

    if has_bess:
        if economic_config.cost_per_kwh is None or economic_config.cost_per_kw is None:
            metrics.bess_cost = None
            metrics.notes.append("BESS cost unavailable: supply both economic coefficients.")
        else:
            metrics.bess_cost = (
                economic_config.cost_per_kwh * bess_config.energy_capacity_kwh
                + economic_config.cost_per_kw * bess_config.power_rating_kw
            )
    if curtailment_kw is None:
        metrics.notes.append("Curtailment unavailable: this run has no complete action records.")
    if shedding_kw is None:
        metrics.notes.append("Load shedding unavailable: this run has no complete action records.")
    if metrics.curtailment_energy_kwh is not None:
        metrics.available_pv_energy_kwh = metrics.pv_generation_energy_kwh + metrics.curtailment_energy_kwh
    if metrics.load_shedding_energy_kwh is not None:
        metrics.requested_load_energy_kwh = metrics.served_load_energy_kwh + metrics.load_shedding_energy_kwh
    if not metrics.feasible:
        metrics.notes.append("This run has network or reserve violations; retain its infeasible status.")
    return metrics


def percentage_reduction(baseline: float | None, candidate: float | None) -> float | None:
    """Return reduction percent; negative is worse and None means unavailable."""
    if baseline is None or candidate is None:
        return None
    _check_nonnegative(baseline, "baseline")
    _check_nonnegative(candidate, "candidate")
    if baseline == 0:
        if candidate == 0:
            return 0.0
        return None
    return 100.0 * (baseline - candidate) / baseline
