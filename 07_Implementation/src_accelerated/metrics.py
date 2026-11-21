"""Summarize simulation performance and the agreed two-coefficient BESS cost."""
from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite

from .bess import BESSConfig
from .simulation import TimeSeriesSimulationResult


@dataclass
class EconomicConfig:
    cost_per_kwh: float | None = 385.0
    cost_per_kw: float | None = 770.0
    currency: str = "USD"
    discount_rate: float = 0.06
    lifetime_years: int = 10
    annual_om_fraction: float = 0.02
    curtailment_penalty_per_kwh: float = 0.07
    shedding_penalty_per_kwh: float = 12.0
    grid_import_tariff_per_kwh: float | None = None
    grid_export_tariff_per_kwh: float | None = None
    fixed_installation_cost: float = 0.0
    terminal_energy_price_per_kwh: float | None = None
    annual_hours: float = 8760.0
    scenario: str = "Ali2022 battery + Cordova2022 sensitivity; discount is project assumption"
    annual_day_weights: tuple[float, ...] = ()
    annualization_basis: str = ""
    terminal_policy: str = "equal_soc"
    terminal_soc_tolerance: float = 1e-6
    provenance: str = "CAPEX/lifetime/O&M: Ali2022; penalties: Cordova2022 distinct penalties; discount 6%: project assumption; tariffs: user supplied"


    def __post_init__(self):
        for name in ("cost_per_kwh", "cost_per_kw"):
            value = getattr(self, name)
            if value is not None:
                _check_nonnegative(value, name)
        for name in ("discount_rate", "annual_om_fraction", "curtailment_penalty_per_kwh",
                     "shedding_penalty_per_kwh", "fixed_installation_cost", "annual_hours", "terminal_soc_tolerance"):
            _check_nonnegative(getattr(self, name), name)
        if isinstance(self.lifetime_years,bool) or not isinstance(self.lifetime_years, int) or self.lifetime_years < 1:
            raise ValueError("Battery lifetime must be a positive integer")
        if self.terminal_energy_price_per_kwh is not None:
            _check_nonnegative(self.terminal_energy_price_per_kwh, "terminal_energy_price_per_kwh")
        if self.annual_hours <= 0:
            raise ValueError("annual_hours must be positive")
        if self.currency != "USD":
            raise ValueError("This economic scenario requires all monetary inputs in USD")
        for name in ("grid_import_tariff_per_kwh", "grid_export_tariff_per_kwh"):
            if getattr(self, name) is not None:
                _check_nonnegative(getattr(self, name), name)
        if self.terminal_policy not in ("equal_soc", "priced_energy"):
            raise ValueError("Choose equal_soc or explicitly priced_energy terminal policy")
        if self.terminal_policy == "priced_energy" and not self.terminal_energy_price_per_kwh:
            raise ValueError("Priced terminal policy requires an explicit positive replacement energy price")
        for w in self.annual_day_weights:
            _check_nonnegative(w, "annual day weight")
        if self.annual_hours not in (8760, 8784):
            raise ValueError("Annual coverage must be 365 or 366 days")


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
    annualized_bess_cost: float | None = None
    annual_grid_cost: float | None = None
    annual_curtailment_cost: float | None = None
    annual_shedding_cost: float | None = None
    annual_terminal_energy_cost: float | None = None
    annual_total_cost: float | None = None
    final_soc_deviation: float | None = None
    annual_capital_recovery: float | None = None
    annual_fixed_om: float | None = None
    annual_grid_purchases: float | None = None
    annual_export_credit: float | None = None
    annualization_basis: str | None = None
    fully_disconnected_bus_hours: float | None = None
    hours_with_full_disconnection: float | None = None
    service_unverified_hours: float | None = None
    buses_shed_over_50_percent_hours: float | None = None
    buses_shed_over_80_percent_hours: float | None = None
    shedding_above_50_percent_kwh: float | None = None
    shedding_above_80_percent_kwh: float | None = None
    controller_policy_score: float | None = None



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


SERVICE_ABS_KW = 1e-6
SERVICE_REL = 1e-6


def load_service(requested_kw, served_kw):
    if requested_kw is None or requested_kw <= SERVICE_ABS_KW or served_kw is None:
        return None, None
    fraction = min(1., max(0., served_kw / requested_kw))
    return fraction, served_kw <= max(SERVICE_ABS_KW, SERVICE_REL * requested_kw)


def service_verified(step):
    correction = getattr(step, "correction", None)
    return (step.power_flow.converged and step.requested_point is not None
            and (correction is None or correction.status in
                 ("not_needed", "verified", "legacy_proportional_validation")))


