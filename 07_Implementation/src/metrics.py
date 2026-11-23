"""Summarize hourly energy and transparent annual ownership costs."""
from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite

from .bess import BESSConfig
from .simulation import TimeSeriesSimulationResult


@dataclass
class EconomicConfig:
    """Annual cost = grid net cost + penalties + straight-line BESS ownership.

    Battery annual ownership = initial purchase / useful life + annual O&M,
    where annual O&M is a declared fraction of the initial purchase cost.
    This is a simple accounting model, not discounted cash-flow analysis.
    """
    cost_per_kwh: float | None = 385.0
    cost_per_kw: float | None = 770.0
    currency: str = "USD"
    curtailment_penalty_per_kwh: float = 0.07
    shedding_penalty_per_kwh: float = 12.0
    grid_import_tariff_per_kwh: float | None = None
    grid_export_tariff_per_kwh: float | None = None
    lifetime_years: int = 10
    annual_om_fraction: float = 0.02
    scenario: str = "Direct annual grid cost, penalties and straight-line BESS ownership"
    provenance: str = "CAPEX / lifetime + annual O&M (% of CAPEX); no discount, CRF or reserve"
    power_cost_basis: str = "kw"
    inverter_kva_per_kw: float = 1.0
    annualization_method: str = 'straight_line'
    nominal_interest_rate: float = 0.05
    annual_inflation_rate: float = 0.01

    def __post_init__(self):
        if self.annualization_method not in ('straight_line', 'real_crf'):
            raise ValueError('annualization_method must be straight_line or real_crf')
        for rate in (self.nominal_interest_rate, self.annual_inflation_rate):
            if not isfinite(rate) or not 0 <= rate < 1.:
                raise ValueError('Interest and inflation must be finite fractions between 0 and 1')
        if self.power_cost_basis not in ('kw', 'kva'):
            raise ValueError('Power cost basis must be kw or kva')
        if not isfinite(self.inverter_kva_per_kw) or self.inverter_kva_per_kw < 1.:
            raise ValueError('inverter_kva_per_kw must be >= 1')
        for name in ("cost_per_kwh", "cost_per_kw"):
            value = getattr(self, name)
            if value is not None:
                _check_nonnegative(value, name)
        for name in ("curtailment_penalty_per_kwh", "shedding_penalty_per_kwh",
                     "annual_om_fraction"):
            _check_nonnegative(getattr(self, name), name)
        if isinstance(self.lifetime_years, bool) or not isinstance(self.lifetime_years, int) or self.lifetime_years < 1:
            raise ValueError("BESS lifetime must be a positive integer number of years")
        if self.currency != "USD":
            raise ValueError("All monetary inputs in this study must use USD")
        for name in ("grid_import_tariff_per_kwh", "grid_export_tariff_per_kwh"):
            if getattr(self, name) is not None:
                _check_nonnegative(getattr(self, name), name)


