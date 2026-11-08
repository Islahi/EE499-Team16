"""GA population/generation sizing and offspring count verification."""
import pytest
from src_accelerated.optimizer import (BESSCandidate, CandidateEvaluation,
    OptimizationBounds, OptimizerConfig, genetic_optimize)
from src_accelerated.network_model import NetworkModel, Bus, Line, Load


@pytest.mark.parametrize('population', [3, 4, 5, 6])
def test_ga_preserves_odd_and_even_population(population):
    network = NetworkModel(
        [Bus(1, 'slack', 12.66, True), Bus(2, 'load', 12.66)],
        [Line('1-2', 1, 2, 0.03, 0.02)],
        [Load('L2', 2, 100., 40.)], [], 1000., 60.)
    bounds = OptimizationBounds((2,), (100., 200., 300.), (200., 400., 600.))
    def evaluate(n, p, c):
        return CandidateEvaluation(c, c.power_rating_kw + c.energy_capacity_kwh, True)
    conf = OptimizerConfig(population_size=population, max_iterations=4, seed=11,
                           cache_evaluations=False)
    result = genetic_optimize(network, None, bounds, evaluate, conf)
    assert result.metadata['population_size'] == population
    assert result.metadata['crossover_method'] == 'one_point_two_offspring'
    assert result.iterations == 4
    # With caching disabled, exactly N population members are evaluated in each generation.
    assert len(result.evaluations) == population * 4
    assert result.success
