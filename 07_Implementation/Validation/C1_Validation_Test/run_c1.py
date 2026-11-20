"""EE499 Team 16 - C1: validate ALL static radial test networks.

Place this file beside src_accelerated/, Working_RDS/, and references/.
Run simply:  python run_c1.py
No ZIPs, command-line arguments, or changes to the original FBS implementation.
"""

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src_accelerated.network_loader import load_network
from src_accelerated.fbs import FBSConfig, OperatingPoint, run_fbs

ROOT = Path(__file__).resolve().parent
NETWORK_FOLDER = ROOT / "Working_RDS"
REFERENCE_FOLDER = ROOT / "references"
RESULT_FOLDER = ROOT / "C1_results"
PLOT_FOLDER = RESULT_FOLDER / "plots"

FREQUENCY_HZ = 60.0      # Workbook study input
MAX_ITERATIONS = 100
FBS_TOLERANCE = 1e-8
VOLTAGE_LIMIT = 0.01     # Maximum absolute error, pu
LOSS_LIMIT_PERCENT = 1.0  # Provisional review target


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def save_csv(path, data):
    if data:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)


def num(x):
    return float(x) if x not in (None, "") else None


def static_loads(network):
    """Paper's nominal static loads, with all PV/BESS explicitly set to zero."""
    ids = [bus.bus_id for bus in network.buses]
    p = {i: 0.0 for i in ids}
    q = p.copy()
    for load in network.loads:
        p[load.bus_id] += load.p_base_kw
        q[load.bus_id] += load.q_base_kvar
    zero = {i: 0.0 for i in ids}
    return OperatingPoint(p, q, zero.copy(), zero.copy(), zero.copy(), zero.copy())


def show(x, decimals=4):
    return "-" if x is None else f"{x:.{decimals}f}"


def plot_voltage_profile(network_name, fbs_map, paper_map, out_path):
    bus_ids = sorted(fbs_map)
    fbs_vals = [fbs_map[b] for b in bus_ids]
    paper_bus_ids = [b for b in bus_ids if paper_map.get(b) is not None]
    paper_vals = [paper_map[b] for b in paper_bus_ids]

    plt.figure(figsize=(10, 5))
    plt.plot(bus_ids, fbs_vals, marker="o", linewidth=1.5, markersize=3, label="FBS")
    if paper_bus_ids:
        plt.plot(paper_bus_ids, paper_vals, marker="s", linestyle="--", linewidth=1.2, markersize=3, label="Published")
    plt.xlabel("Bus number")
    plt.ylabel("Voltage magnitude (pu)")
    plt.title(f"Voltage profile - {network_name}")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=180)
    plt.close()