def annual_capital_recovery_factor(economics: EconomicConfig) -> float:
    """Straight-line legacy or real CRF using stated interest/inflation assumptions."""
    years = economics.lifetime_years
    if economics.annualization_method == 'straight_line':
        return 1.0 / years
    real = (1.0 + economics.nominal_interest_rate) / (1.0 + economics.annual_inflation_rate) - 1.0
    if abs(real) < 1e-12:
        return 1.0 / years
    compound = (1.0 + real) ** years
    return real * compound / (compound - 1.0)


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
    annual_grid_cost: float | None = None
    annual_curtailment_cost: float | None = None
    annual_shedding_cost: float | None = None
    annual_bess_capital_cost: float | None = None
    annual_bess_om_cost: float | None = None
    annualized_bess_cost: float | None = None
    annual_operating_cost: float | None = None
    annual_total_cost: float | None = None
    annual_terminal_inventory_adjustment: float | None = None
    final_soc_deviation: float | None = None
    terminal_energy_change_kwh: float | None = None
    terminal_soc_details: list[str] | None = None
    annual_grid_purchases: float | None = None
    annual_export_credit: float | None = None
    fully_disconnected_bus_hours: float | None = None
    hours_with_full_disconnection: float | None = None
    service_unverified_hours: float | None = None
    buses_shed_over_50_percent_hours: float | None = None
    buses_shed_over_80_percent_hours: float | None = None
    shedding_above_50_percent_kwh: float | None = None
    shedding_above_80_percent_kwh: float | None = None
    controller_policy_score: float | None = None
    # Reactive power-hour integral (kvarh), NOT energy stored in the battery.
    bess_reactive_dispatch_kvarh: float = 0.0
    pv_reactive_dispatch_kvarh: float = 0.0



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

    fleet_configs = (tuple(bess_config) if isinstance(bess_config, (tuple, list)) else None)
    if fleet_configs is not None:
        if len(fleet_configs) != len({c.bus_id for c in fleet_configs}):
            raise ValueError("Fleet cost configuration contains duplicate battery locations")
    has_bess = any(step.bess_step is not None or getattr(step, "fleet_steps", None) for step in steps)
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
        metrics.bess_reactive_dispatch_kvarh += sum(abs(q) for q in getattr(point, 'q_bess_kvar', {}).values()) * dt_hours
        metrics.pv_reactive_dispatch_kvarh += sum(abs(q) for q in getattr(point, 'q_pv_kvar', {}).values()) * dt_hours
        metrics.peak_grid_import_kw = max(metrics.peak_grid_import_kw, flow.slack_p_kw)
        metrics.voltage_min_pu = min(metrics.voltage_min_pu, min(flow.voltage_mag_pu.values()))
        metrics.voltage_max_pu = max(metrics.voltage_max_pu, max(flow.voltage_mag_pu.values()))
        if step.voltage_violations:
            metrics.voltage_violation_hours += dt_hours
            metrics.voltage_violation_bus_hours += len(step.voltage_violations) * dt_hours
        unit_steps = (list(step.fleet_steps.values()) if getattr(step, "fleet_steps", None)
                      else [step.bess_step] if step.bess_step is not None else [])
        for unit_step in unit_steps:
            actual_kw = unit_step.actual_power_kw
            metrics.bess_charge_energy_kwh += max(-actual_kw, 0.0) * dt_hours
            metrics.bess_discharge_energy_kwh += max(actual_kw, 0.0) * dt_hours
            hour_soc_after = getattr(unit_step, "soc_after", step.bess_state.soc if step.bess_state is not None else unit_step.soc_before)
            hour_soc_min = min(unit_step.soc_before, hour_soc_after)
            hour_soc_max = max(unit_step.soc_before, hour_soc_after)
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
                sum(economic_config.cost_per_kwh * c.energy_capacity_kwh
                    + economic_config.cost_per_kw * c.power_rating_kw * (economic_config.inverter_kva_per_kw if economic_config.power_cost_basis == 'kva' else 1.0)
                    for c in (fleet_configs or (bess_config,)))
            )
    if metrics.bess_cost is not None:
        metrics.annual_bess_capital_cost = metrics.bess_cost * annual_capital_recovery_factor(economic_config)
        metrics.annual_bess_om_cost = metrics.bess_cost * economic_config.annual_om_fraction
        metrics.annualized_bess_cost = metrics.annual_bess_capital_cost + metrics.annual_bess_om_cost
    try:
        validate_annual_inputs([step.timestamp for step in steps], economic_config, dt_hours)
    except ValueError as error:
        metrics.notes.append(f"Annual costs unavailable: {error}")
    else:
        # Direct energy ledger: every recorded hourly value occurs exactly once.
        metrics.annual_grid_purchases = (metrics.grid_import_energy_kwh
            * economic_config.grid_import_tariff_per_kwh)
        metrics.annual_export_credit = (metrics.grid_export_energy_kwh
            * economic_config.grid_export_tariff_per_kwh)
        metrics.annual_grid_cost = metrics.annual_grid_purchases - metrics.annual_export_credit
        if metrics.curtailment_energy_kwh is not None:
            metrics.annual_curtailment_cost = (metrics.curtailment_energy_kwh
                * economic_config.curtailment_penalty_per_kwh)
        if metrics.load_shedding_energy_kwh is not None:
            metrics.annual_shedding_cost = (metrics.load_shedding_energy_kwh
                * economic_config.shedding_penalty_per_kwh)
        # Terminal inventory is priced for fair annual candidate economics.
        # This is an accounting cost of hypothetical grid energy needed to
        # restore a deficit, NOT a physical terminal-SOC equality constraint.
        # The unmet energy must still be reported and may not be chargeable
        # under the real network conditions. Surplus inventory is not credited.
        if has_bess:
            configs = fleet_configs if fleet_configs is not None else (bess_config,)
            states = getattr(simulation_result, "final_fleet_states", None)
            if not states and fleet_configs is None:
                states = {bess_config.bus_id: simulation_result.final_bess_state}
            if not states or any(c.bus_id not in states or states[c.bus_id] is None for c in configs):
                raise ValueError("Missing final BESS states for terminal energy reporting")
            deviations = []
            energy_change = 0.0
            details = []
            recharge_cost = 0.0
            for c in configs:
                initial_kwh = c.energy_capacity_kwh * c.soc_initial
                final_kwh = states[c.bus_id].energy_kwh
                delta_kwh = final_kwh - initial_kwh
                energy_change += delta_kwh
                if delta_kwh < 0:
                    recharge_cost += (-delta_kwh / c.eta_charge) * economic_config.grid_import_tariff_per_kwh
                deviations.append(delta_kwh / c.energy_capacity_kwh)
                details.append(f"Bus {c.bus_id}: initial {100*c.soc_initial:.3f}% | "
                               f"final {100*final_kwh/c.energy_capacity_kwh:.3f}% | "
                               f"stored energy change {delta_kwh:+.3f} kWh")
            metrics.annual_terminal_inventory_adjustment = recharge_cost
            metrics.final_soc_deviation = max(deviations, key=abs)
            metrics.terminal_energy_change_kwh = energy_change
            metrics.terminal_soc_details = details
            if (getattr(simulation_result, "dispatch_timing", None) or {}).get("fleet_dispatch_mode") == "daily_milp_dispatch":
                metrics.notes.append("Daily MILP dispatch dispatch enforces daily SOC restoration within the "
                                     "solver tolerance. The annual terminal inventory ledger uses the "
                                     "recorded final state.")
            else:
                metrics.notes.append("No terminal SOC closure: any terminal energy deficit receives a grid-purchase "
                                     "replacement-cost adjustment in the annual objective. "
                                     "Physical feasibility of replenishment is unverified.")
        operating_components = (metrics.annual_grid_cost, metrics.annual_curtailment_cost,
                                metrics.annual_shedding_cost)
        if all(value is not None for value in operating_components):
            metrics.annual_operating_cost = (sum(operating_components)
                + (metrics.annual_terminal_inventory_adjustment or 0.))
            if metrics.annualized_bess_cost is not None:
                metrics.annual_total_cost = metrics.annual_operating_cost + metrics.annualized_bess_cost
    if curtailment_kw is None:
        metrics.notes.append("Curtailment unavailable: this run has no complete action records.")
    if shedding_kw is None:
        metrics.notes.append("Load shedding unavailable: this run has no complete action records.")
    if metrics.curtailment_energy_kwh is not None:
        metrics.available_pv_energy_kwh = metrics.pv_generation_energy_kwh + metrics.curtailment_energy_kwh
    if metrics.load_shedding_energy_kwh is not None:
        metrics.requested_load_energy_kwh = metrics.served_load_energy_kwh + metrics.load_shedding_energy_kwh
    if not metrics.feasible:
        metrics.notes.append("This run has unresolved network, line or battery constraints; retain its infeasible status.")
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


