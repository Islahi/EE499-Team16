"""
run_simulation.py
Driver for the 5-bus development case.

1. Solves one operating point (full load, full PV) with fbs.py and verifies it.
2. Runs a 24 hour loop, scaling load and PV each hour, calling the same solver.
3. Saves results to CSV and makes the charts used in the report.

The hourly load/PV multipliers are made-up development values, not measured data.
"""
import copy
import csv
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from network_model import build_default_5bus_network
from fbs import run_fbs

OUT = "/home/claude/w/"

LOAD_MULT = [0.55, 0.50, 0.48, 0.47, 0.50, 0.60, 0.75, 0.90, 0.95, 0.90, 0.88, 0.90,
             0.92, 0.90, 0.88, 0.90, 0.95, 1.10, 1.20, 1.15, 1.00, 0.85, 0.70, 0.60]
PV_MULT = [0, 0, 0, 0, 0, 0.02, 0.15, 0.35, 0.55, 0.75, 0.90, 1.00,
           1.00, 0.92, 0.78, 0.58, 0.35, 0.12, 0, 0, 0, 0, 0, 0]


def scaled_network(load_k, pv_k):
    net = copy.deepcopy(build_default_5bus_network())
    for ld in net.loads:
        ld.p_pu *= load_k
        ld.q_pu *= load_k
    for pv in net.pv_units:
        pv.p_pu *= pv_k
    return net


def check_power_balance(net, res):
    """substation P  -  (net load P + losses P)  in kW"""
    kw = net.base_mva * 1000
    slack_p = res.branch_results[0].s_sending_pu.real * kw
    net_load = sum(net.net_bus_injection_pu(b).real for b in net.buses) * kw
    loss = res.total_p_loss_pu * kw
    return slack_p, net_load, loss, slack_p - net_load - loss


def check_branch_loss(net, res):
    """recompute |I|^2 * R by hand for every branch and compare (kW)"""
    kw = net.base_mva * 1000
    out = []
    for br in res.branch_results:
        ln = next(l for l in net.lines if l.from_bus == br.from_bus and l.to_bus == br.to_bus)
        hand = abs(br.i_pu) ** 2 * ln.r_pu * kw
        out.append((br.from_bus, br.to_bus, hand, br.p_loss_pu * kw))
    return out


def check_voltage_drop(net, res):
    """rough check on the first branch: dV ~ (R*P + X*Q)/V1"""
    ln = net.lines[0]
    s = res.branch_results[0].s_sending_pu
    dv = (ln.r_pu * s.real + ln.x_pu * s.imag) / 1.0
    return 1.0 - dv, res.bus_results[2].v_mag_pu


