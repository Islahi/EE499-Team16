"""Joint Multi-BESS Stationary GA optimizer inspired by Ahmed, Sindi et al. (2023).

Encodes a complete stationary BESS fleet (up to max_units batteries) in a single
chromosome (SESS mode, Eq. 53) and evolves the population using:
  - Roulette-wheel / tournament selection with elitism
  - Scattered crossover (per-unit gene exchange)
  - Gaussian + discrete mutation with automatic V14 duration (E/P) repair
  - Stall-generation stopping criterion

Evaluates candidate fleets on k-means probability-weighted representative 24-hour
days using the EXACT user economic objective (annualized BESS CAPEX/O&M +
load shedding + PV curtailment + grid import/export cost), then hands the top
diverse candidate fleets to full 8,760/8,784-hour chronological verification.
"""
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from math import floor, inf, isfinite
from multiprocessing import get_context
from random import Random
from time import perf_counter

from .bess import BESSConfig
from .fbs import warm_numba
from .ga_observations import GAObservations
from .metrics import evaluate_results, with_terminal_policy, annual_capital_recovery_factor
from .multi_bess import simulate_timeseries_fleet
from .optimizer import BESSCandidate, OptimizationBounds, _without_progress
from .progress import ProgressEvent
from .representative_days import ScenarioSet


def canonical_fleet(fleet: tuple[BESSCandidate, ...]) -> tuple[BESSCandidate, ...]:
    """Order-invariant canonical key so caching avoids duplicate fleet evaluations."""
    return tuple(sorted(fleet, key=lambda c: (c.bus_id, c.power_rating_kw, c.energy_capacity_kwh)))


@dataclass
class FleetEvaluation:
    fleet: tuple[BESSCandidate, ...]
    objective: float
    feasible: bool
    annual_operational_cost: float = inf
    annual_fixed_cost: float = 0.0
    annual_shedding_kwh: float = 0.0
    annual_curtailment_kwh: float = 0.0
    annual_voltage_dev_pu_h: float = 0.0
    message: str = ""
    elapsed_seconds: float = 0.0


@dataclass
class FleetGAConfig:
    population_size: int = 24
    max_generations: int = 30
    stall_generation_limit: int = 8
    crossover_rate: float = 0.80
    mutation_rate: float = 0.20
    elite_count: int = 2
    seed: int = 42
    workers: int = 1
    relative_tolerance: float = 0.001


def _repair_fleet(
    raw_units: list[BESSCandidate | None],
    bounds: OptimizationBounds,
    max_units: int,
    rng: Random,
) -> tuple[BESSCandidate, ...]:
    """Ensure every active unit obeys V14 duration limits and occupies a unique bus."""
    allowed = bounds.allowed_bus_ids
    feasible_powers = bounds.feasible_power_ratings()
    used_buses: set[int] = set()
    cleaned: list[BESSCandidate] = []
    for unit in raw_units[:max_units]:
        if unit is None:
            continue
        bus = unit.bus_id
        if bus not in allowed or bus in used_buses:
            free = [b for b in allowed if b not in used_buses]
            if not free:
                continue
            bus = rng.choice(free)
        # Snap power & energy to nearest V14-admissible catalog pair
        power = min(feasible_powers, key=lambda p: (abs(p - unit.power_rating_kw), p))
        valid_energies = bounds.energies_for_power(power)
        energy = min(valid_energies, key=lambda e: (abs(e - unit.energy_capacity_kwh), e))
        candidate = BESSCandidate(bus, power, energy)
        bounds.validate_candidate(candidate)
        used_buses.add(bus)
        cleaned.append(candidate)
    return canonical_fleet(tuple(cleaned))


