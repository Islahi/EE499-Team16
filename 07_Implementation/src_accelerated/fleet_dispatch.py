"""Coordinated dispatch through one common feeder operating point."""
from copy import copy
from dataclasses import dataclass, replace
from math import isfinite, sqrt

from .bess import BESSState, FleetUnitStep
from .constraint_dispatch import ConstraintAwareDispatch, DispatchEvent, RollingDispatch, admissible, check_flow
from .dispatch import terminal_request


@dataclass
class FleetHour:
    original: object
    raw: object
    raw_check: object
    operating_point: object
    flow: object
    check: object
    corrected_point: object
    final_flow: object
    correction: object
    records: tuple[FleetUnitStep, ...]
    reserve_kw: float
    power_shortfall: float
    energy_shortfall: float
    event: DispatchEvent | None
    terminal_due: bool


def effective_config(unit):
    config = copy(unit.config)
    real_limit = sqrt(config.power_rating_kw ** 2 - unit.reactive_kvar ** 2)
    config.max_charge_kw = min(config.max_charge_kw, real_limit)
    config.max_discharge_kw = min(config.max_discharge_kw, real_limit)
    return config


def allocate_reserve(units, configs, reserve_kw, duration):
    """Allocate one global requirement over rated, energy-deliverable headroom."""
    limits = [min(config.max_discharge_kw, (min(config.soc_initial, unit.target_soc) - config.soc_min) *
                  config.energy_capacity_kwh * config.eta_discharge / duration) for unit, config in zip(units, configs)]
    weights = [unit.reserve_weight if unit.reserve_weight is not None else limit for unit, limit in zip(units, limits)]
    allocations = [0.0] * len(units)
    remaining = reserve_kw
    eligible = list(range(len(units)))
    while remaining > 1e-9 and eligible:
        denominator = sum(weights[i] for i in eligible)
        shares = {i: remaining * (weights[i] / denominator if denominator else 1 / len(eligible)) for i in eligible}
        capped = [i for i in eligible if shares[i] >= limits[i]]
        if not capped:
            for i in eligible:
                allocations[i] = shares[i]
            remaining = 0.0
            break
        for i in capped:
            allocations[i] = limits[i]
            remaining -= limits[i]
            eligible.remove(i)
    if remaining > 1e-9:
        # Keep the infeasible residual visible with the same global requirement.
        allocations[0] += remaining
    return allocations


