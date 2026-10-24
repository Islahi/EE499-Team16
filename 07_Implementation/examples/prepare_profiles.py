"""Prepare real-weather PV and synthetic demand; optionally check the simulator."""
import argparse
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data_loader import ProfileData
from src.load_generator import LoadGenerationConfig, generate_load_profile
from src.metrics import EconomicConfig, evaluate_results
from src.network_loader import load_network
from src.network_model import PVUnit
from src.pv_model import PVModelConfig, make_pv_profile, read_irradiance
from src.results import export_results, format_summary
from src.simulation import SimulationConfig, simulate_timeseries


REPO = Path(__file__).resolve().parents[2]
WEATHER = REPO / "04_Research/Working_Data/Jeddah_Weather_PV"


def main():
    parser = argparse.ArgumentParser(description="Prepare PV power and synthetic load CSVs; no supplier catalog needed")
    parser.add_argument("--network", type=Path, default=REPO / "04_Research/Working_Data/Network_Data/Working_RDS/IEEE_33Bus_Network_Data.xlsx")
    parser.add_argument("--frequency-hz", type=float, required=True, help="Explicit network study frequency")
    parser.add_argument("--source", choices=("open_meteo", "nasa_power", "prepared"), default="open_meteo")
    parser.add_argument("--irradiance-file", type=Path, help="Defaults to the repository weather file for the chosen provider")
    parser.add_argument("--start", default="2024-01-01T00:00:00", help="Start in the source clock; inclusive")
    duration = parser.add_mutually_exclusive_group()
    duration.add_argument("--hours", type=int, help="Short check or explicit hourly horizon (minimum 2)")
    duration.add_argument("--months", type=int, help="Calendar months; defaults to 3 when --hours is absent")
    parser.add_argument("--pv-bus", type=int, required=True, help="Bus receiving the additional study PV installation")
    parser.add_argument("--pv-rating-kw", type=float, required=True, help="Study array rating; not an inferred supplier rating")
    parser.add_argument("--critical-irradiance", type=float, required=True, help="Rc in W/m²; explicit model input")
    parser.add_argument("--standard-irradiance", type=float, default=1000, help="Rstd in W/m²")
    parser.add_argument("--seed", type=int, default=42, help="Synthetic-load seed")
    parser.add_argument("--output-dir", type=Path, required=True, help="New output folder; existing files are never overwritten")
    parser.add_argument("--simulate", action="store_true", help="Also run/export a no-BESS integration check")
    args = parser.parse_args()

    try:
        if args.output_dir.exists():
            raise ValueError("--output-dir must be a new directory")
        if args.source == "prepared" and args.irradiance_file is None:
            raise ValueError("--irradiance-file is required for prepared data")
        source_path = args.irradiance_file
        if source_path is None:
            name = "OpenMeteo_Jeddah_2024_Hourly.csv" if args.source == "open_meteo" else "NASA_POWER_Jeddah_2024_Hourly.csv"
            source_path = WEATHER / name
        model = PVModelConfig(args.critical_irradiance, args.standard_irradiance)
        load_settings = LoadGenerationConfig(seed=args.seed)
        network = load_network(args.network, frequency_hz=args.frequency_hz)
        study_pv = PVUnit("user_study_pv", args.pv_bus, args.pv_rating_kw)
        network = replace(network, pv_units=[*network.pv_units, study_pv])
        network.validate()
        weather = read_irradiance(source_path, source=args.source)
        start = pd.Timestamp(args.start)
        if pd.isna(start) or start.tzinfo is not None:
            raise ValueError("--start must be a timezone-naive timestamp in the source clock")
        if args.hours is not None:
            if args.hours < 2:
                raise ValueError("--hours must be at least 2")
            end = start + pd.Timedelta(hours=args.hours)
        else:
            months = args.months if args.months is not None else 3
            if months < 1:
                raise ValueError("--months must be positive")
            end = start + pd.DateOffset(months=months)
        selected = weather.loc[(weather.timestamp >= start) & (weather.timestamp < end)].reset_index(drop=True)
        if (len(selected) < 2 or selected.timestamp.iloc[0] != start
                or selected.timestamp.iloc[-1] != end - pd.Timedelta(hours=1)):
            raise ValueError("The source does not cover the complete requested hourly interval")
        pv = make_pv_profile(network, selected, model)
        demand = generate_load_profile(network, selected.timestamp, load_settings)
        manifest = {
            "irradiance_file": str(source_path.resolve()),
            "irradiance_sha256": sha256(source_path.read_bytes()).hexdigest(),
            "source": args.source,
            "source_clock": {
                "nasa_power": "NASA LST in repository file; verify custom files; no civil-time conversion",
                "open_meteo": "Asia/Riyadh in repository file; verify custom files; no timezone conversion",
                "prepared": "Caller-prepared common clock; no timezone conversion",
            }[args.source],
            "network_file": str(args.network.resolve()),
            "network_sha256": sha256(args.network.read_bytes()).hexdigest(),
            "frequency_hz": args.frequency_hz,
            "start_inclusive": start.isoformat(), "end_exclusive": end.isoformat(),
            "hours": len(selected), "additional_study_pv": asdict(study_pv),
            "all_pv_units": [asdict(unit) for unit in network.pv_units],
            "pv_model": asdict(model), "load_generation": asdict(load_settings),
            "pv_notes": pv.attrs, "load_notes": demand.attrs,
            "limitations": ["GHI used as a resource proxy; no tilt/temperature/inverter losses",
                            "Synthetic demand, not measured Jeddah demand; no seasonal or temporal correlation",
                            "Table periods 1-24 mapped to clock hours 00-23; shared bus multiplier"],
        }
        args.output_dir.mkdir(parents=True, exist_ok=False)
        load_path = args.output_dir / "load_profile.csv"
        pv_path = args.output_dir / "pv_profile.csv"
        demand.to_csv(load_path, index=False, encoding="utf-8-sig", mode="x")
        pv.to_csv(pv_path, index=False, encoding="utf-8-sig", mode="x")
        # Verify the actual saved CSV pair through the unchanged loader.
        profiles = ProfileData(csv_load=load_path, csv_pv=pv_path)
        with (args.output_dir / "preparation.json").open("x", encoding="utf-8") as output:
            json.dump(manifest, output, indent=2, ensure_ascii=False, allow_nan=False)
        print(f"Prepared {len(profiles.timestamps)} hourly steps in {args.output_dir.resolve()}")
        print("Demand: synthetic normal samples, shared bus multiplier; NOT measured local demand.")
        print("PV: supplied study ratings, piecewise conversion of weather GHI; no supplier data inferred.")
        print("Network and irradiance source files are unchanged. Settings/provenance: preparation.json")
        if args.simulate:
            result = simulate_timeseries(network, profiles, SimulationConfig())
            metrics = evaluate_results(result, EconomicConfig()) if result.completed and result.converged else None
            context = {"Input preparation": "preparation.json", "Demand": "Literature-based synthetic demand; not measured",
                       "Study": "No-BESS integration check; not storage sizing or independent validation"}
            print(format_summary(result, metrics=metrics, context=context))
            export_results(result, args.output_dir / "simulation", metrics=metrics, context=context)
            if not result.completed or not result.converged:
                raise SystemExit(1)
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