def validate_annual_inputs(timestamps, config, dt_hours=1.):
    """Require an actual complete calendar year: no representative-day weights."""
    import numpy as np
    import pandas as pd
    config.__post_init__()
    if config.grid_import_tariff_per_kwh is None or config.grid_export_tariff_per_kwh is None:
        raise ValueError("Supply grid import and export tariffs (explicit zero is allowed)")
    times = pd.DatetimeIndex(timestamps)
    if len(times) not in (8760, 8784) or dt_hours != 1 or not times.is_unique or not times.is_monotonic_increasing:
        raise ValueError("Annual evaluation requires 8760/8784 unique increasing hourly timestamps")
    if (np.diff(times.as_unit("ns").asi8) != 3600_000_000_000).any():
        raise ValueError("Annual evaluation requires continuous hourly data")
    start = pd.Timestamp(year=times[0].year, month=1, day=1, tz=times.tz)
    end = pd.Timestamp(year=times[0].year + 1, month=1, day=1, tz=times.tz)
    if times[0] != start or times[-1] + pd.Timedelta(hours=1) != end:
        raise ValueError("Use the complete January-to-January calendar year")
    return True

def with_terminal_policy(simulation, economics):
    """Retained import-compatible name; always disable obsolete SOC closure.

    Both historical and new study settings use the same dispatch constraints.
    The end-of-study BESS inventory is recorded, never used as a rejection.
    """
    from dataclasses import replace
    return replace(simulation,
                   terminal_soc_tolerance=None,
                   terminal_cycle_hours=None,
                   predictive_grid_tariff_per_kwh=economics.grid_import_tariff_per_kwh if economics.grid_import_tariff_per_kwh is not None else simulation.predictive_grid_tariff_per_kwh,
                   shedding_penalty_per_kwh=economics.shedding_penalty_per_kwh,
                   curtailment_penalty_per_kwh=economics.curtailment_penalty_per_kwh)
