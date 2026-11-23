"""Rolling battery scheduling from the selected hourly operating inputs."""
from dataclasses import dataclass, field, replace
from time import perf_counter

@dataclass(frozen=True)
class ConstraintAwareDispatch:
    """Configuration shared by the desktop and spawned optimization workers."""

    import_tariff: float | None = None
    export_tariff: float | None = None
    shedding_penalty: float = 12.0
    curtailment_penalty: float = 0.07
    source: str = "historical perfect-foresight diagnostic"
    horizon_hours: int = field(default=24, init=False)
    version: str = field(default="constraint-aware-24h-v1", init=False)


@dataclass
class FlowCheck:
    converged: bool
    minimum_pu: float | None = None
    minimum_bus: int | None = None
    maximum_pu: float | None = None
    maximum_bus: int | None = None
    import_kw: float | None = None
    export_kw: float | None = None
    violations: dict[str, float] = field(default_factory=dict)
    binding: list[str] = field(default_factory=list)


@dataclass
class DispatchEvent:
    policy: str
    source: str
    bus_id: int | None
    horizon_hours: int
    risks: list[dict]
    pre: FlowCheck
    after_bess: FlowCheck | None = None
    final: FlowCheck | None = None
    planned_kw: float = 0.
    request_kw: float = 0.
    after_bess_kw: float | None = None
    accepted_kw: float | None = None
    charge_available_kw: float | None = None
    discharge_available_kw: float | None = None
    terminal_target_kwh: float | None = None
    terminal_remaining_hours: int | None = None
    terminal_charge_headroom_kwh: float | None = None
    terminal_discharge_headroom_kwh: float | None = None
    projected_stress_actions: list[dict] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    correction: dict | None = None
    requested_p_by_bus: dict = field(default_factory=dict)
    requested_q_by_bus: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)


def check_flow(flow, network, config):
    if not flow.converged:
        return FlowCheck(False)
    voltages = flow.voltage_mag_pu
    low, high = min(voltages, key=voltages.get), max(voltages, key=voltages.get)
    violations = {}
    for bus, voltage in voltages.items():
        if voltage < config.voltage_min_pu:
            violations[f"undervoltage:{bus}"] = config.voltage_min_pu - voltage
        if voltage > config.voltage_max_pu:
            violations[f"overvoltage:{bus}"] = voltage - config.voltage_max_pu
    imports, exports = max(0., flow.slack_p_kw), max(0., -flow.slack_p_kw)
    for name, value, limit in (("import", imports, config.grid_import_limit_kw),
                               ("export", exports, config.grid_export_limit_kw)):
        if limit is not None and value > limit + config.control_tolerance_kw:
            violations[name] = value - limit
    if config.enforce_line_ampacity:
        for line in network.lines:
            current = flow.branch_current_a.get(line.line_id, 0.)
            if line.ampacity_a is not None and current > line.ampacity_a + 1e-6:
                violations[f"ampacity:{line.line_id}"] = current - line.ampacity_a
    binding = list(violations)
    for name, value, limit in (("undervoltage", voltages[low], config.voltage_min_pu),
                               ("overvoltage", voltages[high], config.voltage_max_pu),
                               ("import", flow.slack_p_kw, config.grid_import_limit_kw),
                               ("export", -flow.slack_p_kw, config.grid_export_limit_kw)):
        if limit is not None and abs(value - limit) <= 5e-6:
            key = f"{name}:{low if name == 'undervoltage' else high}" if name.endswith("voltage") else name
            if key not in binding:
                binding.append(key)
    if config.enforce_line_ampacity:
        binding.extend(f"ampacity:{line.line_id}" for line in network.lines
                       if line.ampacity_a is not None and f"ampacity:{line.line_id}" not in violations
                       and abs(flow.branch_current_a[line.line_id] - line.ampacity_a) <= 1e-6)
    return FlowCheck(True, voltages[low], low, voltages[high], high, imports, exports, violations, binding)


def admissible(before, after):
    if not after.converged:
        return False
    if not before.converged:
        return not after.violations
    return all(key in before.violations and excess <= before.violations[key] + 1e-10
               for key, excess in after.violations.items())


