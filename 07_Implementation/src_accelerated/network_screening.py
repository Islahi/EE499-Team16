"""Reproducible placement diagnostics against a corrected no-storage feeder."""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from statistics import mean

from .constraint_dispatch import check_flow
from .data_loader import profile_at
from .fbs import prepare_fbs
from .network_control import NetworkCorrector
from .simulation import _operating_point, simulate_timeseries


@dataclass
class BaselineCache:
    fingerprint: str = ""
    result: object = None

    def run(self, network, profiles, settings, economics, clock, progress=None):
        payload = [asdict(network), asdict(settings), asdict(economics), clock, profiles.dt_hours,
                   list(map(str, profiles.timestamps)), "joint-control-fleet-v1"]
        digest = sha256(json.dumps(payload, sort_keys=True).encode())
        for name in ("load_p_kw", "load_q_kvar", "pv_p_kw", "pv_q_kvar"):
            digest.update(json.dumps(getattr(profiles, name), sort_keys=True, allow_nan=False).encode())
        key = digest.hexdigest()
        if key != self.fingerprint or self.result is None:
            run = simulate_timeseries(network, profiles, settings, progress=progress)
            if not run.completed or not run.converged:
                raise ValueError("The no-BESS reference did not complete with converged FBS")
            self.fingerprint, self.result = key, run
        return self.result


def branch_severity(network, baseline):
    order = network.radial_order()
    descendants = {}
    sections = {}
    for bus in order.parent_bus_by_bus:
        if bus == order.slack_bus_id:
            continue
        cursor = bus
        section = None
        while cursor != order.slack_bus_id:
            line = order.parent_line_by_bus[cursor]
            descendants.setdefault(line, []).append(bus)
            parent = order.parent_bus_by_bus[cursor]
            if section is None and (len(order.children_by_bus[parent]) > 1 or parent == order.slack_bus_id):
                section = line
            cursor = parent
        sections[bus] = section
    dt = baseline.dt_hours
    buses = {}
    for bus in sections:
        shed = sum(step.shedding_by_bus_kw[bus] * dt for step in baseline.steps)
        disconnected = sum(step.requested_point.p_load_kw[bus] > 1e-9 and step.operating_point.p_load_kw[bus] <= 1e-8
                           for step in baseline.steps)
        buses[bus] = {"bus": bus, "section": sections[bus], "shed_mwh": shed / 1000,
                      "disconnection_hours": disconnected * dt}
    weakest = [step.dispatch.pre.minimum_bus for step in baseline.steps if step.dispatch and step.dispatch.pre.violations]
    branches = []
    child_by_line = {line: bus for bus, line in order.parent_line_by_bus.items()}
    for line in network.lines:
        group = set(descendants[line.line_id])
        rated = line.ampacity_a
        currents = [step.pre_control_branch_current_a[line.line_id] for step in baseline.steps if step.pre_control_branch_current_a]
        branches.append({"branch": line.line_id, "section": sections[child_by_line[line.line_id]], "descendants": sorted(group),
                         "shed_mwh": sum(buses[bus]["shed_mwh"] for bus in group),
                         "limiting_voltage_hours": sum(bus in group for bus in weakest) * dt,
                         "ampacity_a": rated,
                         "pre_control_overload_hours": (sum(current > rated + 1e-6 for current in currents) * dt
                                                        if rated is not None and currents else None),
                         "maximum_pre_control_a": max(currents, default=None)})
    return branches, buses, sections


def select_windows(baseline, days, count):
    """Select nonoverlapping calendar-aligned windows; never span gaps."""
    steps = baseline.steps
    size = min(days * 24, len(steps))
    starts = list(range(0, len(steps) - size + 1, 24))
    chosen = []
    for number in range(count):
        available = [start for start in starts if all(start >= end or start + size <= first for first, end, _ in chosen)]
        if not available:
            break
        if number == 0:
            rule = "Highest baseline load shedding"
            measure = lambda step: step.shedding_kw or 0.
        elif number == 1:
            rule = "Highest baseline PV curtailment and uncontrolled export"
            measure = lambda step: (step.curtailment_kw or 0.) + ((step.dispatch.pre.export_kw or 0.) if step.dispatch else 0.)
        else:
            rule = "Seasonal separation, with baseline shedding tie-break"
            measure = lambda step: step.shedding_kw or 0.
        start = max(available, key=lambda first: (
            min(abs(first - old) for old, _, _ in chosen) if number >= 2 else 0,
            sum(map(measure, steps[first:first + size])), -first))
        chosen.append((start, start + size, rule))
    return sorted(chosen)


