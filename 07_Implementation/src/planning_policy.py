"""Desktop Joint GA policy, independent of saved Qt widget values."""
from dataclasses import dataclass, replace
from os import cpu_count

from .approved_methodology import auto_workers


DEFAULT_MINIMUM_DISCHARGE_PF = 0.95
DEFAULT_DISPATCH_HORIZON_HOURS = 24
DEFAULT_DISPATCH_EFFICIENCY = 0.95


def desktop_worker_limit() -> int:
    return min(8, cpu_count() or 1)


@dataclass(frozen=True)
class JointSearchPolicy:
    population: int
    workers: int
    generations: int = 20
    crossover: float = 0.80
    mutation: float = 0.20
    stall_generations: int = 6
    relative_tolerance: float = 0.001
    seed: int = 42
    annual_fallbacks: int = 3
    annual_workers: int = 1


def joint_search_policy(bus_count: int) -> JointSearchPolicy:
    # Keep the V15.6 defaults on the 15- and 33-bus feeders. Give larger
    # feeders more initial coverage while bounding the annual search cost.
    population = min(24, max(8, 4 * ((bus_count + 11) // 12)))
    if 12 <= bus_count <= 36:
        population = 12
    return JointSearchPolicy(population=population, workers=auto_workers())


def effective_joint_search(values) -> JointSearchPolicy:
    defaults = joint_search_policy(len(values.get("allowed_buses", ())))
    return replace(defaults, population=values.get("spin_ga_population", defaults.population),
                   generations=values.get("spin_max_generations", defaults.generations),
                   workers=values.get("spin_parallel_workers", defaults.workers))