class FleetDispatch:
    def __init__(self, network, settings, fleet, policy, timestamps, point_at, reserve_kw, solve, corrector, step_battery):
        self.network = network
        self.settings = settings
        self.units = fleet.units
        self.policy = policy
        self.timestamps = timestamps
        self.point_at = point_at
        self.reserve_kw = reserve_kw
        self.solve = solve
        self.corrector = corrector
        self.step_battery = step_battery
        self.configs = [effective_config(unit) for unit in self.units]
        self.reserve = allocate_reserve(self.units, self.configs, reserve_kw, settings.reserve_duration_hours)
        self.states = {unit.unit_id: BESSState(unit.config.energy_capacity_kwh * unit.config.soc_initial,
                                             unit.config.soc_initial) for unit in self.units}
        self.planners = []
        if isinstance(policy, ConstraintAwareDispatch):
            for config, allocation in zip(self.configs, self.reserve):
                self.planners.append(RollingDispatch(network, settings, config, policy, timestamps,
                                                     point_at, allocation, solve))
            for planner in self.planners[1:]:
                planner.uncontrolled = self.planners[0].uncontrolled

    def plan(self, index, profile, capture):
        settings = self.settings
        if self.planners:
            original, raw, before = self.planners[0].uncontrolled(index)
        else:
            original = self.point_at(index)
            raw = self.solve(original)
            before = check_flow(raw, self.network, settings)
        explicit = self.policy(index, profile, {key: copy(state) for key, state in self.states.items()}) if callable(self.policy) else {}
        if not isinstance(explicit, dict) or set(explicit) - self.states.keys():
            raise ValueError("Fleet dispatch callback must return a dictionary keyed by unit ID")
        count = len(self.timestamps)
        cycle = settings.terminal_cycle_hours or count
        remaining = min(cycle - index % cycle - 1, count - index - 1)
        candidates, requests, adjustments = [], [], []
        for i, (unit, config, reserve) in enumerate(zip(self.units, self.configs, self.reserve)):
            state = self.states[unit.unit_id]
            request, trace = self.planners[i].plan(index, state, capture=False) if self.planners else (explicit.get(unit.unit_id, 0.0), None)
            adjusted = request
            if settings.terminal_soc_tolerance is not None:
                target = copy(config)
                target.soc_initial = unit.target_soc
                adjusted = terminal_request(request, state, target, remaining, reserve,
                    charge_headroom_kwh=trace.terminal_charge_headroom_kwh if trace else None,
                    discharge_headroom_kwh=trace.terminal_discharge_headroom_kwh if trace else None)
                if self.planners and adjusted > 0.0:
                    # Individual electrical envelopes are upper bounds. Do not
                    # spend terminal energy on an assumption of simultaneous
                    # future charging across sites sharing feeder/PCC limits.
                    terminal_energy = unit.target_soc * config.energy_capacity_kwh
                    adjusted = min(adjusted, max(0., state.energy_kwh - terminal_energy) * config.eta_discharge)
            if not isinstance(adjusted, (int, float)) or isinstance(adjusted, bool) or not isfinite(adjusted):
                raise ValueError("Fleet power requests must be finite numbers")
            requests.append(adjusted)
            adjustments.append(abs(adjusted - request) > 1e-9)
            battery, _, _ = self.step_battery(config, state, adjusted, reserve, settings.reserve_duration_hours)
            candidates.append(battery.actual_power_kw)

        # A common sign is preferred for normal fleet dispatch. A genuine
        # individual closure constraint can require opposing injections.
        if self.planners and not any(adjustments) and min(candidates) < 0 < max(candidates):
            discharge = "import" in before.violations or any(key.startswith("undervoltage:") for key in before.violations)
            candidates = [value if (value > 0) == discharge else 0.0 for value in candidates]
        point, flow, after = original, raw, before
        powers = tuple(candidates)
        reactive = tuple(unit.reactive_kvar for unit in self.units)
        accepted_p = accepted_q = (0.0,) * len(powers)
        if any(powers) or any(reactive):
            vectors = [(tuple(fraction * value for value in powers), tuple(fraction * value for value in reactive))
                       for fraction in (1.0, .5, .25, .125, .0625)]
            if len(powers) > 1:
                vectors.extend((tuple(value if k == i else 0.0 for k, value in enumerate(powers)),
                                tuple(value if k == i else 0.0 for k, value in enumerate(reactive)))
                               for i in sorted(range(len(powers)), key=lambda k: (-abs(powers[k]), k)))
            tried = set()
            for p_kw, q_kvar in vectors:
                if (p_kw, q_kvar) in tried or not (any(p_kw) or any(q_kvar)):
                    continue
                tried.add((p_kw, q_kvar))
                trial = replace(original, p_bess_kw={**original.p_bess_kw, **{
                    unit.config.bus_id: value for unit, value in zip(self.units, p_kw)}},
                    q_bess_kvar={**original.q_bess_kvar, **{
                    unit.config.bus_id: value for unit, value in zip(self.units, q_kvar)}})
                outcome = self.solve(trial)
                check = check_flow(outcome, self.network, settings)
                if not admissible(before, check):
                    continue
                if (self.planners and self.policy.import_tariff is None and any(value < 0 for value in p_kw)
                        and (check.import_kw or 0) > (before.import_kw or 0) + settings.control_tolerance_kw):
                    continue
                point, flow, after = trial, outcome, check
                accepted_p, accepted_q = p_kw, q_kvar
                break

        corrected, final, correction = self.corrector.correct(point, flow, after)
        final_check = check_flow(final, self.network, settings)
        if (any(accepted_p) or any(accepted_q)) and (not final_check.converged or final_check.violations):
            idle_point, idle_flow, idle_correction = self.corrector.correct(original, raw, before)
            idle = check_flow(idle_flow, self.network, settings)
            if idle.converged and not idle.violations:
                point, flow, after = original, raw, before
                corrected, final, correction = idle_point, idle_flow, idle_correction
                accepted_p = accepted_q = (0.0,) * len(powers)
        records = []
        power_shortfall = energy_shortfall = 0.0
        for i, (unit, config, reserve, request, power, kvar) in enumerate(
                zip(self.units, self.configs, self.reserve, requests, accepted_p, accepted_q)):
            old = self.states[unit.unit_id]
            battery, power_gap, energy_gap = self.step_battery(config, old, power, reserve, settings.reserve_duration_hours)
            if abs(request - battery.actual_power_kw) > 1e-9:
                battery.limited, battery.limit_reason = True, "Fleet electrical or unit charge/discharge limit"
            power_shortfall += power_gap
            energy_shortfall += energy_gap
            reserve_energy = reserve * settings.reserve_duration_hours / config.eta_discharge
            records.append(FleetUnitStep(unit.unit_id, config.bus_id, request, battery, kvar, reserve, reserve_energy,
                max(0., config.max_discharge_kw - reserve),
                max(0., old.energy_kwh - config.soc_min * config.energy_capacity_kwh - reserve_energy), unit.target_soc))
        event = DispatchEvent("coordinated-fleet", getattr(self.policy, "source", "explicit fleet dispatch"), None,
                              min(count - index, 24) if self.planners else 0, [], before,
                              request_kw=sum(requests)) if capture else None
        if event and any(adjustments):
            event.reason_codes.append("terminal_soc")
        return FleetHour(original, raw, before, point, flow, after, corrected, final, correction, tuple(records), self.reserve_kw,
                         power_shortfall, energy_shortfall, event,
                         settings.terminal_soc_tolerance is not None and remaining == 0)

    def commit(self, hour, converged):
        if converged:
            self.states = {record.unit_id: BESSState(record.battery.energy_after_kwh, record.battery.soc_after)
                           for record in hour.records}
        return [record.unit_id for record in hour.records if hour.terminal_due and
                abs(self.states[record.unit_id].soc - record.terminal_target_soc) > self.settings.terminal_soc_tolerance]
