"""NASA POWER irradiance -> hourly PV generation for GoiEner distributor.

Input GoiEner timestamps are naive labels; the user-selected source clock is a
DECLARATION/ASSUMPTION, never inferred from the machine. NASA POWER input is UTC.
All physical network and load input files remain untouched.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd


def checked_clock(value: str) -> str:
    name = str(value or "").strip()
    if not name or name.upper() == "LST":
        raise ValueError("Declare an actual IANA clock or UTC; NASA LST is not a civil timezone")
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown clock {name!r}; use UTC or an IANA timezone (install tzdata if required)") from exc
    return name


def read_nasa_csv(path: str | Path) -> pd.DataFrame:
    """Accept NASA POWER ASCII/CSV or timestamp,irradiance_w_m2 prepared CSV.

    All returned timestamps denote UTC. Raw NASA Wh/m2 hourly values are
    numerically equal to mean W/m2 over a one-hour interval.
    """
    path = Path(path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"NASA irradiance CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        lines = [f.readline() for _ in range(100)]
    skip = None
    for i, line in enumerate(lines):
        clean = line.lstrip("# ").strip().upper()
        if ("YEAR" in clean and "ALLSKY_SFC_SW_DWN" in clean) or (
            "TIMESTAMP" in clean and ("IRRADIANCE_W_M2" in clean or "GHI_WH_M2" in clean)
        ):
            skip = i
            break
    if skip is None:
        raise ValueError("NASA CSV needs YEAR,MO,DY,HR,ALLSKY_SFC_SW_DWN "
                         "or timestamp,irradiance_w_m2")
    table = pd.read_csv(path, skiprows=skip, encoding="utf-8-sig", skipinitialspace=True)
    table.columns = table.columns.str.strip()
    columns = {name.upper(): name for name in table.columns}
    if {"YEAR", "MO", "DY", "HR", "ALLSKY_SFC_SW_DWN"}.issubset(columns):
        parts = {}
        for key, alias in (("YEAR", "year"), ("MO", "month"), ("DY", "day"), ("HR", "hour")):
            parts[alias] = pd.to_numeric(table[columns[key]], errors="raise").astype(int)
        ts = pd.to_datetime(pd.DataFrame(parts), errors="raise")
        irradiation = table[columns["ALLSKY_SFC_SW_DWN"]]
    elif "TIMESTAMP" in columns and ("IRRADIANCE_W_M2" in columns or "GHI_WH_M2" in columns):
        ts = pd.to_datetime(table[columns["TIMESTAMP"]], errors="raise", utc=True).dt.tz_localize(None)
        irradiation = table[columns.get("IRRADIANCE_W_M2", columns.get("GHI_WH_M2"))]
        if "SOURCE_CLOCK" in columns:
            clocks = table[columns["SOURCE_CLOCK"]].astype(str).str.strip().unique()
            if len(clocks) != 1 or clocks[0].upper() != "UTC":
                raise ValueError("Prepared irradiance CSV must explicitly use UTC; convert from LST/local time first")
    else:
        raise ValueError("Required NASA POWER irradiance columns are missing")
    vals = pd.to_numeric(irradiation, errors="raise").to_numpy(dtype=float)
    if not np.isfinite(vals).all() or (vals < 0).any() or (vals > 2000).any():
        raise ValueError("Irradiance contains missing/-999, negative, or implausibly high values")
    result = pd.DataFrame({"timestamp": ts, "irradiance_w_m2": vals})
    if result.timestamp.isna().any() or result.timestamp.duplicated().any():
        raise ValueError("NASA UTC series contains invalid or duplicated timestamps")
    result = result.sort_values("timestamp").reset_index(drop=True)
    return result


def parse_bus_ratings(text: str, known_buses, slack: int) -> dict[int, float]:
    """Parse '5:100, 7:100, 10:150' without changing feeder workbook."""
    allowed = {int(b) for b in known_buses}
    result: dict[int, float] = {}
    if not str(text or "").strip():
        return result
    for token in re.split(r"[,;\\n]+", text):
        token = token.strip()
        if not token:
            continue
        match = re.fullmatch(r"(\\d+)\\s*:\\s*(\\d+(?:\\.\\d+)?)", token)
        if not match:
            raise ValueError(f"PV entry {token!r} is invalid; use bus:rating, e.g. 5:100")
        bus = int(match.group(1))
        rating = float(match.group(2))
        if bus not in allowed or bus == int(slack):
            raise ValueError(f"PV bus {bus} is missing from the network or is the slack bus")
        if rating <= 0 or not np.isfinite(rating):
            raise ValueError("PV installed capacity must be a positive finite kW value")
        if bus in result:
            raise ValueError(f"Duplicate PV bus {bus}")
        result[bus] = rating
    return result


def apply_pv_and_clock(destination: Path, demand_timestamps, network, clock: str,
                       nasa_csv: str | Path | None = None,
                       pv_overrides: dict[int, float] | None = None,
                       site_lat: float | None = None, site_lon: float | None = None,
                       clock_confirmed: bool = False) -> dict:
    """Finalize one existing exported case for strict EE499 one-folder import."""
    destination = Path(destination)
    clock = checked_clock(clock)
    if (site_lat is None) != (site_lon is None):
        raise ValueError("Specify both NASA site latitude and longitude, or neither")
    if site_lat is not None:
        site_lat, site_lon = float(site_lat), float(site_lon)
        if not (np.isfinite(site_lat) and np.isfinite(site_lon)
                and -90 <= site_lat <= 90 and -180 <= site_lon <= 180):
            raise ValueError("NASA site coordinates must be valid decimal degrees")
    manifest_path = destination / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["clock"] = clock
    manifest["clock_status"] = ("USER_DECLARED_SOURCE_CLOCK" if clock_confirmed
                                else "UTC_ASSUMED_UNVERIFIED")
    manifest["clock_alignment_method"] = (
        "GoiEner timestamps preserved. NASA UTC is matched to the explicitly selected "
        "GoiEner source clock; that selection is not independent proof of the source timezone."
    )
    manifest["clock_validation_required_for_formal_study"] = True
    manifest["source_clock_provenance"] = "Selected by operator; original GoiEner source clock not documented"
    if site_lat is not None:
        manifest["site"] = {"latitude": site_lat, "longitude": site_lon,
                            "label": "Operator-supplied NASA irradiance site"}
    if pv_overrides is None:
        ratings = {int(row.bus_id): float(row.pv_rated_kw)
                   for row in network.loads.itertuples() if float(row.pv_rated_kw) > 0}
    else:
        ratings = {int(k): float(v) for k, v in pv_overrides.items()}
    valid_ids = set(network.loads.bus_id.astype(int))
    for bus, rated in ratings.items():
        if bus not in valid_ids or bus == int(network.slack) or not np.isfinite(rated) or rated <= 0:
            raise ValueError(f"Invalid PV installation at bus {bus}: {rated} kW")
    summary_path = destination / "bus_summary.csv"
    summary = pd.read_csv(summary_path)
    summary["pv_rated_kw"] = summary.bus_id.astype(int).map(ratings).fillna(0.0)
    summary.to_csv(summary_path, index=False)
    manifest["pv_installations_kw"] = {str(k): v for k, v in sorted(ratings.items())}
    manifest["pv_installed_capacity_kw"] = float(sum(ratings.values()))
    manifest["pv_bus_count"] = len(ratings)
    times = pd.DatetimeIndex(pd.to_datetime(demand_timestamps, errors="raise"))
    if times.tz is not None:
        raise ValueError("GoiEner timestamps must be timezone-naive input labels")
    if nasa_csv is not None:
        if not ratings:
            raise ValueError("NASA solar selected, but no PV bus ratings are configured. Set bus:kW PV locations.")
        nasa_csv = Path(nasa_csv).expanduser().resolve()
        weather = read_nasa_csv(nasa_csv)
        # Do not silently shift ambiguous daylight-saving or nonexistent hours.
        try:
            utc_times = times.tz_localize(clock, ambiguous="raise", nonexistent="raise").tz_convert("UTC").tz_localize(None)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Could not align demand clock {clock!r} with NASA UTC. "
                             "Check DST ambiguity and original demand timezone.") from exc
        solar = weather.set_index("timestamp")["irradiance_w_m2"].reindex(utc_times)
        if solar.isna().any():
            count = int(solar.isna().sum())
            first = str(utc_times[np.flatnonzero(solar.isna().to_numpy())[0]])
            raise ValueError(f"NASA irradiance is missing {count:,} demanded UTC hours; first missing: {first}")
        ghi = solar.to_numpy(dtype=float)
        critical, standard = 120.0, 1000.0
        factors = np.where(ghi < critical, (ghi / standard) * (ghi / critical),
                           np.minimum(ghi / standard, 1.0))
        factors = np.clip(factors, 0.0, 1.0)
        if not np.any(factors > 0):
            raise ValueError("NASA irradiance is zero throughout the selected demand interval")
        pv_path = destination / "pv_profile.csv"
        with pv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["timestamp", "bus_id", "p_kw", "q_kvar"])
            for stamp, factor in zip(times.strftime("%Y-%m-%d %H:%M:%S"), factors):
                for bus, rated in sorted(ratings.items()):
                    writer.writerow([stamp, bus, f"{factor * rated:.8f}", "0.00000000"])
        irradiance_path = destination / "solar_irradiance.csv"
        pd.DataFrame({"timestamp": times.strftime("%Y-%m-%d %H:%M:%S"),
                      "irradiance_w_m2": ghi,
                      "site_lat": site_lat,
                      "site_lon": site_lon,
                      "source_clock": clock}).to_csv(irradiance_path, index=False)
        shutil.copy2(nasa_csv, destination / "nasa_irradiance_source.csv")
        annual_index = (times.year == 2021)
        total_rating = sum(ratings.values())
        manifest["pv_2021_energy_mwh"] = round(float(factors[annual_index].sum() * total_rating / 1000), 6)
        manifest["pv_2021_peak_kw"] = round(float(factors[annual_index].max() * total_rating), 6) if annual_index.any() else 0.0
        manifest["pv_status"] = "NONZERO MODELED HISTORICAL PV from NASA POWER irradiance; not measured plant output"
        manifest["pv_generation_is_modeled"] = True
        manifest["pv_conversion_source_file"] = "solar_irradiance.csv"
        manifest["pv_profile_rows"] = int(len(times) * len(ratings))
        manifest["pv_reference"] = {
            "units": "kW", "common_source": True, "clock": clock,
            "capacity_kw": total_rating,
            "source": "NASA POWER ALLSKY_SFC_SW_DWN",
            "model": "EE499 piecewise GHI proxy, 120/1000 W/m2, unity PF; no temperature/inverter losses",
            "critical_irradiance_w_m2": 120.0, "standard_irradiance_w_m2": 1000.0,
            "not_measured_generation": True,
        }
        if site_lat is not None:
            manifest["pv_reference"]["site"] = manifest["site"]
        manifest["nasa_irradiance_source_sha256"] = hashlib.sha256(nasa_csv.read_bytes()).hexdigest()
        (destination / "IMPORTANT_PV_AND_VOLTAGE.txt").write_text(
            "Modeled nonzero PV generation imported from NASA POWER irradiance. "
            "Network workbook and bus load profiles are not changed. "
            "Solar output is modeled (not measured). Verify GoiEner source time zone before formal study. "
            "Use dataset PV history; do not enable fallback solar a second time.\\n", encoding="utf-8")
    else:
        manifest["pv_status"] = "ZERO-PV PLACEHOLDER ONLY; no NASA/actual generation supplied"
        manifest["pv_generation_is_modeled"] = False
        manifest["pv_reference"] = {}
    manifest["profile_hashes_sha256"] = {
        filename: hashlib.sha256((destination / filename).read_bytes()).hexdigest()
        for filename in ("load_profile.csv", "pv_profile.csv", "bus_summary.csv", "bus_assignments_used.csv")
    }
    if (destination / "solar_irradiance.csv").exists():
        manifest["profile_hashes_sha256"]["solar_irradiance.csv"] = hashlib.sha256(
            (destination / "solar_irradiance.csv").read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8")
    return manifest
