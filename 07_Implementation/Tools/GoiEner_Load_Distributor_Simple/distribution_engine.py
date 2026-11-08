"""GoiEner-only, independent network load-profile distributor.

Inputs are CLEANED GoiEner sector files, not the huge .tzst archive.
Does not modify workbooks, branch data or voltage settings; does not run power flow.
The output is hourly active/reactive load by bus for the EE499 ProfileData loader.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import hashlib
import json
import re
import shutil
import sys
from typing import Callable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
CATEGORIES = ("residential", "commercial", "manufacturing")
ALIASES = {"industrial": "manufacturing", "industry": "manufacturing", "manufacture": "manufacturing",
           "residential": "residential", "commercial": "commercial", "manufacturing": "manufacturing"}
PROFILES = {
    "residential": "Residential-GoiEner-Aggregate",
    "commercial": "Commercial-GoiEner-Aggregate",
    "manufacturing": "Industrial-GoiEner-Aggregate",
}


@dataclass
class SectorData:
    source: Path
    frame: pd.DataFrame   # timestamp, residential, commercial, manufacturing
    kind: str
    value_choice: str
    note: str

    @property
    def hours(self) -> int:
        return len(self.frame)


@dataclass
class NetworkData:
    source: Path
    loads: pd.DataFrame  # bus_id, p_base_kw, q_base_kvar, pv_rated_kw
    voltage: pd.DataFrame
    slack: int

    @property
    def load_ids(self) -> list[int]:
        d = self.loads
        return d.loc[(d.p_base_kw.abs() > 0) | (d.q_base_kvar.abs() > 0), "bus_id"].astype(int).tolist()

    @property
    def pv_count(self) -> int:
        return int((self.loads.pv_rated_kw > 0).sum())


def checksum(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def category_name(value: str) -> str:
    key = str(value).lower().strip()
    if key not in ALIASES:
        raise ValueError(f"Unsupported customer type: {value!r}")
    return ALIASES[key]


def _standard_dates(values) -> pd.Series:
    d = pd.to_datetime(values, errors="raise")
    if getattr(d.dt, "tz", None) is not None:
        raise ValueError("Timezone-aware input: convert to a consistent local hourly clock before import")
    if d.isna().any():
        raise ValueError("Source has blank timestamps")
    return d


def _longest_valid_run(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Choose longest uninterrupted interval with all 3 sectors, no year or day cap."""
    ordered = frame.sort_values("timestamp").reset_index(drop=True)
    if ordered.timestamp.duplicated().any():
        raise ValueError("Duplicate GoiEner timestamps; clean the source first")
    cols = list(CATEGORIES)
    values = ordered[cols].apply(pd.to_numeric, errors="raise")
    if (values.to_numpy(dtype=float) < 0).any():
        raise ValueError("GoiEner sector powers must be nonnegative")
    ok = np.isfinite(values.to_numpy(dtype=float)).all(axis=1)
    previous = None
    start = None
    best = (0, 0)
    for i, (ts, valid) in enumerate(zip(ordered.timestamp, ok)):
        consecutive = previous is not None and ts - previous == pd.Timedelta(hours=1)
        if not valid:
            if start is not None and i - start > best[1] - best[0]:
                best = (start, i)
            start = None
        elif start is None or not consecutive:
            if start is not None and i - start > best[1] - best[0]:
                best = (start, i)
            start = i
        previous = ts
    if start is not None and len(ordered) - start > best[1] - best[0]:
        best = (start, len(ordered))
    if best[1] - best[0] < 2:
        raise ValueError("No 2-hour or longer common valid interval across the three categories")
    trimmed = ordered.iloc[best[0]:best[1]].copy().reset_index(drop=True)
    trimmed[cols] = trimmed[cols].astype(float)
    if (trimmed[cols].max() <= 0).any():
        raise ValueError("At least one GoiEner sector has zero load over the selected interval")
    return trimmed, int(len(ordered) - len(trimmed))


