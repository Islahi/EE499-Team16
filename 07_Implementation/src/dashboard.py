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
from tempfile import NamedTemporaryFile, TemporaryFile
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from .network_layout import build_layout
from .study_session import _json_value


ASSETS = Path(__file__).parent / "assets"
RUN_FILE = "dashboard_run.json"
MANIFEST_FILE = "dashboard_manifest.json"
HTML_FILE = "dashboard.html"
SCHEMA = 4
CHUNK_HOURS = 168
TABLES = ("hourly.csv", "buses.csv", "branches.csv", "metrics.csv", "evaluations.csv", "service_by_bus.csv",
          "convergence.csv", "economic_comparison.csv", "comparison.csv", "bus_ranking_by_stage.csv",
          "forecast_errors.csv", "forecast_comparison.csv", "annual_finalist_checks.csv",
          "lateral_improvement_by_stage.csv", "screening_candidate_audit.csv",
          "bus_voltages.csv", "line_flows.csv")
UNITS = {"power": "kW", "apparent_power": "kVA", "reactive_power": "kvar", "energy": "kWh", "voltage": "pu",
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
                "loads": [asdict(load) for load in network.loads],
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
    _atomic_write(folder / RUN_FILE, _json(metadata))


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


def _entity_trace(path, key, time_indices, value_key):
    """Read one compact indexed value per entity and hour."""
    entities = {}
    size = len(time_indices)
    if not path.is_file() or not size:
        return entities
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            index = time_indices.get(row.get("timestamp"))
            entity = row.get(key)
            if index is None or entity is None or row.get("converged") == "False":
                continue
            value = _cell(row.get(value_key, ""), value_key)
            if isinstance(value, (int, float)) and isfinite(value):
                if entity not in entities:
                    entities[entity] = [None] * size
                entities[entity][index] = value
    return entities


def _scenario(folder, label, static):
    """Read compact dashboard traces and leave full ledgers in canonical exports."""
    hourly = list(_rows(folder / "hourly.csv"))
    if not hourly and static is not None:
        hourly = [static]
    if not hourly and (folder / "bus_voltages.csv").is_file():
        hourly = [{"timestamp": "Static base case"}]
    minimum = min((row for row in hourly if row.get("converged") is not False
                   and row.get("voltage_min_pu") is not None),
                  key=lambda row: row["voltage_min_pu"], default={})
    worst_timestamp = minimum.get("timestamp")
    voltages = {}
    path = folder / ("bus_voltages.csv" if static is not None or
                     (folder / "bus_voltages.csv").is_file() else "buses.csv")
    time_indices = {row["timestamp"]: index for index, row in enumerate(hourly)}
    compact = len(hourly) <= 336
    voltages_by_hour = _entity_trace(folder / "buses.csv", "bus_id", time_indices, "voltage_pu") if compact else {}
    currents_by_hour = _entity_trace(folder / "branches.csv", "line_id", time_indices, "current_a") if compact else {}
    if worst_timestamp in time_indices and voltages_by_hour:
        index = time_indices[worst_timestamp]
        voltages = {bus: values[index] for bus, values in voltages_by_hour.items() if values[index] is not None}
    elif path.is_file():
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for record in csv.DictReader(stream):
                if record.get("converged") == "False" or ("timestamp" in record and record["timestamp"] != worst_timestamp):
                    continue
                try:
                    voltages[str(record["bus_id"])] = float(record["voltage_pu"])
                except (KeyError, ValueError, TypeError):
                    continue
    return {"label": label, "hours": hourly, "worst_bus_voltages": voltages,
            "voltages_by_hour": voltages_by_hour, "currents_by_hour": currents_by_hour,
            "metrics": list(_rows(folder / "metrics.csv")),
            "fleet_recorded": (folder / "fleet_hourly.csv").is_file()}


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
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), default=_json_value).encode("utf-8")
    return len(raw), b64encode(compress(raw, compresslevel=4, mtime=0)).decode("ascii")


