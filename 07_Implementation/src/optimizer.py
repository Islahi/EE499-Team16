"""Discrete-catalog GWO search using public simulation and metrics interfaces.

GWO equations: https://github.com/alimirjalili/GWO/blob/master/GWO.m
Catalog rounding, explicit evaluation and feasible-leader retention are the
project's adaptations. The search is a heuristic, not a global-optimum proof.
"""
from collections.abc import Callable
from bisect import bisect_left, bisect_right
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from copy import copy
from dataclasses import dataclass, field, replace
from itertools import product
from math import floor, isfinite
from multiprocessing import get_context
from queue import Empty, Full
from random import Random
from time import perf_counter, process_time

from .bess import BESSConfig
from .fbs import warm_numba
from .data_loader import ProfileData
from .metrics import EconomicConfig, PerformanceMetrics, evaluate_results, validate_annual_inputs, with_terminal_policy
from .network_model import NetworkModel
from .simulation import ConstraintAwareDispatch, DispatchPolicy, SimulationConfig, simulate_timeseries
from .progress import ProgressEvent


def _check_number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < 0 or (positive and value == 0):
        raise ValueError(f"{name} is outside its allowed range")


@dataclass(frozen=True, order=True)
class BESSCandidate:
    bus_id: int
    power_rating_kw: float
    energy_capacity_kwh: float

    def __post_init__(self):
        if not isinstance(self.bus_id, int) or isinstance(self.bus_id, bool):
            raise ValueError("bus_id must be an integer")
        _check_number(self.power_rating_kw, "power_rating_kw", positive=True)
        _check_number(self.energy_capacity_kwh, "energy_capacity_kwh", positive=True)


@dataclass(frozen=True)
class OptimizationBounds:
    allowed_bus_ids: tuple[int, ...]
    power_ratings_kw: tuple[float, ...]
    energy_capacities_kwh: tuple[float, ...]
    # Nameplate BESS duration is E_rated/P_rated; NOT usable-SOC-hours.
    min_duration_hours: float = 2.0
    max_duration_hours: float = 12.0

    def __post_init__(self):
        for name in ("allowed_bus_ids", "power_ratings_kw", "energy_capacities_kwh"):
            values = tuple(getattr(self, name))
            if not values:
                raise ValueError(f"{name} must not be empty")
            if name == "allowed_bus_ids":
                if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
                    raise ValueError("Allowed bus IDs must be integers")
            else:
                for value in values:
                    _check_number(value, name, positive=True)
            if len(set(values)) != len(values):
                raise ValueError(f"{name} contains duplicates")
            object.__setattr__(self, name, tuple(sorted(values)))
        _check_number(self.min_duration_hours, "min_duration_hours", positive=True)
        _check_number(self.max_duration_hours, "max_duration_hours", positive=True)
        if self.max_duration_hours < self.min_duration_hours:
            raise ValueError("Maximum BESS duration must be >= minimum duration")
        if not self.feasible_power_ratings():
            raise ValueError(
                f"No battery power/energy catalog pair satisfies "
                f"{self.min_duration_hours:g}–{self.max_duration_hours:g} h. "
                "Adjust sizing limits, steps or duration bounds."
            )

    def energy_index_range(self, power_kw):
        """Sorted catalog slice for E/P in [min_duration, max_duration].

        Binary search avoids allocating P×E pair catalogs (which can be huge).
        Small FP tolerance only addresses multiplication round-off at endpoints.
        """
        low = power_kw * self.min_duration_hours
        high = power_kw * self.max_duration_hours
        tol = 1e-10 * max(1.0, abs(high))
        energies = self.energy_capacities_kwh
        return (bisect_left(energies, low - tol), bisect_right(energies, high + tol))

    def energies_for_power(self, power_kw):
        left, right = self.energy_index_range(power_kw)
        return self.energy_capacities_kwh[left:right]

    def feasible_power_ratings(self):
        return tuple(power for power in self.power_ratings_kw
                     if self.energy_index_range(power)[1] > self.energy_index_range(power)[0])

    def feasible_design_count(self):
        return sum(right - left for power in self.power_ratings_kw
                   for left, right in (self.energy_index_range(power),))

    def validate_candidate(self, candidate):
        if candidate.bus_id not in self.allowed_bus_ids:
            raise ValueError(f"BESS bus {candidate.bus_id} is not an eligible location")
        if candidate.power_rating_kw not in self.power_ratings_kw or candidate.energy_capacity_kwh not in self.energy_capacities_kwh:
            raise ValueError(f"BESS candidate is outside the configured P/E catalog: {candidate}")
        duration = candidate.energy_capacity_kwh / candidate.power_rating_kw
        if not self.min_duration_hours - 1e-10 <= duration <= self.max_duration_hours + 1e-10:
            raise ValueError(f"BESS duration {duration:.4g} h is outside "
                             f"{self.min_duration_hours:g}–{self.max_duration_hours:g} h: {candidate}")

    def random_candidate(self, rng):
        power = rng.choice(self.feasible_power_ratings())
        return BESSCandidate(rng.choice(self.allowed_bus_ids), power,
                             rng.choice(self.energies_for_power(power)))

    def validate_network(self, network):
        network.validate()
        unknown = set(self.allowed_bus_ids) - {bus.bus_id for bus in network.buses}
        if unknown:
            raise ValueError(f"Search bounds contain unknown buses: {sorted(unknown)}")