def _load_wide(path: Path) -> tuple[pd.DataFrame, str]:
    original = pd.read_csv(path)
    if "timestamp" not in original:
        raise ValueError("Prepared wide GoiEner CSV must contain 'timestamp'")
    selected = {}
    for category in CATEGORIES:
        candidates = [PROFILES[category], category, category.capitalize()]
        if category == "manufacturing":
            candidates += ["Industrial", "industrial", "Manufacturing"]
        match = next((name for name in candidates if name in original.columns), None)
        if match is None:
            raise ValueError(f"Wide source missing {category} column (expected {PROFILES[category]})")
        selected[category] = original[match]
    out = pd.DataFrame({"timestamp": _standard_dates(original.timestamp), **selected})
    return out, "Values are already selected by the upstream GoiEner Cleaner (average or sum)."


def _load_three(folder: Path, value_choice: str) -> tuple[pd.DataFrame, str]:
    if value_choice not in ("average", "sum"):
        raise ValueError("Profile value must be 'average' or 'sum'")
    column = "average_customer_kw" if value_choice == "average" else "load_kw"
    parts = []
    for category in CATEGORIES:
        path = folder / f"{category}.csv"
        if not path.is_file():
            raise FileNotFoundError(f"Missing cleaned category file: {path.name}")
        df = pd.read_csv(path, usecols=["timestamp", column])
        df["timestamp"] = _standard_dates(df.timestamp)
        parts.append(df.rename(columns={column: category}))
    result = parts[0]
    for part in parts[1:]:
        result = result.merge(part, on="timestamp", how="inner", validate="one_to_one")
    note = f"Three original category files merged using {column}; no raw timestamps were relabeled."
    return result, note


def load_profiles(path: Path, value_choice: str = "average") -> SectorData:
    path = Path(path).expanduser().resolve()
    if path.is_dir():
        if all((path / f"{c}.csv").is_file() for c in CATEGORIES):
            df, note = _load_three(path, value_choice)
            kind = "three-sector-files"
        elif (path / "goiener_distributor_ready.csv").is_file():
            path = path / "goiener_distributor_ready.csv"
            df, note = _load_wide(path)
            kind = "wide"
        else:
            raise FileNotFoundError("Select the CLEANER output folder containing residential.csv, commercial.csv and manufacturing.csv, or choose goiener_distributor_ready.csv directly")
    elif path.is_file():
        df, note = _load_wide(path)
        kind = "wide"
    else:
        raise FileNotFoundError(f"No profile source: {path}")
    trimmed, excluded = _longest_valid_run(df)
    note += f" Common contiguous interval: {len(trimmed):,} hours; {excluded:,} other source rows excluded."
    return SectorData(path, trimmed, kind, value_choice if kind != "wide" else "upstream-selected", note)


