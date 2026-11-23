"""Read the existing GoiEner case contract without modifying distributor output."""
from dataclasses import dataclass
from hashlib import file_digest
import re
from pathlib import Path
import json

import numpy as np
import pandas as pd

from .data_loader import ProfileData
from .approved_methodology import read_manifest_assumptions
from .solar_source import utc_times

SECTORS = ("residential", "commercial", "manufacturing")


def _hash(path):
    with Path(path).open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def discover_cases(folder):
    root = Path(folder)
    def valid(path):
        return all((path / name).is_file() for name in
                   ("load_profile.csv", "bus_assignments_used.csv", "manifest.json"))
    if valid(root):
        return [root]
    cases = sorted(p for p in root.iterdir() if p.is_dir() and valid(p)) if root.is_dir() else []
    if not cases:
        raise ValueError("Choose a GoiEner case or a parent folder containing valid cases")
    return cases


def validate_assignments(frame, bus_ids, slack_id, required):
    if not {"bus_id", "category"}.issubset(frame):
        raise ValueError("Assignments require bus_id and category")
    ids = pd.to_numeric(frame.bus_id, errors="raise")
    if not np.isfinite(ids).all() or (ids % 1 != 0).any() or ids.duplicated().any():
        raise ValueError("Assignment bus IDs must be unique finite integers")
    if set(ids) - set(bus_ids):
        raise ValueError(f"Unknown assignment bus IDs: {sorted(set(ids) - set(bus_ids))}")
    result = {}
    for bus, category in zip(ids, frame.category):
        category = str(category).strip().lower()
        if int(bus) == slack_id:
            if category not in (*SECTORS, "slack", "none", "nan", ""):
                raise ValueError("Invalid slack category")
            continue
        if category not in SECTORS:
            raise ValueError(f"Bus {int(bus)} has unsupported category {category!r}")
        result[int(bus)] = category
    if set(required) - result.keys():
        raise ValueError(f"Missing sector assignments for demand buses {sorted(set(required)-result.keys())}")
    return result


@dataclass
class DistributedDataset:
    folder: Path
    profiles: ProfileData
    assignments: dict
    ratings: dict
    metadata: dict
    pv_valid: bool
    pv_reason: str


def summary_pv_ratings(summary, bus_ids=None):
    if "bus_id" not in summary:
        raise ValueError("bus_summary.csv requires a bus_id column")
    bus = pd.to_numeric(summary.bus_id, errors="raise")
    if not np.isfinite(bus).all() or (bus % 1 != 0).any() or bus.duplicated().any():
        raise ValueError("Invalid or duplicate bus IDs in bus_summary.csv")
    if bus_ids is not None and (unknown := set(bus) - set(bus_ids)):
        raise ValueError(f"Unknown bus IDs in bus_summary.csv: {sorted(unknown)}")
    if "pv_rated_kw" not in summary:
        return {}
    rated = pd.to_numeric(summary.pv_rated_kw, errors="raise")
    if not np.isfinite(rated).all() or (rated < 0).any():
        raise ValueError("PV nameplate ratings must be finite nonnegative kW")
    return {int(b): float(p) for b, p in zip(bus, rated) if p > 0}