@dataclass(frozen=True)
class BESSParameters:
    eta_charge: float
    eta_discharge: float
    soc_min: float = 0.2
    soc_max: float = 1.0
    soc_initial: float = 0.5

    def __post_init__(self):
        for name in ("eta_charge", "eta_discharge"):
            _check_number(getattr(self, name), name, positive=True)
            if getattr(self, name) > 1:
                raise ValueError(f"{name} cannot exceed one")
        for name in ("soc_min", "soc_max", "soc_initial"):
            _check_number(getattr(self, name), name)
        if not 0 <= self.soc_min < self.soc_max <= 1:
            raise ValueError("SOC bounds must satisfy 0 <= min < max <= 1")
        if not self.soc_min <= self.soc_initial <= self.soc_max:
            raise ValueError("Initial SOC must be within the SOC bounds")

    def build_config(self, candidate):
        return BESSConfig(
            bus_id=candidate.bus_id,
            power_rating_kw=candidate.power_rating_kw,
            energy_capacity_kwh=candidate.energy_capacity_kwh,
            soc_min=self.soc_min, soc_max=self.soc_max, soc_initial=self.soc_initial,
            eta_charge=self.eta_charge, eta_discharge=self.eta_discharge,
        )


def annual_economic_objective(metrics: PerformanceMetrics) -> float:
    """All parts are annual money; infeasible candidates have infinite score."""
    if not metrics.feasible:
        return float("inf")
    if metrics.annual_total_cost is None or not isfinite(metrics.annual_total_cost):
        raise ValueError("Annual economic costs unavailable; check tariff and control records")
    return metrics.annual_total_cost




@dataclass
class CandidateEvaluation:
    candidate: BESSCandidate
    objective: float
    feasible: bool
    metrics: PerformanceMetrics | None = None
    message: str = ""
    execution_metadata: dict = field(default_factory=dict)


@dataclass
class SimulationEvaluator:
    economic_config: EconomicConfig
    battery_parameters: BESSParameters
    dispatch_policy: DispatchPolicy | ConstraintAwareDispatch
    simulation_config: SimulationConfig = field(default_factory=SimulationConfig)
    progress: Callable | None = None
    hourly_progress_only: bool = False

    def __post_init__(self):
        self.simulation_config.__post_init__()
        for name in ("cost_per_kwh", "cost_per_kw"):
            value = getattr(self.economic_config, name)
            if value is None:
                raise ValueError(f"Supply {name} before optimization; no default price is assumed")
            _check_number(value, name)
        if not (callable(self.dispatch_policy) or isinstance(self.dispatch_policy, ConstraintAwareDispatch)):
            raise ValueError("Supply an active dispatch policy for optimization")

    def __call__(self, network, profiles, candidate):
        if not isinstance(profiles, ProfileData):
            raise TypeError("SimulationEvaluator expects an hourly ProfileData object")
        self.simulation_config.__post_init__()
        validate_annual_inputs(profiles.timestamps, self.economic_config, profiles.dt_hours)
        bess_config = self.battery_parameters.build_config(candidate)
        def report(event):
            if event.phase == "Simulation":
                event = replace(event, detail=(
                    f"B{candidate.bus_id} {candidate.power_rating_kw:g} kW / "
                    f"{candidate.energy_capacity_kwh:g} kWh | {event.detail}"))
            self.progress(event)

        result = simulate_timeseries(
            network=network, profiles=profiles,
            simulation_config=with_terminal_policy(self.simulation_config, self.economic_config),
            bess_config=bess_config, dispatch_policy=self.dispatch_policy,
            progress=report if self.progress is not None else None,
            hourly_progress_only=self.hourly_progress_only,
            capture_dispatch=False,
        )
        if not result.completed or not result.converged:
            return CandidateEvaluation(candidate, float("inf"), False, message=result.message)
        metrics = evaluate_results(result, self.economic_config, bess_config)
        failed_steps = [step for step in result.steps if not step.feasible]
        reasons = sorted({message for step in failed_steps for message in step.messages
                          if message.startswith(("Voltage limits", "Line ampacity",
                                                 "Network voltage", "BESS cannot", "Corrective control unresolved"))})
        return CandidateEvaluation(
            candidate=candidate, objective=annual_economic_objective(metrics),
            feasible=metrics.feasible, metrics=metrics,
            message="; ".join([result.message, *reasons]),
            execution_metadata=result.dispatch_timing,
        )