def summarize_service(simulation):
    """Count observed service interruptions, without treating missing or unsolved hours as outages."""
    steps, dt = simulation.steps, simulation.dt_hours
    if not steps or not any(step.requested_point is not None for step in steps):
        return {}, []
    totals = dict.fromkeys(("fully_disconnected_bus_hours", "hours_with_full_disconnection",
                           "service_unverified_hours", "buses_shed_over_50_percent_hours",
                           "buses_shed_over_80_percent_hours", "shedding_above_50_percent_kwh",
                           "shedding_above_80_percent_kwh", "controller_policy_score"), 0.)
    buses, streaks = {}, {}
    previous = None
    for step in steps:
        if not service_verified(step):
            totals["service_unverified_hours"] += dt
            streaks.clear()
            previous = None
            continue
        if previous is not None and (step.timestamp - previous).total_seconds() != dt * 3600:
            streaks.clear()
        previous = step.timestamp
        correction = getattr(step, "correction", None)
        totals["controller_policy_score"] += (correction.policy_score or 0.) * dt if correction else 0.
        disconnected = False
        for bus, requested in step.requested_point.p_load_kw.items():
            served = step.operating_point.p_load_kw[bus]
            fraction, outage = load_service(requested, served)
            if fraction is None:
                streaks.pop(bus, None)
                continue
            row = buses.setdefault(bus, [0., 0., 0., 0.])
            row[0] += requested * dt
            row[1] += served * dt
            streaks[bus] = streaks.get(bus, 0.) + dt if outage else 0.
            if outage:
                disconnected = True
                row[2] += dt
                row[3] = max(row[3], streaks[bus])
            shed = 1. - fraction
            for tier, threshold in ((50, .5), (80, .8)):
                if shed > threshold + SERVICE_REL:
                    totals[f"buses_shed_over_{tier}_percent_hours"] += dt
                    totals[f"shedding_above_{tier}_percent_kwh"] += (shed - threshold) * requested * dt
        if disconnected:
            totals["hours_with_full_disconnection"] += dt
    shed_energy = sum(max(0., requested - served) for requested, served, _, _ in buses.values())
    totals["fully_disconnected_bus_hours"] = sum(row[2] for row in buses.values())
    return totals, [(bus, requested, served, max(0., requested-served),
                     100 * served / requested, 100 * max(0., requested-served) / shed_energy if shed_energy else 0.,
                     hours, longest) for bus, (requested, served, hours, longest) in sorted(buses.items())]


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
                + economic_config.fixed_installation_cost
            )
    try:
        weights = validate_annual_inputs([step.timestamp for step in steps], economic_config, dt_hours)
    except ValueError as error:
        metrics.notes.append(f"Annual economics unavailable: {error}")
        weights = None
    if weights is not None and metrics.bess_cost is not None:
        capex = metrics.bess_cost
        metrics.annualization_basis = economic_config.annualization_basis or "Complete calendar year; each hour counted once"
        metrics.annual_capital_recovery = capex * capital_recovery_factor(economic_config.discount_rate, economic_config.lifetime_years)
        metrics.annual_fixed_om = capex * economic_config.annual_om_fraction
        metrics.annualized_bess_cost = metrics.annual_capital_recovery + metrics.annual_fixed_om
        metrics.annual_grid_purchases = sum(w * max(step.power_flow.slack_p_kw, 0) * dt_hours
            * economic_config.grid_import_tariff_per_kwh for w, step in zip(weights, steps))
        metrics.annual_export_credit = sum(w * max(-step.power_flow.slack_p_kw, 0) * dt_hours
            * economic_config.grid_export_tariff_per_kwh for w, step in zip(weights, steps))
        metrics.annual_grid_cost = metrics.annual_grid_purchases - metrics.annual_export_credit
        if curtailment_kw is not None:
            metrics.annual_curtailment_cost = sum(w*p*dt_hours for w,p in zip(weights,curtailment_kw)) * economic_config.curtailment_penalty_per_kwh
        if shedding_kw is not None:
            metrics.annual_shedding_cost = sum(w*p*dt_hours for w,p in zip(weights,shedding_kw)) * economic_config.shedding_penalty_per_kwh
        metrics.annual_terminal_energy_cost = 0.
        if has_bess:
            start = bess_config.energy_capacity_kwh * bess_config.soc_initial
            end = simulation_result.final_bess_state.energy_kwh
            metrics.final_soc_deviation = (end-start)/bess_config.energy_capacity_kwh
            if economic_config.annual_day_weights:
                terminal_ok = all(abs(steps[i].bess_step.soc_before-bess_config.soc_initial) <= economic_config.terminal_soc_tolerance
                    and abs(steps[i+23].bess_state.soc-bess_config.soc_initial) <= economic_config.terminal_soc_tolerance
                    for i in range(0, len(steps), 24) if weights[i] > 0)
            else:
                terminal_ok = abs(metrics.final_soc_deviation) <= economic_config.terminal_soc_tolerance
            if economic_config.terminal_policy == "equal_soc" or economic_config.annual_day_weights:
                if not terminal_ok:
                    metrics.feasible = False
                    metrics.notes.append("Economic terminal SOC equality failed; no free initial energy is permitted")
            else:
                price = economic_config.terminal_energy_price_per_kwh
                if price is None:
                    raise ValueError("Priced terminal policy requires an explicit terminal energy price")
                metrics.annual_terminal_energy_cost = (max(0.,start-end)/bess_config.eta_charge*price
                    - max(0.,end-start)*bess_config.eta_discharge*economic_config.grid_export_tariff_per_kwh)
        components = (metrics.annualized_bess_cost, metrics.annual_grid_cost,
                      metrics.annual_curtailment_cost, metrics.annual_shedding_cost, metrics.annual_terminal_energy_cost)
        if all(v is not None for v in components):
            metrics.annual_total_cost = sum(components)
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
    for name, value in summarize_service(simulation_result)[0].items():
        setattr(metrics, name, value)
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


