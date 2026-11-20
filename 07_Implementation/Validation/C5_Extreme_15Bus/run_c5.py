"""EE499 C5: System 1, all non-slack buses, strict-voltage validation.

Edit c5_settings.py. Run: python run_c5.py
Directly imports unchanged src_accelerated modules from the project.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
import csv
import hashlib
import json
import platform
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import c5_settings as S
from prepare_c5_inputs import prepare_inputs
from plot_extreme_profiles import main as plot_extreme_inputs
from plot_candidate_results import main as plot_candidate_results
from src_accelerated.data_loader import ProfileData
from src_accelerated.metrics import EconomicConfig, evaluate_results
from src_accelerated.network_loader import load_network
from src_accelerated.network_model import PVUnit
from src_accelerated.optimizer import (
    BESSParameters, BESSCandidate, OptimizationBounds, OptimizerConfig,
    SimulationEvaluator, exhaustive_search, genetic_optimize, optimize,
)
from src_accelerated.simulation import GridAwareDispatchPolicy, SimulationConfig, simulate_timeseries

ROOT = Path(__file__).resolve().parent
INPUTS = ROOT / "inputs"
RESULTS = ROOT / "C5_results"
NETWORK = ROOT / "T04_15-Bus_System_1.xlsx"


def write_csv(filename: str, rows: list[dict]) -> None:
    if not rows:
        return
    with (RESULTS / filename).open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def values(candidate):
    if candidate is None:
        return {"bess_bus": None, "bess_power_kw": None, "bess_capacity_kwh": None}
    return {"bess_bus": candidate.bus_id,
            "bess_power_kw": candidate.power_rating_kw,
            "bess_capacity_kwh": candidate.energy_capacity_kwh}


@dataclass(frozen=True)
class ScheduledGridShiftDispatch:
    """C5 test policy: charge from grid at specified clock hours, discharge at peak.

    Uses the selected candidate's power rating. This is NOT a solar-surplus
    or price-optimizing policy; it is a controllable battery-cycling experiment.
    BESS SOC, efficiency and power constraints remain enforced by step_bess.
    """
    battery_power_rating_kw: float

    def __call__(self, index, profile, state):
        hour = pd.Timestamp(profile.timestamp).hour
        if hour in S.CHARGE_HOURS:
            return -self.battery_power_rating_kw * S.CHARGE_POWER_FRACTION
        if hour in S.DISCHARGE_HOURS:
            return self.battery_power_rating_kw * S.DISCHARGE_POWER_FRACTION
        return 0.0


def policy_for(candidate):
    if S.DISPATCH_MODE == "grid_aware":
        return GridAwareDispatchPolicy(import_limit_kw=S.GRID_IMPORT_LIMIT_KW,
                                       export_limit_kw=S.GRID_EXPORT_LIMIT_KW)
    if S.DISPATCH_MODE == "scheduled":
        return ScheduledGridShiftDispatch(candidate.power_rating_kw)
    raise ValueError("DISPATCH_MODE must be 'scheduled' or 'grid_aware'")


@dataclass
class CandidateAwareEvaluator:
    """Delegate each candidate to the ORIGINAL project's SimulationEvaluator."""
    economics: EconomicConfig
    battery: BESSParameters
    config: SimulationConfig

    def __call__(self, network, profiles, candidate):
        return SimulationEvaluator(self.economics, self.battery, policy_for(candidate),
                                   self.config)(network, profiles, candidate)


@dataclass
class CatalogLookupEvaluator:
    """Deterministic objective lookup precomputed by original physical simulator.

    This speeds monthly validation; DO NOT interpret GA/GWO runtime measured
    here as wall-clock runtime of a full physical simulation search.
    """
    evaluations: dict

    def __call__(self, network, profiles, candidate):
        return self.evaluations[candidate]


def summary_row(name, simulation, metrics, candidate):
    if metrics is None:
        return {"case":name, **values(candidate), "completed":simulation.completed,
                "converged":simulation.converged, "feasible":simulation.feasible,
                "message":simulation.message}
    return {
        "case":name, **values(candidate), "completed":simulation.completed,
        "converged":simulation.converged, "feasible":simulation.feasible,
        "duration_hours":metrics.duration_hours,
        "voltage_min_pu":metrics.voltage_min_pu, "voltage_max_pu":metrics.voltage_max_pu,
        "voltage_violation_hours":metrics.voltage_violation_hours,
        "voltage_violation_bus_hours":metrics.voltage_violation_bus_hours,
        "voltage_max_abs_deviation_from_1_pu":max(abs(metrics.voltage_min_pu-1),abs(metrics.voltage_max_pu-1)),
        "line_loss_energy_kwh":metrics.loss_energy_kwh,
        "requested_load_kwh":metrics.requested_load_energy_kwh,
        "served_load_kwh":metrics.served_load_energy_kwh,
        "available_pv_kwh":metrics.available_pv_energy_kwh,
        "utilized_pv_kwh":metrics.pv_generation_energy_kwh,
        "grid_import_kwh":metrics.grid_import_energy_kwh,
        "peak_grid_import_kw":metrics.peak_grid_import_kw,
        "grid_export_kwh":metrics.grid_export_energy_kwh,
        "pv_curtailment_kwh":metrics.curtailment_energy_kwh,
        "load_shedding_kwh":metrics.load_shedding_energy_kwh,
        "bess_charge_kwh":metrics.bess_charge_energy_kwh,
        "bess_discharge_kwh":metrics.bess_discharge_energy_kwh,
        "bess_soc_min":metrics.bess_soc_min, "bess_soc_max":metrics.bess_soc_max,
        "annualized_bess_cost_usd":metrics.annualized_bess_cost,
        "annual_grid_cost_usd":metrics.annual_grid_cost,
        "annual_shedding_cost_usd":metrics.annual_shedding_cost,
        "annual_curtailment_cost_usd":metrics.annual_curtailment_cost,
        "annual_terminal_energy_cost_usd":metrics.annual_terminal_energy_cost,
        "annual_total_cost_usd":metrics.annual_total_cost,
        "message":simulation.message,
    }