def _random_fleet(bounds: OptimizationBounds, max_units: int, rng: Random) -> tuple[BESSCandidate, ...]:
    """Generate a feasible stationary fleet of 1..max_units batteries."""
    n_units = rng.randint(1, min(max_units, len(bounds.allowed_bus_ids)))
    chosen_buses = rng.sample(list(bounds.allowed_bus_ids), k=n_units)
    units = []
    for bus in chosen_buses:
        power = rng.choice(bounds.feasible_power_ratings())
        energy = rng.choice(bounds.energies_for_power(power))
        units.append(BESSCandidate(bus, power, energy))
    return canonical_fleet(tuple(units))


def _pad_chromosome(fleet: tuple[BESSCandidate, ...], max_units: int) -> list[BESSCandidate | None]:
    padded: list[BESSCandidate | None] = list(fleet[:max_units])
    while len(padded) < max_units:
        padded.append(None)
    return padded


def _scattered_crossover(
    parent_a: tuple[BESSCandidate, ...],
    parent_b: tuple[BESSCandidate, ...],
    bounds: OptimizationBounds,
    max_units: int,
    crossover_rate: float,
    rng: Random,
) -> tuple[tuple[BESSCandidate, ...], tuple[BESSCandidate, ...]]:
    """Scattered per-unit crossover (Ahmed et al. Section 4.1) with V14 repair."""
    if rng.random() >= crossover_rate:
        return parent_a, parent_b
    pa = _pad_chromosome(parent_a, max_units)
    pb = _pad_chromosome(parent_b, max_units)
    child_a, child_b = [], []
    for ga, gb in zip(pa, pb):
        if rng.random() < 0.5:
            child_a.append(ga)
            child_b.append(gb)
        else:
            child_a.append(gb)
            child_b.append(ga)
    return (
        _repair_fleet(child_a, bounds, max_units, rng),
        _repair_fleet(child_b, bounds, max_units, rng),
    )


def _gaussian_mutate(
    fleet: tuple[BESSCandidate, ...],
    bounds: OptimizationBounds,
    max_units: int,
    mutation_rate: float,
    rng: Random,
    bus_order: tuple[int, ...],
) -> tuple[BESSCandidate, ...]:
    """Gaussian index mutation on bus/P/E plus unit add/drop toggle."""
    slots = _pad_chromosome(fleet, max_units)
    powers = bounds.feasible_power_ratings()
    bus_pos = {b: i for i, b in enumerate(bus_order)}
    mutated: list[BESSCandidate | None] = []
    for slot in slots:
        if rng.random() >= mutation_rate:
            mutated.append(slot)
            continue
        if slot is None:
            # Activate a new battery unit
            power = rng.choice(powers)
            energy = rng.choice(bounds.energies_for_power(power))
            mutated.append(BESSCandidate(rng.choice(bus_order), power, energy))
        else:
            # 15% chance to deactivate a unit (if fleet has >1 unit)
            if len(fleet) > 1 and rng.random() < 0.15:
                mutated.append(None)
                continue
            # Gaussian step in catalog index space (electrically ordered buses)
            if rng.random() < 0.35:
                # A global jump discovers entirely different laterals without
                # requiring weak-bus ranking or prescreening.
                new_bus = rng.choice(bus_order)
            else:
                b_idx = bus_pos.get(slot.bus_id, 0)
                b_step = int(round(rng.gauss(0.0, max(1.0, len(bus_order) * 0.12))))
                new_bus = bus_order[max(0, min(len(bus_order) - 1, b_idx + b_step))]

            p_idx = powers.index(slot.power_rating_kw) if slot.power_rating_kw in powers else 0
            p_step = int(round(rng.gauss(0.0, max(1.0, len(powers) * 0.2))))
            new_power = powers[max(0, min(len(powers) - 1, p_idx + p_step))]

            valid_e = bounds.energies_for_power(new_power)
            e_idx = min(range(len(valid_e)), key=lambda i: abs(valid_e[i] - slot.energy_capacity_kwh))
            e_step = int(round(rng.gauss(0.0, max(1.0, len(valid_e) * 0.25))))
            new_energy = valid_e[max(0, min(len(valid_e) - 1, e_idx + e_step))]
            mutated.append(BESSCandidate(new_bus, new_power, new_energy))
    return _repair_fleet(mutated, bounds, max_units, rng)


