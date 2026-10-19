"""Small GWO/exhaustive timing check. All prices/sizes are software-test inputs."""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "07_Implementation"))

from src.dispatch import NetLoadTargetPolicy
from src.metrics import EconomicConfig
from src.optimizer import (BESSParameters, OptimizationBounds, SimulationEvaluator,
                           exhaustive_search)
from src.simulation import SimulationConfig
from src.ui_workflow import DataRequest, RunSettings, prepare_study, run_study


class DiagnosticProgress:
    def __init__(self):
        self.power_flow_calls = 0
        self.completed_hours = 0

    def __call__(self, event):
        if event.phase == "FBS" and event.completed == 0:
            self.power_flow_calls += 1
        if event.phase == "Simulation" and event.detail.startswith("hour completed"):
            self.completed_hours += 1
        if event.phase == "GWO" and event.log:
            print(event.text(), file=sys.stderr)


def diagnostic(network_path, hours=24):
    request = DataRequest(network_path, 60, "auto", "2024-01-01", 1, "none")
    study = prepare_study(request)
    if not 1 <= hours <= len(study.profiles.timestamps):
        raise ValueError(f"hours must be between 1 and {len(study.profiles.timestamps)}")
    study.profiles.timestamps = study.profiles.timestamps[:hours]
    for name in ("load_p_kw", "load_q_kvar", "pv_p_kw", "pv_q_kvar"):
        values = getattr(study.profiles, name)
        setattr(study.profiles, name, {bus: series[:hours] for bus, series in values.items()})
    values = dict(spin_eta_charge_percent=95, spin_eta_discharge_percent=95,
                  spin_soc_min_percent=10, spin_soc_max_percent=90, spin_soc_initial_percent=50,
                  allowed_buses=(4,), spin_opt_power_min_kw=50, spin_opt_power_max_kw=100,
                  spin_opt_power_step_kw=50, spin_opt_energy_min_kwh=100,
                  spin_opt_energy_max_kwh=200, spin_opt_energy_step_kwh=100,
                  spin_gwo_population=3, spin_gwo_iterations=2, spin_gwo_seed=42,
                  group_uncertainty=False)
    settings = RunSettings(SimulationConfig(reserve_fraction=0), EconomicConfig(2, 3),
                           None, values, NetLoadTargetPolicy(600))
    counter = DiagnosticProgress()
    started = perf_counter()
    report = run_study(study, settings, optimization=True, progress=counter)
    gwo_seconds = perf_counter() - started
    result = report.result
    started = perf_counter()
    exhaustive = exhaustive_search(
        study.network, study.profiles, OptimizationBounds((4,), (50, 100), (100, 200)),
        SimulationEvaluator(settings.economics, BESSParameters(.95, .95),
                            settings.dispatch, settings.simulation))
    exhaustive_seconds = perf_counter() - started
    return dict(network=str(network_path), buses=len(study.network.buses), hours=hours,
                population=3, iterations=result.iterations, uncertainty=False,
                gwo_seconds=gwo_seconds, exhaustive_seconds=exhaustive_seconds,
                unique_candidates=result.metadata["unique_candidates"],
                power_flow_calls=counter.power_flow_calls,
                evaluated_hour_steps=counter.completed_hours,
                success=result.success,
                best_candidate=vars(result.best_candidate) if result.best_candidate else None,
                gwo_objective=result.best_objective if result.success else None,
                exhaustive_objective=exhaustive.best_objective if exhaustive.success else None,
                agrees_with_exhaustive=(result.success and exhaustive.success
                                       and abs(result.best_objective - exhaustive.best_objective) < 1e-8),
                run_timing=report.context["Run duration (seconds)"],
                caveat="Tiny four-candidate development check, not a global GWO guarantee or validated battery design. Costs 2/kWh and 3/kW are illustrative.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--compare-ieee33", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    folder = ROOT / "04_Research/Working_Data/Network_Data"
    records = [diagnostic(folder / "Guide_5Bus_Radial_Test.xlsx", args.hours)]
    if args.compare_ieee33:
        records.append(diagnostic(folder / "IEEE_33Bus_Network_Data.xlsx", args.hours))
    text = json.dumps(records, indent=2, allow_nan=False)
    print(text)
    if args.output:
        with args.output.open("x", encoding="utf-8") as destination:
            destination.write(text + "\n")
    return 0 if all(record["agrees_with_exhaustive"] for record in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