class RollingDispatch:
    """Per-simulation cache. Future probes are electrical envelopes, not SOC promises."""

    def __init__(self, network, settings, battery, policy, timestamps, point_at, solve_fbs):
        self.network = network
        self.settings = settings
        self.battery = battery
        self.policy = policy
        self.timestamps = timestamps
        self.point_at = point_at
        self.solve_fbs = solve_fbs
        self.raw = {}
        self.envelopes = {}
        self.charging_headroom_cache = {}
        self.trials = {}
        self.flow_seconds = 0.
        self.flow_trials = 0
        self.plan_seconds = 0.

    def solve(self, point):
        start = perf_counter()
        flow = self.solve_fbs(point)
        self.flow_seconds += perf_counter() - start
        self.flow_trials += 1
        return flow, check_flow(flow, self.network, self.settings)

    def uncontrolled(self, index):
        if index not in self.raw:
            point = self.point_at(index)
            self.raw[index] = (point, *self.solve(point))
        return self.raw[index]

    def trial(self, index, point, power):
        trials = self.trials.setdefault(index, {})
        if power in trials:
            return trials[power]
        trial = replace(point, p_bess_kw={**point.p_bess_kw, self.battery.bus_id: power})
        outcome = self.solve(trial)
        trials[power] = outcome
        return outcome

    def choose(self, index, point, before, requested, *, corrective, preserve_request=False):
        """Sample bounded powers, retaining only verified, non-worsening results."""
        if abs(requested) <= 1e-9:
            return None
        if corrective and not preserve_request and any(
                requested == power for power, _ in self.envelopes.get(index, ())):
            flow, after = self.trial(index, point, requested)
            return requested, flow, after
        best = None
        clear = failed = None
        for fraction in (1., .5, .25, .125, .0625):
            power = requested * fraction
            flow, after = self.trial(index, point, power)
            allowed = admissible(before, after)
            if (allowed and power < 0. and self.policy.import_tariff is None
                    and after.import_kw > (before.import_kw or 0.) + self.settings.control_tolerance_kw):
                allowed = False
            if allowed and preserve_request:
                return power, flow, after
            if allowed and not after.violations:
                clear = (fraction, power, flow, after)
                if not corrective:
                    return power, flow, after
            elif clear:
                failed = fraction
                break
            if not allowed:
                continue
            improved = any(after.violations.get(key, 0.) < excess - 1e-10
                           for key, excess in before.violations.items())
            if corrective and before.converged and not improved:
                continue
            if not corrective:
                return power, flow, after
            # Preserve energy once a sampled action clears all violations.
            score = (len(after.violations), sum(after.violations.values()))
            if best is None or (score, abs(power)) < (best[0], abs(best[1])):
                best = (score, power, flow, after)
        if clear:
            lower = failed or 0.
            for _ in range(8):
                middle = (lower + clear[0]) / 2
                power = requested * middle
                flow, after = self.trial(index, point, power)
                if (after.converged and not after.violations and
                        (power >= 0. or self.policy.import_tariff is not None or
                         after.import_kw <= (before.import_kw or 0.) + self.settings.control_tolerance_kw)):
                    clear = (middle, power, flow, after)
                else:
                    lower = middle
            return clear[1:]
        return best[1:] if best else None

    def envelope(self, index):
        if index in self.envelopes:
            return self.envelopes[index]
        point, _, before = self.uncontrolled(index)
        options = []
        if before.violations or not before.converged:
            battery = self.battery
            import_risk = any(key == "import" or key.startswith("undervoltage") for key in before.violations)
            export_risk = any(key == "export" or key.startswith("overvoltage") for key in before.violations)
            for requested, price, relevant in (
                (max(0., min(battery.power_rating_kw, battery.max_discharge_kw)),
                 self.policy.shedding_penalty, import_risk or not export_risk),
                (-min(battery.power_rating_kw, battery.max_charge_kw),
                 self.policy.curtailment_penalty, export_risk or not import_risk),
            ):
                if relevant:
                    action = self.choose(index, point, before, requested, corrective=True)
                    if action:
                        options.append((action[0], price))
        self.envelopes[index] = tuple(options)
        return self.envelopes[index]

    def charging_headroom(self, index):
        if index in self.charging_headroom_cache:
            return self.charging_headroom_cache[index]
        point, _, pre = self.uncontrolled(index)
        battery = self.battery
        max_charge = min(battery.power_rating_kw, battery.max_charge_kw)
        max_discharge = max(0., min(battery.power_rating_kw, battery.max_discharge_kw))
        if self.policy.import_tariff is None and pre.converged:
            max_charge = min(max_charge, pre.export_kw)
        charge = self.choose(index, point, pre, -max_charge, corrective=False)
        discharge = self.choose(index, point, pre, max_discharge, corrective=False)
        headroom = (-charge[0] * battery.eta_charge if charge else 0.,
                    discharge[0] / battery.eta_discharge if discharge else 0.)
        self.charging_headroom_cache[index] = headroom
        return headroom

    def plan(self, index, state, *, capture):
        start = perf_counter()
        flow_at_start = self.flow_seconds
        self.raw.pop(index - 1, None)
        self.envelopes.pop(index - 1, None)
        self.trials.pop(index - 1, None)
        self.charging_headroom_cache.pop(index - 1, None)
        end = min(len(self.timestamps), index + self.policy.horizon_hours)
        battery = self.battery
        floor = battery.soc_min * battery.energy_capacity_kwh

        risks = []
        future = []
        forecast_actions = []
        for hour in range(index, end):
            _, _, check = self.uncontrolled(hour)
            if check.violations or not check.converged:
                options = self.envelope(hour)
                if capture:
                    risks.append({"timestamp": str(self.timestamps[hour]), "constraints": list(check.violations),
                                  "converged": check.converged,
                                  "tested_action_kw": [power for power, _ in options]})
                if hour > index:
                    future.extend((hour, power, price) for power, price in options if power > 0.)
                    if capture and options:
                        forecast_actions.append((hour, max(options, key=lambda option: (option[1], abs(option[0])))[0]))
        _, _, before = self.uncontrolled(index)
        event = DispatchEvent(self.policy.version, self.policy.source, battery.bus_id,
                              end - index, risks, before)
        if not before.converged:
            event.reason_codes.append("nonconvergence")
        options = self.envelope(index)
        request = 0.
        available = max(0., state.energy_kwh - floor)
        if available <= 1e-9 and any(power > 0. for power, _ in options):
            event.reason_codes.append("no_energy")
        if options:
            power, price = max(options, key=lambda option: (option[1], abs(option[0])))
            if power > 0.:
                # Rank tested corrective opportunities by useful injection and
                # penalty. This score is not a counterfactual energy estimate.
                held = sum(next_power / battery.eta_discharge for _, next_power, next_price in future
                           if next_power * next_price > power * price + 1e-6)
                request = min(power, max(0., available - held) * battery.eta_discharge)
            else:
                request = power
        elif before.converged and not before.violations:
            event.reason_codes.append("no_violation")
            # Use only stated prices when a purchase would be required. Exported
            # PV can be shifted when its stated opportunity cost permits it.
            import_price, export_price = self.policy.import_tariff, self.policy.export_tariff
            target_energy = sum(power / battery.eta_discharge for _, power, price in future
                                if import_price is None or price * battery.eta_charge * battery.eta_discharge > import_price)
            if target_energy > 0. and import_price is not None and export_price is not None and export_price < import_price:
                first_use = min(hour for hour, _, _ in future)
                for hour in range(index + 1, first_use):
                    _, _, check = self.uncontrolled(hour)
                    if check.converged and check.export_kw > self.settings.control_tolerance_kw:
                        tested_charge, _ = self.charging_headroom(hour)
                        target_energy = max(0., target_energy - min(tested_charge, check.export_kw * battery.eta_charge))
            need = max(0., min(battery.soc_max * battery.energy_capacity_kwh, floor + target_energy)
                       - state.energy_kwh)
            if need > 1e-9:
                solar_allowed = export_price is None or any(
                    price * battery.eta_charge * battery.eta_discharge > export_price
                    for _, _, price in future)
                limit = (float("inf") if import_price is not None else
                         before.export_kw if solar_allowed else 0.)
                request = -min(need / battery.eta_charge, limit)
                if not request:
                    event.reason_codes.append("no_charge_headroom")
            elif available > 1e-9 and import_price is not None and import_price > 0. and before.import_kw > 0.:
                retained = sum(power / battery.eta_discharge for _, power, price in future if price >= import_price)
                request = min(before.import_kw, max(0., available - retained) * battery.eta_discharge)
        elif before.converged:
            probes = self.trials.get(index, {})
            if probes and all(check.converged for _, check in probes.values()) and all(
                    all(check.violations.get(key, 0.) >= excess - 1e-10
                        for key, excess in before.violations.items()) for _, check in probes.values()):
                event.reason_codes.append("ineffective_bus_location")
            else:
                event.reason_codes.append("other_constraint")
        event.planned_kw = request
        if forecast_actions:
            eta_charge, eta_discharge = battery.eta_charge, battery.eta_discharge
            ceiling = battery.soc_max * battery.energy_capacity_kwh
            if request > 0.:
                initial_power = min(request, max(0., battery.max_discharge_kw),
                                    max(0., battery.power_rating_kw), available * eta_discharge)
                stored = state.energy_kwh - initial_power / eta_discharge
            else:
                initial_power = min(-request, battery.max_charge_kw, battery.power_rating_kw)
                stored = min(ceiling, state.energy_kwh + initial_power * eta_charge)
            for hour, power in forecast_actions:
                if power >= 0.:
                    power = min(power, max(0., stored - floor) * eta_discharge)
                    stored -= power / eta_discharge
                else:
                    power = max(power, -max(0., ceiling - stored) / eta_charge)
                    stored -= power * eta_charge
                event.projected_stress_actions.append({"timestamp": str(self.timestamps[hour]),
                                                      "forecast_kw": power, "forecast_energy_kwh": stored})
        self.plan_seconds += perf_counter() - start - (self.flow_seconds - flow_at_start)
        return request, event