def rank_locations(network, profiles, settings, baseline, eligible, top_k, exploration, trial_kw, samples=6):
    """Evaluate bounded injections at the same corrected operating points as production."""
    branches, buses, sections = branch_severity(network, baseline)
    steps = baseline.steps
    stress = sorted(range(len(steps)), key=lambda i: (-(steps[i].shedding_kw or 0.), i))[:samples]
    surplus = sorted(range(len(steps)), key=lambda i: (-(steps[i].curtailment_kw or 0.),
                     steps[i].power_flow.slack_p_kw, i))[:samples]
    probes = {(index, direction): _operating_point(network, profile_at(profiles, index))
              for direction, indices in ((1, stress), (-1, surplus)) for index in indices}
    prepared = prepare_fbs(network, settings.fbs_config)
    calls = 0

    def solve(point):
        nonlocal calls
        calls += 1
        return prepared(point)

    corrector = NetworkCorrector(network, settings, solve)
    for bus in eligible:
        records = []
        for (index, direction), raw in probes.items():
            original = steps[index]
            accepted = relief = voltage = cost_relief = 0.
            reason = "No bounded trial passed final constraints"
            final_import = final_export = None
            for fraction in (1., .5, .25):
                power = trial_kw * fraction * direction
                trial = replace(raw, p_bess_kw={**raw.p_bess_kw, bus: power})
                flow = solve(trial)
                check = check_flow(flow, network, settings)
                corrected, final, _ = corrector.correct(trial, flow, check)
                post = check_flow(final, network, settings)
                if not post.converged or post.violations:
                    continue
                shed = sum(raw.p_load_kw.values()) - sum(corrected.p_load_kw.values())
                curtailed = sum(raw.p_pv_kw.values()) - sum(corrected.p_pv_kw.values())
                relief = (original.shedding_kw or 0.) - shed
                if direction < 0 and relief < -1e-6:
                    reason = "Charging increased baseline shedding"
                    continue
                accepted = power
                cost_relief = (relief * settings.shedding_penalty_per_kwh +
                               ((original.curtailment_kw or 0.) - curtailed) * settings.curtailment_penalty_per_kwh)
                weak = [key for key, value in (original.pre_control_voltage_pu or {}).items() if value < settings.voltage_min_pu]
                if weak and flow.converged:
                    voltage = mean(flow.voltage_mag_pu[key] - original.pre_control_voltage_pu[key] for key in weak)
                final_import, final_export = post.import_kw, post.export_kw
                reason = "Verified by corrected Numba FBS"
                break
            records.append({"timestamp": str(steps[index].timestamp), "direction": "discharge" if direction > 0 else "charge",
                            "accepted_kw": accepted, "shed_relief_kw": relief if accepted else None,
                            "corrective_cost_relief_usd_per_kwh": cost_relief / abs(accepted) if accepted else None,
                            "mean_weak_bus_voltage_delta_pu": voltage if accepted else None,
                            "final_import_kw": final_import, "final_export_kw": final_export, "reason": reason})
        discharge = [row for row in records if row["direction"] == "discharge"]
        charge = [row for row in records if row["direction"] == "charge"]
        shed_score = mean((row["shed_relief_kw"] or 0.) / trial_kw for row in discharge)
        voltage_score = mean((row["mean_weak_bus_voltage_delta_pu"] or 0.) / .01 for row in discharge)
        charge_score = mean(-row["accepted_kw"] / trial_kw for row in charge)
        buses[bus].update(shedding_relief_score=shed_score, voltage_support_score=voltage_score,
                          charging_score=charge_score, score=.70 * shed_score + .20 * voltage_score + .10 * charge_score,
                          probes=records, selection="not shortlisted")
    ranked = sorted(eligible, key=lambda bus: (-buses[bus]["score"], bus))
    distinct = []
    for bus in ranked:
        if sections[bus] not in {sections[picked] for picked in distinct}:
            distinct.append(bus)
    core = (distinct + [bus for bus in ranked if bus not in distinct])[:top_k]
    for bus in core:
        buses[bus]["selection"] = "section representative" if bus in distinct else "high trial score"
    extras = sorted((bus for bus in eligible if bus not in core),
                    key=lambda bus: (sections[bus] in {sections[picked] for picked in core}, buses[bus]["score"], bus))[:exploration]
    for bus in extras:
        buses[bus]["selection"] = "exploration outside top K"
    return tuple(core + extras), branches, buses, sections, {"fbs_calls": calls, "correction_seconds": corrector.seconds}
