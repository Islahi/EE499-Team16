"""Rebuild N consecutive hours from original GoiEner and NASA inputs.

Edit c5_settings.py to choose HORIZON_MONTHS or HORIZON_DAYS.
Run: python prepare_c5_inputs.py
Also called automatically by run_c5.py.
"""
from __future__ import annotations
from pathlib import Path
from zipfile import ZipFile
import hashlib
import io
import json

import pandas as pd

import c5_settings as S
from src_accelerated.network_loader import load_network
from src_accelerated.pv_model import PVModelConfig, irradiance_to_power, read_irradiance

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "source_data"
OUT = ROOT / "inputs"
NETWORK = ROOT / "T04_15-Bus_System_1.xlsx"
LOAD_ARCHIVE = SRC / "GoiEner_Distributed_20261110_111453_761547.zip"
NASA = SRC / "POWER_Point_Hourly_20141101_20201129_040d42N_003d70W_UTC.csv"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def timespan():
    start = pd.Timestamp(S.START_DATE)
    if start != start.normalize():
        raise ValueError("START_DATE must be YYYY-MM-DD at midnight")
    if S.HORIZON_DAYS is not None:
        if not isinstance(S.HORIZON_DAYS, int) or S.HORIZON_DAYS < 1:
            raise ValueError("HORIZON_DAYS must be None or a positive integer")
        end = start + pd.DateOffset(days=S.HORIZON_DAYS)
    else:
        if not isinstance(S.HORIZON_MONTHS, int) or S.HORIZON_MONTHS < 1:
            raise ValueError("HORIZON_MONTHS must be a positive integer")
        end = start + pd.DateOffset(months=S.HORIZON_MONTHS)
    expected = pd.date_range(start=start, end=end, freq="h", inclusive="left")
    if len(expected) < 2:
        raise ValueError("At least 2 hours are needed")
    return start, end, expected


