"""K-means representative-day scenario clustering inspired by Ahmed, Sindi et al. (2023).

Compresses a full chronological annual ProfileData (8,760 or 8,784 hours) into
a small set of probability-weighted real 24-hour medoid days so the outer Joint
Multi-BESS GA can screen fleets rapidly with an unbiased annualized economic
objective (BESS CAPEX/O&M + Shed + Curtailment + Grid Import/Export).

All final winning fleets are STILL independently verified on the uninterrupted
8,760/8,784-hour chronological year before acceptance.
"""
from dataclasses import dataclass
from math import isfinite

import numpy as np
import pandas as pd

from .data_loader import ProfileData


@dataclass(frozen=True)
class RepresentativeDay:
    """One real 24-hour medoid day with its cluster weight (number of calendar days)."""
    cluster_id: int
    day_index: int
    start_timestamp: object
    weight_days: float
    probability: float
    profile: ProfileData
    mean_stress_score: float


@dataclass(frozen=True)
class ScenarioSet:
    """Weighted collection of representative 24-hour days covering a full study year."""
    days: tuple[RepresentativeDay, ...]
    total_days: int
    annual_hours: int
    method: str = "kmeans_medoid_24h"

    @property
    def total_screened_hours(self) -> int:
        return sum(len(d.profile.timestamps) for d in self.days)

    def metadata(self) -> dict:
        return {
            "method": self.method,
            "cluster_count": len(self.days),
            "total_days": self.total_days,
            "total_screened_hours": self.total_screened_hours,
            "days": [
                {
                    "cluster_id": d.cluster_id,
                    "day_index": d.day_index,
                    "start": str(d.start_timestamp),
                    "weight_days": round(d.weight_days, 4),
                    "probability": round(d.probability, 6),
                    "stress_score": round(d.mean_stress_score, 4),
                }
                for d in self.days
            ],
        }


