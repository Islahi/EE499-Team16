#!/usr/bin/env python3
"""Download and select GoiEner hourly customer profiles. Data NOT distributed with this script.
Source: https://doi.org/10.5281/zenodo.7362094
"""
from __future__ import annotations
import argparse
import csv
from contextlib import contextmanager
import subprocess
import hashlib
import io
import json
import re
import shutil
import sys
import tarfile
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

BASE = "https://zenodo.org/records/7362094/files"
CHECKSUMS = {
    "metadata.csv": "1876a8fe4f0c22080e9c7936e1b0cfde",
    "imp-pre.tzst": "77d549a1dd9fec438505930750e712db",
    "imp-in.tzst": "dc593839ad812c0dc2d854894097bc13",
    "imp-post.tzst": "1ff85d89fee75da33756c6b7bdbf7a7e",
}

def digest(path, algo="md5"):
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for block in iter(lambda:f.read(4*1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def download(filename: str, directory: Path, retries: int = 4):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    expected_md5 = CHECKSUMS[filename]
    if target.exists() and digest(target) == expected_md5:
        print(f"Already downloaded and verified: {target}")
        return
    partial = target.with_suffix(target.suffix + ".part")
    url = f"{BASE}/{filename}?download=1"
    for attempt in range(retries):
        already = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "Mozilla/5.0 (compatible; GoiEner-Research-Downloader/1.0)"}
        if already:
            headers["Range"] = f"bytes={already}-"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=90) as response:
                status = response.status
                if already and status == 200:
                    # Server ignored Range; restart rather than duplicating bytes.
                    already = 0
                elif already and status != 206:
                    raise RuntimeError(f"Unexpected HTTP status for resumed download: {status}")
                mode = "ab" if already else "wb"
                with open(partial, mode) as out:
                    count = already
                    last_report = time.monotonic()
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk: break
                        out.write(chunk)
                        count += len(chunk)
                        if time.monotonic() - last_report > 8:
                            print(f"  {filename}: {count/1048576:.1f} MiB downloaded", flush=True)
                            last_report = time.monotonic()
            print(f"Checking MD5 for {filename} ...")
            found = digest(partial)
            if found != expected_md5:
                raise ValueError(f"MD5 mismatch: got {found} expected {expected_md5}; file may be incomplete or changed")
            partial.replace(target)
            print(f"Saved and verified: {target} ({target.stat().st_size/1048576:.1f} MiB)")
            return
        except (urllib.error.URLError, OSError, RuntimeError) as exc:
            if attempt + 1 >= retries:
                raise RuntimeError(f"Download failed for {filename}. Download manually from https://zenodo.org/records/7362094 and put it in {directory}. Last error: {exc}") from exc
            print(f"Retry {attempt+1}/{retries} after error: {exc}", file=sys.stderr)
            time.sleep(min(2 ** attempt * 2, 20))
    raise AssertionError("unreachable")


def classify_cnae(cnae: str) -> str | None:
    """Conservative classification for Spanish CNAE-2009 sections.
    C=manufacturing; G=wholesale and retail trade; T=household employer activities.
    cnae may be a section letter or an activity code. Unknowns remain UNCLASSIFIED.
    """
    if cnae is None: return None
    s = str(cnae).strip().upper()
    if not s or s in {"NA", "NAN", "NONE", "NULL", "-"}: return None
    if s[0] in {"C", "G", "T"} and (len(s) == 1 or not s[1].isalpha()):
        return {"C":"manufacturing", "G":"commercial", "T":"residential"}[s[0]]
    # Numeric CNAE codes usually have 2 to 4 digits, occasionally with separators.
    digits = re.sub(r"[^0-9]", "", s)
    if not digits: return None
    number = int(digits[:2])
    if 10 <= number <= 33: return "manufacturing"
    if 45 <= number <= 47: return "commercial"
    if 97 <= number <= 98: return "residential"
    return None


def iso_date(value):
    import pandas as pd
    return pd.to_datetime(value, errors="coerce", utc=True)


def normalize_id(name):
    return Path(name).stem.strip().lower()


