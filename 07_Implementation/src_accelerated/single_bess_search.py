"""Screen one-battery placements and verify finalists on the complete chronology."""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from math import inf
from threading import Lock
from time import perf_counter

import numpy as np

from .constraint_dispatch import check_flow
from .fbs import prepare_fbs
from .metrics import capital_recovery_factor, evaluate_results, validate_annual_inputs, with_terminal_policy
from .network_control import NetworkCorrector
from .optimizer import CandidateEvaluation, _make_result, evaluate_finalists, optimize
from .simulation import simulate_timeseries


_BASELINE_LOCK = Lock()
_baseline = None


def baseline_fingerprint(network, profiles, simulation, economics, clock):
    digest = sha256(repr((asdict(network), asdict(simulation), asdict(economics), clock,
                          tuple(profiles.timestamps), profiles.dt_hours)).encode())
    for name in ("load_p_kw", "load_q_kvar", "pv_p_kw", "pv_q_kvar"):
        for bus, values in sorted(getattr(profiles, name).items()):
            digest.update(f"{name}:{bus}:{len(values)}\n".encode())
            digest.update(np.asarray(values, dtype="<f8").tobytes())
    return digest.hexdigest()


def annual_baseline(network, profiles, evaluator, clock, progress):
    global _baseline
    simulation = with_terminal_policy(evaluator.simulation_config, evaluator.economic_config)
    fingerprint = baseline_fingerprint(network, profiles, simulation, evaluator.economic_config, clock)
    with _BASELINE_LOCK:
        cached = _baseline
    if cached is not None and cached[0] == fingerprint:
        return cached[1], fingerprint, True
    result = simulate_timeseries(network, profiles, simulation, dispatch_policy=None, progress=progress)
    if result.completed and result.converged:
        with _BASELINE_LOCK:
            _baseline = fingerprint, result
    return result, fingerprint, False


