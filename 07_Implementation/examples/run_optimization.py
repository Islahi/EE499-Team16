"""Synthetic GWO demo. Run from the root; see src/README_optimizer.md."""
import argparse
import sys
from dataclasses import replace
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run_simulation import make_demo_profiles
from src.metrics import EconomicConfig, evaluate_results
from src.network_cases import build_guide_5_bus_case
from src.optimizer import (
    BESSParameters, OptimizationBounds, OptimizerConfig, SimulationEvaluator,
    exhaustive_search, optimize, weighted_sum,
)
from src.simulation import SimulationConfig, simulate_timeseries
from src.results import export_results


def print_result(label, result, elapsed):
    print(f"\n{label}: {result.message}")
    print(f"Runtime: {elapsed:.2f} seconds")
    print(f"Evaluator calls: {result.metadata['evaluations']}")
    print(f"Unique candidates: {result.metadata['unique_candidates']} / {result.metadata['catalog_size']}")
    if not result.success:
        return
    candidate = result.best_candidate
    metrics = result.metrics
    print(f"Bus: {candidate.bus_id}, power: {candidate.power_rating_kw:g} kW, "
          f"energy: {candidate.energy_capacity_kwh:g} kWh")
    print(f"Raw WSM score: {result.best_objective:.6f}")
    print(f"Investment cost: {metrics.bess_cost:.2f} {metrics.currency}")
    print(f"Curtailed PV: {metrics.curtailment_energy_kwh:.3f} kWh")
    print(f"Shed load: {metrics.load_shedding_energy_kwh:.3f} kWh")
    print(f"Voltage: {metrics.voltage_min_pu:.5f} to {metrics.voltage_max_pu:.5f} pu")
    print(f"Best-so-far history: {result.convergence_history}")


def main():
    parser = argparse.ArgumentParser(description="Small synthetic BESS GWO/WSM demonstration")
    parser.add_argument("--cost-per-kwh", type=float, required=True,
                        help="Investment cost per kWh (supply illustrative values for a demo)")
    parser.add_argument("--cost-per-kw", type=float, required=True, help="Investment cost per kW")
    parser.add_argument("--currency", default="SAR")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--bus-ids", type=int, nargs="+", default=[2, 4])
    parser.add_argument("--power-ratings-kw", type=float, nargs="+", default=[100, 200])
    parser.add_argument("--energy-capacities-kwh", type=float, nargs="+", default=[500, 1000])
    parser.add_argument("--population-size", type=int, default=8)
    parser.add_argument("--iterations", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--pv-rating-kw", type=float, default=1200)
    parser.add_argument("--grid-import-limit-kw", type=float, default=400)
    parser.add_argument("--grid-export-limit-kw", type=float, default=0)
    parser.add_argument("--dispatch-target-kw", type=float, default=400)
    parser.add_argument("--eta-charge", type=float, default=0.95)
    parser.add_argument("--eta-discharge", type=float, default=0.95)
    parser.add_argument("--compare-exhaustive", action="store_true",
                        help="Evaluate the entire finite catalog as a small-case reference")
    parser.add_argument("--output-dir", type=Path, help="New folder for baseline/GWO/reference exports")
    args = parser.parse_args()
    if args.hours < 2:
        parser.error("--hours must be at least 2")
    if args.output_dir is not None and args.output_dir.exists():
        parser.error("--output-dir must be a new folder; existing runs are not overwritten")

    network = build_guide_5_bus_case()
    network.pv_units[0] = replace(network.pv_units[0], p_rated_kw=args.pv_rating_kw)
    network.validate()
    profiles = make_demo_profiles(network, args.hours)
    settings = SimulationConfig(
        grid_import_limit_kw=args.grid_import_limit_kw,
        grid_export_limit_kw=args.grid_export_limit_kw,
    )
    economics = EconomicConfig(args.cost_per_kwh, args.cost_per_kw, args.currency)
    bounds = OptimizationBounds(args.bus_ids, args.power_ratings_kw, args.energy_capacities_kwh)

    def dispatch(index, profile, state):
        net_load_kw = sum(profile.p_load_kw.values()) - sum(profile.p_pv_kw.values())
        return net_load_kw - args.dispatch_target_kw

    evaluator = SimulationEvaluator(
        economic_config=economics,
        battery_parameters=BESSParameters(args.eta_charge, args.eta_discharge),
        dispatch_policy=dispatch, simulation_config=settings,
    )
    search_settings = OptimizerConfig(args.population_size, args.iterations, args.seed)
    print("Synthetic guide-feeder demo; PV, grid caps and battery parameters are demonstration assumptions.")
    print("Supplied cost coefficients are inputs, not verified project prices.")
    baseline = simulate_timeseries(network, profiles, settings)
    baseline_metrics = None
    if baseline.completed and baseline.converged:
        baseline_metrics = evaluate_results(baseline, economics)
        print(f"No-BESS baseline raw WSM: {weighted_sum(baseline_metrics):.6f}")

    start = perf_counter()
    result = optimize(network, profiles, bounds, evaluator, search_settings)
    print_result("GWO", result, perf_counter() - start)
    print("GWO searches positive BESS installations; compare the baseline separately.")
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=False)
        context = {"study": "Synthetic guide-feeder demo, not a storage recommendation",
                   "arguments": str(vars(args)), "simulation_settings": str(settings),
                   "economics": str(economics), "battery_parameters": str(evaluator.battery_parameters),
                   "weights": str(evaluator.weights), "bounds": str(bounds),
                   "dispatch": "net load minus --dispatch-target-kw"}
        export_results(baseline, args.output_dir / "baseline", metrics=baseline_metrics, context=context)
        export_results(result, args.output_dir / "gwo",
                       baseline_metrics=baseline_metrics if result.metrics is not None else None, context=context)
        print(f"\nSaved CSVs and summaries to {args.output_dir.resolve()}")
    if args.compare_exhaustive:
        start = perf_counter()
        reference = exhaustive_search(network, profiles, bounds, evaluator)
        print_result("Exhaustive catalog reference", reference, perf_counter() - start)
        if args.output_dir is not None:
            export_results(reference, args.output_dir / "exhaustive",
                           baseline_metrics=baseline_metrics if reference.metrics is not None else None, context=context)
        if result.success and reference.success:
            print(f"\nGWO minus exhaustive score: {result.best_objective - reference.best_objective:.6f}")
    if not result.success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