def load_network(path: Path, frequency_hz: float = 60.0, project_dir: Path | None = None,
                 csv_slack: int | None = None) -> NetworkData:
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    if path.suffix.lower() == ".xlsx":
        if path.stat().st_size < 256 and path.read_bytes().startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise ValueError("Workbook is a Git LFS pointer; use the actual .xlsx file")
        project = Path(project_dir or ROOT / "bundled_project").resolve()
        if str(project) not in sys.path:
            sys.path.insert(0, str(project))
        from src.network_loader import load_network as read_xlsx
        net = read_xlsx(path, frequency_hz=frequency_hz)
        ids = {int(b.bus_id): [0.0, 0.0, 0.0] for b in net.buses}
        for load in net.loads:
            ids[int(load.bus_id)][0] += float(load.p_base_kw)
            ids[int(load.bus_id)][1] += float(load.q_base_kvar)
        for pv in net.pv_units:
            ids[int(pv.bus_id)][2] += float(pv.p_rated_kw)
        loads = pd.DataFrame([(i, *v) for i, v in sorted(ids.items())],
                             columns=["bus_id", "p_base_kw", "q_base_kvar", "pv_rated_kw"])
        voltage = pd.DataFrame([{"bus_id": b.bus_id, "base_kv": b.base_kv,
                                 "source_v_set_pu": b.v_set_pu, "is_slack": b.is_slack}
                                for b in net.buses]).sort_values("bus_id")
        slack = int(net.slack_bus_id())
    elif path.suffix.lower() == ".csv":
        loads = pd.read_csv(path)
        required = {"bus_id", "p_base_kw", "q_base_kvar"}
        if not required <= set(loads.columns):
            raise ValueError("Network CSV must include bus_id,p_base_kw,q_base_kvar")
        for c in required:
            loads[c] = pd.to_numeric(loads[c], errors="raise")
        if loads.bus_id.isna().any() or (loads.bus_id % 1 != 0).any():
            raise ValueError("Bus IDs must be integer")
        loads.bus_id = loads.bus_id.astype(int)
        if csv_slack is None:
            if "is_slack" not in loads:
                raise ValueError("Network CSV requires an is_slack column")
            flag = loads.is_slack.astype(str).str.strip().str.lower().isin(("true", "1", "1.0"))
            if int(flag.sum()) != 1:
                raise ValueError("Network CSV needs exactly one is_slack=True row")
            slack = int(loads.loc[flag, "bus_id"].iloc[0])
        else:
            slack = int(csv_slack)
        if "pv_rated_kw" not in loads:
            loads["pv_rated_kw"] = 0.0
        for c in ("pv_rated_kw",):
            loads[c] = pd.to_numeric(loads[c], errors="raise")
        voltage = pd.DataFrame({"bus_id": loads.bus_id,
                                "base_kv": pd.to_numeric(loads.base_kv, errors="coerce") if "base_kv" in loads else np.nan,
                                "source_v_set_pu": pd.to_numeric(loads.v_set_pu, errors="coerce") if "v_set_pu" in loads else np.nan,
                                "is_slack": loads.bus_id.eq(slack)})
        loads = loads[["bus_id", "p_base_kw", "q_base_kvar", "pv_rated_kw"]].copy()
    else:
        raise ValueError("Network must be .xlsx or .csv")
    if loads.bus_id.duplicated().any():
        raise ValueError("Duplicate bus IDs")
    if slack not in set(loads.bus_id):
        raise ValueError("Slack bus not present in network")
    if not np.isfinite(loads[["p_base_kw", "q_base_kvar", "pv_rated_kw"]].to_numpy(float)).all():
        raise ValueError("Network contains nonfinite loads/PV ratings")
    if (loads[["p_base_kw", "q_base_kvar", "pv_rated_kw"]].to_numpy(float) < 0).any():
        raise ValueError("Load and PV base values must be >=0")
    if not loads.loc[(loads.p_base_kw > 0) | (loads.q_base_kvar > 0)].shape[0]:
        raise ValueError("Network has no demand buses")
    return NetworkData(path, loads.sort_values("bus_id").reset_index(drop=True),
                       voltage.sort_values("bus_id").reset_index(drop=True), slack)


def parse_bus_range(spec: str) -> list[int]:
    found = set()
    for part in re.split(r"[,;]", spec):
        part = part.strip()
        if not part:
            continue
        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if match:
            low, high = map(int, match.groups())
            if high < low or high - low > 100000:
                raise ValueError(f"Invalid bus range: {part}")
            found.update(range(low, high + 1))
        elif part.isdigit():
            found.add(int(part))
        else:
            raise ValueError(f"Invalid bus ID/range: {part!r}")
    return sorted(found)


def all_residential(network: NetworkData) -> dict[int, str]:
    return {bus: "residential" for bus in network.load_ids}


def demo_cycle(network: NetworkData) -> dict[int, str]:
    return {bus: CATEGORIES[i % 3] for i, bus in enumerate(network.load_ids)}


def load_mapping(path: Path, network: NetworkData) -> dict[int, str]:
    raw = pd.read_csv(path)
    if "bus_id" not in raw.columns:
        raise ValueError("Mapping CSV requires 'bus_id' column")
    label = "category" if "category" in raw else "customer_type" if "customer_type" in raw else None
    if label is None:
        raise ValueError("Mapping CSV requires 'category' or 'customer_type' column")
    out = {}
    for bus, kind in zip(raw.bus_id, raw[label]):
        bus_id = int(bus)
        if bus_id in out:
            raise ValueError(f"Duplicate assignment at bus {bus_id}")
        out[bus_id] = category_name(kind)
    validate_mapping(network, out)
    return out