def _scenario_blocks(scenario, add):
    """Pack only values consumed by dashboard.js; never duplicate canonical logs."""
    hours = scenario["hours"]
    minimum = min((row for row in hours if row.get("converged") is not False
                   and row.get("voltage_min_pu") is not None),
                  key=lambda row: row["voltage_min_pu"], default={})
    voltages = scenario["worst_bus_voltages"]
    worst_bus = ((minimum.get("minimum_voltage_bus") or minimum.get("min_voltage_bus"))
                 or (min(voltages, key=voltages.get) if voltages else None))
    has_bess = scenario["fleet_recorded"] or any(
        row.get("bess_accepted_soc") is not None for row in hours)
    diagnostic = {
        "nonconverged": sum(row.get("converged") is False for row in hours),
        "infeasible": sum(row.get("feasible") is False or row.get("converged") is False for row in hours),
        "known_status": any(row.get("feasible") is not None or row.get("converged") is False for row in hours),
        "worst_voltage_pu": minimum.get("voltage_min_pu"), "worst_bus": worst_bus, "worst_timestamp": minimum.get("timestamp"),
        "shedding_hours": sum((row.get("shedding_kw") or 0) > 1e-9 for row in hours)
          if any(row.get("shedding_kw") is not None for row in hours) else None,
        "curtailment_hours": sum((row.get("curtailment_kw") or 0) > 1e-9 for row in hours)
          if any(row.get("curtailment_kw") is not None for row in hours) else None,
        "battery_limiter_hours": sum(row.get("bess_limited") is True for row in hours) if has_bess else None,
    }
    return {
        "label": scenario["label"], "metrics": scenario["metrics"],
        "hour_count": len(hours), "first": hours[0] if hours else None,
        "has_bess": has_bess, "diagnostic": diagnostic,
        "worst_bus_voltages": voltages,
        "bus_voltage_block": add(scenario["voltages_by_hour"]) if scenario["voltages_by_hour"] else None,
        "line_current_block": add(scenario["currents_by_hour"]) if scenario["currents_by_hour"] else None,
        "hours_block": add(hours) if 0 < len(hours) <= CHUNK_HOURS else None,
        "hour_windows": [[i, add(hours[i:i+CHUNK_HOURS])] for i in range(0, len(hours), CHUNK_HOURS)]
                        if len(hours) > CHUNK_HOURS else [],
    }


def read_saved_run(folder):
    """Read run metadata and the input snapshot, including legacy exports."""
    folder = Path(folder)
    metadata = _read_json(folder / RUN_FILE)
    if metadata is None:
        if not any((folder / name).is_file() for name in (*TABLES, "summary.md", "summary.txt")):
            raise ValueError("Select the saved run directory containing numerical exports")
        metadata = {"kind": "Archived run", "folder": folder.name, "context": {},
                    "scenarios": {".": "Archived run"}, "legacy": True}
    if not isinstance(metadata, dict) or not isinstance(metadata.get("scenarios", {}), dict):
        raise ValueError("Run metadata does not contain the saved scenario map")
    if not metadata.get("scenarios"):
        metadata = {**metadata, "scenarios": {".": metadata.get("kind", "Archived run")}}
    from .saved_schema import upgrade_saved_fields
    metadata = upgrade_saved_fields(metadata)
    snapshot = _read_json(folder / "inputs" / "input_snapshot.json", {})
    return metadata, snapshot