def _kmeans_pp(features: np.ndarray, k: int, seed: int, max_iter: int = 50):
    """Deterministic NumPy k-means++ clustering (zero external ML dependencies)."""
    n_samples = features.shape[0]
    k = max(1, min(k, n_samples))
    rng = np.random.default_rng(seed)

    # K-means++ initialization
    centroids = np.empty((k, features.shape[1]), dtype=float)
    first = int(rng.integers(0, n_samples))
    centroids[0] = features[first]
    closest_dist_sq = np.sum((features - centroids[0]) ** 2, axis=1)
    for c in range(1, k):
        total = float(closest_dist_sq.sum())
        if total <= 1e-14 or not isfinite(total):
            idx = int(rng.integers(0, n_samples))
        else:
            probs = closest_dist_sq / total
            idx = int(rng.choice(n_samples, p=probs))
        centroids[c] = features[idx]
        dist_sq = np.sum((features - centroids[c]) ** 2, axis=1)
        closest_dist_sq = np.minimum(closest_dist_sq, dist_sq)

    labels = np.zeros(n_samples, dtype=int)
    for _ in range(max_iter):
        # Compute squared Euclidean distances to every centroid
        dists = np.sum((features[:, None, :] - centroids[None, :, :]) ** 2, axis=2)
        new_labels = np.argmin(dists, axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for c in range(k):
            members = features[labels == c]
            if len(members) > 0:
                centroids[c] = members.mean(axis=0)
            else:
                # Re-seed empty cluster to the farthest point
                farthest = int(np.argmax(np.min(dists, axis=1)))
                centroids[c] = features[farthest]
    return labels, centroids


def build_kmeans_scenarios(
    profiles: ProfileData,
    baseline_result=None,
    *,
    voltage_min_pu: float = 0.95,
    n_clusters: int = 12,
    seed: int = 42,
) -> ScenarioSet:
    """Cluster hourly profiles into probability-weighted 24-hour medoid days.

    Features per day combine:
      - 24h normalized aggregate load profile
      - 24h normalized aggregate PV profile
      - daily baseline load shedding & pre-control voltage deficit (if baseline_result is given)
    """
    n_hours = len(profiles.timestamps)
    n_days = n_hours // 24
    if n_days < 1:
        # Short synthetic profile (<24h): wrap as a single representative scenario
        single = RepresentativeDay(
            cluster_id=0,
            day_index=0,
            start_timestamp=profiles.timestamps[0],
            weight_days=1.0,
            probability=1.0,
            profile=profiles,
            mean_stress_score=0.0,
        )
        return ScenarioSet(days=(single,), total_days=1, annual_hours=n_hours)

    usable_hours = n_days * 24
    total_load = np.zeros(usable_hours, dtype=float)
    for arr in profiles.load_p_kw.values():
        total_load += np.asarray(arr[:usable_hours], dtype=float)
    total_pv = np.zeros(usable_hours, dtype=float)
    for arr in profiles.pv_p_kw.values():
        total_pv += np.asarray(arr[:usable_hours], dtype=float)

    load_2d = total_load.reshape(n_days, 24)
    pv_2d = total_pv.reshape(n_days, 24)

    # Extract daily electrical stress from No-BESS baseline if aligned
    stress_shed = np.zeros(n_days, dtype=float)
    stress_volt = np.zeros(n_days, dtype=float)
    if baseline_result is not None and len(getattr(baseline_result, "steps", ())) >= usable_hours:
        steps = baseline_result.steps
        for d in range(n_days):
            s_kwh = 0.0
            v_def = 0.0
            for h in range(d * 24, (d + 1) * 24):
                step = steps[h]
                s_kwh += max(0.0, float(step.shedding_kw or 0.0))
                volts = step.pre_control_voltage_pu or (
                    step.power_flow.voltage_mag_pu if step.power_flow.converged else {}
                )
                if volts:
                    v_def += sum(max(0.0, voltage_min_pu - float(v)) for v in volts.values())
            stress_shed[d] = s_kwh
            stress_volt[d] = v_def

    # Normalize feature blocks so load, PV, and electrical stress are balanced
    def _norm(mat):
        scale = float(np.max(np.abs(mat)))
        return mat / scale if scale > 1e-12 else np.zeros_like(mat)

    load_norm = _norm(load_2d)
    pv_norm = _norm(pv_2d)
    # Give stress features explicit weight so critical shedding/undervoltage days
    # form their own clusters instead of being averaged away.
    shed_norm = _norm(stress_shed)[:, None] * 2.5
    volt_norm = _norm(stress_volt)[:, None] * 1.5
    features = np.hstack([load_norm, pv_norm, shed_norm, volt_norm])

    k = max(1, min(int(n_clusters), n_days))
    labels, centroids = _kmeans_pp(features, k, seed=seed)

    # Preserve exact annual-day scaling (including any partial trailing hours)
    day_scale = (n_hours / 24.0) / n_days
    rep_days = []
    for c in range(k):
        member_indices = np.flatnonzero(labels == c)
        if len(member_indices) == 0:
            continue
        # Select the real medoid day closest to the cluster centroid
        member_feats = features[member_indices]
        dists = np.sum((member_feats - centroids[c]) ** 2, axis=1)
        medoid_local = int(np.argmin(dists))
        day_idx = int(member_indices[medoid_local])
        start_ts = pd.Timestamp(profiles.timestamps[day_idx * 24])
        end_ts = start_ts + pd.Timedelta(hours=24)
        day_profile = profiles.slice(start_ts, end_ts)
        weight_days = float(len(member_indices)) * day_scale
        prob = float(len(member_indices)) / float(n_days)
        mean_stress = float(np.mean(stress_shed[member_indices]) + 1000.0 * np.mean(stress_volt[member_indices]))
        rep_days.append(
            RepresentativeDay(
                cluster_id=len(rep_days),
                day_index=day_idx,
                start_timestamp=profiles.timestamps[day_idx * 24],
                weight_days=weight_days,
                probability=prob,
                profile=day_profile,
                mean_stress_score=mean_stress,
            )
        )

    # Sort deterministically by day_index
    rep_days.sort(key=lambda d: d.day_index)
    rep_days = tuple(
        RepresentativeDay(
            cluster_id=i,
            day_index=d.day_index,
            start_timestamp=d.start_timestamp,
            weight_days=d.weight_days,
            probability=d.probability,
            profile=d.profile,
            mean_stress_score=d.mean_stress_score,
        )
        for i, d in enumerate(rep_days)
    )
    return ScenarioSet(days=rep_days, total_days=n_days, annual_hours=n_hours)
