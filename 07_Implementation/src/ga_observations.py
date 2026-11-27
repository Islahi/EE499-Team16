"""Passive generation observations for the existing stationary fleet GA."""
from dataclasses import asdict
from math import isfinite
from os import getenv
from statistics import mean, median


def finite(value):
    return value if isfinite(value) else None


class GAObservations:
    """Assign IDs from observed cache insertion order and retain scalar evidence."""

    def __init__(self, level):
        self.level = level
        self.generations = []
        self.fleet_ids = {}
        self.lineage = []
        self.failed = False

    @classmethod
    def start(cls, level):
        try:
            level = level or getenv("EE499_GA_DIAGNOSTICS", "summary")
            return cls(level) if level in ("summary", "detail") else None
        except Exception:
            return None

    def candidate_id(self, fleet):
        if fleet not in self.fleet_ids:
            self.fleet_ids[fleet] = len(self.fleet_ids) + 1
        return self.fleet_ids[fleet]

    def generation(self, index, population, pending, ranked, cache_size, best, reference, stall, duration):
        if self.failed:
            return
        try:
            for fleet in pending:
                self.candidate_id(fleet)
            unique = len(set(population))
            values = [item.objective for item in ranked if item.feasible and isfinite(item.objective)]
            self.generations.append({
                "index": index + 1, "seconds": duration,
                "slots": len(population), "new": len(pending),
                "previous": unique - len(pending), "duplicates": len(population) - unique,
                "unique_total": cache_size, "feasible_slots": len(values), "invalid_slots": len(ranked) - len(values),
                "best_so_far": finite(best), "best": min(values) if values else None,
                "mean": mean(values) if values else None, "median": median(values) if values else None,
                "significant_reference": finite(reference), "stall": stall,
                "members": [self.candidate_id(fleet) for fleet in population],
                "ranked": [self.candidate_id(item.fleet) for item in ranked],
                "new_ids": [self.candidate_id(fleet) for fleet in pending],
            })
        except Exception:
            self.failed = True

    def offspring(self, generation, slot, parents, crossed, mutated):
        if self.level != "detail" or self.failed:
            return
        try:
            self.lineage.append((generation + 2, slot, parents, crossed, mutated))
        except Exception:
            self.failed = True

    def report(self, ranked, workers):
        if self.failed:
            return {"schema": 1, "status": "capture_failed"}
        try:
            return {
                "schema": 1, "status": "recorded", "level": self.level, "effective_workers": workers,
                "generations": self.generations,
                "candidates": [{
                    "id": self.candidate_id(item.fleet), "fleet": [asdict(unit) for unit in item.fleet],
                    "screen_rank": rank, "feasible": item.feasible, "objective": finite(item.objective),
                    "annual_operational_cost": finite(item.annual_operational_cost),
                    "annual_fixed_cost": item.annual_fixed_cost if item.feasible else None,
                    "annual_shedding_kwh": item.annual_shedding_kwh if item.feasible else None,
                    "annual_curtailment_kwh": item.annual_curtailment_kwh if item.feasible else None,
                    "message": item.message, "evaluation_seconds": item.elapsed_seconds,
                } for rank, item in enumerate(ranked, 1)],
                "lineage": [[generation, slot, [self.fleet_ids.get(p) for p in parents],
                             [asdict(unit) for unit in crossed], self.fleet_ids.get(child)]
                            for generation, slot, parents, crossed, child in self.lineage],
            }
        except Exception:
            return {"schema": 1, "status": "capture_failed"}
