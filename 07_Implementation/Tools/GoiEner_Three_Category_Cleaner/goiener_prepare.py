#!/usr/bin/env python3
"""GoiEner multi-year, three-category load cleaning and aggregation.

Input: metadata.csv and imp-pre.tzst (or a .tar/.tar.zst archive).
Output: one hourly aggregate CSV each for residential, commercial and
manufacturing plus one wide CSV usable as a GoiEner source in the EE499
Load Distributor v3. Raw sources are never changed.

CNAE caveat: CNAE 97/98 identifies household *activities*, not all domestic
metering. `--residential-tariff-proxy` additionally uses unidentified 2.x-
tariff customers as UNVERIFIED residential proxies. Never report these as
verified households.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import io
import csv
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import threading
from typing import Iterator

import numpy as np
import pandas as pd

SECTORS = ("residential", "commercial", "manufacturing")
WIDE_NAMES = {
    "residential": "Residential-GoiEner-Aggregate",
    "commercial": "Commercial-GoiEner-Aggregate",
    "manufacturing": "Industrial-GoiEner-Aggregate",
}


def classify_cnae(raw) -> str | None:
    if pd.isna(raw):
        return None
    s = str(raw).strip().upper()
    if s in ("", "NAN", "NONE", "NA", "NULL", "-"):
        return None
    if s in ("T", "G", "C"):
        return {"T": "residential", "G": "commercial", "C": "manufacturing"}[s]
    # Only numeric CNAE activity divisions, not arbitrary strings.
    digits = re.sub(r"\D", "", s)
    if len(digits) < 2:
        return None
    division = int(digits[:2])
    if 97 <= division <= 98:
        return "residential"
    if 45 <= division <= 47:
        return "commercial"
    if 10 <= division <= 33:
        return "manufacturing"
    return None


def classification(df: pd.DataFrame, residential_tariff_proxy: bool) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "user" not in df.columns or "cnae" not in df.columns:
        raise ValueError("metadata.csv needs 'user' and 'cnae' columns")
    df["user"] = df["user"].astype("string").str.strip().str.lower()
    if df["user"].isna().any() or df["user"].duplicated().any():
        raise ValueError("metadata.csv contains blank or duplicate customer IDs")
    df["sector"] = df["cnae"].map(classify_cnae)
    df["classification_basis"] = np.where(df["sector"].isna(), "unclassified", "cnae_class")
    if residential_tariff_proxy:
        if "contracted_tariff" not in df.columns:
            raise ValueError("--residential-tariff-proxy requires contracted_tariff metadata")
        tariff = df["contracted_tariff"].fillna("").astype(str).str.strip()
        mask = df["sector"].isna() & tariff.str.match(r"^2(?:[.,]|$)")
        df.loc[mask, "sector"] = "residential"
        df.loc[mask, "classification_basis"] = "UNVERIFIED_2x_tariff_proxy"
    return df


@contextmanager
def stream_tar(path: Path) -> Iterator[tarfile.TarFile]:
    if path.suffix.lower() in (".tzst", ".zst") or path.name.lower().endswith(".tar.zst"):
        try:
            import zstandard as zstd
        except ImportError:
            zstd = None
        if zstd is not None:
            with path.open("rb") as source, zstd.ZstdDecompressor().stream_reader(source) as stream:
                with tarfile.open(fileobj=stream, mode="r|") as tar:
                    yield tar
        elif shutil.which("zstd"):
            proc = subprocess.Popen(["zstd", "-dc", str(path)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
                    yield tar
            finally:
                if proc.stdout:
                    proc.stdout.close()
                code = proc.wait()
                if code != 0:
                    raise RuntimeError(f"zstd failed with status {code}")
        else:
            raise RuntimeError("Install zstandard: python -m pip install zstandard (or install zstd CLI)")
    else:
        with tarfile.open(path, mode="r|*") as tar:
            yield tar


def clean_customer(content, start: pd.Timestamp, end: pd.Timestamp):
    """Internal interpolation only; do not manufacture readings before/after participation.

    Treat duplicate local timestamps by mean aggregation; report how many.
    We interpret timezone-naive source timestamps as a consistent source clock.
    """
    try:
        raw = pd.read_csv(io.BytesIO(content.read()), low_memory=False)
    except (ValueError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        return None, {"reason": f"unreadable CSV: {exc}"}
    cols = {str(col).strip().lower(): col for col in raw.columns}
    if "timestamp" not in cols or "kwh" not in cols:
        return None, {"reason": f"missing timestamp/kWh columns: {list(raw.columns)}"}
    ts = pd.to_datetime(raw[cols["timestamp"]], errors="coerce", utc=True).dt.tz_localize(None)
    vals = pd.to_numeric(raw[cols["kwh"]], errors="coerce")
    bad_count = int((~np.isfinite(vals) | (vals < 0)).sum())
    vals = vals.where(np.isfinite(vals) & (vals >= 0), np.nan)
    df = pd.DataFrame({"timestamp": ts, "load": vals})
    invalid_dates = int(df.timestamp.isna().sum())
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return None, {"reason": "all timestamps invalid"}
    duplicate_hours = int(df.timestamp.duplicated().sum())
    # For ambiguous repeated source-clock timestamps, mean repeats; flag for review.
    hourly = df.groupby("timestamp", sort=True)["load"].mean()
    hourly = hourly.loc[(hourly.index >= start) & (hourly.index <= end)]
    if hourly.empty:
        return None, {"reason": "customer has no records in metadata time span"}
    first, last = hourly.index.min(), hourly.index.max()
    # Include internal absent hours with no restriction on the size of the gap.
    expected = pd.date_range(first, last, freq="h")
    raw_internal = hourly.reindex(expected)
    missing_internal = int(raw_internal.isna().sum())
    interpolated = raw_internal.interpolate(method="linear", limit_area="inside")
    remaining = int(interpolated.isna().sum())
    if remaining:
        # If leading/trailing corrupted data remain inside the recorded range,
        # fill using nearest observed value (NOT beyond the recorded range).
        interpolated = interpolated.ffill().bfill()
    if interpolated.isna().all():
        return None, {"reason": "no usable nonnegative readings"}
    # The provider may have already imputed records in imp-pre; capture this separately.
    source_imputed = 0
    if "imputed" in cols:
        flags = pd.to_numeric(raw[cols["imputed"]], errors="coerce").fillna(0)
        source_imputed = int((flags != 0).sum())
    return interpolated.to_numpy(dtype="float64"), {
        "first": str(expected[0]), "last": str(expected[-1]),
        "missing_hours_interpolated": missing_internal,
        "duplicate_timestamps_collapsed": duplicate_hours,
        "invalid_readings": bad_count,
        "invalid_timestamps": invalid_dates,
        "provider_preimputed_records": source_imputed,
        "hours": len(expected),
    }


def prepare(metadata: Path, archive: Path, output: Path, residential_tariff_proxy=False,
            wide_value="average", logger=print) -> dict:
    """Process all identifiable customers and all time stamps found in the archive.

    `wide_value=average` is recommended for the bus-distribution tool because
    participant counts vary over time; raw category sums are retained separately.
    """
    metadata = Path(metadata)
    archive = Path(archive)
    output = Path(output)
    if not metadata.is_file() or not archive.is_file():
        raise FileNotFoundError("Select existing metadata.csv and imp-pre.tzst")
    if wide_value not in ("average", "sum"):
        raise ValueError("wide_value must be 'average' or 'sum'")
    output.mkdir(parents=True, exist_ok=True)
    meta = classification(pd.read_csv(metadata, dtype="string", low_memory=False), residential_tariff_proxy)
    # A generous union of recorded membership spans. Output is trimmed to actual data.
    if {"start_date", "end_date"}.issubset(meta.columns):
        bounds = pd.concat([pd.to_datetime(meta.start_date, errors="coerce", utc=True),
                            pd.to_datetime(meta.end_date, errors="coerce", utc=True)]).dropna()
        if bounds.empty:
            raise ValueError("No valid metadata start/end dates")
        global_start = bounds.min().tz_localize(None).floor("h") - pd.Timedelta(days=2)
        global_end = bounds.max().tz_localize(None).ceil("h") + pd.Timedelta(days=2)
    else:
        raise ValueError("metadata requires start_date and end_date to establish the full available period")
    hours = pd.date_range(global_start, global_end, freq="h")
    if len(hours) > 300000:
        raise ValueError("Unexpectedly large timestamp span in metadata; check dates")
    logger(f"Reference date span: {hours[0]} through {hours[-1]} (trimmed to observed data on export)")
    logger("Processing every classified customer's member CSV without limiting the number of years...")
    n = len(hours)
    total = {sector: np.zeros(n, dtype=np.float64) for sector in SECTORS}
    count = {sector: np.zeros(n, dtype=np.int32) for sector in SECTORS}
    # Track whether the values were constructed via interpolation in this step.
    filled = {sector: np.zeros(n, dtype=np.int32) for sector in SECTORS}
    loaded = Counter()
    skipped = Counter()
    manifest = []
    classified = meta[meta.sector.isin(SECTORS)]
    lookups = classified.set_index("user", drop=False)
    with stream_tar(archive) as tf:
        for member in tf:
            if not member.isfile() or not member.name.lower().endswith(".csv"):
                continue
            ident = Path(member.name).stem.strip().lower()
            if ident not in lookups.index:
                continue
            row = lookups.loc[ident]
            fileobj = tf.extractfile(member)
            if fileobj is None:
                skipped["unreadable_member"] += 1
                continue
            # Per-file reading is bounded (one customer in memory at a time).
            # Use metadata start/end only as a loose sanity bound; avoid limiting
            # actual file to the selected modeling years.
            with fileobj:
                values, quality = clean_customer(fileobj, global_start, global_end)
            if values is None:
                skipped[quality.get("reason", "invalid")] += 1
                continue
            start = pd.Timestamp(quality["first"])
            start_pos = int((start - global_start).total_seconds() // 3600)
            end_pos = start_pos + len(values)
            if start_pos < 0 or end_pos > n:
                skipped["out_of_metadata_time_bounds"] += 1
                continue
            sector = row["sector"]
            total[sector][start_pos:end_pos] += values
            count[sector][start_pos:end_pos] += 1
            # Per-customer interpolated values tracked as count; for precise mask
            # we would retain all individual missing indices, which adds memory.
            # The per-customer count is kept in the manifest instead.
            loaded[sector] += 1
            manifest.append({"user": ident, "sector": sector,
                             "classification_basis": row["classification_basis"],
                             "cnae": str(row.get("cnae", "")), **quality})
            if sum(loaded.values()) % 500 == 0:
                logger(f"Processed {sum(loaded.values()):,} customers; "
                       + ", ".join(f"{s}={loaded[s]}" for s in SECTORS))
    del filled
    pd.DataFrame(manifest).to_csv(output / "customer_quality_manifest.csv", index=False)
    # Find union of observed classification streams; not metadata-only dates.
    observed_any = np.any(np.stack([count[s] > 0 for s in SECTORS]), axis=0)
    if not observed_any.any():
        raise RuntimeError("No customer series matched the metadata. Check archive and customer IDs.")
    first_idx = int(np.flatnonzero(observed_any)[0])
    last_idx = int(np.flatnonzero(observed_any)[-1]) + 1
    ix = hours[first_idx:last_idx]
    wide = pd.DataFrame({"timestamp": ix})
    sector_summary = {}
    for sector in SECTORS:
        raw_total = total[sector][first_idx:last_idx]
        n_active = count[sector][first_idx:last_idx]
        avg = np.divide(raw_total, n_active, out=np.full(len(ix), np.nan), where=n_active > 0)
        # After per-customer interpolation, gaps may remain where NO customer
        # from the sector participates. Interpolate within observed sector span.
        active = n_active > 0
        raw_series = pd.Series(np.where(active, raw_total, np.nan), index=ix)
        avg_series = pd.Series(avg, index=ix)
        filled_sum = raw_series.interpolate(method="time", limit_area="inside")
        filled_avg = avg_series.interpolate(method="time", limit_area="inside")
        gap_hours = int((~active).sum())
        # Never fill outside first/last observed sector date. Missing outside
        # span remain blank and are not reported as zero loads.
        save = pd.DataFrame({
            "timestamp": ix,
            "load_kwh": filled_sum.to_numpy(),
            "load_kw": filled_sum.to_numpy(),
            "average_customer_kw": filled_avg.to_numpy(),
            "active_customers": n_active,
            "no_customer_data_hour": (~active).astype(int),
        })
        save.to_csv(output / f"{sector}.csv", index=False, float_format="%.7f")
        wide[WIDE_NAMES[sector]] = (filled_avg if wide_value == "average" else filled_sum).to_numpy()
        sector_summary[sector] = {
            "customers_with_data": int(loaded[sector]),
            "first_observed_hour": str(ix[np.flatnonzero(active)[0]]) if active.any() else None,
            "last_observed_hour": str(ix[np.flatnonzero(active)[-1]]) if active.any() else None,
            "hours_without_customer_data_in_union": gap_hours,
            "hours_interpolated_without_any_customer": int(((~active) & filled_sum.notna().to_numpy()).sum()),
            "min_active_customers": int(n_active[active].min()) if active.any() else 0,
            "max_active_customers": int(n_active.max()),
        }
    # Full chronological union (may contain blank entries at sector boundaries).
    wide.to_csv(output / "goiener_three_profiles.csv", index=False, float_format="%.7f")
    # The original Load Distributor requires all three sector profiles finite
    # and hourly. Produce a separate longest-overlap file with NO arbitrary
    # calendar-year cap; leave complete raw histories in their own files.
    valid = wide[list(WIDE_NAMES.values())].notna().all(axis=1).to_numpy()
    longest_start, longest_end, run_start = 0, 0, None
    for pos, good in enumerate(np.r_[valid, False]):
        if good and run_start is None:
            run_start = pos
        if not good and run_start is not None:
            # Existing EE499 GUI rejects source histories that start mid-day.
            # Keep the longest full overlap starting at a midnight, without
            # adding an arbitrary end-date or 8760-hour restriction.
            midnight = next((k for k in range(run_start, min(pos, run_start + 24))
                             if ix[k].hour == 0), pos)
            if pos - midnight > longest_end - longest_start:
                longest_start, longest_end = midnight, pos
            run_start = None
    overlap_hours = longest_end - longest_start
    if overlap_hours >= 24:
        wide.iloc[longest_start:longest_end].to_csv(
            output / "goiener_distributor_ready.csv", index=False, float_format="%.7f")
        logger(f"Distributor-ready common overlap: {overlap_hours} hours (no year cap)")
    else:
        logger("WARNING: No 24+ hour common overlap across the 3 classified categories; "
               "review classifications or select compatible customers before distribution.")
    df_skipped = meta[~meta.user.isin([m["user"] for m in manifest])]
    df_skipped[["user", "cnae", "sector", "classification_basis"]].to_csv(
        output / "unclassified_or_unused_customers.csv", index=False)
    qc = {
        "input_metadata": str(metadata), "input_archive": str(archive),
        "source": "GoiEner Zenodo 7362094, pre-pandemic cleaned meter archive",
        "start": str(ix[0]), "end": str(ix[-1]), "hours_in_union": len(ix),
        "longest_common_overlap_hours": overlap_hours,
        "distributor_ready_file": "goiener_distributor_ready.csv" if overlap_hours >= 24 else None,
        "selected_classification": "CNAE numerical divisions 97-98 households activities, 45-47 trade, 10-33 manufacturing",
        "residential_tariff_proxy_enabled": bool(residential_tariff_proxy),
        "residential_proxy_caveat": "CNAE 97-98 is NOT equivalent to all domestic smart meters; 2.x tariff is an unverified proxy and may contain small businesses.",
        "wide_csv_values": wide_value,
        "wide_csv_note": "Use 'average' for a stable shape when the number of participating customers changes. Category files also include true hourly sums, active count and average.",
        "sector_statistics": sector_summary,
        "skipped_members": dict(skipped),
        "customer_quality_manifest": "customer_quality_manifest.csv",
        "input_time_note": "Timezone-naive timestamps treated as consistent source time; ambiguous duplicate hours collapsed by mean. Not a certified DST conversion.",
        "interpolation_note": "Missing internal customer hours linearly interpolated without gap-size limit; empty category hours interpolated only internally. Provider preimputation retained.",
        "source_data_status": "User-supplied archive processed locally; original archive not modified",
    }
    (output / "quality_report.json").write_text(json.dumps(qc, indent=2), encoding="utf-8")
    logger("Created three sector CSVs + wide GUI source: " + str(output))
    logger("Loaded customers: " + ", ".join(f"{s}={loaded[s]}" for s in SECTORS))
    return qc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True, help="Path to metadata.csv")
    parser.add_argument("--archive", type=Path, required=True, help="Path to imp-pre.tzst")
    parser.add_argument("--output", type=Path, required=True, help="Output folder")
    parser.add_argument("--residential-tariff-proxy", action="store_true",
                        help="Include otherwise unclassified 2.x tariff customers as UNVERIFIED residential proxies")
    parser.add_argument("--wide-value", choices=("average", "sum"), default="average")
    args = parser.parse_args()
    prepare(args.metadata, args.archive, args.output,
            residential_tariff_proxy=args.residential_tariff_proxy,
            wide_value=args.wide_value)


if __name__ == "__main__":
    main()