def assert_strict_feasibility(sim, name):
    """Independently check all feasible final hourly points, AFTER permitted controls."""
    if sim.feasible:
        for st in sim.steps:
            for bus, v in st.power_flow.voltage_mag_pu.items():
                if not S.VOLTAGE_MIN_PU - 1e-9 <= v <= S.VOLTAGE_MAX_PU + 1e-9:
                    raise AssertionError(f"{name} marked feasible at {st.timestamp}, bus {bus}, V={v}")
            grid_kw = st.power_flow.slack_p_kw
            if S.GRID_IMPORT_LIMIT_KW is not None and grid_kw > S.GRID_IMPORT_LIMIT_KW+1e-3:
                raise AssertionError(f"{name} import exceeds cap at {st.timestamp}: {grid_kw}")
            # Check the per-case export cap; the unlimited-export reference is intentionally excluded.
            if name != "Unrestricted export" and S.GRID_EXPORT_LIMIT_KW is not None and -grid_kw > S.GRID_EXPORT_LIMIT_KW+1e-3:
                raise AssertionError(f"{name} export exceeds cap at {st.timestamp}: {-grid_kw}")


def voltage_rows(sim, case, baseline_steps=None):
    rows = []
    for i, st in enumerate(sim.steps):
        for bus, voltage in sorted(st.power_flow.voltage_mag_pu.items()):
            base = (baseline_steps[i].power_flow.voltage_mag_pu[bus]
                    if baseline_steps is not None else voltage)
            rows.append({"timestamp":str(st.timestamp), "case":case, "bus_id":bus,
                         "voltage_pu":voltage, "base_voltage_pu":base,
                         "delta_v_pu":voltage-base,
                         "within_voltage_limit":S.VOLTAGE_MIN_PU-1e-10 <= voltage <= S.VOLTAGE_MAX_PU+1e-10})
    return rows


def operation_rows(sim):
    rows = []
    for st in sim.steps:
        b = st.bess_step
        rows.append({"timestamp":str(st.timestamp),
                     "requested_bess_kw":st.bess_request_kw,
                     "actual_bess_kw":b.actual_power_kw if b else 0.0,
                     "bess_soc":st.bess_state.soc if st.bess_state else None,
                     "bess_energy_kwh":st.bess_state.energy_kwh if st.bess_state else None,
                     "grid_import_kw":max(0.,st.power_flow.slack_p_kw),
                     "grid_export_kw":max(0.,-st.power_flow.slack_p_kw),
                     "curtailment_kw":st.curtailment_kw,
                     "shedding_kw":st.shedding_kw,
                     "min_voltage_pu":min(st.power_flow.voltage_mag_pu.values()),
                     "max_voltage_pu":max(st.power_flow.voltage_mag_pu.values())})
    return rows


def draw_input_profiles():
    input_df = pd.read_csv(INPUTS / "hourly_input_summary.csv", parse_dates=["timestamp"])
    daily = input_df.set_index("timestamp").resample("D")[["load_kw", "pv_kw"]].sum()
    fig, ax = plt.subplots(figsize=(11,4.5))
    ax.plot(daily.index, daily.load_kw, label="Demand energy", lw=1.7)
    ax.plot(daily.index, daily.pv_kw, label="Modeled PV energy", lw=1.7)
    ax.set(ylabel="Daily energy (kWh)",title="C5 source demand and modeled PV over selected horizon")
    ax.grid(alpha=.2)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(RESULTS/"inputs_daily_energy.png",dpi=170)
    plt.close(fig)


