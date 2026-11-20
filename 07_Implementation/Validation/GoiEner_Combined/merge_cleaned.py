#!/usr/bin/env python3
"""Merge GoiEner Pre, During, Post cleaner outputs without altering readings.

Usage:
  python merge_cleaned.py --input Cleaned.zip --output GoiEner_Combined

Dependencies: pandas, numpy. Input is a ZIP containing
Cleaned/{Pre,During,Post}/goiener_distributor_ready.csv,
Cleaned/{Pre,During,Post}/goiener_three_profiles.csv, sector CSVs, and quality_report.json.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

PERIODS = ("Pre", "During", "Post")
SECTORS = ("residential", "commercial", "manufacturing")
REQUIRED = (
    "Residential-GoiEner-Aggregate",
    "Commercial-GoiEner-Aggregate",
    "Industrial-GoiEner-Aggregate",
)


def read_table(zf: ZipFile, period: str, filename: str) -> pd.DataFrame:
    member = f"Cleaned/{period}/{filename}"
    try:
        with zf.open(member) as f:
            df = pd.read_csv(f, low_memory=False)
    except KeyError as ex:
        raise ValueError(f"Missing input file: {member}") from ex
    if "timestamp" not in df.columns:
        raise ValueError(f"No timestamp column in {member}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="raise")
    if df["timestamp"].isna().any() or df["timestamp"].duplicated().any():
        raise ValueError(f"Missing or duplicated timestamps in {member}")
    if not df["timestamp"].is_monotonic_increasing:
        raise ValueError(f"Out-of-order timestamps in {member}")
    return df


def stitch(frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    all_frames = []
    dup_events = []
    for priority, period in enumerate(PERIODS):
        f = frames[period].copy()
        f["source_period"] = period
        f["source_priority"] = priority
        all_frames.append(f)
    union = pd.concat(all_frames, ignore_index=True)
    dups = union[union.duplicated("timestamp", keep=False)]
    for ts, group in dups.groupby("timestamp", sort=True):
        if len(group) != 2:
            raise ValueError(f"Unexpected {len(group)} overlapping source records at {ts}")
        group = group.sort_values("source_priority")
        old, new = group.iloc[0], group.iloc[1]
        entry = {"timestamp": ts.isoformat(sep=" "), "old_source": old["source_period"], "chosen_source": new["source_period"]}
        for col in REQUIRED:
            if col not in group.columns:
                continue
            entry[col+"_old"] = None if pd.isna(old[col]) else float(old[col])
            entry[col+"_chosen"] = None if pd.isna(new[col]) else float(new[col])
        dup_events.append(entry)
    union = (union.sort_values(["timestamp", "source_priority"])
             .drop_duplicates("timestamp", keep="last")
             .drop(columns="source_priority")
             .sort_values("timestamp").reset_index(drop=True))
    ts = union["timestamp"]
    expected = pd.date_range(ts.min(), ts.max(), freq="h")
    if len(union) != len(expected) or not ts.equals(pd.Series(expected, name="timestamp")):
        missing = expected.difference(pd.DatetimeIndex(ts))
        raise ValueError(f"Gap or irregular timestamps in stitched series: {len(missing)} missing hours; first {missing[:5].tolist()}")
    return union.drop(columns="source_period"), union[["timestamp", "source_period"]], dup_events


def create_report(quality: dict, all_wide: pd.DataFrame, ready: pd.DataFrame,
                  overlaps: list[dict], provenance: pd.DataFrame) -> dict:
    first, last = ready["timestamp"].iloc[[0, -1]]
    return {
        "dataset": "GoiEner original Zenodo record 7362094; merged Pre/During/Post cleaned sector averages",
        "source_files": {p: quality[p].get("input_archive") for p in PERIODS},
        "source_date_ranges": {p: {"start": quality[p].get("start"), "end": quality[p].get("end"),
                                    "distributor_ready_hours": quality[p].get("longest_common_overlap_hours")}
                               for p in PERIODS},
        "merge_policy": "On the two duplicated boundary hours, keep the later archive: During over Pre and Post over During. Do not average, rescale, or interpolate stitched values.",
        "selected_output_values": "Average kW per active customer, by sector, as produced by each original cleaner run; not the summed load of all smart meters.",
        "ready_file": "goiener_distributor_ready.csv",
        "ready_start": first.strftime("%Y-%m-%d %H:%M:%S"),
        "ready_end": last.strftime("%Y-%m-%d %H:%M:%S"),
        "ready_hours": len(ready),
        "ready_missing_values_by_sector": {c: int(ready[c].isna().sum()) for c in REQUIRED},
        "ready_nonpositive_values_by_sector": {c: int((ready[c] <= 0).sum()) for c in REQUIRED},
        "all_history_file": "goiener_three_profiles.csv",
        "all_history_start": all_wide["timestamp"].iloc[0].strftime("%Y-%m-%d %H:%M:%S"),
        "all_history_end": all_wide["timestamp"].iloc[-1].strftime("%Y-%m-%d %H:%M:%S"),
        "all_history_hours": len(all_wide),
        "all_history_missing_by_sector": {c: int(all_wide[c].isna().sum()) for c in REQUIRED},
        "source_period_hour_counts_ready": provenance[provenance["timestamp"].between(first, last)]["source_period"].value_counts().to_dict(),
        "boundary_overlap_count": len(overlaps),
        "boundary_overlaps": overlaps,
        "classification": quality["Pre"].get("selected_classification"),
        "residential_tariff_proxy_enabled_in_input_reports": {p: quality[p].get("residential_tariff_proxy_enabled") for p in PERIODS},
        "input_time_note": quality["Pre"].get("input_time_note"),
        "limitations": [
            "Archive periods can have different customer cohorts, affecting sector averages at archive boundaries.",
            "The existing cleaner's preimputation and gap-filling were retained; this merge did not add further interpolation.",
            "The residential tariff proxy is enabled in all uploaded quality reports, even if it was assumed to be unchecked.",
            "CNAE divisions 97-98 do not represent all residential customers; tariff 2.x is a proxy, not verified household classification.",
            "Timestamps are timezone-naive; align them carefully with NASA POWER UTC before joint simulations.",
            "This is a category-average profile suitable for load-distribution shape construction, not actual aggregate feeder consumption.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="ZIP containing Cleaned/{Pre,During,Post}")
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f"Output directory not empty: {args.output}")
    args.output.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.input) as zf:
        quality = {p: json.loads(zf.read(f"Cleaned/{p}/quality_report.json")) for p in PERIODS}
        for period in PERIODS:
            assert quality[period]["wide_csv_values"] == "average", "Source files are not comparable (different wide_csv_values)"
        ready_frames = {p: read_table(zf, p, "goiener_distributor_ready.csv") for p in PERIODS}
        wide_frames = {p: read_table(zf, p, "goiener_three_profiles.csv") for p in PERIODS}
        for p in PERIODS:
            if list(ready_frames[p].columns) != ["timestamp", *REQUIRED]:
                raise ValueError(f"Unexpected ready schema in {p}")
            if list(wide_frames[p].columns) != ["timestamp", *REQUIRED]:
                raise ValueError(f"Unexpected wide schema in {p}")
        ready, ready_source, overlaps = stitch(ready_frames)
        wide, wide_source, wide_overlaps = stitch(wide_frames)
        # The ready interval must be fully represented in all-history values.
        aligned = wide.set_index("timestamp").loc[ready["timestamp"], REQUIRED]
        if not np.allclose(aligned.to_numpy(), ready[list(REQUIRED)].to_numpy(), rtol=0, atol=1e-8, equal_nan=True):
            raise ValueError("Ready and wide profiles disagree after merging")
        if ready[list(REQUIRED)].isna().any().any():
            raise ValueError("The proposed distributor-ready merged interval contains NaNs")
        if (ready[list(REQUIRED)] < 0).any().any():
            raise ValueError("Negative category profile value encountered")
        ready.to_csv(args.output / "goiener_distributor_ready.csv", index=False, date_format="%Y-%m-%d %H:%M:%S", float_format="%.10g")
        wide.to_csv(args.output / "goiener_three_profiles.csv", index=False, date_format="%Y-%m-%d %H:%M:%S", float_format="%.10g")
        wide_source.rename(columns={"source_period":"source_archive_period"}).to_csv(
            args.output / "source_periods.csv", index=False, date_format="%Y-%m-%d %H:%M:%S")
        # Preserve the three sector's detailed time-series measurements from each archive.
        sector_dir = args.output / "sector_details"
        sector_dir.mkdir(exist_ok=True)
        for sector in SECTORS:
            f = {p: read_table(zf, p, sector + ".csv") for p in PERIODS}
            combined, _, _ = stitch(f)
            combined.to_csv(sector_dir / (sector + ".csv"), index=False,
                            date_format="%Y-%m-%d %H:%M:%S", float_format="%.10g")
        report = create_report(quality, wide, ready, overlaps, ready_source)
        (args.output / "quality_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        pd.DataFrame(overlaps).to_csv(args.output / "boundary_comparison.csv", index=False)
        # Basic monthly diagnostic means; time indexes indicate local source clock (not certified UTC).
        monthly = ready.copy()
        monthly["month"] = monthly["timestamp"].dt.to_period("M").astype(str)
        by_month = monthly.groupby("month", as_index=False)[list(REQUIRED)].mean()
        by_month.to_csv(args.output / "monthly_category_means.csv", index=False)
    print(f"Merged continuous ready range: {report['ready_start']} to {report['ready_end']} ({len(ready):,} hours)")
    print(f"All-history wide range: {report['all_history_start']} to {report['all_history_end']} ({len(wide):,} hours, some sectors absent outside common interval)")
    print(f"Overlap hours resolved with later archive: {len(overlaps)}")
    print(f"Saved to: {args.output.resolve()}")

if __name__ == "__main__":
    main()