def load_distributed(folder, network, network_path=None, clock=None):
    cases = discover_cases(folder)
    if len(cases) != 1:
        raise ValueError("Multiple cases found; select one case before importing")
    case = cases[0]
    meta = json.loads((case / "manifest.json").read_text(encoding="utf-8-sig"))
    assumptions = read_manifest_assumptions(meta)
    ids = {b.bus_id for b in network.buses}
    slack = network.slack_bus_id()
    network.validate()
    original = meta.get("network_sha256")
    selected = _hash(network_path) if network_path else None
    meta["distributor_network_sha256"] = original
    meta["selected_network_sha256"] = selected
    meta["workbook_provenance"] = (
        "Selected workbook differs from distributor's original workbook."
        if selected and original and selected != original else
        "Workbook matches distributor provenance." if selected and original else
        "Original or selected workbook fingerprint unavailable.")
    units = meta.get("simulation_units")
    if units and not re.fullmatch(r"P\s+kW\s*,\s*Q\s+kvar(?:\s*,\s*one hour average power)?", str(units).strip(), re.I):
        raise ValueError(f"Unsupported simulation_units {units!r}; expected active kW and reactive kvar")
    load = pd.read_csv(case / "load_profile.csv")
    if "timestamp" not in load:
        raise ValueError("load_profile.csv is missing the timestamp column")
    zero = load[["timestamp"]].drop_duplicates().assign(bus_id=slack, p_kw=0., q_kvar=0.)
    pv_path = case / "pv_profile.csv"
    profiles = ProfileData.__new__(ProfileData)
    profiles._from_frames(load, zero)
    if set(profiles.load_p_kw) - ids:
        raise ValueError(f"Load profiles contain unknown bus IDs: {sorted(set(profiles.load_p_kw) - ids)}")
    if pv_path.exists():
        pv_frame = pd.read_csv(pv_path)
        pv_only = ProfileData.__new__(ProfileData)
        pv_only._from_frames(zero, pv_frame)
        unknown = set(pv_only.pv_p_kw) - ids
        if unknown:
            raise ValueError(f"PV profile contains unknown bus IDs: {sorted(unknown)}")
        profiles.pv_p_kw, profiles.pv_q_kvar = pv_only.pv_p_kw, pv_only.pv_q_kvar
    required = {l.bus_id for l in network.loads if l.p_base_kw or l.q_base_kvar} - {slack}
    required |= {b for b, p in profiles.load_p_kw.items() if (np.any(p) or np.any(profiles.load_q_kvar[b])) and b != slack}
    if required - profiles.load_p_kw.keys():
        raise ValueError(f"Missing load profiles for demand buses {sorted(required - profiles.load_p_kw.keys())}")
    if np.any(profiles.load_p_kw.get(slack, [0])) or np.any(profiles.load_q_kvar.get(slack, [0])):
        raise ValueError("Slack-bus demand must be zero in sector forecasting inputs")
    assignments = validate_assignments(pd.read_csv(case / "bus_assignments_used.csv"), ids, slack, required)
    if meta.get("hours", len(profiles.timestamps)) != len(profiles.timestamps):
        raise ValueError("Manifest hours contradict the profile coverage")
    for field, stamp in (("start", profiles.timestamps[0]), ("end", profiles.timestamps[-1])):
        if meta.get(field) and pd.Timestamp(meta[field]) != stamp:
            raise ValueError(f"Manifest {field} contradicts profile timestamp {stamp}")
    source_clock = assumptions["clock"]
    if clock and source_clock and clock != source_clock:
        raise ValueError("Dataset clock conflicts with selected clock; convert timestamps explicitly")
    meta["clock"] = clock or source_clock
    utc_times(profiles.timestamps, meta["clock"])
    ratings = {}
    summary_path = case / "bus_summary.csv"
    if summary_path.exists():
        summary = pd.read_csv(summary_path)
        ratings = summary_pv_ratings(summary, ids)
        if "category" in summary:
            for row in summary.itertuples():
                if int(row.bus_id) in assignments and str(row.category).strip().lower() != assignments[int(row.bus_id)]:
                    raise ValueError("bus_summary categories conflict with explicit assignments")
    workbook_ratings = {}
    for unit in network.pv_units:
        workbook_ratings[unit.bus_id] = workbook_ratings.get(unit.bus_id, 0) + unit.p_rated_kw
    meta["pv_rating_conflicts"] = {str(b): [workbook_ratings.get(b, 0), ratings.get(b, 0)]
        for b in set(workbook_ratings)|set(ratings)
        if ratings and workbook_ratings and workbook_ratings.get(b, 0) != ratings.get(b, 0)}
    flagged = "placeholder" in str(meta.get("pv_status", "")).lower()
    nonzero = any(np.any(p) for p in profiles.pv_p_kw.values())
    pv_meta = meta.get("pv_reference") or {}
    credible = (pv_meta.get("units") == "kW" and pv_meta.get("common_source") is True and bool(meta["clock"])
                and pv_meta.get("clock",meta["clock"]) == meta["clock"])
    unrated_generation = any(np.any(p) for b, p in profiles.pv_p_kw.items() if b not in ratings)
    valid = nonzero and not unrated_generation and not flagged and credible and bool(ratings)
    failure = None
    if nonzero and not flagged:
        declared = meta.get("pv_installations_kw")
        if declared is not None:
            if not isinstance(declared, dict) or any(not str(key).isdecimal() for key in declared):
                raise ValueError("pv_installations_kw must map bus IDs to nameplate ratings")
            normalized = summary_pv_ratings(pd.DataFrame(declared.items(), columns=["bus_id", "pv_rated_kw"]), ids)
            if normalized.keys() != ratings.keys() or any(not np.isclose(normalized[b], ratings[b]) for b in ratings):
                raise ValueError("Distributor PV nameplates conflict between pv_installations_kw and bus_summary.csv")
        for name, value in (("pv_installed_capacity_kw", meta.get("pv_installed_capacity_kw")),
                            ("pv_reference.capacity_kw", assumptions["reference_capacity_kw"])):
            if value is not None and ratings and not np.isclose(float(value), sum(ratings.values())):
                raise ValueError(f"Distributor {name} conflicts with the total PV nameplate in bus_summary.csv")
        if any(np.any(q) for q in profiles.pv_q_kvar.values()):
            valid = False
            failure = "Common modeled-PV history requires unity power factor; pv_profile.csv contains nonzero q_kvar"
        if unrated_generation:
            failure = "PV generation has no distributor nameplate at bus " + ", ".join(
                str(b) for b, p in profiles.pv_p_kw.items() if b not in ratings and np.any(p))
    if valid:
        factors = []
        for b, rating in ratings.items():
            p = np.asarray(profiles.pv_p_kw.get(b, []))
            if len(p) != len(profiles.timestamps) or (p > rating+1e-6).any():
                valid = False
                failure = f"PV history for bus {b} is absent or exceeds its distributor nameplate of {rating:g} kW"
                break
            factors.append(p/rating)
        if valid and any(not np.allclose(f, factors[0], atol=1e-8, rtol=1e-6) for f in factors[1:]):
            valid = False
    hashes = {p.name: _hash(p) for p in case.iterdir()
              if p.is_file() and p.suffix in (".csv", ".json", ".txt")}
    for name, expected in meta.get("profile_hashes_sha256", {}).items():
        path = case / name
        if path.parent.resolve() != case.resolve() or not path.is_file() or (hashes[name] if name in hashes else _hash(path)) != expected:
            raise ValueError(f"Dataset source hash mismatch for {name}")
    meta["source_hashes"] = hashes
    reason = "Validated common modeled-PV history" if valid else "PV history absent, placeholder or unverified; supply a separate historical source when PV is installed"
    return DistributedDataset(case, profiles, assignments, ratings, meta, valid, failure or reason)