def regenerate_dashboard(run_folder):
    """Read saved numeric data and atomically rebuild the report and manifest."""
    from .model_information import model_information

    folder = Path(run_folder).resolve(strict=True)
    metadata, snapshot = read_saved_run(folder)
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
        "objective": "grid_imports-export_credit+load_shedding_penalty+pv_curtailment_penalty+CAPEX*annual_capital_recovery_factor+annual_OandM",
        "simulation": metadata.get("simulation"), "solver": metadata.get("solver"),
        "network_control": metadata.get("network_control"),
        "source": context.get("Active input source"), "forecast": context.get("Forecast model"),
        "dispatch": context.get("Dispatch policy"), "provenance": context.get("Runtime provenance"),
        "input_hashes": input_hashes,
        "files": files,
        "summary": (list(_rows(folder / "metrics.csv")) or
                    next((scenario["metrics"] for scenario in trace_data.values() if scenario["metrics"]), [])),
    }
    with TemporaryFile(mode="w+", encoding="ascii", dir=folder) as spool:
        block_count = 0
        total_size = 0

        def add(data):
            nonlocal block_count, total_size
            size, encoded = _pack(data)
            key = block_count
            spool.write(f'<script id="report-block-{key}" type="application/octet-stream" data-bytes="{size}">{encoded}</script>\n')
            block_count += 1
            total_size += size
            return key

        evaluations = list(_rows(folder / "evaluations.csv"))
        feasible = [item for item in evaluations if item.get("feasible") is True]
        ranked = sorted((item for item in feasible if item.get("annual_cost") is not None),
                        key=lambda item: item["annual_cost"])[:8]
        payload = {"manifest": manifest, "metadata": metadata,
                   "scenarios": {key: _scenario_blocks(value, add) for key, value in trace_data.items()},
                   "ranked": ranked, "feasible_count": len(feasible), "candidate_count": len(evaluations),
                   "infeasible_count": sum(item.get("feasible") is False for item in evaluations),
                   "evaluation_block": add(evaluations) if evaluations else None,
                   "convergence": list(_rows(folder / "convergence.csv")),
                   "economic_comparison": list(_rows(folder / "economic_comparison.csv")),
                   "forecast_errors": list(_rows(folder / "forecast_errors.csv")),
                   "forecast_comparison_block": add(list(_rows(folder / "forecast_comparison.csv")))
                      if (folder / "forecast_comparison.csv").is_file() else None}
        from .dashboard_series import catalogue
        inputs_cache = {}
        for key, trace in trace_data.items():
            payload["scenarios"][key]["gallery"] = catalogue(_scenario_folder(folder, key), trace["hours"], add,
                root=folder, snapshot=snapshot, inputs_cache=inputs_cache,
                static=metadata.get("kind") == "base case" or (folder / "bus_voltages.csv").is_file())
        payload["input_info"] = snapshot
        raw_size, packed = _pack(payload)
        template = (ASSETS / "dashboard.html").read_text(encoding="utf-8")
        styles = (ASSETS / "dashboard.css").read_text(encoding="utf-8")
        if not metadata.get("legacy"):
            styles += (ASSETS / "model_information.css").read_text(encoding="utf-8")
        scripts = (ASSETS / "dashboard_gallery.js").read_text(encoding="utf-8") + "\n" + (ASSETS / "dashboard.js").read_text(encoding="utf-8")
        # Compress the offline viewer too, so small and historical reports stay compact.
        script_source = b64encode(compress(scripts.encode("utf-8"), mtime=0)).decode("ascii")
        bootstrap = ("(async()=>{const b=Uint8Array.from(atob('" + script_source +
                     "'),c=>c.charCodeAt(0));const s=document.createElement('script');"
                     "s.textContent=await new Response(new Blob([b]).stream().pipeThrough(new DecompressionStream('gzip'))).text();"
                     "document.body.append(s)})().catch(e=>document.getElementById('notice').textContent=e.message);")
        replacements = {
            "<!-- REPORT_STYLE -->": styles,
            "<!-- REPORT_SCRIPT -->": bootstrap,
            "<!-- REPORT_DATA -->": packed,
            "<!-- REPORT_SIZE -->": str(raw_size),
            "<!-- TOTAL_SIZE -->": str(raw_size + total_size),
            "<!-- MODEL_INFORMATION -->": "".join(
                f"<section><h2>{title}</h2>{content}</section>"
                for title, content in model_information(metadata, snapshot).items()),
        }
        for marker, value in replacements.items():
            template = template.replace(marker, value)
        header, footer = template.split("<!-- REPORT_BLOCKS -->")

        def html_parts():
            yield header
            spool.seek(0)
            while part := spool.read(1024 * 1024):
                yield part
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