def pick_candidates(metadata: Path, start: str, end: str, max_per_sector: int, fallback: bool):
    import pandas as pd
    df = pd.read_csv(metadata, low_memory=False, dtype={"cnae": "string"})
    required = {"user", "cnae", "start_date", "end_date"}
    if not required.issubset(df.columns):
        raise ValueError(f"metadata missing columns {sorted(required-set(df.columns))}; found {list(df.columns)}")
    df["begin"] = pd.to_datetime(df["start_date"], errors="coerce", utc=True)
    df["finish"] = pd.to_datetime(df["end_date"], errors="coerce", utc=True)
    beginning = pd.Timestamp(start, tz="UTC")
    ending = pd.Timestamp(end, tz="UTC") + pd.Timedelta(hours=23)
    df = df[(df["begin"] <= beginning) & (df["finish"] >= ending)].copy()
    df["sector"] = df["cnae"].map(classify_cnae)
    if fallback and "contracted_tariff" in df:
        # Only *tentative* residential classification. Do not claim validated household type.
        mask = df["sector"].isna() & df["cnae"].isna() & df["contracted_tariff"].astype(str).str.startswith("2")
        df.loc[mask, "sector"] = "residential_unverified_tariff"
    if "missing_samples_pct" in df.columns:
        df["missing_samples_pct"] = pd.to_numeric(df["missing_samples_pct"], errors="coerce")
        df = df.sort_values(["missing_samples_pct", "begin"], ascending=[True, True], na_position="last")
    all_counts = df["sector"].value_counts(dropna=False).to_dict()
    available = Counter()
    selected = {}
    for _, row in df.iterrows():
        sector = row["sector"]
        if not isinstance(sector, str): continue
        if available[sector] >= max_per_sector: continue
        user = str(row["user"]).strip().lower()
        if len(user) < 10: continue
        selected[user] = (sector, {k: row[k] for k in ("cnae", "contracted_tariff", "start_date", "end_date") if k in row.index})
        available[sector] += 1
    return selected, {str(k): int(v) for k,v in all_counts.items()}


