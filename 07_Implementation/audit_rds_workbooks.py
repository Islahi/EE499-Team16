"""Audit research RDS workbooks with the stable importer and FBS solver."""
import csv
import sys
from pathlib import Path


IMPLEMENTATION = Path(__file__).resolve().parent
REPOSITORY = IMPLEMENTATION.parent
sys.path.insert(0, str(IMPLEMENTATION))

from src_accelerated.fbs import FBSConfig, OperatingPoint, run_fbs
from src_accelerated.network_loader import load_network


def base_operating_point(network):
    bus_ids = [bus.bus_id for bus in network.buses]
    p_load = {bus_id: 0.0 for bus_id in bus_ids}
    q_load = {bus_id: 0.0 for bus_id in bus_ids}
    p_pv = {bus_id: 0.0 for bus_id in bus_ids}
    for load in network.loads:
        p_load[load.bus_id] += load.p_base_kw
        q_load[load.bus_id] += load.q_base_kvar
    for pv in network.pv_units:
        p_pv[pv.bus_id] += pv.p_rated_kw
    zeros = {bus_id: 0.0 for bus_id in bus_ids}
    return OperatingPoint(p_load, q_load, p_pv, zeros.copy(), zeros.copy(), zeros.copy())


def main():
    folder = REPOSITORY / "04_Research" / "Working_Data" / "Network_Data"
    output = IMPLEMENTATION / "rds_workbook_audit.csv"
    rows = []
    for path in sorted(folder.rglob("*.xlsx")):
        row = {"file": str(path.relative_to(folder)), "status": "NOT WORKING", "detail": ""}
        try:
            network = load_network(path, workbook_format="auto", frequency_hz=60.0)
            result = run_fbs(network, base_operating_point(network), FBSConfig(backend="python"))
            voltages = result.voltage_mag_pu
            min_bus = min(voltages, key=voltages.get)
            voltage_ok = all(0.95 <= value <= 1.05 for value in voltages.values())
            row.update({
                "status": "WORKING" if result.converged else "FBS FAILED",
                "buses": len(network.buses),
                "lines": len(network.lines),
                "loads": len(network.loads),
                "iterations": result.iterations,
                "min_voltage_pu": f"{voltages[min_bus]:.6f}",
                "min_voltage_bus": min_bus,
                "loss_kw": f"{result.total_loss_p_kw:.6f}",
                "voltage_0.95_to_1.05": "PASS" if voltage_ok else "FAIL",
                "detail": result.message,
            })
        except Exception as error:
            row["detail"] = f"{type(error).__name__}: {error}"
        rows.append(row)
    fields = ["file", "status", "buses", "lines", "loads", "iterations",
              "min_voltage_pu", "min_voltage_bus", "loss_kw",
              "voltage_0.95_to_1.05", "detail"]
    with output.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print("\t".join(str(row.get(field, "")) for field in fields))
    print(f"AUDIT_FILE\t{output}")


if __name__ == "__main__":
    main()