def main():
    RESULT_FOLDER.mkdir(exist_ok=True)
    PLOT_FOLDER.mkdir(exist_ok=True)
    catalog = {r["workbook"]: r for r in csv_rows(REFERENCE_FOLDER / "workbook_to_paper_case_catalog.csv")}
    paper_cases = {int(r["table"]): r for r in csv_rows(REFERENCE_FOLDER / "paper_case_references.csv")}
    paper_lines = {}
    for line in csv_rows(REFERENCE_FOLDER / "paper_branch_references.csv"):
        paper_lines.setdefault(int(line["table"]), []).append(line)

    results, buses = [], []
    for file in sorted(NETWORK_FOLDER.glob("*.xlsx")):
        print("Testing:", file.name)
        table_text = catalog.get(file.name, {}).get("paper_table", "")
        table = int(table_text) if table_text else None
        paper = paper_cases.get(table)
        n = load_network(file, workbook_format="auto", frequency_hz=FREQUENCY_HZ)
        point = static_loads(n)
        fbs = run_fbs(n, point, FBSConfig(
            max_iterations=MAX_ITERATIONS, voltage_tolerance_pu=FBS_TOLERANCE,
            backend="python"))
        weakest = min(fbs.voltage_mag_pu, key=fbs.voltage_mag_pu.get)

        # Read the paper's tabulated voltage and impedance for each bus/branch.
        refs = paper_lines.get(table, [])
        ref_by_bus = {int(r["bus_to"]): r for r in refs}
        ref_by_line = {frozenset((int(r["bus_from"]), int(r["bus_to"]))): r for r in refs}
        errors = []
        paper_voltage_map = {}
        for bus, voltage in sorted(fbs.voltage_mag_pu.items()):
            ref = ref_by_bus.get(bus)
            v_paper = num(ref["v_pqsum_pu"]) if ref else None
            error = abs(voltage - v_paper) if v_paper is not None else None
            paper_voltage_map[bus] = v_paper
            buses.append({"network": file.name, "bus_id": bus,
                          "fbs_voltage_pu": voltage, "paper_voltage_pu": v_paper,
                          "absolute_error_pu": error})
            if error is not None:
                errors.append(error)

        plot_voltage_profile(file.stem, fbs.voltage_mag_pu, paper_voltage_map, PLOT_FOLDER / f"{file.stem}_voltage_profile.png")
        

        # Independent input check: prevents a modified workbook receiving a
        # clean reference pass merely because its voltages happen to be close.
        mismatch = 0
        if paper:
            z_base = n.buses[0].base_kv ** 2 / (n.base_power_kva / 1000)
            for line in n.lines:
                ref = ref_by_line.get(frozenset((line.from_bus, line.to_bus)))
                if (ref is None or
                    abs(line.r_ohm / z_base - float(ref["r_pu_reported"])) > 0.0002 or
                    abs(line.x_ohm / z_base - float(ref["x_pu_reported"])) > 0.0002):
                    mismatch += 1

        row = {
            "network": file.name,
            "paper_table": table,
            "paper_pages": paper["pdf_pages"] if paper else None,
            "paper_sbase_printed": num(paper["published_sbase_printed"]) if paper else None,
            "fbs_sbase_mva": n.base_power_kva / 1000,
            "paper_vbase_kv": num(paper["base_kv"]) if paper else None,
            "fbs_vbase_kv": n.buses[0].base_kv,
            "paper_load_p_kw": num(paper["p_load_kw"]) if paper else None,
            "fbs_load_p_kw": sum(point.p_load_kw.values()),
            "paper_load_q_kvar": num(paper["q_load_kvar"]) if paper else None,
            "fbs_load_q_kvar": sum(point.q_load_kvar.values()),
            "paper_loss_p_kw": num(paper["p_loss_kw"]) if paper else None,
            "fbs_loss_p_kw": fbs.total_loss_p_kw,
            "paper_loss_q_kvar": num(paper["q_loss_kvar"]) if paper else None,
            "fbs_loss_q_kvar": fbs.total_loss_q_kvar,
            "paper_min_voltage_pu": num(paper["v_min_pu"]) if paper else None,
            "fbs_min_voltage_pu": fbs.voltage_mag_pu[weakest],
            "paper_weakest_bus": int(paper["weakest_bus"]) if paper else None,
            "fbs_weakest_bus": weakest,
            "bus_count": len(n.buses),
            "converged": fbs.converged,
            "iterations": fbs.iterations,
            "max_voltage_error_pu": max(errors) if errors else None,
            "impedance_mismatch_count": mismatch if paper else None,
            "p_loss_error_percent": None,
            "status": None,
        }
        if paper and table != 18:  # 70-bus paper losses combine two feeders.
            row["p_loss_error_percent"] = 100 * abs(
                row["fbs_loss_p_kw"] - row["paper_loss_p_kw"]) / row["paper_loss_p_kw"]

        if not fbs.converged:
            row["status"] = "FAIL: did not converge"
        elif not paper:
            row["status"] = "NO PAPER REFERENCE"
        elif mismatch or abs(row["fbs_vbase_kv"] - row["paper_vbase_kv"]) > 0.001:
            row["status"] = "REVIEW: network data differ"
        elif len(errors) != len(n.buses) - 1:
            row["status"] = "REVIEW: incomplete voltage references"
        elif max(errors) > VOLTAGE_LIMIT:
            row["status"] = "FAIL: voltage error"
        elif table == 18:
            row["status"] = "FEEDER: see combined result"
        elif row["p_loss_error_percent"] > LOSS_LIMIT_PERCENT:
            row["status"] = "REVIEW: power loss"
        else:
            row["status"] = "PASS"
        results.append(row)

    # Table 18 in the publication has TWO substations (split into two XLSX).
    # The paper's total loads and losses must be compared with both feeder sums.
    pair = [r for r in results if r["paper_table"] == 18]
    if len(pair) == 2:
        whole = {key: None for key in results[0]}
        whole.update({"network": "T18_COMBINED (not a separate workbook)",
                      "paper_table": 18, "paper_pages": paper_cases[18]["pdf_pages"],
                      "bus_count": sum(r["bus_count"] for r in pair),
                      "converged": all(r["converged"] for r in pair),
                      "iterations": max(r["iterations"] for r in pair),
                      "max_voltage_error_pu": max(r["max_voltage_error_pu"] for r in pair),
                      "impedance_mismatch_count": sum(r["impedance_mismatch_count"] for r in pair)})
        for name in ("sbase_mva", "vbase_kv"):
            whole["fbs_" + name] = pair[0]["fbs_" + name]
        for name in ("load_p_kw", "load_q_kvar", "loss_p_kw", "loss_q_kvar"):
            whole["paper_" + name] = pair[0]["paper_" + name]
            whole["fbs_" + name] = sum(r["fbs_" + name] for r in pair)
        for name in ("sbase_printed", "vbase_kv", "min_voltage_pu", "weakest_bus"):
            whole["paper_" + name] = pair[0]["paper_" + name]
        weakest_feeder = min(pair, key=lambda r: r["fbs_min_voltage_pu"])
        whole["fbs_min_voltage_pu"] = weakest_feeder["fbs_min_voltage_pu"]
        whole["fbs_weakest_bus"] = weakest_feeder["fbs_weakest_bus"]
        whole["p_loss_error_percent"] = 100 * abs(
            whole["fbs_loss_p_kw"] - whole["paper_loss_p_kw"]) / whole["paper_loss_p_kw"]
        whole["status"] = "PASS" if (whole["converged"] and
            all(r["status"] == "FEEDER: see combined result" for r in pair) and
            whole["p_loss_error_percent"] <= LOSS_LIMIT_PERCENT) else "REVIEW"
        results.append(whole)

    save_csv(RESULT_FOLDER / "c1_summary.csv", results)
    save_csv(RESULT_FOLDER / "c1_bus_voltages.csv", buses)
    

    # A human-readable report matching the published summary shown in the PDF.
    lines = []
    for r in results:
        lines += ["=" * 72, f"{r['network']}  [Table {r['paper_table'] or '-'}]",
                  "                                   Published          Project FBS"]
        for label, suffix, digits in (
            ("S_base (paper printed / MVA)", "sbase_printed", 2),
            ("V_base (kV)", "vbase_kv", 3),
            ("Total active power load (kW)", "load_p_kw", 4),
            ("Total reactive power load (kVAr)", "load_q_kvar", 4),
            ("Total active power losses (kW)", "loss_p_kw", 4),
            ("Total reactive power losses (kVAr)", "loss_q_kvar", 4),
            ("Minimum voltage (pu)", "min_voltage_pu", 6)):
            model_key = "fbs_sbase_mva" if suffix == "sbase_printed" else "fbs_" + suffix
            lines.append(f"{label:<36}{show(r.get('paper_' + suffix), digits):>12} {show(r.get(model_key), digits):>20}")
        lines += [f"Weakest bus: published={r['paper_weakest_bus']}, FBS={r['fbs_weakest_bus']}",
                  f"FBS iterations: {r['iterations']} (not provided by the paper)",
                  f"Maximum bus voltage error: {show(r['max_voltage_error_pu'], 7)} pu",
                  f"Active power loss error: {show(r['p_loss_error_percent'], 4)} %",
                  f"Input impedance mismatches: {r['impedance_mismatch_count']}",
                  f"Result: {r['status']}"]
        if r["paper_table"] == 18:
            lines.append("NOTE: Table 18 reference loads/losses apply to the combined two-feeder system.")
    (RESULT_FOLDER / "c1_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\nTested {len(results) - (len(pair) == 2)} workbooks. Results: {RESULT_FOLDER}")


if __name__ == "__main__":
    main()