def read_csv_member(fileobj, start_ts, end_ts, coverage_limit, imputed_limit):
    import pandas as pd
    raw = fileobj.read()
    df = pd.read_csv(io.BytesIO(raw))
    if not {"timestamp", "kWh"}.issubset(df.columns): return None, "missing timestamp/kWh columns"
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["kWh"] = pd.to_numeric(df["kWh"], errors="coerce")
    df = df.dropna(subset=["timestamp", "kWh"])
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="first")
    df = df[(df["timestamp"] >= start_ts) & (df["timestamp"] <= end_ts)].copy()
    expected = int((end_ts - start_ts).total_seconds()//3600) + 1
    actual = len(df)
    if actual == 0 or actual/expected < coverage_limit:
        return None, f"coverage {actual}/{expected} ({(actual/expected)*100:.1f}%)"
    if "imputed" in df:
        df["imputed"] = pd.to_numeric(df["imputed"], errors="coerce").fillna(0).astype(int)
        imputed_rate = float((df["imputed"] != 0).mean())
        if imputed_rate > imputed_limit:
            return None, f"imputed share {imputed_rate:.1%} exceeds {imputed_limit:.1%}"
    else:
        df["imputed"] = -1
        imputed_rate = float("nan")
    df["p_kw_avg"] = df["kWh"]  # for 1-hour meter reading, kWh/1h = average kW
    return df[["timestamp", "kWh", "imputed", "p_kw_avg"]], {"coverage": round(actual/expected,4), "imputed_fraction": round(imputed_rate,4), "rows": actual}


@contextmanager
def open_zstd_tar(archive: Path):
    """Read a .tar.zst / .tzst sequentially using Python zstandard or installed zstd CLI."""
    try:
        import zstandard as zstd
    except ImportError:
        zstd = None
    if zstd is not None:
        with archive.open("rb") as inp, zstd.ZstdDecompressor().stream_reader(inp) as decompressed:
            with tarfile.open(fileobj=decompressed, mode="r|") as tf:
                yield tf
    elif shutil.which("zstd"):
        p = subprocess.Popen(["zstd", "-dc", str(archive)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            with tarfile.open(fileobj=p.stdout, mode="r|") as tf:
                yield tf
        finally:
            if p.stdout: p.stdout.close()
            code = p.wait()
            if code != 0:
                msg = p.stderr.read().decode("utf-8", errors="replace") if p.stderr else ""
                raise RuntimeError(f"zstd decompress failed (code={code}): {msg}")
            if p.stderr: p.stderr.close()
    else:
        raise RuntimeError("Install zstandard via pip OR install the zstd command-line utility")


def extract(args):
    import pandas as pd
    metadata = Path(args.metadata)
    archive = Path(args.archive)
    output = Path(args.output)
    if not metadata.exists() or not archive.exists():
        raise FileNotFoundError("metadata.csv and imp-pre.tzst are required; use download command or copy files manually")
    if args.end < args.start:
        raise ValueError("end date must be >= start date")
    start_ts = pd.Timestamp(args.start)
    end_ts = pd.Timestamp(args.end) + pd.Timedelta(days=1) - pd.Timedelta(hours=1)
    selected, counts = pick_candidates(metadata,args.start,args.end,args.max_per_sector,args.residential_fallback_tariff)
    print("Potential customer counts covering requested period, by CNAE classification:", counts)
    print("Selected potential profiles:", dict(Counter(v[0] for v in selected.values())))
    if not selected:
        raise ValueError("No customer has metadata covering the requested window. Try a shorter window, e.g. 2017-01-01 to 2018-12-31")
    output.mkdir(parents=True, exist_ok=True)
    summary = []
    found = set()
    with open_zstd_tar(archive) as tf:
            for member in tf:
                if not member.isfile() or not member.name.lower().endswith(".csv"): continue
                ident = normalize_id(member.name)
                if ident not in selected: continue
                found.add(ident)
                with tf.extractfile(member) as content:
                    if content is None: continue
                    df, quality = read_csv_member(content,start_ts,end_ts,args.min_coverage,args.max_imputed)
                sector, original = selected[ident]
                if df is None:
                    print(f"Skipped {ident[:10]} ({sector}): {quality}")
                    continue
                folder = output / sector
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / (ident + ".csv")
                df.to_csv(target, index=False)
                summary.append({"user":ident,"sector":sector,"file":str(target.relative_to(output)),
                                "start":args.start,"end":args.end, **quality,"cnae":original.get("cnae", ""),
                                "contracted_tariff":original.get("contracted_tariff", "")})
                print(f"Extracted {sector}: {len(df)} hours -> {target.name}")
    with (output/"extraction_manifest.csv").open("w", newline="", encoding="utf-8") as f:
        fields = ["user","sector","file","start","end","coverage","imputed_fraction","rows","cnae","contracted_tariff"]
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(summary)
    with (output/"data_quality.json").open("w",encoding="utf-8") as f:
        json.dump({"source":"https://doi.org/10.5281/zenodo.7362094", "target_start":args.start,
                   "target_end":args.end, "max_per_sector":args.max_per_sector,"candidate_metadata_counts":counts,
                   "extracted_counts": dict(Counter(row["sector"] for row in summary)),
                   "note":"CNAE T/97-98 represents domestic household employment activities, NOT a guaranteed sample of household electricity consumers. An empty residential sector requires manual verification; the optional tariff fallback is a heuristic.",
                   "status":"actual data from Zenodo archives"}, f, indent=2)
    print(f"Done. Extracted {len(summary)} customer profiles to {output}")
    if not summary:
        print("No selected profiles passed all data-quality filters; adjust dates/thresholds or inspect customer metadata.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    dl = sub.add_parser("download", help="Download original metadata and optional large pre-2020 archive")
    dl.add_argument("--directory", default="goiener_original")
    dl.add_argument("--with-pre", action="store_true", help="Also download 792MB imp-pre.tzst")
    ex = sub.add_parser("extract", help="Extract residential/commercial/manufacturing series from downloaded archive")
    ex.add_argument("--metadata", default="goiener_original/metadata.csv")
    ex.add_argument("--archive", default="goiener_original/imp-pre.tzst")
    ex.add_argument("--output", default="goiener_selected")
    ex.add_argument("--start", default="2017-01-01", help="Inclusive YYYY-MM-DD")
    ex.add_argument("--end", default="2019-12-31", help="Inclusive YYYY-MM-DD")
    ex.add_argument("--max-per-sector", type=int, default=5)
    ex.add_argument("--min-coverage", type=float, default=0.98)
    ex.add_argument("--max-imputed", type=float, default=0.10)
    ex.add_argument("--residential-fallback-tariff", action="store_true", help="Add unverified 2.X-tariff customers if CNAE missing")
    args = p.parse_args()
    if args.command == "download":
        download("metadata.csv",Path(args.directory))
        if args.with_pre: download("imp-pre.tzst",Path(args.directory))
        else: print("Metadata only. Run with --with-pre to download the 792MB pre-2020 load archive.")
    else: extract(args)

if __name__ == "__main__":
    try: main()
    except Exception as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        sys.exit(1)
