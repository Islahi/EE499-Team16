"""Read the existing GoiEner case contract without modifying distributor output."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json

import numpy as np
import pandas as pd

from .data_loader import ProfileData

SECTORS = ("residential", "commercial", "manufacturing")


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
        raise ValueError("Assignments contain unknown network buses")
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
    if (not np.isfinite(bus).all() or (bus % 1 != 0).any() or bus.duplicated().any()
            or (bus_ids is not None and set(bus) - set(bus_ids))):
        raise ValueError("Invalid, duplicate or unknown bus IDs in bus_summary.csv")
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
    ids = {b.bus_id for b in network.buses}
    slack = network.slack_bus_id()
    if meta.get("bus_count", len(ids)) != len(ids):
        raise ValueError("Dataset bus count differs from the electrical network")
    expected_hash = meta.get("network_sha256")
    if expected_hash and network_path and expected_hash != sha256(Path(network_path).read_bytes()).hexdigest():
        raise ValueError("Dataset network SHA256 differs from the selected workbook")
    load = pd.read_csv(case / "load_profile.csv")
    zero = load[["timestamp"]].drop_duplicates().assign(bus_id=slack, p_kw=0., q_kvar=0.)
    pv_path = case / "pv_profile.csv"
    profiles = ProfileData.__new__(ProfileData)
    profiles._from_frames(load, zero)
    if set(profiles.load_p_kw) - ids:
        raise ValueError("Load profiles contain unknown network bus IDs")
    pv_error = None
    if pv_path.exists():
        try:
            pv_only = ProfileData.__new__(ProfileData)
            pv_only._from_frames(zero, pd.read_csv(pv_path))
            if set(pv_only.pv_p_kw)-ids:
                raise ValueError("PV profile contains unknown bus IDs")
            profiles.pv_p_kw, profiles.pv_q_kvar = pv_only.pv_p_kw, pv_only.pv_q_kvar
        except (ValueError,TypeError) as error:
            pv_error = str(error)
            meta["pv_validation_error"] = pv_error
    required = {l.bus_id for l in network.loads if l.p_base_kw or l.q_base_kvar} - {slack}
    required |= {b for b, p in profiles.load_p_kw.items() if np.any(p) and b != slack}
    if required - profiles.load_p_kw.keys():
        raise ValueError("Dataset is missing demand buses required by the network")
    if np.any(profiles.load_p_kw.get(slack, [0])):
        raise ValueError("Slack-bus demand must be zero in sector forecasting inputs")
    assignments = validate_assignments(pd.read_csv(case / "bus_assignments_used.csv"), ids, slack, required)
    if meta.get("hours", len(profiles.timestamps)) != len(profiles.timestamps):
        raise ValueError("Manifest hours contradict the profile coverage")
    source_clock = meta.get("clock") or meta.get("timezone") or meta.get("time_zone")
    if clock and source_clock and clock != source_clock:
        raise ValueError("Dataset clock conflicts with selected clock; convert timestamps explicitly")
    meta["clock"] = clock or source_clock
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
    valid = nonzero and not unrated_generation and not flagged and credible and bool(ratings) and pv_error is None
    if valid:
        factors = []
        for b, rating in ratings.items():
            p = np.asarray(profiles.pv_p_kw.get(b, []))
            if len(p) != len(profiles.timestamps) or (p > rating+1e-6).any():
                valid = False
                break
            factors.append(p/rating)
        if valid and any(not np.allclose(f, factors[0], atol=1e-8, rtol=1e-6) for f in factors[1:]):
            valid = False
    for name, expected in meta.get("profile_hashes_sha256", {}).items():
        path = case / name
        if path.parent.resolve() != case.resolve() or not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Dataset source hash mismatch for {name}")
    meta["source_hashes"] = {p.name: sha256(p.read_bytes()).hexdigest() for p in case.iterdir()
                             if p.is_file() and p.suffix in (".csv", ".json", ".txt")}
    reason = "Validated common modeled-PV history" if valid else "PV history absent, placeholder or unverified; supply a separate historical source when PV is installed"
    return DistributedDataset(case, profiles, assignments, ratings, meta, valid, reason)
