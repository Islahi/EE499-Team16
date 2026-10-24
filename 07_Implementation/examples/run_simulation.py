"""Run a synthetic hourly comparison: python examples/run_simulation.py."""
import argparse
import math
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.bess import BESSConfig
from src.data_loader import ProfileData
from src.metrics import EconomicConfig, evaluate_results, percentage_reduction
from src.network_cases import build_guide_5_bus_case
from src.results import export_results
from src.simulation import SimulationConfig, simulate_timeseries


def make_demo_profiles(network, hours):
    load_rows = ["timestamp,bus_id,p_kw,q_kvar"]
    pv_rows = ["timestamp,bus_id,p_kw,q_kvar"]
    start = datetime(2026, 1, 1)
    for index in range(hours):
        hour = index % 24
        timestamp = (start + timedelta(hours=index)).isoformat()
        load_factor = 0.65 + 0.20 * math.cos((hour - 19) * math.pi / 12)
        pv_factor = max(0.0, math.sin((hour - 6) * math.pi / 12))
        for load in network.loads:
            load_rows.append(
                f"{timestamp},{load.bus_id},"
                f"{load.p_base_kw * load_factor},{load.q_base_kvar * load_factor}"
            )
        for pv in network.pv_units:
            pv_rows.append(f"{timestamp},{pv.bus_id},{pv.p_rated_kw * pv_factor},0")
    return ProfileData(
        csv_load=StringIO("\n".join(load_rows)),
        csv_pv=StringIO("\n".join(pv_rows)),
    )


def dispatch_bess(index, profile, state):
    # Demonstration only: discharge above 600 kW net load; charge below it.
    net_load_kw = sum(profile.p_load_kw.values()) - sum(profile.p_pv_kw.values())
    return net_load_kw - 600.0


def print_results(label, result, economic_config, bess_config=None):
    print(f"\n{label}: {result.message}")
    print(f"Hours: {len(result.steps)}, feasible: {result.feasible}")
    if not result.completed or not result.converged:
        for step in result.steps:
            if not step.power_flow.converged:
                print(step.timestamp, step.messages)
        return None
    metrics = evaluate_results(result, economic_config, bess_config)
    print(f"Voltage range: {metrics.voltage_min_pu:.5f} to {metrics.voltage_max_pu:.5f} pu")
    print(f"Line-loss energy: {metrics.loss_energy_kwh:.3f} kWh")
    print(f"Grid import: {metrics.grid_import_energy_kwh:.3f} kWh")
    print(f"Grid export: {metrics.grid_export_energy_kwh:.3f} kWh")
    print(f"PV curtailment: {metrics.curtailment_energy_kwh:.3f} kWh")
    print(f"Load shedding: {metrics.load_shedding_energy_kwh:.3f} kWh")
    print(f"Battery charge/discharge: {metrics.bess_charge_energy_kwh:.3f} / "
          f"{metrics.bess_discharge_energy_kwh:.3f} kWh")
    if metrics.bess_cost is None:
        print("BESS investment cost: unavailable until both cost coefficients are supplied")
    else:
        print(f"BESS investment cost: {metrics.bess_cost:.2f} {metrics.currency}")
    for note in metrics.notes:
        print(f"Note: {note}")
    if result.final_bess_state is not None:
        print(f"Final BESS SOC: {result.final_bess_state.soc:.2%}")
        print("First six hours: timestamp | request kW | actual kW | end SOC")
        for step in result.steps[:6]:
            print(
                f"{step.timestamp} | {step.bess_request_kw:8.2f} | "
                f"{step.bess_step.actual_power_kw:8.2f} | {step.bess_state.soc:.2%}"
            )
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Synthetic hourly FBS/BESS demonstration")
    parser.add_argument("--hours", type=int, default=24, help="Number of hours (minimum 2)")
    parser.add_argument("--cost-per-kwh", type=float, help="BESS energy investment coefficient")
    parser.add_argument("--cost-per-kw", type=float, help="BESS power investment coefficient")
    parser.add_argument("--currency", default="SAR", help="Currency label for both coefficients")
    parser.add_argument("--grid-import-limit-kw", type=float, help="Optional upstream import cap")
    parser.add_argument("--grid-export-limit-kw", type=float, help="Optional upstream export cap")
    parser.add_argument("--pv-rating-kw", type=float, help="Override the demo's bus-4 PV rating")
    parser.add_argument("--output-dir", type=Path, help="New folder for baseline and BESS CSV exports")
    args = parser.parse_args()
    if args.hours < 2:
        parser.error("--hours must be at least 2")
    if args.output_dir is not None and args.output_dir.exists():
        parser.error("--output-dir must be a new folder; existing runs are not overwritten")
    network = build_guide_5_bus_case()
    if args.pv_rating_kw is not None:
        if not math.isfinite(args.pv_rating_kw) or args.pv_rating_kw < 0:
            parser.error("--pv-rating-kw must be finite and nonnegative")
        network.pv_units[0] = replace(network.pv_units[0], p_rated_kw=args.pv_rating_kw)
    profiles = make_demo_profiles(network, args.hours)
    settings = SimulationConfig(
        grid_import_limit_kw=args.grid_import_limit_kw,
        grid_export_limit_kw=args.grid_export_limit_kw,
    )
    economics = EconomicConfig(
        cost_per_kwh=args.cost_per_kwh, cost_per_kw=args.cost_per_kw, currency=args.currency
    )
    bess = BESSConfig(
        bus_id=4, energy_capacity_kwh=1000.0, power_rating_kw=200.0,
        soc_min=0.1, soc_max=0.9, soc_initial=0.5,
        eta_charge=0.95, eta_discharge=0.95,
    )
    print("Synthetic guide-network demo; inputs and efficiencies are demonstration assumptions.")
    baseline = simulate_timeseries(network, profiles, settings)
    with_bess = simulate_timeseries(network, profiles, settings, bess, dispatch_bess)
    baseline_metrics = print_results("No BESS", baseline, economics)
    bess_metrics = print_results("With BESS", with_bess, economics, bess)
    if baseline_metrics is not None and bess_metrics is not None:
        comparisons = [
            ("Line-loss", baseline_metrics.loss_energy_kwh, bess_metrics.loss_energy_kwh),
            ("PV curtailment", baseline_metrics.curtailment_energy_kwh, bess_metrics.curtailment_energy_kwh),
            ("Load shedding", baseline_metrics.load_shedding_energy_kwh, bess_metrics.load_shedding_energy_kwh),
        ]
        for label, baseline_value, bess_value in comparisons:
            reduction = percentage_reduction(baseline_value, bess_value)
            if reduction is not None:
                print(f"\n{label} reduction for this demonstration: {reduction:.2f}%")
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=False)
        context = {"study": "Synthetic guide-feeder demo, not real-data validation",
                   "arguments": str(vars(args)), "simulation_settings": str(settings),
                   "economics": str(economics), "candidate_battery_settings": str(vars(bess)),
                   "dispatch": "net load minus 600 kW; demonstration only"}
        export_results(baseline, args.output_dir / "baseline", metrics=baseline_metrics, context=context)
        export_results(with_bess, args.output_dir / "with_bess", metrics=bess_metrics,
                       baseline_metrics=baseline_metrics if bess_metrics is not None else None, context=context)
        print(f"\nSaved CSVs and summaries to {args.output_dir.resolve()}")
    if not baseline.converged or not with_bess.converged:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