def validate_mapping(network: NetworkData, mapping: dict[int, str]):
    expected = set(network.load_ids)
    actual = set(mapping)
    if expected != actual:
        raise ValueError(f"Need category for every load bus: missing {sorted(expected - actual)[:12]}"+
                         (f"; not load buses {sorted(actual - expected)[:12]}" if actual - expected else ""))
    for category in mapping.values():
        category_name(category)


def normalized_multipliers(source: SectorData, anchor: str) -> dict[str, np.ndarray]:
    if anchor not in ("mean", "peak"):
        raise ValueError("Normalization must be mean or peak")
    result = {}
    for category in CATEGORIES:
        values = source.frame[category].to_numpy(dtype="float64")
        ref = float(values.mean() if anchor == "mean" else values.max())
        if ref <= 0 or not np.isfinite(ref):
            raise ValueError(f"Cannot normalize {category}: invalid reference value")
        result[category] = values / ref
    return result


def _safe_filename(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", name)[:100] or "network"


def export_network(network: NetworkData, source: SectorData, mapping: dict[int, str],
                   destination: Path, anchor: str = "mean", allow_zero_pv: bool = False,
                   chunk_hours: int = 168, progress: Callable[[str], None] | None = None) -> dict:
    validate_mapping(network, mapping)
    if network.pv_count > 0 and not allow_zero_pv:
        raise ValueError(f"{network.pv_count} PV buses detected in {network.source.name}. GoiEner contains no PV generation. Explicitly enable zero-PV placeholders for load-only experiments or use a separate real PV profile.")
    if destination.exists():
        raise FileExistsError(f"Export destination already exists: {destination}")
    if chunk_hours < 1:
        raise ValueError("chunk_hours must be positive")
    mult = normalized_multipliers(source, anchor)
    network_values = network.loads.sort_values("bus_id").reset_index(drop=True)
    bus = network_values.bus_id.to_numpy(dtype=int)
    pbase = network_values.p_base_kw.to_numpy(dtype=float)
    qbase = network_values.q_base_kvar.to_numpy(dtype=float)
    names = [mapping.get(int(b), "residential") for b in bus]
    # No-load buses always output zero P and Q regardless of fallback name.
    # Only three sector curves are held in memory regardless of bus count.
    all_factors = np.vstack([mult[c] for c in CATEGORIES])
    category_index = np.array([CATEGORIES.index(n) for n in names], dtype=int)
    all_time = source.frame.timestamp
    pv_ids = network_values.loc[network_values.pv_rated_kw > 0, "bus_id"].to_numpy(dtype=int)
    if not len(pv_ids):
        pv_ids = np.array([network.slack], dtype=int)
    destination.mkdir(parents=True, exist_ok=False)
    try:
        load_path = destination / "load_profile.csv"
        pv_path = destination / "pv_profile.csv"
        with load_path.open("w", encoding="utf-8", newline="") as lf, pv_path.open("w", encoding="utf-8", newline="") as pf:
            load_writer = csv.writer(lf)
            pv_writer = csv.writer(pf)
            load_writer.writerow(["timestamp", "bus_id", "p_kw", "q_kvar"])
            pv_writer.writerow(["timestamp", "bus_id", "p_kw", "q_kvar"])
            for first in range(0, source.hours, chunk_hours):
                last = min(first + chunk_hours, source.hours)
                times = all_time.iloc[first:last].dt.strftime("%Y-%m-%d %H:%M:%S").to_numpy()
                for h, timestamp in enumerate(times):
                    factors = all_factors[category_index, first + h]
                    p = pbase * factors
                    q = qbase * factors
                    load_writer.writerows((timestamp, int(i), f"{pv:.8f}", f"{qv:.8f}") for i, pv, qv in zip(bus, p, q))
                    pv_writer.writerows((timestamp, int(i), "0.00000000", "0.00000000") for i in pv_ids)
                if progress:
                    progress(f"{network.source.name}: {last:,}/{source.hours:,} hours exported")
        assignments = pd.DataFrame([{"bus_id": int(i), "category": mapping[int(i)], "profile": PROFILES[mapping[int(i)]]}
                                    for i in network.load_ids])
        assignments.to_csv(destination / "bus_assignments_used.csv", index=False)
        network.voltage.to_csv(destination / "source_voltage_settings_READ_ONLY.csv", index=False)
        summary = pd.DataFrame({"bus_id": bus, "base_p_kw": pbase, "base_q_kvar": qbase,
                                "category": names, "pv_rated_kw": network_values.pv_rated_kw,
                                "mean_profile_p_kw": [float(pbase[i] * mult[names[i]].mean()) for i in range(len(bus))],
                                "peak_profile_p_kw": [float(pbase[i] * mult[names[i]].max()) for i in range(len(bus))]})
        summary.to_csv(destination / "bus_summary.csv", index=False)
        manifest = {
            "source_name": "GoiEner cleaned hourly demand profiles",
            "source_path": str(source.source),
            "source_file_hash_sha256": checksum(source.source) if source.source.is_file() else None,
            "source_description": source.note,
            "source_value": source.value_choice,
            "network_file": str(network.source),
            "network_sha256": checksum(network.source),
            "bus_count": int(len(bus)), "load_bus_count": len(mapping), "pv_bus_count": network.pv_count,
            "start": str(all_time.iloc[0]), "end": str(all_time.iloc[-1]),
            "hours": source.hours, "normalization": anchor,
            "simulation_units": "P kW, Q kvar, one hour average power",
            "pv_status": "ZERO-PV PLACEHOLDER ONLY; no measured PV series was supplied, even where PV units exist",
            "sector_assignment_status": "User-provided or declared scenario; no bus types inferred by program",
            "voltage_status": "All network voltage settings unchanged; hourly bus voltages require separate FBS",
            "profile_output_rows": int(len(bus) * source.hours),
        }
        (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (destination / "IMPORTANT_PV_AND_VOLTAGE.txt").write_text(
            "GoiEner provides electricity demand only, not PV output. pv_profile.csv contains explicit ZERO values, "
            "including for installed PV buses if the user opted in. Replace this with an appropriate real PV "
            "generation series before evaluating PV curtailment or economic BESS benefits. The original feeder "
            "workbook, topology, impedances, base kV, slack voltage and other voltage settings remain UNCHANGED. "
            "The FBS solver must calculate operating bus voltages hour by hour.\n", encoding="utf-8")
        return manifest
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def export_many(network_paths: list[Path], source: SectorData, output: Path,
                mapping_style: str, anchor: str, allow_zero_pv: bool,
                map_folder: Path | None = None, frequency_hz: float = 60.0,
                progress: Callable[[dict], None] | None = None) -> pd.DataFrame:
    if output.exists():
        raise FileExistsError(f"Output folder already exists: {output}")
    output.mkdir(parents=True)
    results = []
    used = set()
    try:
        for index, path in enumerate(network_paths, 1):
            row = {"network": str(path), "status": "failed", "output": "", "message": ""}
            try:
                case = load_network(path, frequency_hz=frequency_hz)
                if mapping_style == "all_residential":
                    mapping = all_residential(case)
                elif mapping_style == "demo_cycle":
                    mapping = demo_cycle(case)
                elif mapping_style == "csv":
                    if map_folder is None:
                        raise ValueError("Choose mapping directory when using mapping CSVs")
                    mpath = map_folder / f"{path.stem}_assignments.csv"
                    if not mpath.is_file():
                        raise FileNotFoundError(f"Missing mapping file {mpath.name}")
                    mapping = load_mapping(mpath, case)
                else:
                    raise ValueError(f"Unknown assignment mode {mapping_style}")
                name = _safe_filename(path.stem)
                if name in used:
                    name = f"{name}_{index:02d}"
                used.add(name)
                folder = output / name
                manifest = export_network(case, source, mapping, folder, anchor, allow_zero_pv,
                                          progress=(lambda msg: None))
                row.update(status="ok", output=str(folder), message=f"{manifest['hours']:,} h × {manifest['bus_count']} buses")
            except Exception as exc:
                row["message"] = f"{type(exc).__name__}: {exc}"
            results.append(row)
            if progress:
                progress({**row, "index": index, "total": len(network_paths)})
    finally:
        pd.DataFrame(results).to_csv(output / "batch_summary.csv", index=False)
    return pd.DataFrame(results)
