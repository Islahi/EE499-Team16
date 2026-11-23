"""Barebones sequential multi-BESS siting for EE499.

Adaptation of Karve et al. (2025) sequential weak-bus selection. The network
objective, constraints, and GWO implementation here are our EE499 design,
NOT a reproduction of the article's IGWO/TOPSIS APL/PSI/VSI formulation.

Each accepted battery stays installed. Every new candidate is evaluated
alongside the entire installed fleet in one physically coupled FBS model.
"""
from dataclasses import asdict, dataclass, field, replace
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from copy import copy
from math import ceil, inf, isfinite
from time import perf_counter

from .metrics import evaluate_results, validate_annual_inputs, with_terminal_policy, annual_capital_recovery_factor
from .optimizer import (BESSCandidate, CandidateEvaluation, OptimizationResult,
                        OptimizerConfig, OptimizationBounds, optimize, _without_progress)
from .simulation import simulate_timeseries
from .screening_soc import ChronologicalSOCWarmStarts
from .single_bess_search import screen_buses
from .feeder_aware import (ImprovementRules, lateral_map, summarize_laterals,
                           balanced_shortlist, representative_lateral_windows,
                           incremental_and_cumulative_improvement)


def annual_fleet(network, profiles, evaluator, fleet, *, capture_dispatch=True,
                 progress=None, continue_after_failure=False):
    """Same annual simulation for selection, screening and final replay."""
    cfgs = tuple(evaluator.battery_parameters.build_config(c) for c in fleet)
    settings = with_terminal_policy(evaluator.simulation_config, evaluator.economic_config)
    if cfgs:
        if continue_after_failure:
            settings = replace(settings, stop_on_power_flow_failure=False)
        result = simulate_timeseries(network, profiles, settings, bess_fleet=cfgs,
                                     capture_dispatch=capture_dispatch, progress=progress)
        coverage = annual_coverage(result, profiles) if len(profiles.timestamps) in (8760, 8784) else None
        metrics = (evaluate_results(result, evaluator.economic_config, cfgs)
                   if result.completed and result.converged and (coverage is None or coverage['complete']) else None)
    else:
        if capture_dispatch:
            # Reuse the existing full-profile-content fingerprint cache across
            # repeated runs in the same Windows process. It invalidates when
            # network, input profiles, settings, or economics change.
            from .single_bess_search import annual_baseline
            result, _, cache_hit = annual_baseline(
                network, profiles, evaluator, profiles.timestamps[0], progress)
            result.dispatch_timing['no_bess_cache_hit'] = cache_hit
        else:
            result = simulate_timeseries(network, profiles, settings, bess_config=None,
                                         dispatch_policy=None, capture_dispatch=False,
                                         progress=progress)
        metrics = evaluate_results(result, evaluator.economic_config, None) if result.completed and result.converged else None
    return result, metrics


def annual_coverage(result, profiles):
    """Audit timestamps, not just simulator.completed; do not extrapolate short runs.

    The 8760/8784-hour gate is applied to *verified annual finalists*. GWO
    screening is intentionally performed on a separately labeled short window.
    """
    expected = tuple(profiles.timestamps)
    got = tuple(step.timestamp for step in result.steps)
    aligned = len(got) == len(expected) and all(a == b for a, b in zip(got, expected))
    n = len(got)
    complete = bool(result.completed and aligned and n == len(expected) and
                    len(expected) in (8760, 8784) and profiles.dt_hours == 1.0)
    return {'expected_hours': len(expected), 'processed_hours': n,
            'coverage_percent': 100.0 * n / len(expected) if expected else 0.0,
            'complete': complete,
            'status': ('complete_annual' if complete else
                       'incomplete_annual' if n < len(expected) else 'timestamp_mismatch'),
            'converged': bool(result.converged),
            'feasible': bool(result.feasible),
            'first_timestamp': str(got[0]) if got else None,
            'last_timestamp': str(got[-1]) if got else None}


@dataclass
class FleetWindowEvaluator:
    """Evaluate GWO size/location on selected contiguous periods, not annual claims."""
    original_evaluator: object
    installed: tuple[BESSCandidate, ...]
    annual_hours: int
    reference_shedding_kwh: float = 0.0
    reference_voltage_pu_hours: float = 0.0
    reference_annual_cost: float = 1.0
    # Scoped to one installed fleet, exact representative windows, input set,
    # cost/dispatch settings. Never reuse after the fleet or windows change.
    evaluation_cache: dict = field(default_factory=dict)
    cache_hits: int = 0
    soc_warm_starts: object = None

    def __call__(self, network, windows, candidate):
        if candidate in self.evaluation_cache:
            self.cache_hits += 1
            return self.evaluation_cache[candidate]
        result = self._evaluate_uncached(network, windows, candidate)
        self.evaluation_cache[candidate] = result
        return result

    def _evaluate_uncached(self, network, windows, candidate):
        configs = tuple(self.original_evaluator.battery_parameters.build_config(c)
                        for c in (*self.installed, candidate))
        economics = self.original_evaluator.economic_config
        # Screening windows and full-year replay both have no terminal SOC closure.
        settings = with_terminal_policy(self.original_evaluator.simulation_config, economics)
        hours = 0
        energy_import = energy_export = shed = curt = voltage_deficit = 0.0
        terminal_recharge_cost = 0.0
        soc_inputs = []
        for window in windows:
            # Each physical window starts at its *estimated actual annual SOC*,
            # not with freshly gifted 50%-SOC battery energy. The full-year
            # candidate evaluation still uses exact uninterrupted SOC.
            if self.soc_warm_starts is not None:
                idx = self.soc_warm_starts.starts[len(soc_inputs)]
                estimates = self.soc_warm_starts.window_start_energy(idx, configs, configs[-1])
                from copy import copy as copy_config
                active = []
                for config in configs:
                    copied = copy_config(config)
                    copied.soc_initial = min(config.soc_max, max(config.soc_min,
                                         estimates[config.bus_id] / config.energy_capacity_kwh))
                    active.append(copied)
                window_configs = tuple(active)
                soc_inputs.append({'start':str(window.timestamps[0]),
                                   'initial_soc':{c.bus_id: c.soc_initial for c in window_configs}})
            else:
                window_configs = configs
            simulation = simulate_timeseries(network, window, settings,
                                             bess_fleet=window_configs, capture_dispatch=False)
            if (not simulation.completed or len(simulation.steps) != len(window.timestamps)
                    or not simulation.converged or not simulation.feasible):
                return CandidateEvaluation(candidate, inf, False, message='Representative period infeasible')
            metrics = evaluate_results(simulation, economics, window_configs)
            if metrics.load_shedding_energy_kwh is None or metrics.curtailment_energy_kwh is None:
                return CandidateEvaluation(candidate, inf, False, message='Missing corrective-control records')
            voltage_deficit += sum(max(0., settings.voltage_min_pu - value) * simulation.dt_hours
                                   for step in simulation.steps for value in step.pre_control_voltage_pu.values())
            energy_import += metrics.grid_import_energy_kwh
            energy_export += metrics.grid_export_energy_kwh
            shed += metrics.load_shedding_energy_kwh
            curt += metrics.curtailment_energy_kwh
            hours += len(window.timestamps)
            # Each representative window starts at an independent initial SOC.
            # Charge for its net inventory depletion to avoid gifting very large
            # BESS units free energy during each sampled week. The annual year
            # is still verified with uninterrupted SOC dynamics.
            for config in window_configs:
                final_state = (simulation.final_fleet_states or {}).get(config.bus_id)
                if final_state is None:
                    return CandidateEvaluation(candidate, inf, False, message='Missing window final SOC')
                delta = config.energy_capacity_kwh * config.soc_initial - final_state.energy_kwh
                if delta > 0:
                    terminal_recharge_cost += (delta / config.eta_charge) * economics.grid_import_tariff_per_kwh
                elif delta < 0:
                    terminal_recharge_cost += delta * config.eta_discharge * economics.grid_export_tariff_per_kwh
        if not hours:
            return CandidateEvaluation(candidate, inf, False, message='Empty representative window')
        purchase = sum(economics.cost_per_kw * c.power_rating_kw * (economics.inverter_kva_per_kw if economics.power_cost_basis == 'kva' else 1.0)
                       + economics.cost_per_kwh * c.energy_capacity_kwh for c in configs)
        fixed_yearly = purchase * (annual_capital_recovery_factor(economics) + economics.annual_om_fraction)
        operational = (energy_import * economics.grid_import_tariff_per_kwh
                       - energy_export * economics.grid_export_tariff_per_kwh
                       + shed * economics.shedding_penalty_per_kwh
                       + curt * economics.curtailment_penalty_per_kwh)
        estimated_cost = (operational + terminal_recharge_cost) * self.annual_hours / hours + fixed_yearly
        # Technical-first GWO screening. Cost is retained as a smaller
        # preference, not a hard blocker against feeder improvements.
        shedding_ratio = (shed / self.reference_shedding_kwh
                          if self.reference_shedding_kwh > 1e-7 else 0.0)
        voltage_ratio = (voltage_deficit / self.reference_voltage_pu_hours
                         if self.reference_voltage_pu_hours > 1e-7 else 0.0)
        cost_ratio = estimated_cost / max(1., abs(self.reference_annual_cost))
        # Voltage is valued until the physical limit is met; more shedding
        # reduction remains the primary technical preference. If only one
        # stressed metric exists, give it the complete technical weight.
        active_shed = self.reference_shedding_kwh > 1e-7
        active_voltage = self.reference_voltage_pu_hours > 1e-7
        if active_shed and active_voltage:
            technical = 0.80 * shedding_ratio + 0.20 * voltage_ratio
        elif active_shed:
            technical = shedding_ratio
        elif active_voltage:
            technical = voltage_ratio
        else:
            technical = None
        score = .94 * technical + .06 * cost_ratio if technical is not None else cost_ratio
        return CandidateEvaluation(candidate, score, True,
                                   message='Representative technical-first screening score (not annual USD)',
                                   execution_metadata={'screened_shedding_kwh': shed, 'screened_voltage_deficit_pu_hours': voltage_deficit,
                                                       'estimated_annual_cost': estimated_cost, 'hours': hours,
                                                       'screening_only': True,
                                                       'soc_estimator': 'candidate-specific annual chronological energy proxy' if self.soc_warm_starts is not None else 'independent cold starts',
                                                       'window_initial_soc': soc_inputs,
                                                       'terminal_inventory_adjustment_usd': terminal_recharge_cost})


