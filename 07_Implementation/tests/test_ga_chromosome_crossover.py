"""Standard two-offspring single-point crossover regression tests."""
import pytest
from src_accelerated.optimizer import _one_point_crossover


class FixedRNG:
    def __init__(self, chance, cut=None):
        self.chance = chance
        self.cut = cut
        self.random_calls = 0
        self.cut_calls = 0

    def random(self):
        self.random_calls += 1
        return self.chance

    def randrange(self, start, stop):
        self.cut_calls += 1
        assert (start, stop) == (1, 3)
        return self.cut


def test_standard_crossover_produces_two_complementary_children():
    a = (5, 100.0, 400.0)
    b = (10, 300.0, 900.0)
    rng = FixedRNG(chance=0.10, cut=1)
    assert _one_point_crossover(a, b, rng, 0.80) == (
        (5, 300.0, 900.0), (10, 100.0, 400.0))
    assert rng.random_calls == 1
    assert rng.cut_calls == 1


def test_standard_crossover_can_cut_after_second_gene():
    a = (5, 100.0, 400.0)
    b = (10, 300.0, 900.0)
    rng = FixedRNG(chance=0.10, cut=2)
    assert _one_point_crossover(a, b, rng, 0.80) == (
        (5, 100.0, 900.0), (10, 300.0, 400.0))
    assert rng.random_calls == 1


def test_no_crossover_copies_both_parents():
    a = (5, 100.0, 400.0)
    b = (10, 300.0, 900.0)
    rng = FixedRNG(chance=0.90)
    assert _one_point_crossover(a, b, rng, 0.80) == (a, b)
    assert rng.random_calls == 1
    assert rng.cut_calls == 0


def test_invalid_parent_lengths_rejected():
    with pytest.raises(ValueError):
        _one_point_crossover((1,), (2,), FixedRNG(.1), .8)
