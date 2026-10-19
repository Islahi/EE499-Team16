"""Discrete-catalog GWO search using public simulation and metrics interfaces.

GWO equations: https://github.com/alimirjalili/GWO/blob/master/GWO.m
Catalog rounding, explicit evaluation and feasible-leader retention are the
project's adaptations. The search is a heuristic, not a global-optimum proof.
"""
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import copy
from dataclasses import dataclass, field, replace
from itertools import product
from math import floor, isclose, isfinite
from random import Random

from .bess import BESSConfig
from .data_loader import ProfileData
from .metrics import EconomicConfig, PerformanceMetrics, evaluate_results
from .network_model import NetworkModel
from .simulation import DispatchPolicy, SimulationConfig, simulate_timeseries
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

    def validate_network(self, network):
        network.validate()
        unknown = set(self.allowed_bus_ids) - {bus.bus_id for bus in network.buses}
        if unknown:
            raise ValueError(f"Search bounds contain unknown buses: {sorted(unknown)}")


@dataclass(frozen=True)
class BESSParameters:
    eta_charge: float
    eta_discharge: float
    soc_min: float = 0.1
    soc_max: float = 0.9
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


@dataclass(frozen=True)
class ObjectiveWeights:
    cost: float = 0.50
    curtailment: float = 0.25
    shedding: float = 0.25

    def __post_init__(self):
        for name in ("cost", "curtailment", "shedding"):
            _check_number(getattr(self, name), name)
        if not isclose(self.cost + self.curtailment + self.shedding, 1.0, abs_tol=1e-9):
            raise ValueError("Objective weights must add up to one")


def weighted_sum(metrics: PerformanceMetrics, weights: ObjectiveWeights | None = None) -> float:
    """Apply the agreed raw WSM; missing components cannot be scored as zero."""
    settings = weights if weights is not None else ObjectiveWeights()
    components = [metrics.bess_cost, metrics.curtailment_energy_kwh, metrics.load_shedding_energy_kwh]
    if any(value is None for value in components):
        raise ValueError("WSM needs cost, curtailment and shedding values")
    for value in components:
        _check_number(value, "WSM component")
    if not metrics.feasible:
        return float("inf")
    return (settings.cost * metrics.bess_cost
            + settings.curtailment * metrics.curtailment_energy_kwh
            + settings.shedding * metrics.load_shedding_energy_kwh)


@dataclass
class CandidateEvaluation:
    candidate: BESSCandidate
    objective: float
    feasible: bool
    metrics: PerformanceMetrics | None = None
    message: str = ""


@dataclass
class SimulationEvaluator:
    economic_config: EconomicConfig
    battery_parameters: BESSParameters
    dispatch_policy: DispatchPolicy
    simulation_config: SimulationConfig = field(default_factory=SimulationConfig)
    weights: ObjectiveWeights = field(default_factory=ObjectiveWeights)
    progress: Callable | None = None

    def __post_init__(self):
        for name in ("cost_per_kwh", "cost_per_kw"):
            value = getattr(self.economic_config, name)
            if value is None:
                raise ValueError(f"Supply {name} before optimization; no default price is assumed")
            _check_number(value, name)
        if not callable(self.dispatch_policy):
            raise ValueError("Supply a callable dispatch_policy for optimization")

    def __call__(self, network, profiles, candidate):
        if not isinstance(profiles, ProfileData):
            raise TypeError("SimulationEvaluator expects ProfileData; wrap in uncertainty.ScenarioEvaluator for ScenarioSet")
        bess_config = self.battery_parameters.build_config(candidate)
        result = simulate_timeseries(
            network=network, profiles=profiles, simulation_config=self.simulation_config,
            bess_config=bess_config, dispatch_policy=self.dispatch_policy,
            progress=self.progress,
        )
        if not result.completed or not result.converged:
            return CandidateEvaluation(candidate, float("inf"), False, message=result.message)
        metrics = evaluate_results(result, self.economic_config, bess_config)
        return CandidateEvaluation(
            candidate=candidate, objective=weighted_sum(metrics, self.weights),
            feasible=metrics.feasible, metrics=metrics, message=result.message,
        )


@dataclass
class OptimizerConfig:
    population_size: int = 12
    max_iterations: int = 20
    seed: int = 42
    cache_evaluations: bool = True
    initial_candidates: tuple[BESSCandidate, ...] = ()
    workers: int = 1

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
    values = []
    for coordinate, catalog in zip(position, _catalogs(bounds)):
        index = max(1, min(len(catalog), floor(coordinate + 0.5))) - 1
        values.append(catalog[index])
    return BESSCandidate(*values)


def _position_from_candidate(candidate, bounds):
    values = (candidate.bus_id, candidate.power_rating_kw, candidate.energy_capacity_kwh)
    position = []
    for value, catalog in zip(values, _catalogs(bounds)):
        if value not in catalog:
            raise ValueError(f"Initial/evaluated candidate is outside the configured catalog: {candidate}")
        position.append(float(catalog.index(value) + 1))
    return position


