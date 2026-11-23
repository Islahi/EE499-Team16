"""Replay a saved hourly input snapshot against one or both shedding policies."""
import argparse
from dataclasses import asdict, fields, replace
from hashlib import file_digest, sha256
import importlib.util
import json
from pathlib import Path
import os
import platform
import sys
from time import perf_counter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="Saved run containing inputs/network.xlsx and both profile CSVs")
    parser.add_argument("report", type=Path, help="JSON output path")
    parser.add_argument("--source", type=Path, help="Optional extracted reference src directory")
    parser.add_argument("--window", choices=("stress", "week", "year"), action="append")
    parser.add_argument("--policy", choices=("minimum_energy", "progressive"), action="append")
    parser.add_argument("--reserve-percent", type=float, default=10.)
    parser.add_argument("--expected-pv-sites", type=int, default=5)
    parser.add_argument("--revision", default="local working tree")
    parser.add_argument("--search", nargs="+", choices=("quick", "standard", "thorough"),
                        help="Run the reduced B14/B30 fixed-size annual search")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--worker-sweep", nargs="+", type=int, help="Compare requested worker counts on twelve 168-hour candidates")
    parser.add_argument("--no-bess-only", action="store_true")
    parser.add_argument("--dashboard", type=Path, help="Save the first replay's normal CSV/JSON and HTML report")
    args = parser.parse_args()

    if args.source is not None:
        source = args.source.resolve()
        package = importlib.util.spec_from_file_location("src", source / "__init__.py",
                                                         submodule_search_locations=[str(source)])
        module = importlib.util.module_from_spec(package)
        sys.modules[package.name] = module
        package.loader.exec_module(module)

    import numba
    import numpy
    import pandas
    import scipy
    from src.bess import BESSConfig
    from src.constraint_dispatch import ConstraintAwareDispatch
    from src.data_loader import ProfileData
    from src.fbs import warm_numba
    from src.metrics import EconomicConfig, evaluate_results, with_terminal_policy
    from src.network_loader import load_network
    from src.network_model import PVUnit
    from src.simulation import SimulationConfig, simulate_timeseries

    inputs = args.run / "inputs"
    names = ("network.xlsx", "load_profile.csv", "pv_profile.csv", "input_snapshot.json")
    hashes = {}
    for name in names:
        path = inputs / name
        if path.is_file():
            with path.open("rb") as stream:
                hashes[name] = file_digest(stream, "sha256").hexdigest()
    clock = json.loads((inputs / "input_snapshot.json").read_text(encoding="utf-8")).get("clock")
    network = load_network(inputs / "network.xlsx", frequency_hz=60.)
    profiles = ProfileData(inputs / "load_profile.csv", inputs / "pv_profile.csv")
    installation_metadata = args.run / "dashboard_run.json"
    workbook_pv = [asdict(unit) for unit in network.pv_units]
    if installation_metadata.is_file():
        saved = json.loads(installation_metadata.read_text(encoding="utf-8"))
        if "pv_installations" in saved:
            network = replace(network, pv_units=[PVUnit(**row) for row in saved["pv_installations"]])
        with installation_metadata.open("rb") as stream:
            hashes["dashboard_run.json"] = file_digest(stream, "sha256").hexdigest()
    pv = {}
    for unit in network.pv_units:
        pv[unit.bus_id] = pv.get(unit.bus_id, 0.) + unit.p_rated_kw
    # Run snapshots also store effective dispatched PV separately from the source workbook.
    profile_sites = {bus for bus, values in profiles.pv_p_kw.items() if max(values, default=0.) > 0.}
    warnings = []
    if len(profile_sites) != args.expected_pv_sites or (args.expected_pv_sites == 5 and 12 not in profile_sites):
        warnings.append(f"Expected {args.expected_pv_sites} PV sites; active profile buses are {sorted(profile_sites)}")
    if set(pv) != profile_sites:
        warnings.append("Installed PV rows and the effective run profile sites differ; no PV rows were invented")
    economics = EconomicConfig(grid_import_tariff_per_kwh=.10, grid_export_tariff_per_kwh=0.)
    battery = BESSConfig(14, 6250., 1250., .20, 1., .50, .90, .90)
    dispatch = ConstraintAwareDispatch(import_tariff=.10, export_tariff=0., shedding_penalty=12., curtailment_penalty=.07)
    report = dict(input_sha256=hashes, clock=clock, buses=len(network.buses),
                  branches=len(network.radial_order().forward_line_ids), workbook_pv=workbook_pv,
                  installed_pv_kw_by_bus=pv, total_installed_pv_kw=sum(pv.values()),
                  effective_profile_pv_sites=sorted(profile_sites), warnings=warnings,
                  first=str(profiles.timestamps[0]), last=str(profiles.timestamps[-1]), source_revision=args.revision,
                  fixed_battery=vars(battery), economics=asdict(economics),
                  environment=dict(platform=platform.platform(), processor=platform.processor(), logical_cpus=os.cpu_count(),
                                   python=platform.python_version(),
                                   numpy=numpy.__version__, scipy=scipy.__version__, pandas=pandas.__version__, numba=numba.__version__),
                  numba_readiness=warm_numba(), runs=[])
    args.report.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    windows = {"stress": ("2021-01-11 20:00", "2021-01-11 21:00"),
               "week": ("2021-07-01", "2021-07-08"), "year": ("2021-01-01", "2022-01-01")}
    for name in args.window or ([] if args.search or args.worker_sweep else ["stress", "week"]):
        subset = profiles.slice(*windows[name])
        for policy in args.policy or ["minimum_energy", "progressive"]:
            accepts_policy = "shedding_policy" in {field.name for field in fields(SimulationConfig)}
            if not accepts_policy and policy != "minimum_energy":
                raise ValueError("The reference source supports only minimum-energy shedding")
            settings = SimulationConfig(grid_import_limit_kw=7500., grid_export_limit_kw=0.,
                                        reserve_fraction=args.reserve_percent / 100.,
                                        **({"shedding_policy": policy} if accepts_policy else {}))
            for selected in (None, battery) if name != "stress" and not args.no_bess_only else (None,):
                started = perf_counter()
                simulation = simulate_timeseries(network, subset, with_terminal_policy(settings, economics),
                                                 selected, dispatch if selected else None)
                wall_seconds = perf_counter() - started
                metrics = evaluate_results(simulation, economics, selected)
                bus_hours = hours = 0
                trace = sha256()
                for step in simulation.steps:
                    requested = step.requested_point.p_load_kw
                    served = step.operating_point.p_load_kw
                    verified = step.dispatch and step.dispatch.correction["status"] in ("not_needed", "verified")
                    outages = sum(request > 1e-6 and served[bus] <= max(1e-6, request * 1e-6)
                                  for bus, request in requested.items()) if verified else 0
                    bus_hours += outages
                    hours += outages > 0
                    numbers = [step.power_flow.slack_p_kw, *step.power_flow.voltage_mag_pu.values(), *served.values()]
                    trace.update(repr((step.feasible, [round(number, 7) for number in numbers])).encode())
                row = dict(window=name, policy=policy, bess_bus=selected.bus_id if selected else None,
                           settings=asdict(settings), hours=len(simulation.steps), feasible=metrics.feasible,
                           shed_mwh=metrics.load_shedding_energy_kwh / 1000., curtailment_mwh=metrics.curtailment_energy_kwh / 1000.,
                           full_bus_hours=bus_hours, outage_hours=hours, modeled_usd_per_year=metrics.annual_total_cost,
                           minimum_voltage=metrics.voltage_min_pu, max_export_kw=max(max(0., -step.power_flow.slack_p_kw) for step in simulation.steps),
                           failed_network_hours=sum(bool(step.dispatch.final.violations) for step in simulation.steps),
                           terminal_soc=simulation.final_bess_state.soc if selected else None,
                           physical_trace_sha256=trace.hexdigest(), wall_seconds=wall_seconds, timing=simulation.dispatch_timing)
                report["runs"].append(row)
                save()
                print(f"{name} | {policy} | {'B14' if selected else 'No BESS'} | {wall_seconds:.2f} s | {row['shed_mwh']:.4f} MWh shed | {bus_hours} bus-hours", flush=True)
                if args.dashboard is not None and len(report["runs"]) == 1:
                    from src.dashboard import regenerate_dashboard, write_run_metadata
                    from src.results import export_results
                    context = {"Network": f"{len(network.buses)}-bus radial feeder", "Clock": clock,
                               "Economic inputs": asdict(economics), "Simulation settings": asdict(settings),
                               "Dispatch timing": simulation.dispatch_timing}
                    started = perf_counter()
                    export_results(simulation, args.dashboard, metrics=metrics, context=context,
                                   input_snapshot={"profiles": subset, "workbook": inputs / "network.xlsx",
                                                   "metadata": {"clock": clock, "dt_hours": subset.dt_hours}})
                    write_run_metadata(args.dashboard, network, "simulation", context, settings)
                    html = regenerate_dashboard(args.dashboard)
                    report["dashboard"] = dict(html_bytes=html.stat().st_size, export_wall_seconds=perf_counter()-started)
                    save()
                    print(f"Offline dashboard and canonical exports saved under {html.parent}", flush=True)

    if args.search or args.worker_sweep:
        from src.optimizer import (BESSCandidate, BESSParameters, OptimizationBounds, OptimizerConfig,
                                                SimulationEvaluator, optimize)
        from src.single_bess_search import WindowEvaluator, annual_baseline, optimize_fast_verified

        year = profiles.slice(*windows["year"])
        settings = SimulationConfig(grid_import_limit_kw=7500., grid_export_limit_kw=0.,
                                    reserve_fraction=args.reserve_percent / 100.)
        evaluator = SimulationEvaluator(economics, BESSParameters(.90, .90, .20, 1., .50), dispatch, settings)
        config = OptimizerConfig(population_size=3, max_iterations=2, seed=42, workers=args.workers)
        bounds = OptimizationBounds((14, 30), (1250.,), (6250.,))
        if args.worker_sweep:
            selected = tuple(range(2, 14))
            choices = tuple(BESSCandidate(bus, 1250., 6250.) for bus in selected)
            scope = OptimizationBounds(selected, (1250.,), (6250.,))
            sample = (profiles.slice(*windows["week"]),)
            window_evaluator = WindowEvaluator(evaluator, len(year.timestamps))
            report["worker_sweep"] = []
            for workers in args.worker_sweep:
                sweep_config = OptimizerConfig(12, 1, seed=42, initial_candidates=choices, workers=workers)
                result = optimize(network, sample, scope, window_evaluator, sweep_config)
                wall = result.metadata["search_elapsed_seconds"]
                timings = [row.execution_metadata for row in result.evaluations]
                row = dict(workers=workers, elapsed_seconds=wall, candidate_count=len(timings),
                           candidates_per_second=len(timings) / wall,
                           candidate_cpu_seconds=sum(timing["candidate_cpu_seconds"] for timing in timings),
                           worker_processes=len({timing["worker_pid"] for timing in timings if "worker_pid" in timing}),
                           observed_scores=[row.objective if numpy.isfinite(row.objective) else None for row in result.evaluations])
                report["worker_sweep"].append(row)
                save()
                print(f"{workers} workers | {wall:.2f} s | {row['candidates_per_second']:.3f} candidates/s", flush=True)
        report["searches"] = []
        for mode in args.search or ():
            started = perf_counter()
            print(f"{mode} search started with {args.workers} requested workers", flush=True)
            if mode == "thorough":
                baseline, _, cache_hit = annual_baseline(network, year, evaluator, clock, None)
                optimization = optimize(network, year, bounds, evaluator, config)
                optimization.metadata["baseline_cache_hit"] = cache_hit
            else:
                optimization, baseline = optimize_fast_verified(network, year, bounds, evaluator, config, mode=mode,
                    clock=clock, stage=lambda message: print(message, flush=True))
            baseline_metrics = evaluate_results(baseline, economics)
            choose_bess = optimization.success and (not baseline_metrics.feasible or
                                                    optimization.best_objective < baseline_metrics.annual_total_cost)
            row = dict(mode=mode, workers=args.workers, seed=config.seed, hours=len(year.timestamps),
                       elapsed_seconds=perf_counter()-started, best_battery=asdict(optimization.best_candidate) if optimization.success else None,
                       best_battery_usd_per_year=optimization.best_objective if optimization.success else None,
                       best_battery_shed_kwh=optimization.metrics.load_shedding_energy_kwh if optimization.success else None,
                       no_bess_usd_per_year=baseline_metrics.annual_total_cost,
                       selected="battery" if choose_bess else "No BESS" if baseline_metrics.feasible else None,
                       metadata=optimization.metadata,
                       evaluations=[dict(candidate=asdict(item.candidate), feasible=item.feasible,
                                         annual_usd=item.objective if item.feasible else None, timing=item.execution_metadata)
                                    for item in optimization.evaluations])
            report["searches"].append(row)
            save()
            print(f"{mode} | {row['elapsed_seconds']:.1f} s | {row['selected']} | best battery {row['best_battery']}", flush=True)


if __name__ == "__main__":
    main()