def draw_voltage_plots(base_sim, bess_sim):
    n = min(len(base_sim.steps),len(bess_sim.steps))
    times = pd.to_datetime([step.timestamp for step in base_sim.steps[:n]])
    buses = sorted(base_sim.steps[0].power_flow.voltage_mag_pu)
    vb = np.array([[st.power_flow.voltage_mag_pu[bus] for bus in buses]
                   for st in base_sim.steps[:n]])
    ve = np.array([[st.power_flow.voltage_mag_pu[bus] for bus in buses]
                   for st in bess_sim.steps[:n]])
    worst_hour = int(np.argmin(vb.min(axis=1)))
    worst_time = times[worst_hour]

    fig,ax=plt.subplots(figsize=(10,5))
    ax.plot(buses,vb[worst_hour],"o-",label="Base case",lw=1.7)
    ax.plot(buses,ve[worst_hour],"s-",label="Optimized BESS",lw=1.7)
    ax.axhline(S.VOLTAGE_MIN_PU,c="red",ls="--",lw=1,label="Voltage limits")
    ax.axhline(S.VOLTAGE_MAX_PU,c="red",ls="--",lw=1)
    ax.axhline(1,c="grey",ls=":",lw=1)
    ax.set(xlabel="Bus ID",ylabel="Voltage (pu)",
           title=f"C5 voltage profile at base-case worst-voltage hour: {worst_time}")
    ax.set_xticks(buses)
    ax.legend()
    ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(RESULTS/"voltage_by_bus_worst_hour.png",dpi=170)
    plt.close(fig)

    fig,ax=plt.subplots(figsize=(11,5))
    ax.plot(times,vb.min(axis=1),label="Base case: min bus voltage",lw=1)
    ax.plot(times,ve.min(axis=1),label="Optimized BESS: min bus voltage",lw=1)
    ax.axhline(S.VOLTAGE_MIN_PU,c="red",ls="--",lw=1,label="0.95 pu limit")
    ax.set(xlabel="Time",ylabel="Minimum bus voltage (pu)",
           title="C5 minimum hourly bus voltage: base vs optimized BESS")
    ax.legend()
    ax.grid(alpha=.2)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(RESULTS/"minimum_voltage_over_horizon.png",dpi=170)
    plt.close(fig)

    day = worst_time.normalize()
    mask = (times >= day) & (times < day+pd.Timedelta(days=1))
    inds = np.flatnonzero(mask)
    if len(inds):
        vlo=min(S.VOLTAGE_MIN_PU, min(vb[inds].min(),ve[inds].min()))
        vhi=max(S.VOLTAGE_MAX_PU, max(vb[inds].max(),ve[inds].max()))
        for name,data in (("base",vb),("optimized",ve)):
            fig,ax=plt.subplots(figsize=(11,5))
            im=ax.imshow(data[inds].T,origin="lower",aspect="auto",cmap="viridis",vmin=vlo,vmax=vhi)
            ax.set_yticks(range(len(buses)),labels=buses)
            ax.set_xticks(range(len(inds)), labels=[int(times[j].hour) for j in inds])
            ax.set(xlabel="Hour",ylabel="Bus ID",title=f"{name.capitalize()} voltage heatmap at {day.date()} (common scale)")
            fig.colorbar(im,ax=ax,label="Voltage (pu)")
            fig.tight_layout()
            fig.savefig(RESULTS/f"voltage_heatmap_{name}.png",dpi=170)
            plt.close(fig)

    delta=ve-vb
    fig,ax=plt.subplots(figsize=(10,5))
    ax.plot(buses,delta[worst_hour],"o-",label="BESS - base")
    ax.axhline(0,c="black",lw=.8)
    ax.set(xlabel="Bus ID",ylabel="Voltage change (pu)",
           title=f"BESS voltage effect at worst base voltage hour: {worst_time}")
    ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(RESULTS/"voltage_change_worst_hour.png",dpi=170)
    plt.close(fig)

    # The worst baseline-voltage hour may be an idle-BESS hour; show an
    # additional plot at MAXIMUM measured voltage effect, with a zoomed axis.
    max_effect_hour = int(np.argmax(np.max(np.abs(delta),axis=1)))
    effect_time = times[max_effect_hour]
    fig,ax=plt.subplots(figsize=(10,5))
    ax.plot(buses,vb[max_effect_hour],"o-",label="Base case",lw=2)
    ax.plot(buses,ve[max_effect_hour],"s-",label="Optimized BESS",lw=2)
    ax.set(xlabel="Bus ID",ylabel="Voltage (pu)",
           title=f"C5 bus voltages at largest BESS voltage effect: {effect_time}")
    ax.set_xticks(buses)
    ax.grid(alpha=.2)
    ax.legend()
    fig.tight_layout()
    fig.savefig(RESULTS/"voltage_by_bus_max_effect_hour.png",dpi=170)
    plt.close(fig)

    fig,ax=plt.subplots(figsize=(10,5))
    ax.bar(buses,delta[max_effect_hour])
    ax.axhline(0,color="black",lw=.9)
    ax.set(xlabel="Bus ID",ylabel="Change in voltage (pu): BESS - base",
           title=f"C5 battery impact at {effect_time} (maximum |delta V|)")
    ax.set_xticks(buses)
    ax.grid(alpha=.2,axis="y")
    fig.tight_layout()
    fig.savefig(RESULTS/"voltage_change_max_effect_hour.png",dpi=170)
    plt.close(fig)

    # Complete month heatmap of voltage changes (all hours, not just one day).
    fig,ax=plt.subplots(figsize=(12,5.7))
    max_abs=max(float(np.max(np.abs(delta))),1e-10)
    im=ax.imshow(delta.T,origin="lower",aspect="auto",cmap="coolwarm",
                 vmin=-max_abs,vmax=max_abs,interpolation="nearest")
    ax.set_yticks(range(len(buses)),labels=buses)
    positions=np.linspace(0,len(times)-1,min(9,len(times)),dtype=int)
    ax.set_xticks(positions,labels=[str(times[i])[:10] for i in positions],rotation=30,ha="right")
    ax.set(xlabel="Date",ylabel="Bus ID",title="C5 bus voltage changes from BESS (every hourly step)")
    fig.colorbar(im,ax=ax,label="Voltage change (pu): BESS - base")
    fig.tight_layout()
    fig.savefig(RESULTS/"voltage_difference_heatmap_full_horizon.png",dpi=170)
    plt.close(fig)

    voltage_effect_rows=[]
    for j,bus in enumerate(buses):
        values=delta[:,j]
        k=int(np.argmax(np.abs(values)))
        voltage_effect_rows.append({"bus_id":bus,
                                    "largest_absolute_change_pu":float(np.abs(values).max()),
                                    "change_at_largest_impact_pu":float(values[k]),
                                    "time_of_largest_impact":str(times[k]),
                                    "mean_absolute_change_pu":float(np.abs(values).mean())})
    write_csv("voltage_impact_by_bus.csv",voltage_effect_rows)


def draw_raw_baseline_comparison(raw_sim, controlled_sim):
    """Expose the raw network voltage violations masked by automatic shedding.

    Both are WITHOUT BESS. One has corrective controls disabled, the other has
    the study's corrective controls enabled. The optimizer is compared against
    the controlled baseline; the raw run exposes the original voltage problem.
    """
    if len(raw_sim.steps) != len(controlled_sim.steps):
        raise ValueError("Uncorrected and corrected baseline horizons differ")
    ts = pd.to_datetime([step.timestamp for step in raw_sim.steps])
    buses = sorted(raw_sim.steps[0].power_flow.voltage_mag_pu)
    raw = np.array([[s.power_flow.voltage_mag_pu[b] for b in buses] for s in raw_sim.steps])
    fixed = np.array([[s.power_flow.voltage_mag_pu[b] for b in buses] for s in controlled_sim.steps])
    worst = int(np.argmin(raw.min(axis=1)))
    fig, ax = plt.subplots(figsize=(12, 5.4))
    ax.plot(ts, raw.min(axis=1), label="Raw base (no voltage controls)", lw=1)
    ax.plot(ts, fixed.min(axis=1), label="Controlled base (may shed load)", lw=1)
    ax.axhline(S.VOLTAGE_MIN_PU, color="red", ls="--", label="0.95 pu minimum")
    ax.set(xlabel="Time", ylabel="Minimum voltage across buses (pu)",
           title="System 1: uncorrected versus controlled no-BESS voltage")
    ax.legend(); ax.grid(alpha=.2); fig.autofmt_xdate(); fig.tight_layout()
    fig.savefig(RESULTS / "raw_vs_controlled_baseline_min_voltage.png", dpi=170)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 5.0))
    ax.plot(buses, raw[worst], "o-", label="Raw base (no controls)")
    ax.plot(buses, fixed[worst], "s-", label="Controlled base (no BESS)")
    ax.axhline(S.VOLTAGE_MIN_PU, color="red", ls="--", label="0.95 pu minimum")
    ax.axhline(S.VOLTAGE_MAX_PU, color="red", ls="--", label="1.05 pu maximum")
    ax.set_xticks(buses)
    ax.set(xlabel="Bus ID", ylabel="Voltage (pu)",
           title=f"System 1: baseline voltages at worst raw hour {ts[worst]}")
    ax.legend(); ax.grid(alpha=.2); fig.tight_layout()
    fig.savefig(RESULTS / "raw_vs_controlled_baseline_buses.png", dpi=170)
    plt.close(fig)
    violation_bushours = int(np.count_nonzero((raw < S.VOLTAGE_MIN_PU) | (raw > S.VOLTAGE_MAX_PU)))
    undervoltage_bushours = int(np.count_nonzero(raw < S.VOLTAGE_MIN_PU))
    overvoltage_bushours = int(np.count_nonzero(raw > S.VOLTAGE_MAX_PU))
    fig,ax=plt.subplots(figsize=(12,5))
    ax.plot(ts,raw.min(axis=1),label="Raw minimum",alpha=.85)
    ax.plot(ts,raw.max(axis=1),label="Raw maximum",alpha=.85)
    ax.plot(ts,fixed.min(axis=1),label="Controlled minimum",alpha=.65)
    ax.plot(ts,fixed.max(axis=1),label="Controlled maximum",alpha=.65)
    ax.axhline(S.VOLTAGE_MIN_PU,color="red",ls="--",lw=1)
    ax.axhline(S.VOLTAGE_MAX_PU,color="red",ls="--",lw=1)
    ax.set(title="Uncorrected and corrected voltage extremes: both limits",xlabel="Time",ylabel="Bus voltage (pu)")
    ax.grid(alpha=.2);ax.legend(ncol=2);fig.autofmt_xdate();fig.tight_layout()
    fig.savefig(RESULTS/"raw_vs_controlled_min_max_voltage.png",dpi=170)
    plt.close(fig)
    affected_hours = int(np.count_nonzero(np.any((raw < S.VOLTAGE_MIN_PU) | (raw > S.VOLTAGE_MAX_PU), axis=1)))
    return {"raw_minimum_voltage_pu": float(raw.min()),
            "raw_maximum_voltage_pu": float(raw.max()),
            "raw_undervoltage_bus_hours": undervoltage_bushours,
            "raw_overvoltage_bus_hours": overvoltage_bushours,
            "raw_violation_bus_hours": violation_bushours,
            "raw_hours_with_violations": affected_hours,
            "corrected_minimum_voltage_pu": float(fixed.min())}