@dataclass
class OptimizerConfig:
    population_size: int = 12
    max_iterations: int = 20
    seed: int = 42
    cache_evaluations: bool = True
    initial_candidates: tuple[BESSCandidate, ...] = ()
    workers: int = 1
    # Convergence means no material improvement in the BEST FEASIBLE objective.
    convergence_min_iterations: int = 8
    convergence_patience: int = 6
    convergence_relative_tolerance: float = 0.001

    def __post_init__(self):
        for name, minimum in (("population_size", 3), ("max_iterations", 1)):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise ValueError("seed must be an integer")
        if not isinstance(self.cache_evaluations, bool):
            raise ValueError("cache_evaluations must be True or False")
        if not isinstance(self.workers, int) or isinstance(self.workers, bool) or self.workers < 1:
            raise ValueError("workers must be a positive integer")
        for name in ("convergence_min_iterations", "convergence_patience"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        _check_number(self.convergence_relative_tolerance, "convergence_relative_tolerance")
        if self.convergence_relative_tolerance >= 1:
            raise ValueError("convergence_relative_tolerance must be less than 1")
        self.initial_candidates = tuple(self.initial_candidates)
        if len(self.initial_candidates) > self.population_size:
            raise ValueError("Too many initial candidates for the population")


@dataclass
class OptimizationResult:
    best_candidate: BESSCandidate | None
    best_objective: float
    metrics: PerformanceMetrics | None
    convergence_history: list[float]
    iterations: int
    success: bool
    message: str
    evaluations: list[CandidateEvaluation]
    metadata: dict[str, object]


Evaluator = Callable[[NetworkModel, object, BESSCandidate], CandidateEvaluation]


def _catalogs(bounds):
    return (bounds.allowed_bus_ids, bounds.power_ratings_kw, bounds.energy_capacities_kwh)


def _candidate_from_position(position, bounds):
    # Repair every wolf BEFORE the expensive FBS/OPF simulation. Only project
    # onto physically admissible catalog pairs; do not penalize infeasible
    # wolves after spending solver time on them.
    bus_ids, powers, energies = _catalogs(bounds)
    bus_idx = max(0, min(len(bus_ids)-1, floor(position[0] + 0.5) - 1))
    power_idx = max(0, min(len(powers)-1, floor(position[1] + 0.5) - 1))
    desired_energy_idx = max(0, min(len(energies)-1, floor(position[2] + 0.5) - 1))
    feasible = bounds.feasible_power_ratings()
    power = min(feasible, key=lambda p: (abs(bisect_left(powers, p) - power_idx), p))
    left, right = bounds.energy_index_range(power)
    energy_idx = max(left, min(right - 1, desired_energy_idx))
    return BESSCandidate(bus_ids[bus_idx], power, energies[energy_idx])


def _position_from_candidate(candidate, bounds):
    bounds.validate_candidate(candidate)
    values = (candidate.bus_id, candidate.power_rating_kw, candidate.energy_capacity_kwh)
    position = []
    for value, catalog in zip(values, _catalogs(bounds)):
        if value not in catalog:
            raise ValueError(f"Initial/evaluated candidate is outside the configured catalog: {candidate}")
        position.append(float(catalog.index(value) + 1))
    return position


def _evaluate(network, profiles, bounds, evaluator, candidate):
    _position_from_candidate(candidate, bounds)  # Strong guard before evaluation.
    started, cpu_started = perf_counter(), process_time()
    evaluation = evaluator(network, profiles, candidate)
    if not isinstance(evaluation, CandidateEvaluation) or evaluation.candidate != candidate:
        raise ValueError("Evaluator must return CandidateEvaluation for the requested candidate")
    if evaluation.feasible:
        if not isinstance(evaluation.objective,(int,float)) or not isfinite(evaluation.objective):
            raise ValueError("Candidate annual objective must be finite (net export revenue may make it negative)")
        if evaluation.metrics is not None and not evaluation.metrics.feasible:
            raise ValueError("Evaluator marked infeasible metrics as a feasible candidate")
    else:
        evaluation = replace(evaluation, objective=float("inf"))
    evaluation.execution_metadata.update(candidate_elapsed_seconds=perf_counter() - started,
                                         candidate_cpu_seconds=process_time() - cpu_started)
    return evaluation


def _without_progress(evaluator):
    """Make a shallow worker-safe evaluator without Qt/progress callbacks."""
    worker_evaluator = copy(evaluator)
    if hasattr(worker_evaluator, "progress"):
        worker_evaluator.progress = None
    for name in ("evaluator", "profile_evaluator", "original_evaluator"):
        if hasattr(worker_evaluator, name):
            setattr(worker_evaluator, name, _without_progress(getattr(worker_evaluator, name)))
    return worker_evaluator


_WORKER_READINESS = None
_WORKER_PROGRESS = None
_WORKER_STUDY = None


def _initialize_numba_worker(progress_queue=None, study=None):
    global _WORKER_READINESS, _WORKER_PROGRESS, _WORKER_STUDY
    start = perf_counter()
    _WORKER_PROGRESS = progress_queue
    _WORKER_STUDY = study
    if progress_queue is not None:
        # A worker may exit while the parent is no longer reading updates.
        progress_queue.cancel_join_thread()
    # A process per wolf already uses multiple cores; avoid each LP/BLAS
    # creating its own nested CPU team and oversubscribing the machine.
    try:
        from threadpoolctl import threadpool_limits
        threadpool_limits(limits=1)
    except ImportError:
        pass
    _WORKER_READINESS = {**warm_numba(), "initializer_seconds": perf_counter() - start}


def _evaluate_process(candidate):
    network, profiles, bounds, evaluator = _WORKER_STUDY
    if _WORKER_PROGRESS is not None and isinstance(evaluator, SimulationEvaluator):
        last_sent = float("-inf")

        def report(event):
            nonlocal last_sent
            if event.phase != "Simulation":
                return
            now = perf_counter()
            if now - last_sent >= 1.0 or event.completed == event.total:
                try:
                    _WORKER_PROGRESS.put_nowait(event)
                except Full:
                    pass  # Display updates must never block a solver worker.
                last_sent = now

        evaluator = replace(evaluator, progress=report, hourly_progress_only=True)
    started = perf_counter()
    result = _evaluate(network, profiles, bounds, evaluator, candidate)
    result.execution_metadata.update(backend="numba", worker_pid=__import__("os").getpid(),
                                     worker_readiness=_WORKER_READINESS,
                                     worker_elapsed_seconds=perf_counter() - started)
    return result


def _drain_worker_progress(progress_queue, progress):
    if progress_queue is None:
        return
    first_hour = latest = None
    while True:
        try:
            latest = progress_queue.get_nowait()
        except Empty:
            break
        if latest.completed == 0 and first_hour is None:
            first_hour = latest
    if first_hour is not None:
        progress(first_hour)
    if latest is not None and latest is not first_hour:
        progress(latest)


def _candidate_cost_key(item):
    """Annual total cost (including straight-line BESS ownership) first; CAPEX breaks ties."""
    capex = item.metrics.bess_cost if item.metrics is not None else float("inf")
    return (item.objective, capex if capex is not None else float("inf"), item.candidate)


def _make_result(evaluations, history, iterations, metadata):
    metadata = dict(metadata)
    metadata["worker_readiness"] = {str(e.execution_metadata["worker_pid"]):e.execution_metadata
        for e in evaluations if e.execution_metadata.get("worker_pid") is not None}
    feasible = [evaluation for evaluation in evaluations if evaluation.feasible]
    best = min(feasible, key=_candidate_cost_key) if feasible else None
    return OptimizationResult(
        best_candidate=best.candidate if best is not None else None,
        best_objective=best.objective if best is not None else float("inf"),
        metrics=best.metrics if best is not None else None,
        convergence_history=history, iterations=iterations, success=best is not None,
        message="Best feasible candidate found." if best is not None else "No feasible candidate found in the evaluated search.",
        evaluations=evaluations, metadata=metadata,
    )


def _move_wolves(positions, leaders, bounds, a, rng):
    new_positions = []
    for position in positions:
        next_position = []
        for dimension, catalog in enumerate(_catalogs(bounds)):
            estimates = []
            for leader in leaders:
                coefficient_a = 2.0 * a * rng.random() - a
                coefficient_c = 2.0 * rng.random()
                distance = abs(coefficient_c * leader[dimension] - position[dimension])
                estimates.append(leader[dimension] - coefficient_a * distance)
            coordinate = sum(estimates) / 3.0
            next_position.append(max(1.0, min(len(catalog), coordinate)))
        new_positions.append(next_position)
    return new_positions


def optimize(network: NetworkModel, profiles, bounds: OptimizationBounds,
             evaluator: Evaluator, optimizer_config: OptimizerConfig, *, progress=None) -> OptimizationResult:
    """Search B/P/E catalogs with seeded GWO and per-call evaluation caching."""
    started = perf_counter()
    bounds.validate_network(network)
    if not callable(evaluator):
        raise ValueError("evaluator must be callable")
    rng = Random(optimizer_config.seed)
    positions = []
    for _ in range(optimizer_config.population_size):
        positions.append(_position_from_candidate(bounds.random_candidate(rng), bounds))
    # Deliberate extreme seeds must also be physically admissible.
    for i, power in enumerate((bounds.feasible_power_ratings()[0], bounds.feasible_power_ratings()[-1])):
        energy = bounds.energies_for_power(power)[0 if i == 0 else -1]
        bus = bounds.allowed_bus_ids[0 if i == 0 else -1]
        positions[i] = _position_from_candidate(BESSCandidate(bus, power, energy), bounds)
    for index, candidate in enumerate(optimizer_config.initial_candidates):
        positions[index] = _position_from_candidate(candidate, bounds)

    cache = {}
    evaluations = []
    best_by_candidate = {}
    history = []
    workers = min(optimizer_config.workers, optimizer_config.population_size)
    context = get_context()
    progress_queue = context.Queue(maxsize=128) if workers > 1 and progress is not None and isinstance(evaluator, SimulationEvaluator) else None
    worker_evaluator = _without_progress(evaluator) if workers > 1 else evaluator
    executor = None
    worker_wait_seconds = 0.
    best_significant = float("inf")
    stagnant_iterations = 0
    stop_reason = "maximum_iterations"
    try:
        if workers > 1:
            executor = ProcessPoolExecutor(max_workers=workers, mp_context=context,
                                           initializer=_initialize_numba_worker,
                                           initargs=(progress_queue, (network, profiles, bounds, worker_evaluator)))
        for iteration in range(optimizer_config.max_iterations):
            if progress is not None:
                progress(ProgressEvent(
                    "GWO", iteration, optimizer_config.max_iterations,
                    f"starting iteration {iteration + 1}", True,
                ))
            candidates = [_candidate_from_position(position, bounds) for position in positions]
            iteration_results = [None] * len(candidates)
            pending = []
            pending_by_candidate = {}
            for candidate_index, candidate in enumerate(candidates):
                if optimizer_config.cache_evaluations and candidate in cache:
                    iteration_results[candidate_index] = cache[candidate]
                elif optimizer_config.cache_evaluations and candidate in pending_by_candidate:
                    pending_by_candidate[candidate].append(candidate_index)
                else:
                    pending.append((candidate_index, candidate))
                    if optimizer_config.cache_evaluations:
                        pending_by_candidate[candidate] = [candidate_index]

            if executor is None:
                for completed, (candidate_index, candidate) in enumerate(pending, 1):
                    evaluation = _evaluate(
                        network, profiles, bounds, evaluator, candidate,
                    )
                    result_indexes = (pending_by_candidate[candidate]
                                      if optimizer_config.cache_evaluations
                                      else (candidate_index,))
                    for result_index in result_indexes:
                        iteration_results[result_index] = evaluation
                    evaluations.append(evaluation)
                    cache[candidate] = evaluation
                    if progress is not None:
                        progress(ProgressEvent(
                            "Candidate", completed, len(pending),
                            f"completed bus {candidate.bus_id}; objective={evaluation.objective:g}",
                            True,
                        ))
            elif pending:
                futures = {
                    executor.submit(_evaluate_process, candidate): (candidate_index, candidate)
                    for candidate_index, candidate in pending
                }
                completed_results = {}
                try:
                    running = set(futures)
                    while running:
                        waiting_since = perf_counter()
                        ready, running = wait(running, timeout=0.25 if progress_queue is not None else None,
                                              return_when=FIRST_COMPLETED)
                        worker_wait_seconds += perf_counter() - waiting_since
                        _drain_worker_progress(progress_queue, progress)
                        for future in ready:
                            candidate_index, candidate = futures[future]
                            completed_results[candidate_index] = future.result()
                            if progress is not None:
                                progress(ProgressEvent(
                                    "Candidate", len(completed_results), len(pending),
                                    f"parallel result bus {candidate.bus_id}; "
                                    f"{candidate.power_rating_kw:g} kW / "
                                    f"{candidate.energy_capacity_kwh:g} kWh", True,
                                ))
                except Exception as error:
                    raise RuntimeError(
                        "Parallel optimization failed. To retry without worker processes, set "
                        f"CPU workers to 1. Cause: {error}"
                    ) from error
                for candidate_index, candidate in pending:
                    evaluation = completed_results[candidate_index]
                    result_indexes = (pending_by_candidate[candidate]
                                      if optimizer_config.cache_evaluations
                                      else (candidate_index,))
                    for result_index in result_indexes:
                        iteration_results[result_index] = evaluation
                    evaluations.append(evaluation)
                    cache[candidate] = evaluation

            for candidate, evaluation in zip(candidates, iteration_results):
                previous = best_by_candidate.get(candidate)
                if previous is None or evaluation.objective < previous.objective:
                    best_by_candidate[candidate] = evaluation
            ranked = sorted(
                (item for item in best_by_candidate.values() if item.feasible),
                key=_candidate_cost_key,
            )
            history.append(ranked[0].objective if ranked else float("inf"))
            # Stop only after a feasible incumbent exists and its best objective
            # has not improved meaningfully for a sustained number of generations.
            # No early stop is inferred from an infeasible population.
            if ranked:
                incumbent = ranked[0].objective
                threshold = optimizer_config.convergence_relative_tolerance * max(1.0, abs(best_significant))
                if not isfinite(best_significant) or incumbent < best_significant - threshold:
                    best_significant = incumbent
                    stagnant_iterations = 0
                else:
                    stagnant_iterations += 1
            if progress is not None:
                progress(ProgressEvent(
                    "GWO", iteration + 1, optimizer_config.max_iterations,
                    f"iteration completed; best objective={history[-1]:g}; "
                    f"evaluations={len(evaluations)}", True,
                ))
            if (ranked and iteration + 1 >= optimizer_config.convergence_min_iterations
                    and stagnant_iterations >= optimizer_config.convergence_patience):
                stop_reason = "converged_no_meaningful_improvement"
                if progress is not None:
                    progress(ProgressEvent("GWO", iteration + 1, optimizer_config.max_iterations,
                        f"Converged: {stagnant_iterations} generations without >"
                        f"{optimizer_config.convergence_relative_tolerance * 100:g}% improvement", True))
                break
            if iteration == optimizer_config.max_iterations - 1:
                break
            if not ranked:
                positions = [
                    _position_from_candidate(bounds.random_candidate(rng), bounds)
                    for _ in positions
                ]
                continue
            leader_candidates = [item.candidate for item in ranked[:3]]
            while len(leader_candidates) < 3:
                leader_candidates.append(leader_candidates[0])
            leaders = [_position_from_candidate(candidate, bounds)
                       for candidate in leader_candidates]
            # Reduce exploration over the scheduled position updates.
            a = 2.0 * (1.0 - iteration / max(1, optimizer_config.max_iterations - 2))
            positions = _move_wolves(positions, leaders, bounds, a, rng)
    finally:
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
        if progress_queue is not None:
            progress_queue.close()

    return _make_result(evaluations, history, len(history), {
        "algorithm": "GWO", "history_axis": "generation", "seed": optimizer_config.seed,
        "stop_reason": stop_reason,
        "convergence_min_iterations": optimizer_config.convergence_min_iterations,
        "convergence_patience": optimizer_config.convergence_patience,
        "convergence_relative_tolerance": optimizer_config.convergence_relative_tolerance,
        "stagnant_generations_at_stop": stagnant_iterations,
        "population_size": optimizer_config.population_size,
        "evaluations": len(evaluations), "unique_candidates": len(cache),
        "cache_evaluations": optimizer_config.cache_evaluations,
        "workers": workers,
        "search_elapsed_seconds": perf_counter() - started,
        "parent_wait_seconds": worker_wait_seconds,
        "cached_or_coalesced_candidates": len(history) * optimizer_config.population_size - len(evaluations),
        "catalog_size": len(bounds.allowed_bus_ids) * bounds.feasible_design_count(),
        "unconstrained_catalog_size": len(bounds.allowed_bus_ids) * len(bounds.power_ratings_kw) * len(bounds.energy_capacities_kwh),
        "duration_limits_hours": [bounds.min_duration_hours, bounds.max_duration_hours],
    })


def evaluate_finalists(network, profiles, bounds, evaluator, candidates, workers, *, progress=None):
    """Evaluate exact finalist tuples on the original chronology, in a stable order."""
    candidates = tuple(candidates)
    workers = min(workers, len(candidates))
    if workers <= 1:
        return [_evaluate(network, profiles, bounds, evaluator, candidate) for candidate in candidates]
    context = get_context()
    study = network, profiles, bounds, _without_progress(evaluator)
    with ProcessPoolExecutor(max_workers=workers, mp_context=context, initializer=_initialize_numba_worker,
                             initargs=(None, study)) as pool:
        results = []
        for index, result in enumerate(pool.map(_evaluate_process, candidates), 1):
            results.append(result)
            if progress is not None:
                progress(ProgressEvent("Annual finalists", index, len(candidates),
                                       f"Verified annual evaluation at bus {result.candidate.bus_id}", True))
    return results


def exhaustive_search(network: NetworkModel, profiles,
                      bounds: OptimizationBounds, evaluator: Evaluator) -> OptimizationResult:
    """Evaluate every catalog combination as a small-case verification reference."""
    bounds.validate_network(network)
    if not callable(evaluator):
        raise ValueError("evaluator must be callable")
    evaluations = []
    history = []
    best_score = float("inf")
    for bus, power in product(bounds.allowed_bus_ids, bounds.feasible_power_ratings()):
        for energy in bounds.energies_for_power(power):
            candidate = BESSCandidate(bus, power, energy)
            evaluation = _evaluate(network, profiles, bounds, evaluator, candidate)
            evaluations.append(evaluation)
            if evaluation.feasible:
                best_score = min(best_score, evaluation.objective)
            history.append(best_score)
    return _make_result(evaluations, history, len(evaluations), {
        "algorithm": "exhaustive", "history_axis": "candidate",
        "evaluations": len(evaluations), "unique_candidates": len(evaluations),
        "catalog_size": len(evaluations),
        "duration_limits_hours": [bounds.min_duration_hours, bounds.max_duration_hours],
    })


def _one_point_crossover(parent_a: tuple, parent_b: tuple, rng: Random,
                         crossover_rate: float) -> tuple[tuple, tuple]:
    """Standard single-point crossover: produce *two* complementary children.

    Make one crossover decision for the parent pair. If it succeeds, choose
    one cut between genes and exchange the tails. Otherwise, copy both
    parents unchanged. Mutation is applied to each child later.
    """
    if len(parent_a) != len(parent_b) or len(parent_a) < 2:
        raise ValueError("Parents must have equal chromosome lengths >= 2")
    if rng.random() < crossover_rate:
        cut = rng.randrange(1, len(parent_a))
        return (parent_a[:cut] + parent_b[cut:],
                parent_b[:cut] + parent_a[cut:])
    return parent_a, parent_b


def genetic_optimize(network: NetworkModel, profiles, bounds: OptimizationBounds,
                     evaluator: Evaluator, optimizer_config: OptimizerConfig, *,
                     progress=None, crossover_rate: float = 0.80,
                     mutation_rate: float = 0.12, elite_count: int = 1) -> OptimizationResult:
    """Discrete GA with tournament selection, standard single-point
    crossover (two children per mating), per-gene mutation and elitism.

    GA and GWO share the same evaluator, catalogs, feasibility checks and fitness.
    """
    bounds.validate_network(network)
    for rate in (crossover_rate, mutation_rate):
        if not 0 <= rate <= 1:
            raise ValueError("GA rates must be between zero and one")
    if not 1 <= elite_count < optimizer_config.population_size:
        raise ValueError("GA elitism must preserve between 1 and population_size-1 candidates")
    rng = Random(optimizer_config.seed)
    catalogs = _catalogs(bounds)
    def random_candidate():
        return bounds.random_candidate(rng)
    population = [random_candidate() for _ in range(optimizer_config.population_size)]
    for i, candidate in enumerate(optimizer_config.initial_candidates):
        bounds.validate_candidate(candidate)
        population[i] = candidate
    cache = {}
    evaluated = []
    history = []
    for generation in range(optimizer_config.max_iterations):
        generation_evals = []
        for candidate in population:
            if optimizer_config.cache_evaluations and candidate in cache:
                evaluation = cache[candidate]
            else:
                evaluation = _evaluate(network, profiles, bounds, evaluator, candidate)
                cache[candidate] = evaluation
                evaluated.append(evaluation)
            generation_evals.append(evaluation)
        ranked = sorted(generation_evals, key=lambda v: (not v.feasible, v.objective, v.candidate))
        feasible = [v for v in cache.values() if v.feasible]
        history.append(min((v.objective for v in feasible), default=float("inf")))
        if progress:
            progress(ProgressEvent("GA", generation + 1, optimizer_config.max_iterations,
                                   f"generation {generation + 1}; best annual cost {history[-1]:.4g}", True))
        if generation == optimizer_config.max_iterations - 1:
            break
        def select():
            return min(rng.sample(generation_evals, k=min(3, len(generation_evals))),
                       key=lambda v: (not v.feasible, v.objective)).candidate
        children = [v.candidate for v in ranked[:elite_count]]
        while len(children) < optimizer_config.population_size:
            parent_a, parent_b = select(), select()
            va = (parent_a.bus_id, parent_a.power_rating_kw, parent_a.energy_capacity_kwh)
            vb = (parent_b.bus_id, parent_b.power_rating_kw, parent_b.energy_capacity_kwh)
            offspring = _one_point_crossover(va, vb, rng, crossover_rate)
            for child in offspring:
                child = tuple(rng.choice(catalog) if rng.random() < mutation_rate else gene
                              for gene, catalog in zip(child, catalogs))
                # Crossover/mutation may separate valid parent P/E pairs.
                child = BESSCandidate(*child)
                position = _position_from_legacy_chromosome(child, catalogs)
                children.append(_candidate_from_position(position, bounds))
                # For odd population sizes, retain only the remaining slots.
                if len(children) == optimizer_config.population_size:
                    break
        population = children
    result = _make_result(evaluated, history, len(history), {
        "algorithm": "GA", "history_axis": "generation", "seed": optimizer_config.seed,
        "population_size": optimizer_config.population_size,
        "evaluations": len(evaluated), "unique_candidates": len(cache),
        "crossover_rate": crossover_rate, "crossover_method": "one_point_two_offspring",
        "mutation_rate": mutation_rate,
        "elite_count": elite_count, "workers": 1,
        "catalog_size": len(bounds.allowed_bus_ids) * bounds.feasible_design_count(),
        "duration_limits_hours": [bounds.min_duration_hours, bounds.max_duration_hours],
    })
    return result


def _position_from_legacy_chromosome(candidate, catalogs):
    """Positions may be temporarily invalid after GA recombination; repair them."""
    return [float(catalog.index(value) + 1) for catalog, value in zip(
        catalogs, (candidate.bus_id, candidate.power_rating_kw, candidate.energy_capacity_kwh))]