def prepare_inputs():
    OUT.mkdir(exist_ok=True, parents=True)
    start, end, expected = timespan()
    net = load_network(NETWORK, workbook_format="auto", frequency_hz=60.0)
    if S.PV_BUS not in {bus.bus_id for bus in net.buses} or S.PV_BUS == net.slack_bus_id():
        raise ValueError("PV_BUS must be an existing non-slack bus")

    with ZipFile(LOAD_ARCHIVE) as z:
        load_path = next(n for n in z.namelist() if n.endswith("/load_profile.csv"))
        summ_path = next(n for n in z.namelist() if n.endswith("/bus_summary.csv"))
        all_load = pd.read_csv(io.BytesIO(z.read(load_path)),
                               usecols=["timestamp", "bus_id", "p_kw", "q_kvar"])
        bus_summary = pd.read_csv(io.BytesIO(z.read(summ_path)))

    # Distributed demand was created from the T04 workbook. Confirm that its
    # nominal per-bus P/Q agrees with the T04 network under test.
    ref = {int(row.bus_id): row for row in bus_summary.itertuples(index=False)}
    for bus in net.buses:
        if bus.bus_id not in ref:
            raise ValueError(f"Missing source bus {bus.bus_id}")
        p = sum(x.p_base_kw for x in net.loads if x.bus_id == bus.bus_id)
        q = sum(x.q_base_kvar for x in net.loads if x.bus_id == bus.bus_id)
        if abs(p - float(ref[bus.bus_id].base_p_kw)) > 1e-4 or abs(q - float(ref[bus.bus_id].base_q_kvar)) > 1e-4:
            raise ValueError(f"T04 demand mismatch at bus {bus.bus_id}")

    all_load["timestamp"] = pd.to_datetime(all_load["timestamp"], errors="raise")
    load = all_load[(all_load.timestamp >= start) & (all_load.timestamp < end)].copy()
    load = load.sort_values(["timestamp", "bus_id"]).reset_index(drop=True)
    load[["p_kw", "q_kvar"]] *= S.LOAD_MULTIPLIER
    if (load.duplicated(["timestamp", "bus_id"]).any() or
            set(load.bus_id) != {b.bus_id for b in net.buses} or
            len(load) != len(expected)*len(net.buses) or
            not pd.DatetimeIndex(load.timestamp.unique()).equals(expected)):
        raise ValueError("Incomplete hourly/bus load rows in requested period")
    if load[["p_kw", "q_kvar"]].isna().any().any() or (load[["p_kw", "q_kvar"]] < 0).any().any():
        raise ValueError("Load contains negative or non-finite values")

    solar = read_irradiance(NASA, source="nasa_power")
    solar = solar[(solar.timestamp >= start) & (solar.timestamp < end)].copy()
    solar = solar.sort_values("timestamp").reset_index(drop=True)
    if not pd.DatetimeIndex(solar.timestamp).equals(expected):
        raise ValueError("Missing irradiance hours in requested period")

    pv_model = PVModelConfig(critical_irradiance_w_m2=S.PV_CRITICAL_IRRADIANCE_W_M2)
    pv_values = [irradiance_to_power(float(g), S.PV_RATING_KW, pv_model)
                 for g in solar.irradiance_w_m2]
    pv = pd.DataFrame({"timestamp": solar.timestamp, "bus_id": S.PV_BUS,
                       "p_kw": pv_values, "q_kvar": 0.0})
    for frame in (load, pv, solar):
        frame["timestamp"] = frame.timestamp.dt.strftime("%Y-%m-%d %H:%M:%S")

    load[["timestamp", "bus_id", "p_kw", "q_kvar"]].to_csv(
        OUT/"load_profile.csv", index=False, float_format="%.8f")
    pv[["timestamp", "bus_id", "p_kw", "q_kvar"]].to_csv(
        OUT/"pv_profile.csv", index=False, float_format="%.8f")
    solar[["timestamp", "irradiance_w_m2"]].to_csv(
        OUT/"irradiance.csv", index=False, float_format="%.4f")
    loads_hourly = load.groupby("timestamp", sort=True).p_kw.sum()
    solar_hourly = pv.set_index("timestamp").p_kw
    summary = pd.DataFrame({"timestamp": loads_hourly.index,
                            "load_kw": loads_hourly.to_numpy(),
                            "pv_kw": solar_hourly.reindex(loads_hourly.index).to_numpy()})
    summary["net_load_kw"] = summary.load_kw - summary.pv_kw
    summary.to_csv(OUT/"hourly_input_summary.csv", index=False, float_format="%.6f")

    manifest = {
        "start_inclusive": str(start), "end_exclusive": str(end), "hours": len(expected),
        "month_count": S.HORIZON_MONTHS if S.HORIZON_DAYS is None else None,
        "day_override": S.HORIZON_DAYS,
        "network": NETWORK.name, "pv_bus": S.PV_BUS, "pv_rated_kw": S.PV_RATING_KW, "load_multiplier": S.LOAD_MULTIPLIER,
        "load_source": LOAD_ARCHIVE.name, "load_source_sha256":file_sha256(LOAD_ARCHIVE),
        "solar_source": NASA.name, "solar_source_sha256":file_sha256(NASA),
        "load_source_note": "Distributed from T04 System 1; verified bus-by-bus P/Q against T04 workbook",
        "solar_model": "src_accelerated.pv_model.irradiance_to_power, NASA POWER GHI proxy",
        "nasa_timezone": "UTC", "goiener_timezone": "not provided (naive)",
        "timezone_note": "Timestamp labels aligned without unsupported timezone conversion",
        "solar_site": "40.4168 N, -3.7038 W (near Madrid); not necessarily the demand location",
        "total_load_kwh": float(summary.load_kw.sum()),
        "total_pv_kwh": float(summary.pv_kw.sum()),
        "min_net_load_kw": float(summary.net_load_kw.min()),
        "solar_surplus_hours": int((summary.net_load_kw < 0).sum()),
        "note": "STRESS TEST: historical demand scaled by LOAD_MULTIPLIER; modelled PV rating modified; not measured/scheduled utility conditions. Demand/PV clocks not independently aligned"
    }
    (OUT/"input_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Prepared {len(expected)} hourly samples ({start} to {end} exclusive). ",
          f"PV bus {S.PV_BUS}; surplus hours {manifest['solar_surplus_hours']}.", flush=True)
    return manifest


if __name__ == "__main__":
    prepare_inputs()