def evaluate_fleet_on_scenarios(
    network,
    scenarios: ScenarioSet,
    evaluator,
    fleet: tuple[BESSCandidate, ...],
) -> FleetEvaluation:
    """Evaluate a stationary BESS fleet across all k-means representative days.

    Minimizes the exact annualized user economic objective:
      annualized BESS CAPEX/O&M + weighted daily (Grid Import/Export + Shed + Curtailment)
      + terminal SOC replacement adjustment for any daily energy imbalance.
    """
    started = perf_counter()
    fleet = canonical_fleet(fleet)
    economics = evaluator.economic_config
    settings = with_terminal_policy(evaluator.simulation_config, economics)
    configs = tuple(evaluator.battery_parameters.build_config(c) for c in fleet)

    # Match evaluate_results() precisely: inverter kVA basis and discounted CRF
    # must agree between scenario screening and annual verification.
    inverter_ratio = economics.inverter_kva_per_kw if economics.power_cost_basis == 'kva' else 1.0
    purchase = sum(
        economics.cost_per_kw * c.power_rating_kw * inverter_ratio
        + economics.cost_per_kwh * c.energy_capacity_kwh
        for c in configs
    )
    annual_fixed = purchase * (annual_capital_recovery_factor(economics) + economics.annual_om_fraction)

    annual_op = 0.0
    annual_shed = 0.0
    annual_curt = 0.0
    annual_vdev = 0.0

    for rep_day in scenarios.days:
        sim = simulate_timeseries_fleet(
            network,
            rep_day.profile,
            settings,
            configs,
            capture_dispatch=False,
            representative_day={"day_index": rep_day.day_index, "cluster_id": rep_day.cluster_id,
                                "start": str(rep_day.start_timestamp)},
        )
        if not sim.completed or not sim.converged or not sim.feasible:
            return FleetEvaluation(
                fleet=fleet,
                objective=inf,
                feasible=False,
                message=f"Scenario day {rep_day.day_index} infeasible: {sim.message}",
                elapsed_seconds=perf_counter() - started,
            )
        metrics = evaluate_results(sim, economics, configs if configs else None)
        if metrics.load_shedding_energy_kwh is None or metrics.curtailment_energy_kwh is None:
            return FleetEvaluation(
                fleet=fleet,
                objective=inf,
                feasible=False,
                message="Missing corrective-control records on scenario day",
                elapsed_seconds=perf_counter() - started,
            )

        day_op = (
            metrics.grid_import_energy_kwh * economics.grid_import_tariff_per_kwh
            - metrics.grid_export_energy_kwh * economics.grid_export_tariff_per_kwh
            + metrics.load_shedding_energy_kwh * economics.shedding_penalty_per_kwh
            + metrics.curtailment_energy_kwh * economics.curtailment_penalty_per_kwh
        )
        # Enforce fair daily inventory accounting (Eq. 47 spirit): charge for net
        # battery energy depleted during the 24h day so large batteries aren't gifted free energy.
        for cfg in configs:
            final_state = (sim.final_fleet_states or {}).get(cfg.bus_id)
            if final_state is not None:
                delta = cfg.energy_capacity_kwh * cfg.soc_initial - final_state.energy_kwh
                if delta > 0.0:
                    day_op += (delta / cfg.eta_charge) * economics.grid_import_tariff_per_kwh
                elif delta < 0.0:
                    day_op += delta * cfg.eta_discharge * economics.grid_export_tariff_per_kwh

        day_vdev = sum(
            abs(float(v) - 1.0)
            for step in sim.steps
            for v in step.power_flow.voltage_mag_pu.values()
        )
        w = rep_day.weight_days
        annual_op += w * day_op
        annual_shed += w * metrics.load_shedding_energy_kwh
        annual_curt += w * metrics.curtailment_energy_kwh
        annual_vdev += w * day_vdev

    total_annual = annual_op + annual_fixed
    return FleetEvaluation(
        fleet=fleet,
        objective=total_annual,
        feasible=True,
        annual_operational_cost=annual_op,
        annual_fixed_cost=annual_fixed,
        annual_shedding_kwh=annual_shed,
        annual_curtailment_kwh=annual_curt,
        annual_voltage_dev_pu_h=annual_vdev,
        message="Scenario-weighted annualized cost verified",
        elapsed_seconds=perf_counter() - started,
    )


