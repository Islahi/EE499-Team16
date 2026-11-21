"""Run a chronological fleet comparison from a saved EE499 input snapshot."""
import argparse
from dataclasses import asdict
import json
from multiprocessing import freeze_support
from pathlib import Path

import pandas as pd

from .data_loader import ProfileData
from .fbs import FBSConfig
from .fleet_optimizer import FleetSearchConfig
from .metrics import EconomicConfig
from .network_loader import load_network
from .simulation import ConstraintAwareDispatch, SimulationConfig
from .ui_workflow import PreparedStudy, RunSettings, run_and_export


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_run", type=Path, help="Saved run directory containing dashboard_run.json and inputs/")
    parser.add_argument("output", type=Path, help="New directory for CSV, JSON and the offline dashboard")
    parser.add_argument("--counts", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument("--capacity", choices=("equal", "flexible"), default="equal")
    parser.add_argument("--objective", choices=("reliability", "economics"), default="reliability")
    parser.add_argument("--total-kw", type=float, default=1250.)
    parser.add_argument("--total-kwh", type=float, default=6250.)
    parser.add_argument("--power-step", type=float, default=250.)
    parser.add_argument("--energy-step", type=float, default=250.)
    parser.add_argument("--capital-budget", type=float)
    parser.add_argument("--annual-cost-budget", type=float)
    parser.add_argument("--fixed-site-cost", type=float)
    parser.add_argument("--reserve-percent", type=float, help="Explicitly override the archived percent of peak load")
    parser.add_argument("--start", help="First source timestamp for a reduced validation study")
    parser.add_argument("--hours", type=int, help="Reduced validation horizon in hours. Omit for an annual run.")
    parser.add_argument("--population", type=int, default=12)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--top-sites", type=int, default=10)
    parser.add_argument("--exploration", type=int, default=2)
    parser.add_argument("--trial-kw", type=float, default=100.)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--window-count", type=int, default=4)
    parser.add_argument("--finalists", type=int, default=5)
    parser.add_argument("--full-horizon", action="store_true")
    parser.add_argument("--distinct-sections", action="store_true")
    parser.add_argument("--buses", type=int, nargs="+", help="Explicit shortlist of eligible installation buses")
    args = parser.parse_args(argv)
    if args.hours is not None and args.hours < 1:
        parser.error("--hours must be positive")
    if args.start and args.hours is None:
        parser.error("Provide --hours when selecting a reduced comparison start")
    inputs = args.session_run / "inputs"
    workbook = next(iter(sorted(inputs.glob("network.*"))), None)
    if workbook is None:
        parser.error("Missing saved network workbook in inputs/")
    with (args.session_run / "dashboard_run.json").open(encoding="utf-8-sig") as stream:
        saved = json.load(stream)
    with (inputs / "input_snapshot.json").open(encoding="utf-8-sig") as stream:
        snapshot = json.load(stream)
    network = load_network(workbook, frequency_hz=saved["topology"]["frequency_hz"])
    profiles = ProfileData(inputs / "load_profile.csv", inputs / "pv_profile.csv")
    if args.hours:
        start = pd.Timestamp(args.start) if args.start else profiles.timestamps[0]
        profiles = profiles.slice(start, start + pd.Timedelta(hours=args.hours))
    context = dict(saved.get("context") or {})
    economic_values = dict(context["Economic inputs"])
    if args.fixed_site_cost is not None:
        economic_values["fixed_installation_cost"] = args.fixed_site_cost
    economics = EconomicConfig(**economic_values)
    sim_values = dict(saved["simulation"])
    sim_values["fbs_config"] = FBSConfig(**sim_values["fbs_config"])
    sim_values["legacy_proportional_validation"] = False
    if args.reserve_percent is not None:
        sim_values["reserve_fraction"] = args.reserve_percent / 100.
    simulation = SimulationConfig(**sim_values)
    search = FleetSearchConfig(tuple(args.counts), args.capacity, args.objective, args.total_kw, args.total_kwh,
        args.annual_cost_budget, args.capital_budget, not args.full_horizon, args.top_sites, args.exploration,
        args.trial_kw, args.window_days, args.window_count, args.finalists, args.distinct_sections,
        require_annual=args.hours is None)
    controls = context.get("Settings controls") or {}
    values = {"fleet_search": asdict(search), "optimizer_algorithm": "GWO", "spin_cpu_workers": args.workers,
        "allowed_buses": tuple(args.buses or [bus.bus_id for bus in network.buses if not bus.is_slack]),
        "spin_gwo_population": args.population, "spin_gwo_iterations": args.iterations, "spin_gwo_seed": args.seed,
        "spin_eta_charge_percent": controls.get("spin_eta_charge_percent", 90.),
        "spin_eta_discharge_percent": controls.get("spin_eta_discharge_percent", 90.),
        "spin_soc_min_percent": controls.get("spin_soc_min_percent", 20.),
        "spin_soc_max_percent": controls.get("spin_soc_max_percent", 100.),
        "spin_soc_initial_percent": controls.get("spin_soc_initial_percent", 50.),
        "spin_opt_power_min_kw": args.power_step, "spin_opt_power_max_kw": args.total_kw, "spin_opt_power_step_kw": args.power_step,
        "spin_opt_energy_min_kwh": args.energy_step, "spin_opt_energy_max_kwh": args.total_kwh, "spin_opt_energy_step_kwh": args.energy_step}
    study = PreparedStudy(network, profiles, None, {"Network": context.get("Network", f"{len(network.buses)}-bus radial feeder"),
        "Clock": snapshot["clock"], "Reference input" : str(args.session_run)})
    study.input_mode = context.get("Active input source") or "historical"
    study.simulation_window = {"start": str(profiles.timestamps[0]), "last": str(profiles.timestamps[-1]),
                               "hours": len(profiles.timestamps), "clock": snapshot["clock"]}
    report = run_and_export(study, RunSettings(simulation, economics, None, values, ConstraintAwareDispatch()), True,
                            args.output, stage=lambda text: print(text, flush=True), network_snapshot=workbook)
    print(report.result.message, flush=True)
    print(f"Fleet comparison: {args.output.resolve() / 'fleet_comparison.csv'}", flush=True)


if __name__ == "__main__":
    freeze_support()
    main()