def _full_year_candidate(network, profiles, evaluator, installed, candidate, *,
                         baseline_laterals=None, initial_laterals=None, rules=None):
    """Perform exhaustive chronological finalist verification with an audit.

    Failed power flow is not silently truncated to a shorter 'year': the
    simulation scans all supplied annual timestamps, and any nonconvergent hour
    makes the candidate ineligible for acceptance.
    """
    result, metrics = annual_fleet(network, profiles, evaluator, (*installed, candidate),
                                  capture_dispatch=True, continue_after_failure=True)
    coverage = annual_coverage(result, profiles)
    timing = dict(result.dispatch_timing)
    timing['annual_coverage'] = coverage
    if not coverage['complete']:
        return (CandidateEvaluation(candidate, inf, False, metrics=None,
                 message=f"Annual verification incomplete ({coverage['processed_hours']}/"
                         f"{coverage['expected_hours']} hours)", execution_metadata=timing), result)
    if metrics is None or not metrics.feasible or metrics.annual_total_cost is None:
        return (CandidateEvaluation(candidate, inf, False, metrics=metrics,
                                    message=result.message, execution_metadata=timing), result)
    if baseline_laterals is not None:
        updated = summarize_laterals(network, result, evaluator.simulation_config.voltage_min_pu,
                                     profiles=profiles)
        target = lateral_map(network)[candidate.bus_id]
        timing['technical_check'] = incremental_and_cumulative_improvement(
            baseline_laterals, updated,
            initial_laterals if initial_laterals is not None else baseline_laterals,
            target, rules or ImprovementRules())
        timing['lateral_metrics_after'] = updated
        # All-candidate year-wide technical value (same weights used by GWO).
        totals_before = [sum(row[field] for row in baseline_laterals.values())
                         for field in ('shedding_kwh', 'voltage_deficit_pu_hours')]
        totals_after = [sum(row[field] for row in updated.values())
                        for field in ('shedding_kwh', 'voltage_deficit_pu_hours')]
        if totals_before[0] > 1e-7 and totals_before[1] > 1e-7:
            timing['annual_technical_remaining_ratio'] = (
                .80*totals_after[0]/totals_before[0] +
                .20*totals_after[1]/totals_before[1])
        else:
            ratios = [after/before for before, after in zip(totals_before,totals_after) if before>1e-7]
            timing['annual_technical_remaining_ratio'] = sum(ratios)/len(ratios) if ratios else 0.0
    return (CandidateEvaluation(candidate, metrics.annual_total_cost, True, metrics=metrics,
                                message='Complete chronological annual FBS verified', execution_metadata=timing), result)



_ANNUAL_WORKER_CONTEXT = None


def _init_annual_worker(study):
    """Initialize one independent annual simulation per worker process."""
    global _ANNUAL_WORKER_CONTEXT
    _ANNUAL_WORKER_CONTEXT = study
    try:
        from threadpoolctl import threadpool_limits
        threadpool_limits(limits=1)
    except ImportError:
        pass
    from .fbs import warm_numba
    warm_numba()


def _run_annual_worker(candidate):
    network, profiles, evaluator, installed, reference_laterals, initial_laterals, rules = _ANNUAL_WORKER_CONTEXT
    return _full_year_candidate(network, profiles, evaluator, installed, candidate,
                                baseline_laterals=reference_laterals,
                                initial_laterals=initial_laterals, rules=rules)


def _verify_annual_batch(network, profiles, evaluator, installed, candidates,
                         reference_laterals, initial_laterals, rules, workers=1):
    """Return full-year checked candidates in input order; never parallelize hours.

    At most two annual tasks run at once to limit RAM usage. Results include
    exact chronological timestamps and the complete accepted-fleet trajectory.
    Multiprocessing is optional; serial mode remains the validation reference.
    """
    candidates = tuple(candidates)
    if not candidates:
        return {}
    if workers <= 1 or len(candidates) == 1:
        return {candidate: _full_year_candidate(network, profiles, evaluator, installed, candidate,
                 baseline_laterals=reference_laterals, initial_laterals=initial_laterals,
                 rules=rules) for candidate in candidates}
    safe_evaluator = copy(evaluator)
    if hasattr(safe_evaluator, 'progress'):
        safe_evaluator.progress = None
    context = (network, profiles, safe_evaluator, tuple(installed), reference_laterals,
               initial_laterals, rules)
    # map returns results in finalist order regardless of finish order.
    with ProcessPoolExecutor(max_workers=min(2, workers, len(candidates)),
                             mp_context=get_context(), initializer=_init_annual_worker,
                             initargs=(context,)) as executor:
        return dict(zip(candidates, executor.map(_run_annual_worker, candidates)))