_GA_WORKER_CONTEXT = None


def _init_ga_worker(context_payload):
    global _GA_WORKER_CONTEXT
    _GA_WORKER_CONTEXT = context_payload
    try:
        from threadpoolctl import threadpool_limits
        threadpool_limits(limits=1)
    except ImportError:
        pass
    warm_numba()


def _eval_ga_worker(fleet):
    network, scenarios, evaluator = _GA_WORKER_CONTEXT
    return evaluate_fleet_on_scenarios(network, scenarios, evaluator, fleet)


def _roulette_select(ranked: list[FleetEvaluation], rng: Random) -> tuple[BESSCandidate, ...]:
    """Roulette-wheel selection on inverse-cost rank fitness (Ahmed et al. Section 4.1)."""
    feasible = [item for item in ranked if item.feasible and isfinite(item.objective)]
    if not feasible:
        return rng.choice(ranked).fleet
    if len(feasible) == 1:
        return feasible[0].fleet
    # Rank-scaled roulette weights avoid numeric overflow with negative export costs
    n = len(feasible)
    weights = [float(n - i) for i in range(n)]
    total = sum(weights)
    pick = rng.random() * total
    acc = 0.0
    for item, weight in zip(feasible, weights):
        acc += weight
        if acc >= pick:
            return item.fleet
    return feasible[-1].fleet


