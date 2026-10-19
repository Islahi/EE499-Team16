"""Inspect an Excel network and optionally run its base-load snapshot."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.fbs import FBSConfig, run_fbs
from src.main import base_operating_point
from src.network_loader import load_network


def main():
    default_source = Path(__file__).resolve().parents[2] / "04_Research/Working_Data/Network_Data/IEEE_33Bus_Network_Data.xlsx"
    parser = argparse.ArgumentParser(description="Read a supported static network Excel workbook")
    parser.add_argument("path", type=Path, nargs="?", default=default_source)
    parser.add_argument("--format", choices=("auto", "project", "ieee33"), default="auto")
    parser.add_argument("--frequency-hz", type=float, help="Study frequency; mandatory for the IEEE33 source")
    parser.add_argument("--power-flow", action="store_true", help="Run base-load/rated-PV snapshot, not an hourly simulation")
    args = parser.parse_args()
    try:
        network = load_network(args.path, workbook_format=args.format, frequency_hz=args.frequency_hz)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f"Source: {args.path.resolve()}")
    print(f"Buses: {len(network.buses)}, in-service lines: {len(network.lines)}, slack: {network.slack_bus_id()}")
    print(f"Base: {network.base_power_kva:g} kVA, {network.buses[0].base_kv:g} kV; frequency: {network.frequency_hz:g} Hz")
    print(f"Base load: {sum(load.p_base_kw for load in network.loads):g} kW / "
          f"{sum(load.q_base_kvar for load in network.loads):g} kvar")
    print(f"PV units: {len(network.pv_units)}; none are invented when absent from the source.")
    print("Static network import only; no hourly profiles loaded and no diagram drawn.")
    if args.power_flow:
        flow = run_fbs(network, base_operating_point(network), FBSConfig())
        print(f"Snapshot: {flow.message}; converged: {flow.converged}")
        print(f"Voltage: {min(flow.voltage_mag_pu.values()):.6f} to {max(flow.voltage_mag_pu.values()):.6f} pu")
        print(f"Active losses: {flow.total_loss_p_kw:.6f} kW")
        print("Snapshot uses base loads/rated PV, not time-varying output. Convergence does not certify voltage/reserve feasibility.")
        if not flow.converged:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
