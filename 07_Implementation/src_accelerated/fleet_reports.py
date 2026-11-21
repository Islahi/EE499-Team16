"""Saved tables for matched fleet comparisons and their placement evidence."""
from dataclasses import asdict
import json

from .metrics import percentage_reduction
from .results import _write_csv


def describe(candidate):
    return {"bus_id": candidate.bus_id, "power_rating_kw": candidate.power_rating_kw,
            "energy_capacity_kwh": candidate.energy_capacity_kwh, "units": [asdict(unit) for unit in candidate.units]}


def write_experiment(folder, experiment):
    folder = folder.resolve()
    details = experiment.metadata
    with (folder / "fleet_experiment.json").open("x", encoding="utf-8") as stream:
        json.dump({"metadata": details, "baseline": asdict(experiment.evaluation),
                   "stage_a": [asdict(item) for item in experiment.screened],
                   "stage_b": [asdict(item) for item in experiment.verified],
                   "winners": {objective: {count: asdict(item) if item else None for count, item in winners.items()}
                               for objective, winners in experiment.winners.items()}},
                  stream, ensure_ascii=False, allow_nan=False)
    baseline = experiment.evaluation.shedding_kwh
    def summary_rows():
        for objective, winners in experiment.winners.items():
            for count, item in winners.items():
                if item is None:
                    yield [objective, count, False, *([None] * 22)]
                    continue
                candidate, saved = item.candidate, item.details
                yield [objective, count, item.feasible, candidate.bus_id, candidate.power_rating_kw,
                       candidate.energy_capacity_kwh, item.capex, item.cost, saved["cost_basis"],
                       saved["annualized_ownership_usd"], item.shedding_kwh / 1000, percentage_reduction(baseline, item.shedding_kwh),
                       item.curtailment_kwh / 1000, saved["grid_import_kwh"] / 1000, saved["losses_kwh"] / 1000,
                       saved["voltage_violation_hours"], saved["export_violation_hours"], saved["ampacity_violation_hours"],
                       saved["reserve_violation_hours"], sum(saved["fully_disconnected_hours_by_bus"].values()),
                       saved["fully_disconnected_hours_by_bus"], saved["max_bus_shedding_fraction"],
                       saved["bus_shedding_fraction_spread"], saved["terminal_soc"], saved["fbs_calls"]]
    _write_csv(folder / "fleet_comparison.csv", ["objective", "unit_count", "verified_feasible", "buses", "total_kw", "total_kwh",
        "capex_usd", "cost_usd", "cost_basis", "annualized_ownership_usd", "shedding_mwh", "shedding_reduction_percent",
        "curtailment_mwh", "grid_import_mwh", "losses_mwh", "voltage_violation_hours", "export_violation_hours",
        "ampacity_violation_hours", "reserve_violation_hours", "complete_disconnection_bus_hours", "complete_disconnection_by_bus",
        "max_bus_shedding_fraction", "bus_shedding_fraction_spread", "terminal_soc_by_unit", "fbs_calls"], summary_rows())
    branches = details["sections"]
    if branches:
        _write_csv(folder / "branch_severity.csv", list(branches[0]), (list(row.values()) for row in branches))
    _write_csv(folder / "location_screening.csv", ["bus", "section", "shed_mwh", "disconnection_hours", "shedding_relief_score",
        "voltage_support_score", "charging_score", "score", "selection"],
        ([row.get(key) for key in ("bus", "section", "shed_mwh", "disconnection_hours", "shedding_relief_score",
         "voltage_support_score", "charging_score", "score", "selection")] for row in details["bus_severity"].values()))