if __name__ == "__main__":
    # -------- one time step: full load, full PV --------
    net = scaled_network(1.0, 1.0)
    res = run_fbs(net, tol_pu=1e-6, max_iter=100)
    print(res.summary())
    print()
    print("power balance (slack, net load, loss, error):", check_power_balance(net, res))
    print("branch loss hand check:", check_branch_loss(net, res))
    print("voltage drop estimate vs solver (bus 2):", check_voltage_drop(net, res))

    # tolerance trial
    for tol in (1e-3, 1e-6, 1e-9, 1e-12):
        r = run_fbs(scaled_network(1.0, 1.0), tol_pu=tol, max_iter=200)
        print(f"tol {tol:g}: iterations {r.iterations}, V4 = {r.bus_results[4].v_mag_pu:.8f}, "
              f"loss = {r.total_p_loss_pu * 1000:.6f} kW")

    # -------- hourly loop --------
    rows = []
    for h in range(24):
        n = scaled_network(LOAD_MULT[h], PV_MULT[h])
        r = run_fbs(n, tol_pu=1e-6, max_iter=100)
        slack_p, net_load, loss, err = check_power_balance(n, r)
        vmin_bus = min(r.bus_results.values(), key=lambda b: b.v_mag_pu)
        gross = sum(l.p_pu for l in n.loads) * 1000
        pv_kw = sum(p.p_pu for p in n.pv_units) * 1000
        rows.append(dict(hour=h, load_kw=gross, pv_kw=pv_kw, substation_kw=slack_p,
                         loss_kw=loss, vmin_pu=vmin_bus.v_mag_pu, vmin_bus=vmin_bus.bus_id,
                         iterations=r.iterations, converged=r.converged, balance_err_kw=err))

    with open(OUT + "hourly_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    hrs = [r["hour"] for r in rows]
    GREEN = "#1a6b52"

    # chart 1: voltage profile for the single operating point
    fig, ax = plt.subplots(figsize=(6.2, 3.0), dpi=200)
    ids = sorted(res.bus_results)
    vals = [res.bus_results[i].v_mag_pu for i in ids]
    bars = ax.bar([f"Bus {i}" for i in ids], vals, color=GREEN, width=0.55)
    ax.set_ylim(0.9, 1.02)
    ax.axhline(0.95, color="#b03a2e", linestyle="--", linewidth=0.8)
    ax.text(4.45, 0.952, "0.95 limit", fontsize=7, color="#b03a2e", ha="right")
    ax.set_ylabel("Voltage (p.u.)")
    ax.set_title("One operating point: bus voltages")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.003, f"{v:.4f}", ha="center", fontsize=7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(OUT + "fig_voltage_profile.png")
    plt.close()

    # chart 2: load and PV
    fig, ax = plt.subplots(figsize=(6.2, 2.8), dpi=200)
    ax.plot(hrs, [r["load_kw"] for r in rows], color=GREEN, label="Total load (kW)")
    ax.plot(hrs, [r["pv_kw"] for r in rows], color="#d68910", label="PV output (kW)")
    ax.set_xlabel("Hour")
    ax.set_ylabel("kW")
    ax.set_xticks(range(0, 24, 3))
    ax.legend(fontsize=7, frameon=False)
    ax.set_title("Hourly load and PV input")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(OUT + "fig_inputs.png")
    plt.close()

    # chart 3: min voltage by hour
    fig, ax = plt.subplots(figsize=(6.2, 2.8), dpi=200)
    ax.plot(hrs, [r["vmin_pu"] for r in rows], color=GREEN, marker="o", markersize=3)
    ax.axhline(0.95, color="#b03a2e", linestyle="--", linewidth=0.8)
    ax.text(0.2, 0.9515, "0.95 limit", fontsize=7, color="#b03a2e")
    ax.set_xlabel("Hour")
    ax.set_ylabel("Lowest bus voltage (p.u.)")
    ax.set_xticks(range(0, 24, 3))
    ax.set_title("Lowest voltage in the network each hour (always Bus 4)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(OUT + "fig_vmin.png")
    plt.close()

    # chart 4: losses by hour
    fig, ax = plt.subplots(figsize=(6.2, 2.8), dpi=200)
    ax.bar(hrs, [r["loss_kw"] for r in rows], color=GREEN, width=0.7)
    ax.set_xlabel("Hour")
    ax.set_ylabel("Loss (kW)")
    ax.set_xticks(range(0, 24, 3))
    ax.set_title("Total line losses each hour")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(OUT + "fig_losses.png")
    plt.close()

    print()
    print("all hours converged:", all(r["converged"] for r in rows))
    print("max |balance error| kW:", max(abs(r["balance_err_kw"]) for r in rows))
    print("daily substation kWh:", round(sum(r["substation_kw"] for r in rows), 1),
          "daily loss kWh:", round(sum(r["loss_kw"] for r in rows), 1))
    worst = min(rows, key=lambda r: r["vmin_pu"])
    print("worst hour:", worst["hour"], worst["vmin_pu"], "loss", worst["loss_kw"])
    print("hours below 0.95:", [r["hour"] for r in rows if r["vmin_pu"] < 0.95])
