"""Synthetic ARIMA/Monte Carlo demo; optional common-candidate GWO search."""
import argparse
from dataclasses import replace
from pathlib import Path
from random import Random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run_simulation import make_demo_profiles
from src.metrics import EconomicConfig
from src.network_cases import build_guide_5_bus_case
from src.optimizer import BESSParameters, OptimizationBounds, OptimizerConfig, SimulationEvaluator, optimize
from src.simulation import SimulationConfig
from src.uncertainty import ScenarioEvaluator, UncertaintyConfig, generate_scenarios, select_scenarios
from src.results import export_results


def main():
    parser = argparse.ArgumentParser(description="Synthetic uncertainty workflow: 100 scenarios, 45 selected")
    parser.add_argument("--history-hours", type=int, default=168)
    parser.add_argument("--forecast-hours", type=int, default=24)
    parser.add_argument("--validation-hours", type=int, default=24)
    parser.add_argument("--arima-order", type=int, nargs=3, default=(1, 0, 0), metavar=("P", "D", "Q"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--pv-rating-kw", type=float, default=1200)
    parser.add_argument("--optimize", action="store_true")
    parser.add_argument("--cost-per-kwh", type=float)
    parser.add_argument("--cost-per-kw", type=float)
    parser.add_argument("--eta-charge", type=float, default=0.95)
    parser.add_argument("--eta-discharge", type=float, default=0.95)
    parser.add_argument("--grid-import-limit-kw", type=float, default=400)
    parser.add_argument("--grid-export-limit-kw", type=float, default=0)
    parser.add_argument("--dispatch-target-kw", type=float, default=400)
    parser.add_argument("--output-dir", type=Path, help="New folder for scenario-GWO CSV exports; requires --optimize")
    args = parser.parse_args()
    if args.optimize and (args.cost_per_kwh is None or args.cost_per_kw is None):
        parser.error("--optimize requires --cost-per-kwh and --cost-per-kw")
    if args.output_dir is not None:
        if not args.optimize:
            parser.error("--output-dir requires --optimize (exports evaluated results, not raw profiles)")
        if args.output_dir.exists():
            parser.error("--output-dir must be a new folder; existing runs are not overwritten")

    network = build_guide_5_bus_case()
    network.pv_units[0] = replace(network.pv_units[0], p_rated_kw=args.pv_rating_kw)
    network.validate()
    history = make_demo_profiles(network, args.history_hours)
    # Synthetic history only: add visible day-to-day variation so ARIMA has errors to learn.
    rng = Random(args.seed)
    for active, reactive in ((history.load_p_kw, history.load_q_kvar), (history.pv_p_kw, history.pv_q_kvar)):
        for bus_id, values in active.items():
            for index in range(len(values)):
                factor = rng.uniform(0.85, 1.0)
                values[index] *= factor
                reactive[bus_id][index] *= factor
    capacities = {}
    for pv in network.pv_units:
        capacities[pv.bus_id] = capacities.get(pv.bus_id, 0) + pv.p_rated_kw
    scenarios = generate_scenarios(history, UncertaintyConfig(
        forecast_hours=args.forecast_hours, pv_capacity_kw=capacities,
        seed=args.seed, validation_hours=args.validation_hours, arima_order=tuple(args.arima_order),
    ))
    selected = select_scenarios(scenarios)
    print("Synthetic guide-feeder data; not a real-data forecast or BESS recommendation.")
    print(f"Generated: {len(scenarios.scenarios)}, selected: {len(selected.scenarios)}")
    print(f"Groups: {selected.metadata['selection_counts']}")
    print(f"Future hours per case: {args.forecast_hours}")
    for kind, buses in scenarios.metadata["validation"].items():
        for bus_id, scores in buses.items():
            model, naive = scores["arima"], scores["repeat_last_day"]
            print(f"{kind} bus {bus_id}: holdout RMSE {model['rmse_kw']:.3f} kW "
                  f"(last-day baseline {naive['rmse_kw']:.3f}); MAPE {model['mape_percent']}")
    for kind, buses in scenarios.metadata["models"].items():
        for bus_id, details in buses.items():
            if details["warnings"]:
                print(f"Fit warnings for {kind} bus {bus_id}: {details['warnings']}")
    print(selected.metadata["weighting"])
    if not args.optimize:
        return

    def dispatch(index, profile, state):
        return sum(profile.p_load_kw.values()) - sum(profile.p_pv_kw.values()) - args.dispatch_target_kw

    evaluator = ScenarioEvaluator(SimulationEvaluator(
        EconomicConfig(args.cost_per_kwh, args.cost_per_kw),
        BESSParameters(args.eta_charge, args.eta_discharge), dispatch,
        SimulationConfig(grid_import_limit_kw=args.grid_import_limit_kw,
                         grid_export_limit_kw=args.grid_export_limit_kw),
    ))
    # Small demonstration catalog; configure the actual study bounds separately.
    result = optimize(network, selected, OptimizationBounds((2, 4), (100,), (500, 1000)),
                      evaluator, OptimizerConfig(population_size=4, max_iterations=2, seed=args.seed))
    print(result.message)
    if args.output_dir is not None:
        context = {"study": "Synthetic guide-feeder uncertainty demo",
                   "arguments": str(vars(args)), "aggregation": selected.metadata["weighting"],
                   "selection": str(selected.metadata["selection_counts"]),
                   "forecast_validation": str(scenarios.metadata["validation"]),
                   "simulation_settings": str(evaluator.profile_evaluator.simulation_config),
                   "battery_parameters": str(evaluator.profile_evaluator.battery_parameters),
                   "weights": str(evaluator.profile_evaluator.weights),
                   "bounds": "buses (2,4); kW (100,); kWh (500,1000)",
                   "dispatch": "net load minus --dispatch-target-kw"}
        export_results(result, args.output_dir, context=context)
        print(f"Saved CSVs and summary to {args.output_dir.resolve()}")
    if not result.success:
        raise SystemExit(1)
    print(f"Best sampled common candidate: {result.best_candidate}")
    print(f"Stress-set mean raw WSM: {result.best_objective:.6f}")
    print(f"Investment counted once: {result.metrics.bess_cost:.2f} SAR")
    print(f"Mean curtailed PV: {result.metrics.curtailment_energy_kwh:.3f} kWh")
    print(f"Mean shed load: {result.metrics.load_shedding_energy_kwh:.3f} kWh")
    print("Compare against no-BESS separately before recommending an installation.")


if __name__ == "__main__":
    main()