def draw_battery_profile(bess_sim):
    rows=operation_rows(bess_sim)
    clock=pd.to_datetime([row["timestamp"] for row in rows])
    power=np.array([row["actual_bess_kw"] for row in rows])
    soc=np.array([row["bess_soc"] for row in rows])
    fig,ax=plt.subplots(figsize=(11,5))
    ax.plot(clock,power,label="BESS power (positive discharge)",lw=.85)
    ax.axhline(0,color="black",linewidth=.7)
    ax2=ax.twinx()
    ax2.plot(clock,soc*100,label="SOC",c="tab:orange",alpha=.8,lw=.9)
    ax.set(xlabel="Time",ylabel="Battery power (kW)",title="Optimized BESS operation over the selected horizon")
    ax2.set_ylabel("State of charge (%)")
    ax2.set_ylim(0,105)
    ax.grid(alpha=.2)
    h1,l1=ax.get_legend_handles_labels(); h2,l2=ax2.get_legend_handles_labels()
    ax.legend(h1+h2,l1+l2,loc="upper right")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(RESULTS/"bess_power_and_soc.png",dpi=170)
    plt.close(fig)


def draw_stress_operations(base_sim, best_sim):
    """Compare actual grid exchange and hourly controls for the two physical runs."""
    times=pd.to_datetime([st.timestamp for st in base_sim.steps])
    for metric,attribute,unit,name in (("PV curtailed","curtailment_kw","kW","curtailment_comparison.png"),
                                      ("Demand shed","shedding_kw","kW","shedding_comparison.png")):
        base=[getattr(st,attribute) for st in base_sim.steps]
        best=[getattr(st,attribute) for st in best_sim.steps]
        fig,ax=plt.subplots(figsize=(11,4.6))
        ax.plot(times,base,label="No BESS",lw=1.3)
        ax.plot(times,best,label="Optimized BESS",lw=1.1)
        ax.set(xlabel="Time",ylabel=metric+" ("+unit+")",title=metric+" under capped grid import/export")
        ax.grid(alpha=.2);ax.legend();fig.autofmt_xdate();fig.tight_layout()
        fig.savefig(RESULTS/name,dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,4.8))
    ax.plot(times,[st.power_flow.slack_p_kw for st in base_sim.steps],label="Grid exchange without BESS",lw=1.2)
    ax.plot(times,[st.power_flow.slack_p_kw for st in best_sim.steps],label="Grid exchange with BESS",lw=1.0)
    if S.GRID_IMPORT_LIMIT_KW is not None: ax.axhline(S.GRID_IMPORT_LIMIT_KW,c="red",ls="--",lw=1,label="Import cap")
    if S.GRID_EXPORT_LIMIT_KW is not None: ax.axhline(-S.GRID_EXPORT_LIMIT_KW,c="orange",ls=":",lw=1,label="Export cap")
    ax.set(xlabel="Time",ylabel="Slack power (kW; +import / −export)",title="Bus 1 power flow after corrective controls")
    ax.grid(alpha=.2);ax.legend();fig.autofmt_xdate();fig.tight_layout()
    fig.savefig(RESULTS/"slack_power_comparison.png",dpi=170);plt.close(fig)


def draw_optimization_plot(histories, exact_cost):
    fig,ax=plt.subplots(figsize=(10,5))
    for method in ("GA","GWO"):
        sample=[r for r in histories if r["algorithm"] == method]
        for seed in sorted(set(r["seed"] for r in sample)):
            y=[r["best_so_far_usd_per_year"] for r in sample if r["seed"]==seed]
            ax.plot(range(1,len(y)+1),y,alpha=.12,lw=.8)
        means=[statistics.mean(r["best_so_far_usd_per_year"] for r in sample if r["iteration"]==i)
               for i in range(1,S.ITERATIONS+1)]
        ax.plot(range(1,S.ITERATIONS+1),means,linewidth=2,label=method+" mean")
    ax.axhline(exact_cost,c="black",ls="--",label="Exhaustive best")
    ax.set(xlabel="Iteration / generation",ylabel="Best cost (USD/year)",
           title="C5 GA/GWO convergence against exhaustive minimum")
    ax.grid(alpha=.2)
    ax.legend()
    fig.tight_layout()
    fig.savefig(RESULTS/"convergence_comparison.png",dpi=170)
    plt.close(fig)