def capital_recovery_factor(rate, life):
    _check_nonnegative(rate, "discount_rate")
    if isinstance(life, bool) or not isinstance(life, (int, float)) or not isfinite(life) or life <= 0:
        raise ValueError("Lifetime must be positive")
    # Stable for rates close to zero.
    from math import expm1, log1p
    return rate / (-expm1(-life*log1p(rate))) if rate else 1/life


def validate_annual_inputs(timestamps, config, dt_hours=1.):
    """Return annual occurrence weights or block unsupported annual claims."""
    import numpy as np
    import pandas as pd
    config.__post_init__()
    if config.grid_import_tariff_per_kwh is None or config.grid_export_tariff_per_kwh is None:
        raise ValueError("Supply import purchase price and export compensation (explicit 0 is allowed)")
    times = pd.DatetimeIndex(timestamps)
    if len(times) == 0 or dt_hours != 1 or not times.is_unique or not times.is_monotonic_increasing:
        raise ValueError("Annual evaluation requires unique increasing hourly timestamps")
    if len(times)>1 and (np.diff(times.as_unit("ns").asi8) != 3600_000_000_000).any():
        raise ValueError("Annual evaluation requires continuous hourly data")
    begin = pd.Timestamp(year=times[0].year, month=1, day=1)
    end = pd.Timestamp(year=times[0].year+1, month=1, day=1)
    if not config.annual_day_weights:
        if times[0] != begin or times[-1]+pd.Timedelta(hours=1) != end:
            raise ValueError("Use a complete calendar year or justified seasonal representative-day weights")
        return np.ones(len(times))
    if not config.annualization_basis.strip():
        raise ValueError("Representative-day weights require a stated seasonal basis")
    days = np.asarray(config.annual_day_weights, dtype=float)
    if times[0].hour != 0 or len(times) % 24 or len(days)*24 != len(times):
        raise ValueError("Provide one annual occurrence weight per complete midnight-to-midnight day")
    if not np.isfinite(days).all() or (days<0).any() or not np.isclose(days.sum()*24, config.annual_hours):
        raise ValueError("Representative-day weights must cover exactly 365/366 annual days")
    selected = times[::24][days>0]
    if len(set((selected.month-1)//3)) < 4:
        raise ValueError("Representative days must include all four seasonal quarters")
    if config.terminal_policy != "equal_soc":
        raise ValueError("Representative-day economics requires equal initial/terminal SOC per selected day")
    return np.repeat(days, 24)


def with_terminal_policy(simulation, economics):
    """Apply the same terminal policy to physical and economic evaluation."""
    from dataclasses import replace
    equal = economics.terminal_policy == "equal_soc"
    return replace(simulation,
                   terminal_soc_tolerance=economics.terminal_soc_tolerance if equal else None,
                   terminal_cycle_hours=24 if equal and economics.annual_day_weights else None,
                   shedding_penalty_per_kwh=economics.shedding_penalty_per_kwh,
                   curtailment_penalty_per_kwh=economics.curtailment_penalty_per_kwh)
