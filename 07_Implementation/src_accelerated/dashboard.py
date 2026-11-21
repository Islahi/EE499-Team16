"""Build and package offline reports from canonical run exports."""
import argparse
from base64 import b64encode
import csv
from dataclasses import asdict
from gzip import compress
from hashlib import file_digest, sha256
import json
from math import isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from .network_layout import build_layout
from .study_session import _json_value


ASSETS = Path(__file__).parent / "assets"
RUN_FILE = "dashboard_run.json"
MANIFEST_FILE = "dashboard_manifest.json"
HTML_FILE = "dashboard.html"
SCHEMA = 2
CHUNK_HOURS = 168
TABLES = ("hourly.csv", "buses.csv", "branches.csv", "metrics.csv", "evaluations.csv", "service_by_bus.csv",
          "convergence.csv", "economic_comparison.csv", "comparison.csv",
          "bus_voltages.csv", "line_flows.csv")
UNITS = {"power": "kW", "reactive_power": "kvar", "energy": "kWh", "voltage": "pu",
         "current": "A", "soc": "fraction", "duration": "hours", "annual_cost": "USD/year"}


def _safe_json(value):
    if isinstance(value, float) and not isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): _safe_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json(item) for item in value]
    return _json_value(value)


def _json(value):
    return json.dumps(_safe_json(value), ensure_ascii=False, allow_nan=False, separators=(",", ":"), default=str)