def main():
    RESULTS.mkdir(parents=True,exist_ok=True)
    manifest=prepare_inputs()    # always regenerate to match settings
    plot_extreme_inputs()
    net=load_network(NETWORK,workbook_format="auto",frequency_hz=60.0)
    net.pv_units.append(PVUnit(f"C5_PV{S.PV_BUS}",S.PV_BUS,S.PV_RATING_KW))
    net.validate()
    profiles=ProfileData(INPUTS/"load_profile.csv",INPUTS/"pv_profile.csv")
    assert len(profiles.timestamps)==manifest["hours"]
    bounds=OptimizationBounds(allowed_bus_ids=S.ALLOWED_BUS_IDS,
                              power_ratings_kw=S.POWER_RATINGS_KW,
                              energy_capacities_kwh=S.ENERGY_CAPACITIES_KWH)
    battery=BESSParameters(S.ETA_CHARGE,S.ETA_DISCHARGE,
                           soc_min=S.SOC_MIN,soc_initial=S.SOC_INITIAL,soc_max=S.SOC_MAX)
    economics=EconomicConfig(cost_per_kw=S.COST_PER_KW,cost_per_kwh=S.COST_PER_KWH,
                             discount_rate=S.DISCOUNT_RATE,lifetime_years=S.LIFETIME_YEARS,
                             annual_om_fraction=S.ANNUAL_OM_FRACTION,
                             curtailment_penalty_per_kwh=S.CURTAILMENT_PENALTY,
                             shedding_penalty_per_kwh=S.SHEDDING_PENALTY,
                             grid_import_tariff_per_kwh=S.GRID_IMPORT_TARIFF,
                             grid_export_tariff_per_kwh=S.GRID_EXPORT_TARIFF,
                             annual_hours=S.ANNUAL_HOURS)
    settings=SimulationConfig(voltage_min_pu=S.VOLTAGE_MIN_PU,
                              voltage_max_pu=S.VOLTAGE_MAX_PU,
                              reserve_fraction=S.RESERVE_FRACTION,
                              enforce_line_ampacity=S.ENFORCE_LINE_AMPACITY,
                              allow_pv_curtailment=S.ALLOW_PV_CURTAILMENT,
                              allow_load_shedding=S.ALLOW_LOAD_SHEDDING,
                              grid_import_limit_kw=S.GRID_IMPORT_LIMIT_KW,
                              grid_export_limit_kw=S.GRID_EXPORT_LIMIT_KW)
    evaluator=CandidateAwareEvaluator(economics,battery,settings)
    print("C5 starts | hours:",manifest["hours"],"| strict voltage:",
          (S.VOLTAGE_MIN_PU,S.VOLTAGE_MAX_PU),"| dispatch:",S.DISPATCH_MODE,flush=True)

    print("Running raw no-BESS baseline (NO curtailment/shedding corrections)...", flush=True)
    raw_settings = replace(settings, allow_pv_curtailment=False, allow_load_shedding=False)
    raw_sim = simulate_timeseries(net, profiles, raw_settings)
    if not raw_sim.completed or not raw_sim.converged:
        raise RuntimeError("Uncorrected baseline did not converge/complete")
    raw_metrics = evaluate_results(raw_sim, economics)
    raw_row = summary_row("Raw base (no corrective actions)", raw_sim, raw_metrics, None)
    write_csv("raw_baseline_summary.csv", [raw_row])
    write_csv("raw_baseline_voltage_hourly.csv", voltage_rows(raw_sim,"Raw base"))
    print("Running controlled no-BESS baseline...",flush=True)
    base_sim=simulate_timeseries(net,profiles,settings)
    base_metrics=(evaluate_results(base_sim,economics) if base_sim.converged and base_sim.completed else None)
    assert_strict_feasibility(base_sim,"Base")
    base_row=summary_row("Base (no BESS)",base_sim,base_metrics,None)
    write_csv("base_case_summary.csv",[base_row])
    if not base_sim.completed or not base_sim.converged:
        (RESULTS/"C5_experiment_report.md").write_text(
            "# C5 run aborted\n\nBaseline power flow failed or did not complete. "
            "See `base_case_summary.csv`. No catalog comparison generated.\n",encoding="utf-8")
        raise RuntimeError("Baseline power flow did not converge: inspect base_case_summary.csv")
    write_csv("base_voltage_hourly.csv",voltage_rows(base_sim,"Base"))
    print("Running same network with UNLIMITED export as a counterfactual...", flush=True)
    no_export_cap_settings = replace(settings, grid_export_limit_kw=None)
    no_export_cap_sim = simulate_timeseries(net, profiles, no_export_cap_settings)
    if not no_export_cap_sim.completed or not no_export_cap_sim.converged:
        raise RuntimeError("Counterfactual no-export-limit run failed")
    no_export_cap_metrics = evaluate_results(no_export_cap_sim,economics)
    no_export_cap_row = summary_row("Unrestricted export (no BESS)", no_export_cap_sim, no_export_cap_metrics, None)
    write_csv("unrestricted_export_baseline_summary.csv", [no_export_cap_row])
    print("No export cap: curtailment",round(no_export_cap_metrics.curtailment_energy_kwh,2),
          "kWh; export",round(no_export_cap_metrics.grid_export_energy_kwh,2),"kWh",flush=True)
    raw_checks = draw_raw_baseline_comparison(raw_sim, base_sim)
    (RESULTS / "raw_baseline_violation_counts.json").write_text(json.dumps(raw_checks, indent=2), encoding="utf-8")
    print("Raw baseline Vmin", round(raw_checks["raw_minimum_voltage_pu"], 6),
          "raw bus-hours outside limits", raw_checks["raw_violation_bus_hours"], flush=True)
    print("Controlled baseline voltage min/max",base_row.get("voltage_min_pu"),base_row.get("voltage_max_pu"),
          "feasible",base_sim.feasible, "shedding (kWh)", base_row.get("load_shedding_kwh"), flush=True)

    print(f"Running exhaustive search ({len(S.ALLOWED_BUS_IDS)*len(S.POWER_RATINGS_KW)*len(S.ENERGY_CAPACITIES_KWH)} candidates)...",flush=True)
    t=perf_counter()
    exhaustive=exhaustive_search(net,profiles,bounds,evaluator)
    physical_eval_seconds=perf_counter()-t
    candidates=[]
    for e in exhaustive.evaluations:
        metrics=e.metrics
        candidates.append({**values(e.candidate),
                           "cost_usd_per_year":e.objective,
                           "feasible":e.feasible,
                           "voltage_min_pu":metrics.voltage_min_pu if metrics else None,
                           "voltage_max_pu":metrics.voltage_max_pu if metrics else None,
                           "voltage_violation_bus_hours":metrics.voltage_violation_bus_hours if metrics else None,
                           "curtailment_kwh":metrics.curtailment_energy_kwh if metrics else None,
                           "shedding_kwh":metrics.load_shedding_energy_kwh if metrics else None,
                           "charge_kwh":metrics.bess_charge_energy_kwh if metrics else None,
                           "discharge_kwh":metrics.bess_discharge_energy_kwh if metrics else None,
                           "message":e.message})
    write_csv("exhaustive_candidates.csv",candidates)
    plot_candidate_results()
    available=[e.objective for e in exhaustive.evaluations if e.feasible]
    spread=((max(available)-min(available))/abs(min(available))*100
            if available and min(available)!=0 else None)
    print("Exhaustive time",round(physical_eval_seconds,2),"s; feasible",len(available),
          "/",len(exhaustive.evaluations),flush=True)
    if not exhaustive.success:
        (RESULTS/"C5_experiment_report.md").write_text(
            "# C5 results\n\nNo feasible BESS candidate found under strict voltage limits. "
            "See `exhaustive_candidates.csv`; GA/GWO comparison omitted.\n",encoding="utf-8")
        draw_input_profiles()
        write_csv("base_vs_optimized_summary.csv", [raw_row, base_row])
        print("No feasible candidate. All candidates correctly rejected; inspect records.",flush=True)
        return

    # The table shortcut is legitimate for comparing discrete heuristic choices
    # against deterministic exhaustive scores, but NOT for end-to-end runtime.
    search_evaluator=(CatalogLookupEvaluator({e.candidate:e for e in exhaustive.evaluations})
                      if S.USE_PRECOMPUTED_SCORES else evaluator)
    histories=[]; runs=[]
    for seed in range(1,S.RUN_SEEDS+1):
        for method, search in (("GA",genetic_optimize),("GWO",optimize)):
            cfg=OptimizerConfig(population_size=S.POPULATION_SIZE,max_iterations=S.ITERATIONS,
                                seed=seed,cache_evaluations=True,workers=1)
            t=perf_counter()
            result=search(net,profiles,bounds,search_evaluator,cfg)
            runtime=perf_counter()-t
            gap=((result.best_objective-exhaustive.best_objective)/abs(exhaustive.best_objective)*100
                 if result.success and exhaustive.best_objective!=0 else None)
            runs.append({"algorithm":method,"seed":seed,**values(result.best_candidate),
                         "feasible":result.success,"annual_cost_usd":result.best_objective,
                         "exhaustive_annual_cost_usd":exhaustive.best_objective,
                         "gap_percent":gap,
                         "exact_match":result.best_candidate==exhaustive.best_candidate,
                         "within_5_percent":gap is not None and gap<=S.TARGET_GAP_PERCENT+1e-10,
                         "unique_candidate_evaluations":len(result.evaluations),
                         "iterations":result.iterations,"runtime_seconds":runtime,
                         "runtime_mode":"search_lookup_only" if S.USE_PRECOMPUTED_SCORES else "full_simulator"})
            histories.extend({"algorithm":method,"seed":seed,"iteration":i+1,
                              "best_so_far_usd_per_year":v}
                             for i,v in enumerate(result.convergence_history))
        if seed % 5 == 0 or seed == S.RUN_SEEDS:
            print(f"Finished {seed}/{S.RUN_SEEDS} seeds",flush=True)
    write_csv("search_runs.csv",runs)
    write_csv("convergence_history.csv",histories)
    summary=[]
    for name in ("GA","GWO"):
        group=[x for x in runs if x["algorithm"]==name]
        passed=sum(bool(x["within_5_percent"]) for x in group)
        matched=sum(bool(x["exact_match"]) for x in group)
        summary.append({"algorithm":name,"runs":len(group),"within_5_percent":passed,
                        "exact_matches":matched,"pass_rate":passed/len(group),
                        "protocol_pass":passed>=S.REQUIRED_PASSES if len(group)==20 else "pilot_not_assessed",
                        "mean_gap_percent":statistics.mean(x["gap_percent"] for x in group if x["gap_percent"] is not None),
                        "mean_unique_evaluations":statistics.mean(x["unique_candidate_evaluations"] for x in group),
                        "mean_search_seconds":statistics.mean(x["runtime_seconds"] for x in group),
                        "all_candidates_within_5_percent":spread<=S.TARGET_GAP_PERCENT,
                        "catalog_spread_percent":spread,
                        "exact_best_cost_usd_per_year":exhaustive.best_objective,
                        **values(exhaustive.best_candidate)})
    write_csv("algorithm_summary.csv",summary)

    representative={"Exhaustive best":exhaustive.best_candidate}
    for name in ("GA","GWO"):
        feasible_runs=[x for x in runs if x["algorithm"]==name and x["feasible"]]
        if feasible_runs:
            winner=min(feasible_runs,key=lambda x:(x["annual_cost_usd"],x["seed"]))
            representative[name+" best"]=BESSCandidate(winner["bess_bus"],winner["bess_power_kw"],winner["bess_capacity_kwh"])

    summaries=[raw_row, base_row, no_export_cap_row]
    all_voltages=(voltage_rows(raw_sim,"Raw base")+voltage_rows(base_sim,"Base")+
                  voltage_rows(no_export_cap_sim,"Unrestricted export (no BESS)"))
    cache_sim={}
    for label,candidate in representative.items():
        if candidate not in cache_sim:
            cfg=battery.build_config(candidate)
            sim=simulate_timeseries(net,profiles,settings,bess_config=cfg,dispatch_policy=policy_for(candidate))
            metrics=evaluate_results(sim,economics,cfg) if sim.converged and sim.completed else None
            assert_strict_feasibility(sim,label)
            cache_sim[candidate]=(sim,metrics)
        sim,metrics=cache_sim[candidate]
        summaries.append(summary_row(label,sim,metrics,candidate))
        all_voltages.extend(voltage_rows(sim,label,base_sim.steps))
    write_csv("base_vs_optimized_summary.csv",summaries)
    write_csv("all_cases_voltage_hourly.csv",all_voltages)
    best_sim,best_metrics=cache_sim[exhaustive.best_candidate]
    write_csv("base_vs_best_voltage_hourly.csv",[r for r in all_voltages if r["case"] in ("Base","Exhaustive best")])
    write_csv("optimized_bess_hourly.csv",operation_rows(best_sim))
    draw_input_profiles()
    draw_voltage_plots(base_sim,best_sim)
    draw_battery_profile(best_sim)
    draw_stress_operations(base_sim,best_sim)
    draw_optimization_plot(histories,exhaustive.best_objective)

    recorded={
        "input_manifest":manifest,
        "simulation_hours":len(profiles.timestamps),
        "source_sha256":{f:hashlib.sha256((ROOT/"src_accelerated"/f).read_bytes()).hexdigest()
                         for f in ("optimizer.py","simulation.py","metrics.py","bess.py","fbs.py")},
        "python_version":platform.python_version(),
        "settings":{n:getattr(S,n) for n in dir(S) if n.isupper() and not n.startswith("_")},
        "exhaustive_real_simulation_seconds":physical_eval_seconds,
        "search_runtime_mode":"lookup_only; excludes FBS/simulation evaluation"
                              if S.USE_PRECOMPUTED_SCORES else "end_to_end",
        "candidate_catalog_size":len(exhaustive.evaluations),
        "raw_baseline_violation_check":raw_checks,
        "candidate_feasible_count":len(available),
        "exact_candidate":values(exhaustive.best_candidate),
        "exact_annual_cost_usd":exhaustive.best_objective,
        "base_annual_cost_usd":base_row.get("annual_total_cost_usd"),
        "notes":["Synthetic stress: 160% of historical active/reactive loads; 2000 kW modeled PV at bus 13",
                 "Grid import capped at 650 kW; grid export forbidden in principal experiment; both limits adjustable",
                 "Unrestricted-export baseline is a separate counterfactual: import/voltage limits remain active",
                 "Voltage strict AFTER permitted curtailment and load shedding; raw voltage violations reported separately",
                 "Curtailed PV is foregone generation, not exported energy; no export-fee term was added",
                 "Voltage is a hard constraint, annualized cost is the only optimization target",
                 "The BESS control is grid-aware heuristic (self-consumption), not optimal charge/discharge dispatch",
                 "USD/kW and USD/kWh capital coefficients are illustrative independent model assumptions",
                 "Reference network ampacity values are unverified, so line thermal constraints are disabled",
                 "Annual totals extrapolate the selected sample; not verified yearly costs",
                 "NASA UTC and GoiEner zone-unspecified stamps aligned by label; actual timezone matching unverified"]
    }
    (RESULTS/"test_settings.json").write_text(json.dumps(recorded,indent=2,default=str),encoding="utf-8")

    cost_base=base_row.get("annual_total_cost_usd")
    cost_best=best_metrics.annual_total_cost
    delta_cost=(cost_best-cost_base if cost_base is not None else None)
    exact_match_summary=", ".join(f"{r['algorithm']}: {r['exact_matches']}/{r['runs']}"
                                   for r in summary)
    shed_reduction=base_metrics.load_shedding_energy_kwh-best_metrics.load_shedding_energy_kwh
    curt_reduction=base_metrics.curtailment_energy_kwh-best_metrics.curtailment_energy_kwh
    report=f"""# EE499 C5 — Extreme import/export and voltage stress (System 1)

**Test date:** {manifest['start_inclusive']} through {manifest['end_exclusive']} (exclusive); **{manifest['hours']} hours**.  
**Network:** 15-bus System 1, T04 workbook. **Candidate buses:** 2–15 (all non-slack buses).  
**Stress:** historical load ×{S.LOAD_MULTIPLIER:.2f} for both P and Q; modeled solar rating {S.PV_RATING_KW:.0f} kW on bus {S.PV_BUS}.  
**Bus 1 grid limits:** import ≤{S.GRID_IMPORT_LIMIT_KW} kW; export ≤{S.GRID_EXPORT_LIMIT_KW} kW (zero export).  
**Voltage constraint:** {S.VOLTAGE_MIN_PU:.2f}–{S.VOLTAGE_MAX_PU:.2f} pu at EVERY bus/hour *after* permitted correction.  
**Dispatch:** `{S.DISPATCH_MODE}`; charges from solar surplus, discharges against net demand when possible.  

**Important:** This scenario is deliberately synthetic. Scaled demand and enlarged PV rating are not a forecast, not a historical measurement, and not a claim of engineering realism for this feeder. Line ampacity checks are disabled because verified limits are unavailable.

## 1. Evidence of genuine stress

- Source-derived sample demand **{manifest['total_load_kwh']:,.1f} kWh** and modeled available PV **{manifest['total_pv_kwh']:,.1f} kWh** (after synthetic scaling).
- Hours with *aggregate* solar surplus: **{manifest['solar_surplus_hours']}**.
- Raw no-BESS minimum/maximum voltages: **{raw_checks['raw_minimum_voltage_pu']:.6f} / {raw_checks['raw_maximum_voltage_pu']:.6f} pu**.
- Raw undervoltage bus-hours: **{raw_checks['raw_undervoltage_bus_hours']}**; raw overvoltage bus-hours: **{raw_checks['raw_overvoltage_bus_hours']}**. Total raw bus-hours outside allowed band: **{raw_checks['raw_violation_bus_hours']}**.
- Correction is allowed to shed demand or curtail PV to restore the feasible network operating point. **Feasible does not mean all demand served or all PV used.**

## 2. Why the export limit matters

| No-BESS comparison | Export limited to {S.GRID_EXPORT_LIMIT_KW} kW | Unlimited grid export |
|---|---:|---:|
| PV curtailed (kWh) | {base_metrics.curtailment_energy_kwh:,.2f} | {no_export_cap_metrics.curtailment_energy_kwh:,.2f} |
| Grid export (kWh) | {base_metrics.grid_export_energy_kwh:,.4f} | {no_export_cap_metrics.grid_export_energy_kwh:,.2f} |
| Load shed (kWh) | {base_metrics.load_shedding_energy_kwh:,.2f} | {no_export_cap_metrics.load_shedding_energy_kwh:,.2f} |
| Annualized modeled cost (USD) | {base_metrics.annual_total_cost:,.2f} | {no_export_cap_metrics.annual_total_cost:,.2f} |

Unlimited export does NOT remove voltage constraints. Any remaining curtailment with unlimited export can be caused by network voltage behavior; see hourly profiles.

## 3. Exhaustive optimization against GA/GWO

- Options: **{len(exhaustive.evaluations)}** = {len(S.ALLOWED_BUS_IDS)} locations × {len(S.POWER_RATINGS_KW)} power sizes × {len(S.ENERGY_CAPACITIES_KWH)} energy sizes; **{len(available)} feasible** after allowed controls.
- Catalog optimum: **bus {exhaustive.best_candidate.bus_id}, {exhaustive.best_candidate.power_rating_kw:g} kW / {exhaustive.best_candidate.energy_capacity_kwh:g} kWh**.
- Exact matches (GA/GWO): **{exact_match_summary}**.
- Entire feasible catalog cost spread: **{spread:.3f}%**. The 5% pass metric is {'NON-DISCRIMINATING' if spread <= S.TARGET_GAP_PERCENT else 'discriminating'} for this catalog.
- Exhaustive real simulation time: **{physical_eval_seconds:.2f}s**. Search timing is **{'lookup-only, not end-to-end' if S.USE_PRECOMPUTED_SCORES else 'full simulator'}**.

## 4. Main no-BESS vs best-BESS comparison (same strict limits)

| Metric | Controlled no BESS | Best BESS |
|---|---:|---:|
| Feasible after corrective controls | {base_sim.feasible} | {best_sim.feasible} |
| Voltage min (pu) | {base_metrics.voltage_min_pu:.6f} | {best_metrics.voltage_min_pu:.6f} |
| Voltage max (pu) | {base_metrics.voltage_max_pu:.6f} | {best_metrics.voltage_max_pu:.6f} |
| PV curtailment (kWh) | {base_metrics.curtailment_energy_kwh:,.2f} | {best_metrics.curtailment_energy_kwh:,.2f} |
| Load shedding (kWh) | {base_metrics.load_shedding_energy_kwh:,.2f} | {best_metrics.load_shedding_energy_kwh:,.2f} |
| Grid import (kWh) | {base_metrics.grid_import_energy_kwh:,.2f} | {best_metrics.grid_import_energy_kwh:,.2f} |
| Grid export (kWh) | {base_metrics.grid_export_energy_kwh:,.4f} | {best_metrics.grid_export_energy_kwh:,.4f} |
| Line losses (kWh) | {base_metrics.loss_energy_kwh:,.2f} | {best_metrics.loss_energy_kwh:,.2f} |
| Battery charge (kWh) | 0 | {best_metrics.bess_charge_energy_kwh:,.2f} |
| Battery discharge (kWh) | 0 | {best_metrics.bess_discharge_energy_kwh:,.2f} |
| Annualized modeled cost (USD/year) | {base_metrics.annual_total_cost:,.2f} | {best_metrics.annual_total_cost:,.2f} |

**Change:** shedding decreased by **{shed_reduction:,.2f} kWh** ({shed_reduction/max(base_metrics.load_shedding_energy_kwh,1e-12)*100:.2f}%); PV curtailment decreased by **{curt_reduction:,.2f} kWh** ({curt_reduction/max(base_metrics.curtailment_energy_kwh,1e-12)*100:.2f}%). Cost changed by **${cost_best-cost_base:+,.2f}/year** (a sample-extrapolated illustration, not a validated yearly prediction).

## 5. Cost interpretation

- `annual_grid_cost = annual_factor × (import_price × import_kWh − export_credit × export_kWh)`.
- `annual_curtailment_cost = annual_factor × (curtailment_penalty × curtailed_kWh)`.
- `annual_shedding_cost = annual_factor × (VoLL × shed_kWh)`.
- Battery capital is annualized with CRF plus O&M; initial/end SOC imbalance corrected separately.
- **Exported power is not curtailed**. In this model export receives a credit; NO export fee is assumed. A curtailment penalty is an assumed opportunity-cost proxy, NOT an actual payment charged by the grid.
- Import, export, shedding and curtailment monetary coefficients are illustrative, as are both independent battery capital unit rates; sources of current tariffs/fees have not been established.

## 6. Files

- `inputs/input_manifest.json`: original input provenance, stress multipliers, sample energy and count of surplus hours.
- `raw_baseline_voltage_hourly.csv`, `raw_vs_controlled_min_max_voltage.png`: both uncorrected voltage boundaries.
- `unrestricted_export_baseline_summary.csv`: same strict network limits with the grid export cap removed.
- `base_vs_optimized_summary.csv`: technical and economic comparisons.
- `exhaustive_candidates.csv`, `search_runs.csv`, `algorithm_summary.csv`: all candidates and heuristic performance.
- `base_vs_best_voltage_hourly.csv`, `voltage_impact_by_bus.csv`: every bus/hour and voltage changes.
- `curtailment_comparison.png`, `shedding_comparison.png`, `slack_power_comparison.png`: actual network actions and Bus 1 exchange.
- `optimized_bess_hourly.csv`, `bess_power_and_soc.png`: battery operation.

## Limitations and next checks

- Full available PV and source load were intentionally distorted; solar on a single bus at 2 MW may be physically unsuitable without feeder reinforcements. This is an **algorithm stress test**.
- Grid-aware battery control follows a heuristic, not optimal joint dispatch. Any reduction is under that specific policy, not the best achievable operational benefit.
- Line thermal/ampacity constraints are NOT enforced; results cannot demonstrate thermal feasibility.
- The NASA irradiance UTC and GoiEner unspecified local time are matched by timestamp label, not validated in a common physical timezone.
- Monthly results annualized with 8760/simulated_hours assume this window repeats all year. Do NOT interpret as observed annual outcomes.
"""
    (RESULTS/"C5_experiment_report.md").write_text(report,encoding="utf-8")
    print(f"DONE: results saved in {RESULTS}",flush=True)
    print(f"Raw Vmin: {raw_checks['raw_minimum_voltage_pu']:.5f}, violations: {raw_checks['raw_violation_bus_hours']} bus-hours")
    print(f"Controlled base V min/max: {base_metrics.voltage_min_pu:.5f} / {base_metrics.voltage_max_pu:.5f}")
    print(f"BESS V min/max: {best_metrics.voltage_min_pu:.5f} / {best_metrics.voltage_max_pu:.5f}")
    print(f"BESS charge/discharge: {best_metrics.bess_charge_energy_kwh:.2f} / {best_metrics.bess_discharge_energy_kwh:.2f} kWh")


if __name__=="__main__":
    main()
