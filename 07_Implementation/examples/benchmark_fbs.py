"""Compare reference and optional FBS backends on one radial workbook."""
import argparse
from pathlib import Path
import statistics
import sys
from time import perf_counter


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src_accelerated.fbs import FBSConfig, OperatingPoint, backend_available, run_fbs
from src_accelerated.network_loader import load_network


def base_operating_point(network):
    """Build the benchmark point from installed base loads and rated PV."""
    bus_ids = [bus.bus_id for bus in network.buses]
    loads = network.loads_by_bus()
    pv_units = network.pv_by_bus()
    zeros = {bus_id: 0.0 for bus_id in bus_ids}
    return OperatingPoint(
        {bus_id: sum(load.p_base_kw for load in loads[bus_id]) for bus_id in bus_ids},
        {bus_id: sum(load.q_base_kvar for load in loads[bus_id]) for bus_id in bus_ids},
        {bus_id: sum(unit.p_rated_kw for unit in pv_units[bus_id]) for bus_id in bus_ids},
        zeros.copy(), zeros.copy(), zeros.copy(),
    )


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("network", type=Path)
    parser.add_argument("--format", choices=("auto", "project", "ieee33"), default="auto")
    parser.add_argument("--frequency-hz", type=float, default=60)
    parser.add_argument("--runs", type=int, default=100)
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    if arguments.runs < 1:
        raise ValueError("--runs must be positive")
    network = load_network(
        arguments.network,
        workbook_format=arguments.format,
        frequency_hz=arguments.frequency_hz,
    )
    operating_point = base_operating_point(network)
    reference = run_fbs(network, operating_point, FBSConfig())
    print(f"Reference converged={reference.converged}; loss={reference.total_loss_p_kw:.9g} kW")
    for backend in ("python", "numpy", "numba", "gpu"):
        available, reason = backend_available(backend)
        if not available:
            print(f"{backend:>6}: skipped ({reason})")
            continue
        # This untimed call includes JIT compilation and CUDA initialization.
        warmup = run_fbs(network, operating_point, FBSConfig(backend=backend))
        if abs(warmup.total_loss_p_kw - reference.total_loss_p_kw) > 1e-7:
            raise RuntimeError(f"{backend} result does not match the Python reference")
        durations = []
        for _ in range(arguments.runs):
            started = perf_counter()
            run_fbs(network, operating_point, FBSConfig(backend=backend))
            durations.append(perf_counter() - started)
        print(
            f"{backend:>6}: median {statistics.median(durations) * 1000:.3f} ms; "
            f"minimum {min(durations) * 1000:.3f} ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