def representative_windows(baseline, profiles, count):
    """Pick distinct complete weeks from each intended regime, with seasonal coverage."""
    weeks = [list(range(start, start + 168)) for start in range(0, len(profiles.timestamps) - 167, 168)]
    if len(weeks) < count:
        raise ValueError("Screening requires a complete year of hourly profiles")
    pressure = []
    for week in weeks:
        steps = [baseline.steps[index] for index in week]
        pressure.append((sum(step.shedding_kw or 0. for step in steps),
                         sum(step.curtailment_kw or 0. for step in steps),
                         sum(sum(step.requested_point.p_load_kw.values()) for step in steps)))
    median = float(np.median([value[2] for value in pressure]))
    rankings = (lambda i: -pressure[i][0], lambda i: -pressure[i][1],
                lambda i: abs(pressure[i][2] - median), lambda i: -pressure[i][0] - pressure[i][1])
    picked = []
    seasons = [(profiles.timestamps[week[84]].month - 1) // 3 for week in weeks]
    for key in rankings[:count]:
        remaining = [i for i in range(len(weeks)) if seasons[i] not in {seasons[j] for j in picked}]
        picked.append(min(remaining, key=lambda i: (key(i), i)))
    return [weeks[i] for i in sorted(picked)]


def screen_buses(network, baseline, windows, eligible, simulation, limit, exploratory):
    order = network.radial_order()
    solve = prepare_fbs(network, simulation.fbs_config)
    corrector = NetworkCorrector(network, simulation, solve)
    slack = order.slack_bus_id
    topological_branch = {}
    for bus in eligible:
        child, parent = bus, order.parent_bus_by_bus[bus]
        forks = []
        while True:
            if len(order.children_by_bus[parent]) > 1:
                forks.append(child)
            if parent == slack:
                break
            child, parent = parent, order.parent_bus_by_bus[parent]
        topological_branch[bus] = forks[-1] if forks else child
    # One measured injection and one charging experiment per selected week.
    trials = {}
    for week in windows:
        loss_hour = max(week, key=lambda i: (baseline.steps[i].shedding_kw or 0., -i))
        pv_hour = max(week, key=lambda i: (baseline.steps[i].curtailment_kw or 0., -i))
        trials[loss_hour, 100.] = None
        if baseline.steps[pv_hour].curtailment_kw:
            trials[pv_hour, -100.] = None
    evidence = []
    for bus in eligible:
        avoided = recovered_pv = 0.
        verified_probes = 0
        for index, kw in trials:
            step = baseline.steps[index]
            raw = step.requested_point
            injected = replace(raw, p_bess_kw={**raw.p_bess_kw, bus: kw})
            flow = solve(injected)
            point, flow, correction = corrector.correct(injected, flow, check_flow(flow, network, simulation))
            if correction.status not in ("verified", "not_needed"):
                continue
            verified_probes += 1
            if kw > 0.:
                shedding = sum(raw.p_load_kw.values()) - sum(point.p_load_kw.values())
                avoided += (step.shedding_kw or 0.) - shedding
            else:
                curtailed = sum(raw.p_pv_kw.values()) - sum(point.p_pv_kw.values())
                recovered_pv += (step.curtailment_kw or 0.) - curtailed
        local_shed = sum((step.shedding_by_bus_kw or {}).get(bus, 0.) for step in baseline.steps)
        voltage_deficit = sum(max(0., simulation.voltage_min_pu - (step.pre_control_voltage_pu or {}).get(bus, 1.))
                              for step in baseline.steps)
        evidence.append(dict(bus=bus, avoided_shedding_probe_kw=avoided, recovered_pv_probe_kw=recovered_pv,
                             local_baseline_shedding_kwh=local_shed, voltage_deficit_pu_hours=voltage_deficit,
                             feeder_branch=topological_branch[bus], verified_probes=verified_probes))
    ranked = sorted(evidence, key=lambda item: (-item["avoided_shedding_probe_kw"], -item["recovered_pv_probe_kw"],
                    -item["voltage_deficit_pu_hours"], -item["local_baseline_shedding_kwh"], item["bus"]))
    selected = ranked[:limit]
    remaining = ranked[limit:]
    for _ in range(min(exploratory, len(remaining))):
        covered = {item["feeder_branch"] for item in selected}
        choice = next((item for item in remaining if item["feeder_branch"] not in covered), remaining[-1])
        selected.append(choice)
        remaining.remove(choice)
    eligible_buses = {item["bus"] for item in selected}
    for item in ranked:
        item["retained"] = item["bus"] in eligible_buses
    return tuple(sorted(eligible_buses)), ranked, len(trials)


@dataclass
class WindowEvaluator:
    evaluator: object
    hours_in_year: int

    def __call__(self, network, windows, candidate):
        evaluator = self.evaluator
        economics = evaluator.economic_config
        battery = evaluator.battery_parameters.build_config(candidate)
        settings = with_terminal_policy(evaluator.simulation_config, economics)
        energy_shed = curtailment = purchases = credits = 0.
        failures = terminal_failures = total_hours = 0
        for profiles in windows:
            result = simulate_timeseries(network, profiles, settings, battery, evaluator.dispatch_policy,
                                         capture_dispatch=False)
            if not result.completed or not result.converged:
                return CandidateEvaluation(candidate, inf, False, message="Screening window FBS did not converge")
            metrics = evaluate_results(result, economics, battery)
            total_hours += len(result.steps)
            failures += sum(not step.feasible for step in result.steps)
            terminal_failures += sum(any(message.startswith("Terminal SOC closure") for message in step.messages)
                                     for step in result.steps)
            energy_shed += metrics.load_shedding_energy_kwh
            curtailment += metrics.curtailment_energy_kwh
            purchases += metrics.grid_import_energy_kwh
            credits += metrics.grid_export_energy_kwh
        capex = (economics.cost_per_kwh * battery.energy_capacity_kwh +
                 economics.cost_per_kw * battery.power_rating_kw + economics.fixed_installation_cost)
        ownership = capex * (capital_recovery_factor(economics.discount_rate, economics.lifetime_years) +
                             economics.annual_om_fraction)
        estimate = (purchases * economics.grid_import_tariff_per_kwh - credits * economics.grid_export_tariff_per_kwh +
                    curtailment * economics.curtailment_penalty_per_kwh + energy_shed * economics.shedding_penalty_per_kwh +
                    ownership * total_hours / self.hours_in_year)
        return CandidateEvaluation(candidate, estimate, failures == terminal_failures,
                                   message="Screening estimate; independent weeks start at the configured initial SOC",
                                   execution_metadata=dict(screened_shedding_kwh=energy_shed,
                                                           screened_terminal_failure_hours=terminal_failures,
                                                           screened_infeasible_hours=failures))


def _pick_finalists(evaluations, count, incumbents):
    valid = [evaluation for evaluation in evaluations if np.isfinite(evaluation.objective)]
    cost = sorted(valid, key=lambda row: (not row.feasible, row.objective, row.candidate))
    reliability = sorted(valid, key=lambda row: (not row.feasible,
                         row.execution_metadata["screened_shedding_kwh"], row.candidate))
    finalists = list(dict.fromkeys(incumbents))
    interleaved = [row.candidate for pair in zip(cost, reliability) for row in pair]
    for candidate in interleaved[:2]:
        if candidate not in finalists and len(finalists) < count:
            finalists.append(candidate)
    visited = {candidate.bus_id for candidate in finalists}
    for candidate in interleaved:
        if candidate.bus_id not in visited and len(finalists) < count:
            finalists.append(candidate)
            visited.add(candidate.bus_id)
    finalists.extend(candidate for candidate in dict.fromkeys(interleaved) if candidate not in finalists and len(finalists) < count)
    return finalists


def optimize_fast_verified(network, profiles, bounds, evaluator, config, *, mode, clock=None,
                           settings=None, stage=lambda _: None, progress=None):
    """Return an ordinary optimization result containing only full-year evaluations."""
    settings = settings or {}
    economics = evaluator.economic_config
    validate_annual_inputs(profiles.timestamps, economics, profiles.dt_hours)
    if economics.annual_day_weights:
        raise ValueError("Fast verified optimization requires a complete unweighted calendar year")
    if mode not in ("quick", "standard"):
        raise ValueError("Choose quick or standard screening")
    quick = mode == "quick"
    site_count = int(settings.get("screen_sites", 4 if quick else 9))
    exploratory = int(settings.get("screen_exploratory", 2 if quick else 3))
    finalist_count = int(settings.get("screen_finalists", 5 if quick else 8))
    if site_count < 1 or exploratory < 0 or finalist_count < 5:
        raise ValueError("Choose at least one screened site, zero or more exploration sites and five finalists")
    stage("Evaluating the annual no-BESS baseline before screening")
    started = perf_counter()
    baseline, fingerprint, cache_hit = annual_baseline(network, profiles, evaluator, clock, progress)
    timing = {"baseline_seconds": perf_counter() - started}
    if not baseline.completed or not baseline.converged:
        raise ValueError("Annual no-BESS FBS did not converge. Review the inputs or use Thorough to bypass screening.")
    stage("Screening single-BESS locations with measured FBS injection and charging trials")
    started = perf_counter()
    windows = representative_windows(baseline, profiles, 2 if quick else 4)
    sites, evidence, probes = screen_buses(network, baseline, windows, bounds.allowed_bus_ids,
                                         with_terminal_policy(evaluator.simulation_config, economics), site_count, exploratory)
    timing["location_screen_seconds"] = perf_counter() - started
    periods = [(profiles.timestamps[week[0]], profiles.timestamps[week[-1]] +
                (profiles.timestamps[1] - profiles.timestamps[0])) for week in windows]
    subprofiles = tuple(profiles.slice(start, end) for start, end in periods)
    screened_bounds = replace(bounds, allowed_bus_ids=sites)
    screened_config = replace(config, max_iterations=min(config.max_iterations, 6) if quick else config.max_iterations,
                              initial_candidates=tuple(candidate for candidate in config.initial_candidates
                                                       if candidate.bus_id in sites))
    stage("Running GWO on representative weeks. Interim figures are screening estimates.")
    started = perf_counter()
    screen = optimize(network, subprofiles, screened_bounds, WindowEvaluator(evaluator, len(profiles.timestamps)),
                      screened_config, progress=progress)
    timing["representative_gwo_seconds"] = perf_counter() - started
    finalists = _pick_finalists(screen.evaluations, finalist_count, config.initial_candidates)
    stage(f"Evaluating {len(finalists)} finalists on all {len(profiles.timestamps)} hours")
    started = perf_counter()
    evaluated = evaluate_finalists(network, profiles, bounds, evaluator, finalists, config.workers, progress=progress)
    timing["annual_finalists_seconds"] = perf_counter() - started
    history, best = [], inf
    for row in evaluated:
        if row.feasible:
            best = min(best, row.objective)
        history.append(best)
    reliable = min((row for row in evaluated if row.feasible), default=None,
                   key=lambda row: (row.metrics.load_shedding_energy_kwh, row.objective, row.candidate))
    return _make_result(evaluated, history, screen.iterations, {
        "algorithm": "GWO", "search_mode": f"{mode} fast verified", "history_axis": "full-year finalist",
        "seed": config.seed, "workers": config.workers, "annual_verification_hours": len(profiles.timestamps),
        "screening_candidate_count": len(screen.evaluations), "screening_probe_hours_per_bus": probes,
        "screening_estimate_window_cost_history": [v if np.isfinite(v) else None for v in screen.convergence_history],
        "screening_window_soc": "Independent weeks start at requested initial SOC; annual replay enforces full continuity",
        "screening_periods": [{"start": str(start), "end_exclusive": str(end)} for start, end in periods],
        "screened_locations": evidence, "baseline_fingerprint": fingerprint, "baseline_cache_hit": cache_hit,
        "verified_minimum_shedding_candidate": (dict(candidate=asdict(reliable.candidate),
            annual_shedding_kwh=reliable.metrics.load_shedding_energy_kwh, annual_cost=reliable.objective) if reliable else None),
        "stage_wall_seconds": timing,
    }), baseline