def _hash(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def _atomic_write(path, content):
    with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        target = Path(temporary.name)
        try:
            for part in (content,) if isinstance(content, str) else content:
                temporary.write(part.encode("utf-8"))
        except BaseException:
            temporary.close()
            target.unlink(missing_ok=True)
            raise
    try:
        target.replace(path)
    finally:
        target.unlink(missing_ok=True)


def write_run_metadata(folder, network, kind, context, simulation, *, optimizer=None,
                       snapshot=None, scenarios=None):
    """Save immutable run identity, original settings and schematic geometry."""
    folder = Path(folder)
    layout = build_layout(network)
    topology = {"buses": [asdict(bus) for bus in sorted(network.buses, key=lambda bus: bus.bus_id)],
                "lines": [asdict(line) for line in sorted(network.lines, key=lambda line: line.line_id)],
                "base_power_kva": network.base_power_kva, "frequency_hz": network.frequency_hz}
    metadata = {
        "run_id": context.get("Run ID") or str(uuid4()), "folder": folder.name, "kind": kind, "context": context,
        "solver": {"name": "FBS Numba CPU", "config": asdict(simulation.fbs_config)},
        "network_control": ("static_fbs" if snapshot is not None else "legacy_proportional_validation"
                            if simulation.legacy_proportional_validation else "bus_specific_joint"),
        "simulation": context.get("Simulation settings", asdict(simulation)), "optimizer": optimizer, "static": snapshot,
        "scenarios": scenarios or {".": kind},
        "topology": topology,
        "topology_sha256": sha256(_json(topology).encode("utf-8")).hexdigest(),
        "layout": {"positions": layout.positions, "routes": layout.routes},
        "pv_buses": sorted({pv.bus_id for pv in network.pv_units}),
        "pv_installations": [asdict(pv) for pv in network.pv_units],
    }
    with (folder / RUN_FILE).open("x", encoding="utf-8") as stream:
        stream.write(_json(metadata))


def _read_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else default


def _cell(value, key):
    if value is None or value == "" or value in ("nan", "inf", "-inf"):
        return None
    if (key in ("timestamp", "line_id", "axis", "message", "messages", "bess_limit_reason",
                "metric", "unit", "alternative", "currency", "fbs_message", "notes",
                "voltage_violation_bus_ids", "status")):
        return value
    if value in ("True", "False"):
        return value == "True"
    try:
        return int(value)
    except ValueError:
        try:
            number = float(value)
            return number if isfinite(number) else None
        except ValueError:
            return value


def _rows(path):
    if path.is_file():
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                yield {key: _cell(value, key) for key, value in row.items()}


def _entity_columns(path, key, time_indices, fields=None):
    """Use timestamp-indexed columns to avoid repeating bus IDs and JSON keys."""
    entities = {}
    size = len(time_indices)
    for row in _rows(path):
        index = time_indices.get(row["timestamp"]) if "timestamp" in row else 0
        entity = str(row[key])
        if index is None or index >= size:
            continue
        columns = entities.setdefault(entity, {})
        for field, value in row.items():
            if field not in ("timestamp", "step_index", key) and (fields is None or field in fields):
                if field not in columns:
                    columns[field] = [None] * size
                columns[field][index] = value
    return entities


def _scenario(folder, label, static):
    hourly = list(_rows(folder / "hourly.csv"))
    if not hourly and static is not None:
        hourly = [static]
    if not hourly and (folder / "bus_voltages.csv").is_file():
        hourly = [{"timestamp": "Static base case"}]
    indices = {row["timestamp"]: index for index, row in enumerate(hourly)}
    buses = _entity_columns(folder / "buses.csv", "bus_id", indices, {
        "voltage_pu", "voltage_angle_deg", "load_input_kw", "load_input_kvar", "pv_input_kw",
        "pv_input_kvar", "bess_input_kw", "curtailment_kw", "shedding_kw", "diagnostic_only",
        "requested_load_kw", "requested_load_kvar", "shedding_kvar", "remaining_load_fraction",
        "available_pv_kw", "pre_control_voltage_pu", "shed_load_percent", "fully_disconnected"})
    branches = _entity_columns(folder / "branches.csv", "line_id", indices, {
        "current_a", "sending_p_kw", "sending_q_kvar", "loss_p_kw", "diagnostic_only"})
    if static is not None or (folder / "bus_voltages.csv").is_file():
        buses = _entity_columns(folder / "bus_voltages.csv", "bus_id", indices)
        branches = _entity_columns(folder / "line_flows.csv", "line_id", indices)
        for kind in ("load", "pv"):
            for row in _rows(folder / "inputs" / f"{kind}_profile.csv"):
                columns = buses.setdefault(str(row["bus_id"]), {})
                columns[f"{kind}_input_kw"] = [row["p_kw"]]
                columns[f"{kind}_input_kvar"] = [row["q_kvar"]]
    events = []
    if (folder / "dispatch_events.jsonl").is_file():
        with (folder / "dispatch_events.jsonl").open(encoding="utf-8") as stream:
            events = [json.loads(line) for line in stream if line.strip()]
    return {"label": label, "hours": hourly, "buses": buses, "branches": branches,
            "metrics": list(_rows(folder / "metrics.csv")), "events": events,
            "service_by_bus": list(_rows(folder / "service_by_bus.csv"))}


def _source_files(folder, scenarios):
    for relative in scenarios:
        directory = folder / relative
        for path in sorted(directory.iterdir()):
            if (path.is_file() and not path.is_symlink() and path.name != MANIFEST_FILE
                    and (path.suffix in (".csv", ".json", ".jsonl") or path.name in ("summary.md", "summary.txt"))):
                yield path
    for directory in ("inputs",):
        source = folder / directory
        if source.is_dir():
            yield from sorted(path for path in source.iterdir() if path.is_file() and not path.is_symlink())
    if (folder / RUN_FILE).is_file():
        yield folder / RUN_FILE


def _scenario_folder(folder, name):
    directory = (folder / name).resolve()
    if name not in (".", "no_bess", "best_bess") or not directory.is_relative_to(folder):
        raise ValueError("Unexpected report scenario path")
    return directory


def _pack(value):
    raw = _json(value).encode("utf-8")
    return len(raw), b64encode(compress(raw, compresslevel=4, mtime=0)).decode("ascii")


def _scenario_blocks(scenario, metadata, add):
    """Keep the summary small and store exact traces behind independent blocks."""
    hours, events, buses = (scenario[name] for name in ("hours", "events", "buses"))
    hour_count = len(hours)
    has_bess = any(row.get("bess_accepted_soc") is not None for row in hours)
    minimum_hour = min((row for row in hours if row.get("converged") is not False
                        and row.get("voltage_min_pu") is not None), key=lambda row: row["voltage_min_pu"], default={})
    index = {row["timestamp"]: i for i, row in enumerate(hours)}
    minimum_index = index.get(minimum_hour.get("timestamp"), 0)
    low_buses = [(columns["voltage_pu"][minimum_index], bus) for bus, columns in buses.items()
                 if columns.get("voltage_pu") and columns["voltage_pu"][minimum_index] is not None]
    worst_bus = ((minimum_hour.get("minimum_voltage_bus") or minimum_hour.get("min_voltage_bus"))
                or (min(low_buses)[1] if low_buses else None))
    diagnostic = {
        "nonconverged": sum(row.get("converged") is False for row in hours),
        "infeasible": sum(row.get("feasible") is False or row.get("converged") is False for row in hours),
        "known_status": any(row.get("feasible") is not None or row.get("converged") is False for row in hours),
        "worst_voltage_pu": minimum_hour.get("voltage_min_pu"), "worst_bus": worst_bus,
        "shedding_hours": sum((row.get("shedding_kw") or 0) > 1e-9 for row in hours)
        if any(row.get("shedding_kw") is not None for row in hours) else None,
        "curtailment_hours": sum((row.get("curtailment_kw") or 0) > 1e-9 for row in hours)
        if any(row.get("curtailment_kw") is not None for row in hours) else None,
        "battery_limiter_hours": sum(row.get("bess_limited") is True for row in hours) if has_bess else None,
    }
    event_chunks = {}
    unmatched_events = []
    event_index = []
    for event in events:
        hour_index = index.get(event["timestamp"])
        if hour_index is None:
            unmatched_events.append(event)
            continue
        event_chunks.setdefault(hour_index // CHUNK_HOURS, []).append(event)
        pre = event.get("pre") or {}
        final = event.get("final") or {}
        row = hours[hour_index]
        compact = {key: event[key] for key in ("timestamp", "bus_id", "accepted_kw", "shedding_kw", "curtailment_kw",
                   "planned_kw", "terminal_target_kwh", "charge_available_kw", "discharge_available_kw", "reason_codes")
                   if key in event}
        compact["pre"] = {key: pre[key] for key in ("minimum_pu", "minimum_bus", "maximum_bus") if key in pre}
        compact["pre"]["violation_keys"] = list((pre.get("violations") or {}).keys())
        compact["severity"] = (4 if row.get("converged") is False or final.get("converged") is False else
                               3 if final.get("violations") or row.get("feasible") is False else
                               2 if (event.get("shedding_kw") or 0) > 1e-9 else
                               1 if (event.get("curtailment_kw") or 0) > 1e-9 or row.get("bess_limited") is True else 0)
        event_index.append(compact)

    network_chunks = []
    limits = metadata.get("simulation") or {}
    low, high = limits.get("voltage_min_pu"), limits.get("voltage_max_pu")
    rated = {line["line_id"]: line["ampacity_a"] for line in (metadata.get("topology") or {}).get("lines", [])
             if limits.get("enforce_line_ampacity", True) and line.get("ampacity_a") is not None}
    if buses:
        for start in range(0, hour_count, CHUNK_HOURS):
            stop = min(start + CHUNK_HOURS, hour_count)
            data = {}
            for bus, columns in buses.items():
                voltage = columns.get("voltage_pu", [])
                shed = columns.get("shedding_kw", [])
                served = columns.get("load_input_kw", [])
                # Display-only encodings for the overview schematic. Exact
                # electrical values remain in their independent entity blocks.
                flags = "".join("?" if value is None or low is None or high is None else
                                "L" if value < low else "H" if value > high else "N" for value in voltage[start:stop])
                intensities = [max(1, round(100 * power / (power + load))) if power is not None and power > 0
                               and load is not None and power + load > 0 else 0
                               for power, load in zip(shed[start:stop], served[start:stop])]
                fractions = columns.get("remaining_load_fraction", [])[start:stop]
                disconnected = columns.get("fully_disconnected", [])[start:stop]
                data[bus] = [flags, intensities, [round(value, 1) if value is not None and value > 0 else 0
                                                  for value in shed[start:stop]],
                             [round(value * 100) if value is not None else None for value in fractions],
                             "".join("Y" if flag is True else "N" if flag is False else "?" for flag in disconnected)]
            overloads = {line: "".join("X" if amps is not None and amps > limit + 1e-6 else "-" for amps in
                         scenario["branches"].get(line, {}).get("current_a", [])[start:stop]) for line, limit in rated.items()}
            network_chunks.append(add({"buses": data, "overloads": overloads}))

    shedding_ranking = []
    for bus, columns in buses.items():
        observed = [(power, row.get("dt_hours")) for power, row in zip(columns.get("shedding_kw", []), hours)
                    if power is not None]
        if observed and all(dt is not None for _, dt in observed):
            shedding_ranking.append((bus, sum(power * dt for power, dt in observed)))

    return {
        "label": scenario["label"], "metrics": scenario["metrics"], "hour_count": hour_count,
        "first": hours[0] if hours else None, "has_bess": has_bess, "diagnostic": diagnostic,
        "shedding_ranking": shedding_ranking,
        "service_by_bus": scenario["service_by_bus"],
        "hours_block": add(hours) if hours else None,
        "bus_blocks": {key: add(value) for key, value in buses.items()},
        "branch_blocks": {key: add(value) for key, value in scenario["branches"].items()},
        "network_blocks": network_chunks, "chunk_hours": CHUNK_HOURS,
        "event_index_block": add(event_index) if event_index else None,
        "event_blocks": {key: add(value) for key, value in event_chunks.items()},
        "unmatched_event_block": add(unmatched_events) if unmatched_events else None,
    }


def regenerate_dashboard(run_folder):
    """Read saved numeric data and atomically rebuild the report and manifest."""
    folder = Path(run_folder).resolve(strict=True)
    metadata = _read_json(folder / RUN_FILE)
    if metadata is None:
        if not any((folder / name).is_file() for name in (*TABLES, "summary.md", "summary.txt")):
            raise ValueError("Select the saved run directory containing numerical exports")
        metadata = {"kind": "Archived run", "folder": folder.name, "context": {},
                    "scenarios": {".": "Archived run"}, "legacy": True}
    if not isinstance(metadata, dict) or not isinstance(metadata.get("scenarios"), dict):
        raise ValueError("Run metadata does not contain the saved scenario map")
    snapshot = _read_json(folder / "inputs" / "input_snapshot.json", {})
    scenarios = metadata["scenarios"]
    trace_data = {name: _scenario(_scenario_folder(folder, name), label, metadata.get("static"))
                  for name, label in scenarios.items()}
    files = {path.relative_to(folder).as_posix(): _hash(path)
             for path in dict.fromkeys(_source_files(folder, {".": "", **scenarios}))}
    previous = _read_json(folder / MANIFEST_FILE, {})
    for name, digest in previous.get("files", {}).items():
        if files.get(name) != digest:
            raise ValueError(f"Canonical result file changed or is missing: {name}")
    run_id = metadata.get("run_id") or "archive-" + sha256(_json(files).encode("utf-8")).hexdigest()
    hours = next((scenario["hours"] for scenario in trace_data.values() if scenario["hours"]), [])
    context = metadata.get("context", {})
    prices = context.get("Economic inputs")
    input_hashes = {f"inputs/{name}": _hash(folder / "inputs" / name)
                    for name in ("network.xlsx", "load_profile.csv", "pv_profile.csv", "input_snapshot.json")
                    if (folder / "inputs" / name).is_file()}
    if metadata.get("kind") == "base case":
        hours = []
    manifest = {
        "schema_version": SCHEMA, "run_id": run_id, "kind": metadata["kind"],
        "folder": metadata["folder"], "scenarios": scenarios, "units": UNITS,
        "topology_sha256": metadata.get("topology_sha256"),
        "clock": snapshot.get("clock", context.get("Clock")),
        "dt_hours": snapshot.get("dt_hours", hours[0].get("dt_hours") if hours else None),
        "interval": snapshot.get("window", {"start": hours[0]["timestamp"],
                                              "last": hours[-1]["timestamp"]} if hours else None),
        "timestamp_count": len(hours),
        "timestamp_sha256": sha256(_json([row["timestamp"] for row in hours]).encode("utf-8")).hexdigest(),
        "currency": prices.get("currency") if prices else None, "economics": prices,
        "objective": "annualized_bess_ownership+net_grid+curtailment+shedding+terminal_adjustment",
        "simulation": metadata.get("simulation"), "solver": metadata.get("solver"),
        "network_control": metadata.get("network_control"),
        "source": context.get("Active input source"), "forecast": context.get("Forecast model"),
        "dispatch": context.get("Dispatch policy"), "provenance": context.get("Runtime provenance"),
        "input_hashes": input_hashes,
        "files": files,
        "summary": (list(_rows(folder / "metrics.csv")) or
                    next((scenario["metrics"] for scenario in trace_data.values() if scenario["metrics"]), [])),
    }
    blocks = []

    def add(data):
        key = len(blocks)
        blocks.append(_pack(data))
        return key

    evaluations = list(_rows(folder / "evaluations.csv"))
    feasible = [item for item in evaluations if item.get("feasible") is True]
    ranked = sorted((item for item in feasible if item.get("annual_cost") is not None),
                    key=lambda item: item["annual_cost"])[:8]
    payload = {"manifest": manifest, "metadata": metadata,
               "scenarios": {key: _scenario_blocks(value, metadata, add) for key, value in trace_data.items()},
               "ranked": ranked, "feasible_count": len(feasible), "candidate_count": len(evaluations),
               "infeasible_count": sum(item.get("feasible") is False for item in evaluations),
               "evaluation_block": add(evaluations) if evaluations else None,
               "convergence": list(_rows(folder / "convergence.csv")),
               "economic_comparison": list(_rows(folder / "economic_comparison.csv"))}
    raw_size, packed = _pack(payload)
    template = (ASSETS / "dashboard.html").read_text(encoding="utf-8")
    replacements = {
        "<!-- REPORT_STYLE -->": (ASSETS / "dashboard.css").read_text(encoding="utf-8"),
        "<!-- REPORT_SCRIPT -->": (ASSETS / "dashboard.js").read_text(encoding="utf-8"),
        "<!-- REPORT_DATA -->": packed,
        "<!-- REPORT_SIZE -->": str(raw_size),
        "<!-- TOTAL_SIZE -->": str(raw_size + sum(size for size, _ in blocks)),
    }
    for marker, value in replacements.items():
        template = template.replace(marker, value)
    header, footer = template.split("<!-- REPORT_BLOCKS -->")

    def html_parts():
        yield header
        for key, (size, data) in enumerate(blocks):
            yield f'<script id="report-block-{key}" type="application/octet-stream" data-bytes="{size}">'
            yield data
            yield "</script>\n"
        yield footer

    _atomic_write(folder / HTML_FILE, html_parts())
    manifest["html_sha256"] = _hash(folder / HTML_FILE)
    _atomic_write(folder / MANIFEST_FILE, _json(manifest))
    return folder / HTML_FILE


def package_dashboard(run_folder, destination):
    """Package canonical files verbatim. The browser can read the stored HTML entry."""
    folder = Path(run_folder).resolve(strict=True)
    target = Path(destination).resolve()
    manifest = _read_json(folder / MANIFEST_FILE)
    if manifest is None or not (folder / HTML_FILE).is_file():
        regenerate_dashboard(folder)
        manifest = _read_json(folder / MANIFEST_FILE)
    if manifest.get("html_sha256") and _hash(folder / HTML_FILE) != manifest["html_sha256"]:
        raise ValueError("The HTML dashboard changed. Regenerate it from the canonical run files before packaging.")
    sources = []
    for name, digest in manifest["files"].items():
        source = (folder / name).resolve()
        if not source.is_relative_to(folder) or not source.is_file() or _hash(source) != digest:
            raise ValueError(f"Canonical result file changed or is missing: {name}")
        sources.append((source, name))
    if target in {source for source, _ in sources} or target in (folder / HTML_FILE, folder / MANIFEST_FILE):
        raise ValueError("Choose a separate ZIP destination")
    with NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
        path = Path(temporary.name)
    try:
        with ZipFile(path, "w", compression=ZIP_DEFLATED) as package:
            package.write(folder / HTML_FILE, HTML_FILE, compress_type=ZIP_STORED)
            package.write(folder / MANIFEST_FILE, MANIFEST_FILE)
            for source, name in sources:
                package.write(source, name)
        path.replace(target)
    finally:
        path.unlink(missing_ok=True)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_folder", type=Path, help="Saved results directory")
    parser.add_argument("--zip", type=Path, help="Optional portable ZIP destination")
    args = parser.parse_args()
    print(regenerate_dashboard(args.run_folder))
    if args.zip:
        print(package_dashboard(args.run_folder, args.zip))


if __name__ == "__main__":
    main()
