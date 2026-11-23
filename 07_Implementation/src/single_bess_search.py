"""Screen one-battery placements and verify finalists on the complete chronology."""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from math import ceil, inf
from threading import Lock
from time import perf_counter

import numpy as np

from .metrics import evaluate_results, validate_annual_inputs, with_terminal_policy
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



def screen_buses(network, baseline, eligible, simulation, *, shedding_weight=0.5):
    """Shortlist the highest-priority one-third using equal rank weights.

    Each eligible non-slack bus gets (1) a voltage rank from its accumulated
    *pre-correction* undervoltage and (2) a shedding rank from its *post-
    correction* unserved energy. Lower ranks are more urgent. The final score
    is 0.5*voltage_rank + 0.5*shedding_rank. Equal shedding amounts share the
    same rank (notably zero-shedding buses), so bus ID cannot create artificial
    shedding priority. GWO still evaluates real annual costs independently.
    """
    if not isinstance(shedding_weight, (int, float)) or isinstance(shedding_weight, bool) or not 0 <= shedding_weight <= 1:
        raise ValueError('shedding_weight must be within [0, 1]')
    valid = sorted(set(int(bus) for bus in eligible))
    slack = network.slack_bus_id()
    bus_ids = {bus.bus_id for bus in network.buses}
    if not valid or slack in valid or not set(valid) <= bus_ids:
        raise ValueError("Eligible BESS sites must be known, non-slack buses")
    if not baseline.steps:
        raise ValueError("A full-year operating result is required for bus screening")
    hours = float(baseline.dt_hours)
    if not np.isfinite(hours) or hours <= 0:
        raise ValueError("Bus screening requires a positive finite time step")
    traces = {bus: [] for bus in valid}
    shed_energy = {bus: 0.0 for bus in valid}
    for step in baseline.steps:
        voltages = step.pre_control_voltage_pu
        if not isinstance(voltages, dict) or any(bus not in voltages for bus in valid):
            raise ValueError("Pre-correction voltages are missing; rerun the annual simulation with voltage capture")
        shedding = step.shedding_by_bus_kw
        if not isinstance(shedding, dict):
            raise ValueError("Per-bus load shedding is missing; rerun the annual simulation with correction records")
        for bus in valid:
            v = float(voltages[bus])
            shed_kw = float(shedding.get(bus, 0.0))
            if not np.isfinite(v) or v <= 0:
                raise ValueError(f"Invalid pre-correction voltage for bus {bus}: {v}")
            if not np.isfinite(shed_kw) or shed_kw < -1e-9:
                raise ValueError(f"Invalid load shedding for bus {bus}: {shed_kw}")
            traces[bus].append(v)
            shed_energy[bus] += max(0.0, shed_kw) * hours
    evidence = []
    for bus in valid:
        values = np.asarray(traces[bus], dtype=float)
        deficit = np.maximum(0., simulation.voltage_min_pu - values)
        evidence.append({
            'bus': bus,
            'voltage_deficit_pu_hours': float(deficit.sum() * hours),
            'worst_pre_control_voltage_pu': float(values.min()),
            'undervoltage_hours': float(np.count_nonzero(deficit > 0) * hours),
            'local_baseline_shedding_kwh': float(shed_energy[bus]),
        })

    # Equal ranks for exactly equal metrics. In particular, no-shedding buses
    # all receive the same shedding rank; alphabetical/numeric IDs are not a
    # proxy for technical weakness.
    voltage_sorted = sorted(evidence, key=lambda r: (-r['voltage_deficit_pu_hours'],
                    r['worst_pre_control_voltage_pu'], -r['undervoltage_hours'], r['bus']))
    last_voltage = None
    for index, row in enumerate(voltage_sorted, 1):
        signature = (round(row['voltage_deficit_pu_hours'], 10),
                     round(row['worst_pre_control_voltage_pu'], 10), row['undervoltage_hours'])
        if signature != last_voltage:
            rank = index
            last_voltage = signature
        row['voltage_rank'] = rank
    shedding_sorted = sorted(evidence, key=lambda r: (-r['local_baseline_shedding_kwh'], r['bus']))
    last_shedding = None
    for index, row in enumerate(shedding_sorted, 1):
        signature = round(row['local_baseline_shedding_kwh'], 9)
        if signature != last_shedding:
            rank = index
            last_shedding = signature
        row['shedding_rank'] = rank
    for row in evidence:
        row['combined_score'] = ((1 - shedding_weight) * row['voltage_rank'] +
                                 shedding_weight * row['shedding_rank'])
    ranked = sorted(evidence, key=lambda row: (row['combined_score'],
                    row['shedding_rank'] if shedding_weight > .5 else row['voltage_rank'],
                    row['voltage_rank'] if shedding_weight > .5 else row['shedding_rank'], row['bus']))
    count = ceil(len(valid) / 3)
    for index, row in enumerate(ranked, 1):
        row['rank'] = index
        row['combined_rank'] = index
        row['retained'] = index <= count
    return tuple(row['bus'] for row in ranked[:count]), ranked, 0


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
        failures = total_hours = 0
        for profiles in windows:
            result = simulate_timeseries(network, profiles, settings, battery, evaluator.dispatch_policy,
                                         capture_dispatch=False)
            if not result.completed or not result.converged:
                return CandidateEvaluation(candidate, inf, False, message="Screening window FBS did not converge")
            metrics = evaluate_results(result, economics, battery)
            total_hours += len(result.steps)
            failures += sum(not step.feasible for step in result.steps)
            energy_shed += metrics.load_shedding_energy_kwh
            curtailment += metrics.curtailment_energy_kwh
            purchases += metrics.grid_import_energy_kwh
            credits += metrics.grid_export_energy_kwh
        operating_estimate = (purchases * economics.grid_import_tariff_per_kwh
                              - credits * economics.grid_export_tariff_per_kwh
                              + curtailment * economics.curtailment_penalty_per_kwh
                              + energy_shed * economics.shedding_penalty_per_kwh)
        # Screening windows are representative, not a full year. Annualize their
        # operating component to the study calendar before adding one FULL annual
        # ownership charge (never multiply fixed annual ownership by window count).
        capex = (candidate.power_rating_kw * economics.cost_per_kw
                 + candidate.energy_capacity_kwh * economics.cost_per_kwh)
        annual_bess_cost = capex / economics.lifetime_years + capex * economics.annual_om_fraction
        annual_hours = self.hours_in_year
        if total_hours <= 0:
            raise ValueError("Screening windows have no valid duration")
        estimate = operating_estimate * (annual_hours / total_hours) + annual_bess_cost
        return CandidateEvaluation(candidate, estimate, failures == 0,
                                   message="Screening estimate; independent weeks start at the configured initial SOC",
                                   execution_metadata=dict(screened_shedding_kwh=energy_shed,
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
    if mode not in ("quick", "standard"):
        raise ValueError("Choose quick or standard screening")
    quick = mode == "quick"
    finalist_count = 5 if quick else 8
    stage("Evaluating the annual no-BESS baseline before screening")
    started = perf_counter()
    baseline, fingerprint, cache_hit = annual_baseline(network, profiles, evaluator, clock, progress)
    timing = {"baseline_seconds": perf_counter() - started}
    if not baseline.completed or not baseline.converged:
        raise ValueError("Annual no-BESS FBS did not converge. Review the inputs or use Thorough to bypass screening.")
    stage("Ranking voltage weakness and load shedding (50/50); selecting the top one-third")
    started = perf_counter()
    windows = representative_windows(baseline, profiles, 2 if quick else 4)
    sites, evidence, probes = screen_buses(network, baseline, bounds.allowed_bus_ids,
                                         with_terminal_policy(evaluator.simulation_config, economics))
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
    finalists = _pick_finalists(screen.evaluations, finalist_count, screened_config.initial_candidates)
    stage(f"Evaluating {len(finalists)} finalists on all {len(profiles.timestamps)} hours")
    started = perf_counter()
    # Full-year verification cannot evaluate sites outside the screened catalog.
    evaluated = evaluate_finalists(network, profiles, screened_bounds, evaluator, finalists, config.workers, progress=progress)
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
        "screening_candidate_count": len(screen.evaluations), "screening_probe_hours_per_bus": probes, "screening_method": "50% pre-correction voltage rank + 50% annual bus shedding rank; top ceil(eligible/3)",
        "screening_estimate_window_cost_history": [v if np.isfinite(v) else None for v in screen.convergence_history],
        "screening_window_soc": "Independent weeks start at requested initial SOC; annual replay enforces full continuity",
        "screening_periods": [{"start": str(start), "end_exclusive": str(end)} for start, end in periods],
        "screened_locations": evidence, "ranking_weights": {"voltage": 0.5, "shedding": 0.5}, "baseline_fingerprint": fingerprint, "baseline_cache_hit": cache_hit,
        "verified_minimum_shedding_candidate": (dict(candidate=asdict(reliable.candidate),
            annual_shedding_kwh=reliable.metrics.load_shedding_energy_kwh, annual_cost=reliable.objective) if reliable else None),
        "stage_wall_seconds": timing,
    }), baseline