def run_joint_fleet_ga(
    network,
    scenarios: ScenarioSet,
    bounds: OptimizationBounds,
    evaluator,
    *,
    max_units: int = 3,
    ga_config: FleetGAConfig | None = None,
    seed_fleets: tuple[tuple[BESSCandidate, ...], ...] = (),
    bus_order: tuple[int, ...] | None = None,
    progress=None,
    diagnostics_level: str | None = None,
):
    """Run Joint Multi-BESS GA on representative scenarios."""
    cfg = ga_config or FleetGAConfig()
    rng = Random(cfg.seed)
    ordered_buses = tuple(bus_order) if bus_order else bounds.allowed_bus_ids
    started = perf_counter()

    # Build feasible initial population (includes No-BESS base case + diverse seeds)
    population: list[tuple[BESSCandidate, ...]] = [()]
    randomized_seeds = list(seed_fleets)
    rng.shuffle(randomized_seeds)
    if max_units > 3:
        randomized_seeds.sort(key=lambda fleet: len(fleet) != max_units)
    for sf in randomized_seeds:
        if len(population) >= cfg.population_size:
            break
        repaired = _repair_fleet(list(sf), bounds, max_units, rng)
        if repaired not in population:
            population.append(repaired)
    attempts = 0
    while len(population) < cfg.population_size and attempts < cfg.population_size * 8:
        attempts += 1
        cand = _random_fleet(bounds, max_units, rng)
        if cand not in population:
            population.append(cand)
    while len(population) < cfg.population_size:
        population.append(_random_fleet(bounds, max_units, rng))

    cache: dict[tuple[BESSCandidate, ...], FleetEvaluation] = {}
    history: list[float] = []
    best_significant = inf
    stall_count = 0
    stop_reason = "max_generations"
    observations = GAObservations.start(diagnostics_level)

    workers = min(max(1, cfg.workers), cfg.population_size)
    worker_eval = _without_progress(evaluator) if workers > 1 else evaluator
    pool = None
    try:
        if workers > 1:
            ctx = get_context()
            pool = ProcessPoolExecutor(
                max_workers=workers,
                mp_context=ctx,
                initializer=_init_ga_worker,
                initargs=((network, scenarios, worker_eval),),
            )
        for gen in range(cfg.max_generations):
            generation_started = perf_counter() if observations is not None else None
            if progress is not None:
                progress(
                    ProgressEvent(
                        "GA",
                        gen,
                        cfg.max_generations,
                        f"Generation {gen + 1}/{cfg.max_generations} (pop={len(population)})",
                        True,
                    )
                )
            pending = [f for f in dict.fromkeys(population) if f not in cache]
            if pending:
                if pool is None:
                    for fleet in pending:
                        cache[fleet] = evaluate_fleet_on_scenarios(network, scenarios, evaluator, fleet)
                else:
                    for fleet, ev in zip(pending, pool.map(_eval_ga_worker, pending)):
                        cache[fleet] = ev

            gen_evals = [cache[f] for f in population]
            ranked = sorted(
                gen_evals,
                key=lambda e: (not e.feasible, e.objective, e.annual_fixed_cost, e.fleet),
            )
            feasible_all = [e for e in cache.values() if e.feasible and isfinite(e.objective)]
            best_now = min((e.objective for e in feasible_all), default=inf)
            history.append(best_now)

            if isfinite(best_now):
                tol = cfg.relative_tolerance * max(1.0, abs(best_significant))
                if not isfinite(best_significant) or best_now < best_significant - tol:
                    best_significant = best_now
                    stall_count = 0
                else:
                    stall_count += 1

            if observations is not None:
                observations.generation(gen, population, pending, ranked, len(cache), best_now,
                                        best_significant, stall_count, perf_counter() - generation_started)

            if progress is not None:
                progress(
                    ProgressEvent(
                        "GA",
                        gen + 1,
                        cfg.max_generations,
                        f"Gen {gen + 1} best scenario cost={best_now:,.2f} USD/yr (unique={len(cache)})",
                        True,
                    )
                )

            if isfinite(best_now) and stall_count >= cfg.stall_generation_limit:
                stop_reason = "stall_generation_limit"
                break
            if gen == cfg.max_generations - 1:
                break

            # Elitism + roulette-wheel selection + scattered crossover + Gaussian mutation
            elites = [e.fleet for e in ranked[: max(1, min(cfg.elite_count, len(ranked)))]]
            next_pop: list[tuple[BESSCandidate, ...]] = list(dict.fromkeys(elites))
            while len(next_pop) < cfg.population_size:
                pa = _roulette_select(ranked, rng)
                pb = _roulette_select(ranked, rng)
                ca, cb = _scattered_crossover(pa, pb, bounds, max_units, cfg.crossover_rate, rng)
                for child in (ca, cb):
                    mutated = _gaussian_mutate(child, bounds, max_units, cfg.mutation_rate, rng, ordered_buses)
                    next_pop.append(mutated)
                    if observations is not None and observations.level == "detail":
                        observations.offspring(gen, len(next_pop), (pa, pb), child, mutated)
                    if len(next_pop) >= cfg.population_size:
                        break
            population = next_pop
    finally:
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)

    all_ranked = sorted(
        cache.values(),
        key=lambda e: (not e.feasible, e.objective, e.annual_fixed_cost, e.fleet),
    )
    return {
        "ranked": all_ranked,
        "history": history,
        "generations": len(history),
        "unique_evaluated": len(cache),
        "visited_bus_ids": sorted({unit.bus_id for fleet in cache for unit in fleet}),
        "stop_reason": stop_reason,
        "elapsed_seconds": perf_counter() - started,
        "config": asdict(cfg),
        "academic_diagnostics": observations.report(all_ranked, workers) if observations is not None else None,
    }
