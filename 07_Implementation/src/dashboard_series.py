"""Index archived measurements by entity and time for the self-contained dashboard."""
import csv
import json
from collections import defaultdict
from math import isfinite

BLOCK_HOURS = 336
SKIP = {"timestamp", "step_index", "bus_id", "line_id", "category", "profile", "first_timestamp", "last_timestamp", "from_bus", "to_bus",
        "fbs_message", "message", "messages", "voltage_violation_bus_ids", "bess_limit_reason",
        "correction_status", "limit_reason"}


def number(value):
    if value in ("True", "False"):
        return int(value == "True")
    try:
        x = float(value)
        return x if isfinite(x) else None
    except (ValueError, TypeError):
        return None


def indexed_rows(rows, fields, add):
    """Input may be in bus-major or time-major order. Preserve indices and missing values."""
    buffers = {}
    entries = defaultdict(list)
    available = set()

    def flush(entity):
        bucket, indices, columns = buffers.pop(entity)
        contained = {field: values for field, values in zip(fields, columns) if any(v is not None for v in values)}
        if contained:
            available.update(contained)
            entries[entity].append([min(indices), max(indices), add([indices, contained])])

    for entity, index, values in rows:
        bucket = index // BLOCK_HOURS
        if entity in buffers and buffers[entity][0] != bucket:
            flush(entity)
        if entity not in buffers:
            buffers[entity] = bucket, [], [[] for _ in fields]
        _, indices, columns = buffers[entity]
        indices.append(index)
        for col, value in zip(columns, values):
            col.append(value)
    for entity in list(buffers):
        flush(entity)
    return {"fields": [key for key in fields if key in available], "entities": entries}


def csv_series(path, entity_key, times, add, *, assignments=None, static=False, time_key="timestamp", failed_hours=()):
    if not path.is_file():
        return None
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = [name for name in reader.fieldnames or () if name not in SKIP]
        total = {}
        members = defaultdict(set)
        counts = defaultdict(lambda: defaultdict(int))
        def rows():
            for row in reader:
                stamp = (row.get(time_key, "Static base case" if static else "") or "").replace("T", " ", 1)
                index = times.get(stamp)
                if index is None:
                    continue
                entity = row.get(entity_key, "System")
                diagnostic = row.get("converged") == "False" or index in failed_hours
                values = [None if diagnostic and name not in ("converged", "diagnostic_only", "step_feasible",
                          "requested_load_kw", "requested_load_kvar", "available_pv_kw", "base_kv", "installed_pv_kw",
                          "ampacity_a", "resistance_ohm", "reactance_ohm", "slack_setpoint_pu",
                          "uncontrolled_voltage_pu", "before_correction_voltage_pu", "available_pv_kvar") else number(row.get(name))
                          for name in fields]
                if assignments is not None:
                    for group in ("Total", assignments.get(str(entity))):
                        if group:
                            members[group].add(entity)
                            counts[group][index] += 1
                            item = total.setdefault(group, {}).setdefault(index, [0.] * len(fields))
                            for j, value in enumerate(values):
                                item[j] = item[j] + value if value is not None and item[j] is not None else None
                yield entity, index, values
            for group, samples in total.items():
                for index, values in sorted(samples.items()):
                    yield group, index, values if counts[group][index] == len(members[group]) else [None] * len(fields)
        return indexed_rows(rows(), fields, add)


def control_blocks(path, times, add):
    if not path.is_file():
        return None
    blocks, rows = [], []
    def flush():
        if rows:
            blocks.append([rows[0]["step_index"], rows[-1]["step_index"], add(rows)])
            rows.clear()
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            hour = json.loads(line)
            index = times.get(hour["timestamp"].replace("T", " ", 1))
            if index is None:
                continue
            if rows and index // BLOCK_HOURS != rows[0]["step_index"] // BLOCK_HOURS:
                flush()
            hour["step_index"] = index
            rows.append(hour)
        flush()
    return blocks


def catalogue(folder, hours, add, *, root, snapshot, inputs_cache, static=False):
    stamps = [str(row["timestamp"]).replace("T", " ", 1) for row in hours]
    if not stamps:
        return {}
    times = {stamp: i for i, stamp in enumerate(stamps)}
    failed_hours = {i for i, row in enumerate(hours) if row.get("converged") is False}
    groups = {}
    for group, name, key in (("bus", "bus_voltages.csv" if static else "buses.csv", "bus_id"),
                              ("line", "line_flows.csv" if static else "branches.csv", "line_id"),
                              ("battery", "fleet_hourly.csv", "bus_id")):
        data = csv_series(folder / name, key, times, add, static=static, failed_hours=failed_hours)
        if data and data["entities"]:
            groups[group] = data
    audit = csv_series(folder / "battery_daily_audit.csv", "bus_id", times, add, time_key="last_timestamp")
    if audit and audit["entities"]:
        groups["battery daily audit"] = audit
    # Scenarios with the identical time axis share all immutable input blocks.
    axis = tuple(stamps)
    if axis not in inputs_cache:
        shared = {}
        for group, filename, key, assignments in (
                ("load input", "load_profile.csv", "bus_id", snapshot.get("assignments", {})),
                ("PV input", "pv_profile.csv", "bus_id", {}),
                ("solar source", "solar_reference.csv", None, None)):
            data = csv_series(root / "inputs" / filename, key, times, add, assignments=assignments, static=static)
            if data and data["entities"]:
                shared[group] = data
        forecast = csv_series(root / "forecast_comparison.csv", "category", times, add)
        if forecast and forecast["entities"]:
            shared["forecast"] = forecast
        per_bus = csv_series(root / "forecast_by_bus.csv", "profile", times, add)
        if per_bus and per_bus["entities"]:
            shared["forecast by bus"] = per_bus
        inputs_cache[axis] = shared
    groups.update(inputs_cache[axis])
    fields = list(dict.fromkeys(k for row in hours for k, v in row.items()
                                if k not in SKIP and isinstance(v, (int, float))))
    if fields:
        groups["system"] = indexed_rows((("System", i, [None if row.get("converged") is False and k not in ("converged","diagnostic_only","fbs_iterations","feasible","requested_load_kw","requested_load_kvar","available_pv_kw","dt_hours") else row.get(k) for k in fields])
                                         for i, row in enumerate(hours)), fields, add)
    return {"groups":groups, "timestamps":add(stamps), "controls":control_blocks(folder / "control_decisions.jsonl", times, add)}