def _refine_annual_energy(network, profiles, evaluator, installed, winner, winner_result,
                          bounds, reference_laterals, initial_laterals, rules, workers=1):
    """Cost-vs-reliability check for smaller capacities at fixed bus and kW.

    Only fully verified annual alternatives may replace the GWO-selected
    design. Never force a small battery if annual reliability falls materially.
    Candidate budget <= 4 additional annual simulations per accepted stage.
    """
    origin = winner.candidate
    # Energy-refinement must never revisit a too-short duration at fixed kW.
    choices = [float(e) for e in bounds.energies_for_power(origin.power_rating_kw)
               if e < origin.energy_capacity_kwh]
    if not choices or winner_result is None:
        return winner, winner_result, [], 0
    positions = sorted(set([0, len(choices)//3, (2*len(choices))//3, len(choices)-1]))
    smaller = [BESSCandidate(origin.bus_id, origin.power_rating_kw, choices[k]) for k in positions]
    evaluations = _verify_annual_batch(network, profiles, evaluator, installed, smaller,
                    reference_laterals, initial_laterals, rules, workers=workers)
    base_ratio = winner.execution_metadata.get('annual_technical_remaining_ratio')
    if base_ratio is None:
        return winner, winner_result, [], len(smaller)
    # At most 0.5 percentage point extra weighted annual burden; or 5% of
    # the observed technical benefit if it is larger. Defensible *tolerance*,
    # not a requirement that every option must be smaller.
    tolerance = max(0.005, 0.05 * max(0., 1. - base_ratio))
    selected, selected_result = winner, winner_result
    reports = []
    for candidate in smaller:
        checked = evaluations[candidate]
        item, annual = checked if isinstance(checked, tuple) else (checked, None)
        technical = item.execution_metadata.get('technical_check', {})
        ratio = item.execution_metadata.get('annual_technical_remaining_ratio')
        coverage = item.execution_metadata.get('annual_coverage', {})
        acceptable = bool(item.feasible and technical.get('acceptable', False) and
                          coverage.get('complete', False) and ratio is not None and
                          ratio <= base_ratio + tolerance)
        if acceptable and annual is not None and item.objective < selected.objective - 1e-5:
            selected, selected_result = item, annual
        reports.append({
            'bus':candidate.bus_id, 'power_kw':candidate.power_rating_kw,
            'energy_kwh':candidate.energy_capacity_kwh,
            'annual_cost':item.objective if isfinite(item.objective) else None,
            'annual_technical_remaining_ratio':ratio,
            'technical_acceptable':bool(technical.get('acceptable', False)),
            'near_equivalent_reliability':acceptable,
            'annual_coverage_complete':coverage.get('complete', False),
            'retained':selected.candidate == candidate,
            'criterion':'annual cost lower and weighted technical ratio <= original + '
                        + f'{tolerance:.6f}'})
    for row in reports:
        row['selected_final'] = (row['bus'], row['power_kw'], row['energy_kwh']) == (
            selected.candidate.bus_id, selected.candidate.power_rating_kw, selected.candidate.energy_capacity_kwh)
    return selected, selected_result, reports, len(smaller)


def _power_band(power, bounds):
    minimum, maximum = bounds.power_ratings_kw[0], bounds.power_ratings_kw[-1]
    if maximum <= minimum:
        return 'only'
    position = (power - minimum) / (maximum - minimum)
    return 'low' if position < 1 / 3 else 'medium' if position < 2 / 3 else 'high'


def _diverse_finalists(evaluations, count, network=None, priority=None, bounds=None):
    """Include both weak laterals and larger kW ratings in annual verification.

    Select at most 'count' design points. Explicit high-power and medium-power
    probes are granted slots rather than disappearing behind small cheap kW
    configurations from a single bus. Screen scores are NOT annual results.
    """
    valid = sorted((item for item in evaluations if item.feasible and isfinite(item.objective)),
                   key=lambda item: (item.objective, item.candidate))
    selected = []
    seen = set()
    mapping = lateral_map(network) if network is not None else {}
    def add(item):
        if item is not None and item.candidate not in seen and len(selected) < count:
            selected.append(item.candidate)
            seen.add(item.candidate)
    if not valid:
        return selected
    add(valid[0])
    if mapping:
        first_lateral = mapping[valid[0].candidate.bus_id]
        other_laterals = sorted({mapping[item.candidate.bus_id] for item in valid
                                 if mapping[item.candidate.bus_id] != first_lateral},
                                key=lambda label: (-(priority or {}).get(label, 0.), label))
        if other_laterals:
            add(next((e for e in valid if mapping[e.candidate.bus_id] == other_laterals[0]), None))
    if bounds is not None:
        # Before the third annual verification, always explore a high-power
        # option when one was tested and found feasible during screening.
        for band in ('high', 'medium'):
            add(next((e for e in valid if _power_band(e.candidate.power_rating_kw, bounds) == band), None))
        # For larger annual budgets, explicitly include a compact energy design.
        add(min(valid, key=lambda e: (e.candidate.energy_capacity_kwh, e.objective)))
    if mapping:
        for label in sorted(set(mapping.values()), key=lambda label: (-(priority or {}).get(label, 0.), label)):
            add(next((e for e in valid if mapping[e.candidate.bus_id] == label), None))
    for item in valid:
        if len(selected) >= count:
            break
        if item.candidate.bus_id not in {s.bus_id for s in selected}:
            add(item)
    for item in valid:
        add(item)
        if len(selected) >= count:
            break
    return selected


def _probe_lateral_candidates(evaluator, network, windows, sites, evidence, bounds,
                              installed, annual_hours, reference, *, limit_per_lateral=7,
                              trial_evaluator=None):
    """Deterministic exploration prevents GWO from silently omitting a lateral.

    Only a few catalog-valid kW/kWh combinations are probed. The probes are
    scored on representative periods and never accepted without full-year FBS.
    """
    mapping = lateral_map(network)
    best = {}
    for row in evidence:
        bus = row['bus']
        if bus in sites and mapping[bus] not in best:
            best[mapping[bus]] = bus
    # Probe low, medium and high powers, but only in E/P-compatible ranges.
    # Retain diversity without spending any expensive screening time on
    # invalid battery-duration designs.
    powers = bounds.feasible_power_ratings()
    selected_powers = tuple(dict.fromkeys((powers[0], powers[len(powers)//2], powers[-1])))
    designs = []
    for power in selected_powers:
        energies = bounds.energies_for_power(power)
        for energy in (energies[0], energies[len(energies)//2], energies[-1]):
            design = (power, energy)
            if design not in designs:
                designs.append(design)
    # Seven probes are enough to inspect all three power bands, extremes and
    # one center; do not let a low-power band take all seven positions.
    if len(designs) > 7:
        designs = [designs[i] for i in (0, 2, 3, 4, 5, 6, 8)]
    from .optimizer import BESSCandidate
    reference_shed, reference_voltage, reference_cost = reference
    trial = trial_evaluator or FleetWindowEvaluator(
        evaluator, tuple(installed), annual_hours,
        reference_shed, reference_voltage, reference_cost)
    screened = []
    for bus in best.values():
        for p,e in designs[:max(1,limit_per_lateral)]:
            candidate = BESSCandidate(bus,p,e)
            bounds.validate_candidate(candidate)
            screened.append(trial(network, windows, candidate))
    return screened


def _extend_windows_for_horizon(windows, hours, length=72):
    """Include a full first MPC look-ahead without crossing annual endpoints."""
    extended = []
    for group in windows:
        left = int(group[0])
        right = min(hours, left + length)
        left = max(0, right - length)
        extended.append(tuple(range(left, right)))
    return tuple(extended)


def _reference_window_metrics(baseline, selected_indices, voltage_min_pu):
    shed = voltage = 0.
    for group in selected_indices:
        for i in group:
            step = baseline.steps[i]
            shed += (step.shedding_kw or 0.) * baseline.dt_hours
            voltage += sum(max(0., voltage_min_pu - v) for v in step.pre_control_voltage_pu.values()) * baseline.dt_hours
    return shed, voltage




def _verify_fleet_annual(network, profiles, evaluator, fleet):
    """Run authoritative full-year chronological verification for a joint BESS fleet."""
    result, metrics = annual_fleet(
        network, profiles, evaluator, fleet,
        capture_dispatch=True, continue_after_failure=False,
    )
    coverage = annual_coverage(result, profiles) if len(profiles.timestamps) in (8760, 8784) else {
        'expected_hours': len(profiles.timestamps),
        'processed_hours': len(result.steps),
        'coverage_percent': 100.0 * len(result.steps) / max(1, len(profiles.timestamps)),
        'complete': bool(result.completed and len(result.steps) == len(profiles.timestamps)),
        'status': 'complete_short_study' if result.completed else 'incomplete',
        'converged': bool(result.converged),
        'feasible': bool(result.feasible),
    }
    return fleet, result, metrics, coverage


def _annual_fleet_worker_eval(fleet):
    network, profiles, evaluator = _ANNUAL_WORKER_CONTEXT
    return _verify_fleet_annual(network, profiles, evaluator, fleet)


def _select_diverse_fleet_finalists(ranked_fleets, limit):
    """Choose best-ranked distinct non-empty GA fleets; no forced size diversity."""
    non_empty = [ev for ev in ranked_fleets if ev.feasible and isfinite(ev.objective) and ev.fleet]
    chosen = []
    seen = set()

    def _add(ev):
        if ev.fleet not in seen and len(chosen) < limit:
            seen.add(ev.fleet)
            chosen.append(ev)

    # True best-to-worst scenario-cost order. Size diversity was needlessly
    # forcing less-promising fleets into expensive 8,760-hour verification.
    # The GA already explores 1..max_units and has an add/drop gene.
    for ev in non_empty:
        _add(ev)
        if len(chosen) >= limit:
            break
    return chosen


def _stress_screen_fleets(network, profiles, evaluator, finalists, scenarios, *, max_days=6):
    """Independent extreme/seasonal 24h holdouts before full-year verification.

    No stress day belongs to the GA medoids; no holdout affects the GA score.
    This is a *technical rejection* screen, not an annual cost claim. Its
    simulated hours and results are recorded for scientific audit.
    """
    from .data_loader import ProfileData
    from .multi_bess import simulate_timeseries_fleet
    from .metrics import with_terminal_policy
    import numpy as np
    import pandas as pd
    day_count=len(profiles.timestamps)//24
    if day_count<2 or not finalists:
        return list(finalists), [], ()
    medoids={d.day_index for d in scenarios.days}
    eligible=[d for d in range(day_count) if d not in medoids]
    if not eligible:
        return list(finalists), [], ()
    day_load=[];day_pv=[]
    for d in range(day_count):
        a=d*24;z=a+24
        day_load.append(sum(sum(v[a:z]) for v in profiles.load_p_kw.values()))
        day_pv.append(sum(sum(v[a:z]) for v in profiles.pv_p_kw.values()))
    # Distinct load / renewable extremes + one independent day per quarter.
    candidates=[max(eligible,key=lambda d:day_load[d]),
                min(eligible,key=lambda d:day_load[d]),
                max(eligible,key=lambda d:day_pv[d]),
                min(eligible,key=lambda d:day_pv[d])]
    for q in range(4):
        lo=q*day_count//4;hi=(q+1)*day_count//4
        region=[d for d in eligible if lo<=d<hi]
        if region:
            candidates.append(max(region,key=lambda d:day_load[d]-day_pv[d]))
    chosen=tuple(dict.fromkeys(candidates))[:max_days]
    holdouts=[]
    for d in chosen:
        start=pd.Timestamp(profiles.timestamps[d*24]);end=start+pd.Timedelta(hours=24)
        holdouts.append((d,profiles.slice(start,end)))
    settings=with_terminal_policy(evaluator.simulation_config,evaluator.economic_config)
    # Fail a fleet for an independent strict-mode violation, never for a
    # spurious scenario monetary estimate; leave remaining finalists in order.
    survivors=[];records=[]
    for ev in finalists:
        config=tuple(evaluator.battery_parameters.build_config(c) for c in ev.fleet)
        passed=True
        for day,day_profile in holdouts:
            sim=simulate_timeseries_fleet(network,day_profile,settings,config,capture_dispatch=False)
            ok=bool(sim.completed and sim.converged and sim.feasible
                    and len(sim.steps)==len(day_profile.timestamps))
            records.append({'fleet':[asdict(unit) for unit in ev.fleet],
                            'holdout_day_index':day,'hours':len(day_profile.timestamps),
                            'passed':ok,'message':sim.message})
            if not ok:
                passed=False
                break
        if passed:
            survivors.append(ev)
    return survivors,records,chosen


def _optimize_joint_fleet(
    network, profiles, bounds, evaluator, config,
    *, max_units=3, stage=lambda text: None, progress=None,
    finalists_per_stage=6, improvement_rules=None, annual_workers=1,
    ga_crossover_rate=0.80, ga_mutation_rate=0.20,
    baseline_result=None, baseline_metrics=None, initial_laterals=None,
    started=None,
):
    """Joint fleet optimization: k-means scenarios + Joint Multi-BESS GA + 8,760h verification.

    Minimizes the exact user economic target: annualized BESS CAPEX/O&M +
    load shedding + PV curtailment + grid import/export cost.
    """
    from .representative_days import build_kmeans_scenarios
    from .fleet_ga_optimizer import FleetGAConfig, run_joint_fleet_ga, canonical_fleet

    start = started if started is not None else perf_counter()
    rules = improvement_rules or ImprovementRules()
    voltage_min = evaluator.simulation_config.voltage_min_pu
    baseline_cost = baseline_metrics.annual_total_cost

    # V15.5: every explicitly permitted non-slack bus is a GA location gene.
    # Do NOT rank, discard or shortlist buses from the No-BESS voltage profile.
    # The electrical grouping below is used only for *mutation adjacency*, not
    # to restrict eligible sites or prioritize preselected weak buses.
    sites = list(bounds.allowed_bus_ids)
    lat_map = lateral_map(network)
    # Distances use cumulative |R+jX| along the radial path from the slack.
    # This only sets mutation-neighbor order, never excludes locations.
    order = network.radial_order()
    line_impedance = {ln.line_id: (ln.r_ohm**2 + ln.x_ohm**2)**0.5 for ln in network.lines}
    distance = {order.slack_bus_id: 0.0}
    def _distance(bus):
        if bus not in distance:
            parent = order.parent_bus_by_bus[bus]
            distance[bus] = _distance(parent) + line_impedance[order.parent_line_by_bus[bus]]
        return distance[bus]
    bus_order = tuple(sorted(sites, key=lambda b: (lat_map.get(b, ''), _distance(b), b)))
    ga_bounds = bounds
    evidence = []
    stage(f'SESS full-bus search: {len(sites)} eligible non-slack buses; no initial electrical ranking or shortlist')

    # 2. Build k-means probability-weighted representative 24-hour medoid days
    n_days = max(1, len(profiles.timestamps) // 24)
    n_clusters = min(12, n_days)
    scenarios = build_kmeans_scenarios(
        profiles, baseline_result,
        voltage_min_pu=voltage_min,
        n_clusters=n_clusters,
        seed=config.seed,
    )
    stage(
        f'Representative-day screening: clustered {scenarios.total_days} days into '
        f'{len(scenarios.days)} representative 24h scenarios ({scenarios.total_screened_hours}h total)'
    )

    # 3. Build lateral-diverse feasible seed fleets (1..max_units) obeying V14 duration limits
    powers = ga_bounds.feasible_power_ratings()
    p_mid = powers[len(powers) // 2]
    e_mid_list = ga_bounds.energies_for_power(p_mid)
    e_mid = e_mid_list[len(e_mid_list) // 2]
    p_hi = powers[-1]
    e_hi_list = ga_bounds.energies_for_power(p_hi)
    e_hi = e_hi_list[len(e_hi_list) // 2]

    seed_fleets = []
    if config.initial_candidates:
        valid_init = tuple(c for c in config.initial_candidates if c.bus_id in ga_bounds.allowed_bus_ids)
        if valid_init:
            seed_fleets.append(valid_init[:max_units])
    # Representative *geographic* seeds for each lateral are for population
    # diversity only. Every eligible bus remains available to mutations/crossover.
    grouped = {}
    for b in bus_order:
        grouped.setdefault(lat_map.get(b, ''), []).append(b)
    seed_buses = []
    for group in grouped.values():
        seed_buses.extend(dict.fromkeys((group[0], group[len(group)//2], group[-1])))
    for b in seed_buses:
        seed_fleets.append((BESSCandidate(b, p_mid, e_mid),))
    lateral_centers = [group[len(group)//2] for group in grouped.values()]
    if max_units >= 2 and len(lateral_centers) >= 2:
        seed_fleets.append(tuple(BESSCandidate(b, p_mid, e_mid) for b in lateral_centers[:2]))
    if max_units >= 3 and len(lateral_centers) >= 3:
        seed_fleets.append(tuple(BESSCandidate(b, p_mid, e_mid) for b in lateral_centers[:3]))

    # 4. Run Joint Multi-BESS Stationary GA (Ahmed, Sindi et al. 2023 SESS Eq. 53)
    ga_cfg = FleetGAConfig(
        population_size=max(8, int(config.population_size)),
        max_generations=max(4, int(config.max_iterations)),
        stall_generation_limit=config.convergence_patience,
        seed=config.seed,
        workers=min(config.workers, 8),
        crossover_rate=ga_crossover_rate, mutation_rate=ga_mutation_rate,
        relative_tolerance=config.convergence_relative_tolerance,
    )
    stage(
        f'Joint GA: optimizing up to {max_units} stationary BESS '
        f'(pop={ga_cfg.population_size}, max_gen={ga_cfg.max_generations}, workers={ga_cfg.workers})'
    )
    ga_out = run_joint_fleet_ga(
        network, scenarios, ga_bounds, evaluator,
        max_units=max_units,
        ga_config=ga_cfg,
        seed_fleets=tuple(seed_fleets),
        bus_order=bus_order,
        progress=progress,
    )
    stage(f"Joint GA stopped: {ga_out['stop_reason'].replace('_', ' ')} "
          f"after {ga_out['generations']} generations and {ga_out['unique_evaluated']} unique evaluations")

    # 5. First screen distinct extreme/seasonal days. Then verify the
    # highest-ranked survivor over the full chronological year. Verify the next
    # survivor ONLY if the preceding fleet fails feasibility or savings.
    # Keep the user's finalist budget as a safety cap, not an up-front batch.
    finalist_budget=max(1,int(finalists_per_stage))
    candidate_pool=_select_diverse_fleet_finalists(ga_out['ranked'],max(8,finalist_budget*3))
    stage(f'SESS independent stress screen: up to {len(candidate_pool)} candidate fleets')
    survivors,stress_records,stress_days=_stress_screen_fleets(
        network, profiles, evaluator, candidate_pool, scenarios, max_days=6)
    finalists=survivors[:finalist_budget]
    stage(f'SESS annual verification: {len(finalists)} eligible fallback(s), one chronological year at a time')
    verified_records=[]
    verified_evals=[]
    annual_evaluations=0 if getattr(baseline_result,'dispatch_timing',{}).get('no_bess_cache_hit') else 1
    winner_fleet=()
    winner_result=baseline_result
    winner_metrics=baseline_metrics
    winner_cost=baseline_cost
    for rank,ga_ev in enumerate(finalists,1):
        fleet=ga_ev.fleet
        stage(f'Annual finalist {rank}/{len(finalists)}: {[c.bus_id for c in fleet]} '
              f'(full {len(profiles.timestamps)} hourly steps)')
        fleet,yr_res,yr_met,cov=_verify_fleet_annual(network,profiles,evaluator,fleet)
        annual_evaluations+=1
        for unit in fleet:
            bounds.validate_candidate(unit)
        ok=(bool(cov.get('complete')) and yr_met is not None and yr_met.feasible
            and yr_met.annual_total_cost is not None and isfinite(yr_met.annual_total_cost))
        cost_val=yr_met.annual_total_cost if ok else inf
        econ_ok=ok and cost_val<baseline_cost-1e-6
        verified_evals.append(CandidateEvaluation(
            candidate=fleet[-1],objective=cost_val,feasible=ok,
            metrics=yr_met if ok else None,
            message=f'Joint GA finalist ({len(fleet)} unit(s)): {cov.get("status")}',
            execution_metadata={'annual_coverage':cov,'fleet':[asdict(u) for u in fleet]}))
        verified_records.append({
            'fleet':[asdict(u) for u in fleet], 'unit_count':len(fleet),
            'scenario_estimated_annual_cost':ga_ev.objective if isfinite(ga_ev.objective) else None,
            'annual_cost':cost_val if isfinite(cost_val) else None,
            'feasible':ok,'economic_acceptable':econ_ok,
            'verification_status':cov.get('status'),
            'annual_processed_hours':cov.get('processed_hours'),
            'annual_expected_hours':cov.get('expected_hours'),
        })
        if econ_ok:
            winner_fleet=fleet;winner_result=yr_res;winner_metrics=yr_met;winner_cost=cost_val
            stage(f'Annual finalist {rank}: verified feasible saving '
                  f'${baseline_cost-cost_val:,.2f}/year; stopping further annual runs')
            break

    final_laterals = summarize_laterals(network, winner_result, voltage_min, profiles=profiles)
    base_shedding = sum(v['shedding_kwh'] for v in initial_laterals.values())
    final_shedding = sum(v['shedding_kwh'] for v in final_laterals.values())
    base_voltage = sum(v['voltage_deficit_pu_hours'] for v in initial_laterals.values())
    final_voltage = sum(v['voltage_deficit_pu_hours'] for v in final_laterals.values())
    accepted_laterals = [lat_map.get(c.bus_id, '') for c in winner_fleet]

    strict_mode = evaluator.simulation_config.fleet_dispatch_mode == 'daily_milp_dispatch'
    economic = evaluator.economic_config
    annualization = ('real-discount CRF' if economic.annualization_method == 'real_crf' else
                     'straight-line recovery')
    power_cost = ('$ per inverter kVA' if economic.power_cost_basis == 'kva' else '$ per battery kW')

    stage_record = {
        'index': 1,
        'status': 'installed' if winner_fleet else 'not-installed: no verified annual cost saving',
        'algorithm': ('Joint SESS GA with daily MILP dispatch-style daily operating rules' if strict_mode else
                      'Joint SESS Stationary GA with independent P/Q controller'),
        'shortlist': list(sites),
        'weakness_ranking': [],
        'initial_ranking_applied': False,
        'independent_stress_days': list(stress_days),
        'stress_checks': stress_records,
        'screening_iterations': ga_out['generations'],
        'ga_stop_reason': ga_out['stop_reason'],
        'gwo_stop_reason': ga_out['stop_reason'],  # legacy export compatibility
        'ga_evaluations': ga_out['unique_evaluated'],
        'gwo_evaluations': ga_out['unique_evaluated'],  # legacy export compatibility
        'screening_hours_per_candidate': scenarios.total_screened_hours,
        'annual_finalists_verified': len(verified_records),
        'annual_finalists_screened': len(finalists),
        'annual_finalist_budget': finalists_per_stage,
        'full_year_candidates': verified_records,
        'selected': asdict(winner_fleet[-1]) if winner_fleet else None,
        'selected_fleet': [asdict(u) for u in winner_fleet],
        'annual_saving_vs_previous': baseline_cost - winner_cost,
        'updated_annual_cost': winner_cost,
    }

    metadata = {
        'algorithm': ('Joint SESS GA + k-means scenarios + daily MILP dispatch daily P/Q MILP + verified FBS'
                      if strict_mode else 'Joint SESS GA + k-means scenarios + coupled P/Q OPF'),
        'search_mode': 'All eligible buses; joint multi-BESS GA + independent stress holdouts + progressive annual verification',
        'eligible_bus_count': len(sites),
        'eligible_bus_ids': list(sites),
        'ga_visited_bus_ids': ga_out['visited_bus_ids'],
        'ga_visited_bus_count': len(ga_out['visited_bus_ids']),
        'initial_ranking_applied': False,
        'independent_stress_days': list(stress_days),
        'independent_stress_checks': stress_records,
        'independent_stress_candidate_count': len(candidate_pool),
        'annual_verification_fallback_budget': finalist_budget,
        'annual_early_stop_after_first_accepted': True,
        'annual_stress_survivors': len(survivors),
        'inverter_kva_per_kw': evaluator.economic_config.inverter_kva_per_kw,
        'power_cost_basis': evaluator.economic_config.power_cost_basis,
        'history_axis': 'generation',
        'seed': config.seed,
        'workers': ga_cfg.workers,
        'maximum_bess_units': max_units,
        'installed_bess_count': len(winner_fleet),
        'fleet': [asdict(c) for c in winner_fleet],
        'stages': [stage_record],
        'representative_days': scenarios.metadata(),
        'fleet_ga_optimizer': {
            'generations': ga_out['generations'],
            'unique_evaluated': ga_out['unique_evaluated'],
            'stop_reason': ga_out['stop_reason'],
            'elapsed_seconds': round(ga_out['elapsed_seconds'], 4),
            'config': ga_out['config'],
        },
        'screening_method': ('k-means representative 24h medoid days; Daily MILP dispatch MILP with discharge-linked PF and daily SOC restoration; full-year FBS verification'
                             if strict_mode else 'k-means representative 24h medoid days with coupled P/Q OPF; full-year FBS verification'),
        'annual_verification_required_hours': len(profiles.timestamps),
        'annual_verification_policy': 'One full chronological annual verification for first stress-passing best-ranked fleet; sequential annual fallback only on failed feasibility/economics; scenario and stress screening are not annual claims',
        'voltage_acceptance': (f'Verified final hourly {voltage_min:g}–'
                               f'{evaluator.simulation_config.voltage_max_pu:g} pu bounds, '
                               'with the existing voltage-deviation objective toward 1.0 pu'),
        'parallel_gwo_workers': ga_cfg.workers,
        'parallel_annual_workers': 1,
        'annual_requested_workers': annual_workers,
        'annual_worker_policy': 'sequential early stop to avoid unneeded full-year simulations',
        'improvement_rules': asdict(rules),
        'installed_laterals': accepted_laterals,
        'best_bess_candidate': asdict(winner_fleet[-1]) if winner_fleet else None,
        'best_bess_annual_cost': winner_cost if winner_fleet else None,
        'no_bess_selected': not bool(winner_fleet),
        'no_bess_feasible': True,
        'no_bess_annual_cost': baseline_cost,
        'objective_formula': ('grid imports tariff - exports tariff + shedding penalty + curtailment penalty + terminal inventory adjustment + BESS CAPEX annualized by '
                              + annualization + ' + annual O&M; power CAPEX basis: ' + power_cost),
        'bess_lifetime_years': evaluator.economic_config.lifetime_years,
        'annual_om_percent_of_capex': evaluator.economic_config.annual_om_fraction * 100,
        'best_bess_feasible': bool(winner_fleet),
        'feasible_bess_candidates': sum(item.feasible for item in verified_evals),
        'stage_wall_seconds': {'total_seconds': perf_counter() - start},
        'annual_fleet_simulations': annual_evaluations,
        'no_bess_cache_hit': bool(getattr(baseline_result, 'dispatch_timing', {}).get('no_bess_cache_hit')),
        'accepted_annual_results_reused': 1 if winner_fleet else 0,
        'convergence_stopping': 'GA stall_generation_limit',
        'daily_dispatch_assumptions': ({'discharge_linked_positive_q': True,
            'minimum_power_factor': evaluator.simulation_config.minimum_discharge_pf,
            'daily_soc_restoration_verified_hourly': True,
            'mutually_exclusive_charging_and_discharging': True,
            'forecast_source': 'saved hourly input profiles; offline perfect foresight',
            'not_full_mobile_paper_replication': True} if strict_mode else None),
        'cumulative_system_shedding_reduction_percent': (
            100. * (base_shedding - final_shedding) / base_shedding if base_shedding > 1e-9 else None
        ),
        'cumulative_system_voltage_deficit_reduction_percent': (
            100. * (base_voltage - final_voltage) / base_voltage if base_voltage > 1e-9 else None
        ),
        'cumulative_lateral_targets': {
            label: {
                'shedding_percent': (
                    100. * (before['shedding_kwh'] - final_laterals[label]['shedding_kwh']) / before['shedding_kwh']
                    if before['shedding_kwh'] > 1e-9 else None
                ),
                'voltage_percent': (
                    100. * (before['voltage_deficit_pu_hours'] - final_laterals[label]['voltage_deficit_pu_hours'])
                    / before['voltage_deficit_pu_hours']
                    if before['voltage_deficit_pu_hours'] > 1e-9 else None
                ),
            }
            for label, before in initial_laterals.items()
        },
        'delta_annual_cost': winner_cost - baseline_cost,
    }
    result = OptimizationResult(
        best_candidate=winner_fleet[-1] if winner_fleet else None,
        best_objective=winner_cost,
        metrics=winner_metrics,
        convergence_history=ga_out['history'],
        iterations=ga_out['generations'],
        success=True,
        message=(
            f'Joint GA verified {len(winner_fleet)} stationary BESS unit(s) saving '
            f'${baseline_cost - winner_cost:,.2f}/year.'
            if winner_fleet
            else 'No verified stationary BESS fleet beat the No-BESS baseline on annual total cost; No-BESS retained.'
        ),
        evaluations=verified_evals,
        metadata=metadata,
    )
    return result, baseline_result, winner_result


def optimize_sequential_multi(network, profiles, bounds, evaluator, config,
                              *, max_units=3, stage=lambda text: None, progress=None,
                              window_weeks=2, finalists_per_stage=6,
                              improvement_rules=None, annual_workers=None,
                              ga_crossover_rate=0.80, ga_mutation_rate=0.20):
    """Greedy sequential GWO with lateral-aware annual technical acceptance.

    In V13 OPF mode, annual cost becomes a mandatory improvement gate for
    each accepted addition; older V12 modes retain their historical behavior.
    No global-optimality guarantee or re-optimization of installed units.
    """
    rules = improvement_rules or ImprovementRules()
    if annual_workers is None:
        annual_workers = min(2, config.workers)
    if isinstance(annual_workers, bool) or not isinstance(annual_workers, int) or not 1 <= annual_workers <= 2:
        raise ValueError('Annual verification workers must be 1 or 2')
    validate_annual_inputs(profiles.timestamps, evaluator.economic_config, profiles.dt_hours)
    if not isinstance(max_units, int) or isinstance(max_units, bool) or not 1 <= max_units <= 3:
        raise ValueError('BESS units must be an integer from 1 to 3')
    if window_weeks < 1 or finalists_per_stage < 1:
        raise ValueError('Screening weeks and annual finalists must be positive')
    if not bounds.allowed_bus_ids:
        raise ValueError('At least one non-slack eligible bus is necessary')
    if any(c.bus_id not in bounds.allowed_bus_ids for c in config.initial_candidates):
        raise ValueError('Initial candidates must be in the approved allowed buses')
    start = perf_counter()
    stage('No-BESS full-year baseline (all eligible buses stay available to SESS Joint GA)'
          if evaluator.simulation_config.fleet_dispatch_mode in ('opf','daily_milp_dispatch')
          else 'No-BESS full-year simulation and combined voltage/shedding ranking')
    current_result, current_metrics = annual_fleet(network, profiles, evaluator, ())
    if current_metrics is None or not current_metrics.feasible or current_metrics.annual_total_cost is None:
        raise ValueError('No-BESS baseline cannot be verified; review network constraints and inputs')
    baseline_result = current_result
    baseline_cost = current_metrics.annual_total_cost
    initial_laterals = summarize_laterals(network, current_result,
                                         evaluator.simulation_config.voltage_min_pu,
                                         profiles=profiles)
    if evaluator.simulation_config.fleet_dispatch_mode in ('opf', 'daily_milp_dispatch'):
        return _optimize_joint_fleet(
            network, profiles, bounds, evaluator, config,
            max_units=max_units, stage=stage, progress=progress,
            finalists_per_stage=finalists_per_stage,
            improvement_rules=rules, annual_workers=annual_workers,
            ga_crossover_rate=ga_crossover_rate, ga_mutation_rate=ga_mutation_rate,
            baseline_result=baseline_result, baseline_metrics=current_metrics,
            initial_laterals=initial_laterals, started=start,
        )
    accepted_laterals = []
    installed = []
    history = []
    verified = []
    stages = []
    total_iterations = 0
    annual_evaluations = 0 if getattr(current_result, 'dispatch_timing', {}).get('no_bess_cache_hit') else 1
    screening_caches = {}  # Keyed by full stage context; never mix installed fleets.
    for sequence in range(1, max_units + 1):
        remaining = tuple(bus for bus in bounds.allowed_bus_ids
                          if bus not in {item.bus_id for item in installed})
        if not remaining:
            break
        stage(f'Placement {sequence}/{max_units}: reranking voltage and shedding after {len(installed)} BESS installations')
        _, evidence, _ = screen_buses(network, current_result, remaining,
                                      with_terminal_policy(evaluator.simulation_config, evaluator.economic_config),
                                      shedding_weight=0.8)
        sites = balanced_shortlist(network, evidence, remaining, installed=installed, rules=rules)
        if not sites:
            stages.append({'index': sequence, 'status': 'no-eligible-buses'})
            break
        # The newest coupled annual run supplies BOTH pre-control voltages and
        # post-correction per-bus shedding; installed buses are excluded.
        voltage_min = evaluator.simulation_config.voltage_min_pu
        reference_laterals = summarize_laterals(network, current_result, voltage_min, profiles=profiles)
        # Safe early rejection: if there is no shedding or voltage deficit
        # anywhere, no battery can provide the requested technical improvement.
        if (reference_laterals
                and all(row['shedding_kwh'] <= 1e-9 and row['voltage_deficit_pu_hours'] <= 1e-9
                        for row in reference_laterals.values())):
            stages.append({'index': sequence, 'status': 'not-installed: no residual technical problem'})
            stage(f'Placement {sequence}: all laterals satisfy shedding and pre-control voltage targets; stopping')
            break
        priority = {label: (row['shedding_kwh'] + 1000. * row['voltage_deficit_pu_hours'])
                    for label, row in reference_laterals.items()}
        initial_windows = representative_lateral_windows(network, current_result, profiles, window_weeks, voltage_min)
        # The 48h event anchors are retained, but each screening interval is
        # extended to 72h so the MPC receives a full initial look-ahead.
        windows = _extend_windows_for_horizon(initial_windows, len(profiles.timestamps))
        # Some unit tests replace the annual solver with a lightweight mock
        # without hourly records; the real full-year solver always supplies
        # exact annual steps. Keep mock compatibility explicit.
        soc_warm_starts = (ChronologicalSOCWarmStarts.from_annual(
            network, profiles, current_result, evaluator.simulation_config, windows)
            if len(getattr(current_result, 'steps', ())) == len(profiles.timestamps) else None)
        from pandas import Timestamp, Timedelta
        subprofiles = tuple(profiles.slice(profiles.timestamps[indices[0]],
                Timestamp(profiles.timestamps[indices[-1]]) + Timedelta(hours=1)) for indices in windows)
        initial = tuple(c for c in config.initial_candidates if c.bus_id in sites)
        stage_config = replace(config, initial_candidates=initial,
                               workers=min(config.workers, 8),
                               max_iterations=config.max_iterations,
                               seed=config.seed + sequence - 1)
        stage_bounds = replace(bounds, allowed_bus_ids=sites)
        stage(f'Placement {sequence}: GWO on {len(sites)} weak buses, {len(subprofiles)} 72h windows totaling {sum(len(w.timestamps) for w in subprofiles)} hours with annual SOC warm-starts')
        ref_shed, ref_voltage = _reference_window_metrics(current_result, windows, voltage_min)
        reference = (ref_shed, ref_voltage, current_metrics.annual_total_cost)
        cache_key = (tuple(installed), tuple(tuple(group) for group in windows), reference)
        stage_cache = screening_caches.setdefault(cache_key, {})
        screening = FleetWindowEvaluator(evaluator, tuple(installed), len(profiles.timestamps),
                                         *reference, evaluation_cache=stage_cache,
                                         soc_warm_starts=soc_warm_starts)
        search = optimize(network, subprofiles, stage_bounds, screening, stage_config, progress=progress)
        # Multiprocess GWO owns its local cache; merge for deterministic probes
        # in the parent. GWO still controls the complete best-so-far history.
        screening.evaluation_cache.update({item.candidate: item for item in search.evaluations})
        total_iterations += search.iterations
        # Evaluate a few explicit, size-diverse designs in every shortlisted
        # lateral, even if stochastic GWO never visits that region.
        probes = _probe_lateral_candidates(evaluator, network, subprofiles, sites, evidence,
                                           stage_bounds, tuple(installed), len(profiles.timestamps), reference,
                                           trial_evaluator=screening)
        evaluated = {item.candidate: item for item in search.evaluations}
        for item in probes:
            evaluated.setdefault(item.candidate, item)
        candidates = _diverse_finalists(evaluated.values(), finalists_per_stage,
                                        network, priority, bounds)
        for candidate in candidates:
            bounds.validate_candidate(candidate)
        record = {'index': sequence, 'eligible_count': len(remaining),
                  'candidate_count': len(sites), 'shortlist': list(sites),
                  'weakness_ranking': evidence, 'screening_iterations': search.iterations,
                  'gwo_stop_reason': search.metadata.get('stop_reason', 'unknown'),
                  'gwo_evaluations': search.metadata.get('evaluations', 0),
                  'screening_cache_hits': screening.cache_hits,
                  'representative_windows': [{'start': str(w.timestamps[0]),
                                               'end': str(w.timestamps[-1])} for w in subprofiles],
                  'current_annual_cost': current_metrics.annual_total_cost,
                  'lateral_metrics_before': reference_laterals,
                  'improvement_rules': asdict(rules),
                  'full_year_candidates': [],
                  'screening_hours_per_candidate': sum(len(w.timestamps) for w in subprofiles),
                  'screening_selection_policy': 'annual-aware critical lateral events; each selected 48h anchor extended to 72h with annual-chronological candidate-specific SOC warm-start',
                  'screening_soc_proxy': ('candidate-specific annual approximate dispatch inventory; accepted BESS SOC from previously verified annual run; finalist FBS is authoritative' if soc_warm_starts is not None else 'unavailable with mock/reference lacking aligned hourly steps'),
                  'parallel_gwo_workers': stage_config.workers,
                  'parallel_annual_workers': annual_workers,
                  'annual_hours_required': len(profiles.timestamps),
                  'initial_no_bess_lateral_metrics': initial_laterals,
                  'screening_candidates': [{
                      'bus': e.candidate.bus_id,
                      'power_kw': e.candidate.power_rating_kw,
                      'energy_kwh': e.candidate.energy_capacity_kwh,
                      'screening_score': e.objective if isfinite(e.objective) else None,
                      'screening_feasible': bool(e.feasible),
                      'screening_hours': e.execution_metadata.get('hours', 0),
                      'evaluation_kind': 'representative_window_only',
                      'annual_verified': False,
                  } for e in evaluated.values()]}
        winner = None
        winner_result = None
        finalist_simulations_before = annual_evaluations
        # First three diverse finalists are checked in parallel (when workers
        # permit), before the decision to spend further annual verification time.
        initial_count = min(3, len(candidates))
        batches = (list(enumerate(candidates[:initial_count], 1)),
                   list(enumerate(candidates[initial_count:], initial_count + 1)))
        for batch_number, batch in enumerate(batches):
            if batch_number and winner is not None:
                break
            if batch_number and batch:
                stage(f'Placement {sequence}: initial annual finalists failed; extending verification')
            # A zero-stress target lateral can be rejected without a year-long
            # replay. Never label this a verified result.
            def no_problem(candidate):
                target = lateral_map(network)[candidate.bus_id]
                row = reference_laterals.get(target)
                return (row is not None and row['shedding_kwh'] <= 1e-9
                        and row['voltage_deficit_pu_hours'] <= 1e-9)
            to_run = [candidate for _,candidate in batch if not no_problem(candidate)]
            if to_run:
                stage(f'Placement {sequence}: verifying {len(to_run)} annual finalists '
                      f'with {min(annual_workers,len(to_run))} worker(s)')
            checked_by_candidate = _verify_annual_batch(
                network, profiles, evaluator, tuple(installed), to_run,
                reference_laterals, initial_laterals, rules, workers=annual_workers)
            for j, candidate in batch:
                target_lateral = lateral_map(network)[candidate.bus_id]
                if no_problem(candidate):
                    record['full_year_candidates'].append({
                        'bus':candidate.bus_id, 'lateral':target_lateral,
                        'power_kw':candidate.power_rating_kw,
                        'energy_kwh':candidate.energy_capacity_kwh,
                        'annual_cost':None, 'feasible':False,
                        'technical_acceptable':False,
                        'technical_reason':'Early rejection: no residual problem on target lateral',
                        'verification_status':'screening_rejected',
                        'annual_processed_hours':0,
                        'annual_expected_hours':len(profiles.timestamps),
                        'screening_hours':sum(len(w.timestamps) for w in subprofiles),
                    })
                    continue
                checked = checked_by_candidate[candidate]
                # Keep older integration test doubles compatible, but real
                # annual candidates always return (evaluation, full result).
                item, yearly_result = checked if isinstance(checked, tuple) else (checked, None)
                annual_evaluations += 1
                verified.append(item)
                technical = item.execution_metadata.get('technical_check', {})
                technically_acceptable = item.feasible and technical.get('acceptable', False)
                v13_cost_gate = evaluator.simulation_config.fleet_dispatch_mode == 'opf'
                economically_acceptable = (isfinite(item.objective) and
                    item.objective < current_metrics.annual_total_cost - 1e-6)
                coverage = item.execution_metadata.get('annual_coverage', {})
                for screened_row in record['screening_candidates']:
                    if (screened_row['bus'], screened_row['power_kw'], screened_row['energy_kwh']) == (
                            candidate.bus_id, candidate.power_rating_kw, candidate.energy_capacity_kwh):
                        screened_row['annual_verified'] = bool(coverage.get('complete', False) and item.feasible)
                        break
                record['full_year_candidates'].append({
                    'bus':candidate.bus_id, 'lateral':target_lateral,
                    'power_kw':candidate.power_rating_kw, 'energy_kwh':candidate.energy_capacity_kwh,
                    'annual_cost':item.objective if isfinite(item.objective) else None,
                    'feasible':item.feasible, 'technical_acceptable':technically_acceptable,
                    'economic_acceptable':economically_acceptable,
                    'technical_reason':technical.get('reason', item.message),
                    'verification_status':coverage.get('status','mocked_annual_check'),
                    'annual_processed_hours':coverage.get('processed_hours'),
                    'annual_expected_hours':coverage.get('expected_hours',len(profiles.timestamps)),
                    'screening_hours':sum(len(w.timestamps) for w in subprofiles),
                    'annual_coverage_percent':coverage.get('coverage_percent'),
                    'cumulative_target_met':technical.get('cumulative_target_met'),
                    'cumulative_shedding_improvement_percent':technical.get('cumulative_shedding_improvement_percent'),
                    'cumulative_voltage_improvement_percent':technical.get('cumulative_voltage_improvement_percent'),
                    'shedding_improvement_percent':technical.get('shedding_improvement_percent'),
                    'voltage_improvement_percent':technical.get('voltage_improvement_percent'),
                    'voltage_compliant_before_shedding':technical.get('voltage_compliant_before_shedding'),
                    'voltage_deficit_reduction_pu_hours':technical.get('voltage_deficit_reduction_pu_hours'),
                    'shedding_reduction_kwh':technical.get('shedding_reduction_kwh'),
                })
                if technically_acceptable and (economically_acceptable or not v13_cost_gate):
                    # In a cost-minimization study, prefer the least-cost
                    # technically acceptable FULL-YEAR candidate. Never
                    # install a V13 unit that raises annual ownership+operation.
                    if v13_cost_gate:
                        if winner is None or (item.objective, candidate) < (winner.objective, winner.candidate):
                            winner, winner_result = item, yearly_result
                        continue
                    item_ratio = item.execution_metadata.get('annual_technical_remaining_ratio')
                    previous_ratio = (winner.execution_metadata.get('annual_technical_remaining_ratio')
                                      if winner is not None else None)
                    if winner is None or (item_ratio is not None and previous_ratio is not None
                            and (item_ratio < previous_ratio - .01
                                 or (abs(item_ratio - previous_ratio) <= .01 and
                                     (item.objective, candidate) < (winner.objective, winner.candidate)))) or (
                            item_ratio is None and previous_ratio is None and
                            (item.objective, candidate) < (winner.objective, winner.candidate)):
                        winner = item
                        winner_result = yearly_result
        # Refinement occurs only AFTER technical acceptability and full-year
        # coverage are established. We never select a cheaper candidate using
        # only the approximate representative-window score.
        if winner is not None and winner_result is not None and len(profiles.timestamps) in (8760,8784):
            previous = winner.candidate
            winner, winner_result, refinements, extra_checks = _refine_annual_energy(
                network, profiles, evaluator, tuple(installed), winner, winner_result,
                bounds, reference_laterals, initial_laterals, rules, annual_workers)
            annual_evaluations += extra_checks
            record['energy_refinement'] = refinements
            record['energy_refinement_changed_selection'] = winner.candidate != previous
            if winner.candidate != previous:
                stage(f'Placement {sequence}: annual energy refinement chose '
                      f'{winner.candidate.energy_capacity_kwh:g} kWh rather than '
                      f'{previous.energy_capacity_kwh:g} kWh after reliability/cost verification')
        record['annual_finalists_verified'] = annual_evaluations - finalist_simulations_before
        record['annual_finalists_screened'] = len(record['full_year_candidates'])
        record['annual_finalist_budget'] = finalists_per_stage
        if winner is None:
            record['status'] = 'not-installed: no verified incremental annual improvement'
            stages.append(record)
            stage(f'Placement {sequence}: no verified incremental annual improvement among finalists; stopping')
            break
        # Final physical-duration safety gate. No selected battery may bypass
        # the same constraints used by GWO, probes or annual refinement.
        bounds.validate_candidate(winner.candidate)
        # Reuse the FULL YEAR physical result already verified for this winner.
        # A second yearly replay would repeat identical expensive FBS/control work.
        prospective = tuple(installed) + (winner.candidate,)
        if winner_result is None:  # Compatibility with evaluator mocks / older integrations.
            accepted_result, accepted_metrics = annual_fleet(network, profiles, evaluator, prospective,
                                                             capture_dispatch=True)
            annual_evaluations += 1
            record['accepted_result_reused'] = False
        else:
            accepted_result, accepted_metrics = winner_result, winner.metrics
            record['accepted_result_reused'] = True
        if accepted_metrics is None or not accepted_metrics.feasible or (
                abs(accepted_metrics.annual_total_cost - winner.objective) > 1e-5):
            record['status'] = 'not-installed: annual result consistency check failed'
            stages.append(record)
            stage('Full-year result inconsistent; stopping without accepting the candidate')
            break
        savings = current_metrics.annual_total_cost - accepted_metrics.annual_total_cost
        if evaluator.simulation_config.fleet_dispatch_mode == 'opf' and savings <= 1e-6:
            record['status'] = 'not-installed: no verified annual economic saving'
            record['annual_saving_vs_previous'] = savings
            stages.append(record)
            stage(f'Placement {sequence}: no verified annual cost reduction; stopping')
            break
        installed.append(winner.candidate)
        current_result, current_metrics = accepted_result, accepted_metrics
        history.append(current_metrics.annual_total_cost)
        recorded_check = winner.execution_metadata['technical_check']
        accepted_laterals.append(recorded_check['target'])
        record.update({'status':'installed', 'selected':asdict(winner.candidate),
                       'selected_lateral':recorded_check['target'],
                       'technical_check':recorded_check,
                       'cumulative_target_met':recorded_check.get('cumulative_target_met',False),
                       'cumulative_shedding_improvement_percent':recorded_check.get('cumulative_shedding_improvement_percent'),
                       'cumulative_voltage_improvement_percent':recorded_check.get('cumulative_voltage_improvement_percent'),
                       'lateral_metrics_after':winner.execution_metadata.get('lateral_metrics_after'),
                       'annual_saving_vs_previous':savings,
                       'updated_annual_cost':current_metrics.annual_total_cost})
        stages.append(record)
        stage(f'Placement {sequence} installed at bus {winner.candidate.bus_id}; '
              f'annual cost difference {savings:+.2f} USD/year; '
              f'local shedding {recorded_check["shedding_improvement_percent"]:.1f}%, '
              f'voltage deficit {recorded_check["voltage_improvement_percent"]:.1f}%')
    fleet = tuple(installed)
    metadata = {
        'algorithm':'Sequential GWO + lateral-aware technical acceptance',
        'search_mode':('Lateral-diverse screening + annual technical/economic acceptance' if
                       evaluator.simulation_config.fleet_dispatch_mode == 'opf' else
                       'Lateral-diverse technical-first screening + annual verification'),
        'history_axis':'accepted placement', 'seed':config.seed, 'workers':min(config.workers,8),
        'maximum_bess_units': max_units, 'installed_bess_count':len(fleet),
        'fleet':[asdict(c) for c in fleet], 'stages':stages,
        'screening_method':'Annual severity + seasonal diversity: 72-hour chronological windows warm-started by annual SOC proxy; lateral-diverse GWO; independent annual finalists',
        'annual_verification_required_hours':len(profiles.timestamps),
        'annual_verification_policy':'Exact 8760/8784 chronological timestamp coverage and convergence required; screened weeks are never annual claims',
        'incremental_acceptance_floor_percent':None,
        'voltage_acceptance':'Verified final hourly 0.95–1.05 pu network limits required; pre-control voltage deficit is diagnostic rather than veto when annual shedding relief is proven; voltage-only acceptances still guard pre-control voltage',
        'parallel_gwo_workers': min(config.workers,8),
        'parallel_annual_workers': annual_workers,
        'cumulative_target_assessment':'Cumulative shedding goal is informational; voltage judged by absolute compliance and deficit',
        'gwo_technical_weights':{'shedding':0.8,'pre_shedding_voltage_deficit':0.2,'technical':0.94,'economics':0.06},
        'cumulative_targets_met':[bool(stage.get('cumulative_target_met')) for stage in stages if stage.get('status') == 'installed'],
        'improvement_rules':asdict(rules), 'installed_laterals':accepted_laterals,
        'ranking_weights':{'voltage':0.2,'shedding':0.8},
        'best_bess_candidate':asdict(fleet[-1]) if fleet else None,
        'best_bess_annual_cost':current_metrics.annual_total_cost if fleet else None,
        'no_bess_selected':not bool(fleet), 'no_bess_feasible':True,
        'no_bess_annual_cost':baseline_cost,
        'objective_formula':'grid imports * tariff - exports * tariff + shedding * penalty + curtailment * penalty + terminal inventory replacement adjustment + total fleet CAPEX / lifetime + annual O&M',
        'bess_lifetime_years':evaluator.economic_config.lifetime_years,
        'annual_om_percent_of_capex':evaluator.economic_config.annual_om_fraction * 100,
        'best_bess_feasible':bool(fleet), 'feasible_bess_candidates':sum(item.feasible for item in verified),
        'stage_wall_seconds':{'total_seconds':perf_counter()-start},
        'annual_fleet_simulations': annual_evaluations,
        'no_bess_cache_hit': bool(getattr(current_result, 'dispatch_timing', {}).get('no_bess_cache_hit')) if not installed else bool(getattr(baseline_result, 'dispatch_timing', {}).get('no_bess_cache_hit')),
        'accepted_annual_results_reused': sum(bool(s.get('accepted_result_reused')) for s in stages),
        'convergence_stopping': 'best-feasible objective, sustained stagnation',
    }
    final_laterals = summarize_laterals(network, current_result,
                                       evaluator.simulation_config.voltage_min_pu, profiles=profiles)
    base_shedding = sum(v['shedding_kwh'] for v in initial_laterals.values())
    final_shedding = sum(v['shedding_kwh'] for v in final_laterals.values())
    base_voltage = sum(v['voltage_deficit_pu_hours'] for v in initial_laterals.values())
    final_voltage = sum(v['voltage_deficit_pu_hours'] for v in final_laterals.values())
    metadata['cumulative_system_shedding_reduction_percent'] = (
        100. * (base_shedding - final_shedding) / base_shedding if base_shedding > 1e-9 else None)
    metadata['cumulative_system_voltage_deficit_reduction_percent'] = (
        100. * (base_voltage - final_voltage) / base_voltage if base_voltage > 1e-9 else None)
    metadata['cumulative_lateral_targets'] = {
        label: {'shedding_percent': (100. * (before['shedding_kwh'] - final_laterals[label]['shedding_kwh']) /
                                      before['shedding_kwh'] if before['shedding_kwh'] > 1e-9 else None),
                'voltage_percent': (100. * (before['voltage_deficit_pu_hours'] - final_laterals[label]['voltage_deficit_pu_hours']) /
                                     before['voltage_deficit_pu_hours'] if before['voltage_deficit_pu_hours'] > 1e-9 else None)}
        for label, before in initial_laterals.items()}
    metadata['delta_annual_cost'] = current_metrics.annual_total_cost - metadata['no_bess_annual_cost']
    result = OptimizationResult(
        best_candidate=fleet[-1] if fleet else None,
        best_objective=current_metrics.annual_total_cost,
        metrics=current_metrics,
        convergence_history=history,
        iterations=total_iterations,
        success=True,
        message=(f'Sequential verification accepted {len(fleet)} technically improving BESS unit(s).'
                 if fleet else 'No annual finalist met the incremental improvement and non-deterioration requirements; No-BESS baseline retained.'),
        evaluations=verified,
        metadata=metadata,
    )
    return result, baseline_result, current_result