def _evaluate(network, profiles, bounds, evaluator, candidate):
    _position_from_candidate(candidate, bounds)
    evaluation = evaluator(network, profiles, candidate)
    if not isinstance(evaluation, CandidateEvaluation) or evaluation.candidate != candidate:
        raise ValueError("Evaluator must return CandidateEvaluation for the requested candidate")
    if evaluation.feasible:
        _check_number(evaluation.objective, "candidate objective")
        if evaluation.metrics is not None and not evaluation.metrics.feasible:
            raise ValueError("Evaluator marked infeasible metrics as a feasible candidate")
    else:
        evaluation = replace(evaluation, objective=float("inf"))
    return evaluation


def _without_progress(evaluator):
    """Make a shallow worker-safe evaluator without Qt/progress callbacks."""
    worker_evaluator = copy(evaluator)
    if hasattr(worker_evaluator, "progress"):
        worker_evaluator.progress = None
    for name in ("evaluator", "profile_evaluator"):
        if hasattr(worker_evaluator, name):
            setattr(worker_evaluator, name, _without_progress(getattr(worker_evaluator, name)))
    return worker_evaluator


def _evaluate_process(arguments):
    return _evaluate(*arguments)


def _make_result(evaluations, history, iterations, metadata):
    feasible = [evaluation for evaluation in evaluations if evaluation.feasible]
    best = min(feasible, key=lambda item: (item.objective, item.candidate)) if feasible else None
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


def optimize(network: NetworkModel, profiles_or_scenarios, bounds: OptimizationBounds,
             evaluator: Evaluator, optimizer_config: OptimizerConfig, *, progress=None) -> OptimizationResult:
    """Search B/P/E catalogs with seeded GWO and per-call evaluation caching."""
    bounds.validate_network(network)
    if not callable(evaluator):
        raise ValueError("evaluator must be callable")
    rng = Random(optimizer_config.seed)
    positions = []
    for _ in range(optimizer_config.population_size):
        positions.append([rng.uniform(1, len(catalog)) for catalog in _catalogs(bounds)])
    positions[0] = [1.0, 1.0, 1.0]
    positions[1] = [float(len(catalog)) for catalog in _catalogs(bounds)]
    for index, candidate in enumerate(optimizer_config.initial_candidates):
        positions[index] = _position_from_candidate(candidate, bounds)

    cache = {}
    evaluations = []
    best_by_candidate = {}
    history = []
    worker_evaluator = _without_progress(evaluator) if optimizer_config.workers > 1 else evaluator
    executor = (ProcessPoolExecutor(max_workers=optimizer_config.workers)
                if optimizer_config.workers > 1 else None)
    try:
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
                        network, profiles_or_scenarios, bounds, evaluator, candidate,
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
                    executor.submit(_evaluate_process, (
                        network, profiles_or_scenarios, bounds, worker_evaluator, candidate,
                    )): (candidate_index, candidate)
                    for candidate_index, candidate in pending
                }
                completed_results = {}
                try:
                    for completed, future in enumerate(as_completed(futures), 1):
                        candidate_index, candidate = futures[future]
                        completed_results[candidate_index] = future.result()
                        if progress is not None:
                            progress(ProgressEvent(
                                "Candidate", completed, len(pending),
                                f"parallel result bus {candidate.bus_id}; "
                                f"{candidate.power_rating_kw:g} kW / "
                                f"{candidate.energy_capacity_kwh:g} kWh",
                                True,
                            ))
                except Exception as error:
                    raise RuntimeError(
                        "Parallel optimization failed. The evaluator and its inputs must be "
                        "picklable on Windows; retry with one CPU worker for diagnosis."
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
                key=lambda item: (item.objective, item.candidate),
            )
            history.append(ranked[0].objective if ranked else float("inf"))
            if progress is not None:
                progress(ProgressEvent(
                    "GWO", iteration + 1, optimizer_config.max_iterations,
                    f"iteration completed; best objective={history[-1]:g}; "
                    f"evaluations={len(evaluations)}", True,
                ))
            if iteration == optimizer_config.max_iterations - 1:
                break
            if not ranked:
                positions = [
                    [rng.uniform(1, len(catalog)) for catalog in _catalogs(bounds)]
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

    return _make_result(evaluations, history, len(history), {
        "algorithm": "GWO", "history_axis": "generation", "seed": optimizer_config.seed,
        "population_size": optimizer_config.population_size,
        "evaluations": len(evaluations), "unique_candidates": len(cache),
        "cache_evaluations": optimizer_config.cache_evaluations,
        "workers": optimizer_config.workers,
        "catalog_size": len(bounds.allowed_bus_ids) * len(bounds.power_ratings_kw) * len(bounds.energy_capacities_kwh),
    })


def exhaustive_search(network: NetworkModel, profiles_or_scenarios,
                      bounds: OptimizationBounds, evaluator: Evaluator) -> OptimizationResult:
    """Evaluate every catalog combination as a small-case verification reference."""
    bounds.validate_network(network)
    if not callable(evaluator):
        raise ValueError("evaluator must be callable")
    evaluations = []
    history = []
    best_score = float("inf")
    for values in product(*_catalogs(bounds)):
        evaluation = _evaluate(network, profiles_or_scenarios, bounds, evaluator, BESSCandidate(*values))
        evaluations.append(evaluation)
        if evaluation.feasible:
            best_score = min(best_score, evaluation.objective)
        history.append(best_score)
    return _make_result(evaluations, history, len(evaluations), {
        "algorithm": "exhaustive", "history_axis": "candidate",
        "evaluations": len(evaluations), "unique_candidates": len(evaluations),
        "catalog_size": len(evaluations),
    })
