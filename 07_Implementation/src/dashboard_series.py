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


def indexed_rows(rows, fields, add, *, track_fields=False):
    """Input may be in bus-major or time-major order. Preserve indices and missing values."""
    buffers = {}
    entries = defaultdict(list)
    available = set()
    entity_fields = defaultdict(set)

    def flush(entity):
        bucket, indices, columns = buffers.pop(entity)
        contained = {field: values for field, values in zip(fields, columns) if any(v is not None for v in values)}
        if contained:
            available.update(contained)
            if track_fields:
                entity_fields[entity].update(contained)
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
    data = {"fields": [key for key in fields if key in available], "entities": entries}
    if track_fields:
        data["entity_fields"] = {entity: [key for key in fields if key in found]
                                 for entity, found in entity_fields.items()}
    return data


LOAD_OUTPUT = ("requested_load_kw", "requested_load_kvar", "load_input_kw", "load_input_kvar",
               "shedding_kw", "shedding_kvar", "requested_load_kwh", "served_load_kwh", "shed_kwh", "shedding_cost")
OUTPUT_ENERGY = {"requested_load_kwh": "requested_load_kw", "served_load_kwh": "load_input_kw",
                 "shed_kwh": "shedding_kw"}


def load_categories(raw, buses):
    assignments = {str(bus): " ".join(str(category).lower().split())
                   for bus, category in raw.items() if isinstance(category, str) and category.strip()}
    categories = {}
    for bus in sorted(set(buses) | assignments.keys(), key=lambda value: (len(value), value)):
        category = assignments.get(bus, "unclassified")
        reserved = category in {"total", "constructor", "__proto__", "prototype"}
        key = f"category:{category}" if reserved or category.isdecimal() or category.startswith("category:") else category
        entry = categories.setdefault(key, {"label": category.title(), "buses": [],
                                             "source_defined": category not in ("residential", "commercial", "manufacturing", "unclassified")})
        entry["buses"].append(bus)
    return categories


def csv_series(path, entity_key, times, add, *, categories=None, aggregate=False, include=None,
               static=False, time_key="timestamp", failed_hours=(), observe=None,
               energy_fields=None, durations=(), consumption=None, track_fields=False):
    if not path.is_file():
        return None
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = [name for name in reader.fieldnames or () if name not in SKIP and (include is None or name in include)]
        derived = {key: fields.index(power) for key, power in (energy_fields or {}).items()
                   if key not in fields and power in fields and any(durations)}
        recorded = tuple(fields)
        fields.extend(derived)
        health_fields = [(i, key) for i, key in enumerate(fields) if key in (
            "voltage_pu", "uncontrolled_voltage_pu", "pre_control_voltage_pu", "voltage_margin_pu", "voltage_violation",
            "shed_kwh", "curtailed_kwh", "current_a", "loading_percent", "ampacity_a", "overloaded", "loss_p_kw", "loss_q_kvar")]
        totals = defaultdict(dict)
        masks = defaultdict(int)
        bit_by_bus, group_by_bus = {}, {}
        for group, details in (categories or {}).items():
            for bus in details["buses"]:
                bit = 1 << len(bit_by_bus)
                bit_by_bus[bus], group_by_bus[bus] = bit, group
                masks[group] |= bit
                masks["Total"] |= bit
        def rows():
            for row in reader:
                stamp = (row.get(time_key, "Static base case" if static else "") or "").replace("T", " ", 1)
                index = times.get(stamp)
                if index is None:
                    continue
                entity = row.get(entity_key, "System")
                diagnostic = row.get("converged") == "False" or index in failed_hours
                values = [None if diagnostic and name not in ("converged", "diagnostic_only", "step_feasible",
                          "requested_load_kw", "requested_load_kvar", "requested_load_kwh", "available_pv_kw", "base_kv", "installed_pv_kw",
                          "ampacity_a", "resistance_ohm", "reactance_ohm", "slack_setpoint_pu",
                          "uncontrolled_voltage_pu", "before_correction_voltage_pu", "available_pv_kvar") else number(row.get(name))
                          for name in recorded]
                if derived:
                    dt = durations[index]
                    values.extend(values[j] * dt if values[j] is not None and dt is not None else None
                                  for j in derived.values())
                if consumption is not None:
                    consumption.record(entity, index, dict(zip(fields, values)), False)
                if observe is not None:
                    observe(entity, index, {key: values[i] for i, key in health_fields})
                if aggregate:
                    if entity not in bit_by_bus:
                        bit_by_bus[entity] = 1 << len(bit_by_bus)
                        group_by_bus[entity] = "unclassified" if categories is not None else None
                        if categories is not None:
                            categories.setdefault("unclassified", {"label": "Unclassified", "buses": [],
                                                                   "source_defined": False})["buses"].append(entity)
                    bit = bit_by_bus[entity]
                    groups = ("Total", group_by_bus[entity])
                    for group in filter(None, groups):
                        masks[group] |= bit
                        sample = totals[group].setdefault(index, [0, False, [0.] * len(fields)])
                        sample[1] |= bool(sample[0] & bit)
                        sample[0] |= bit
                        for j, value in enumerate(values):
                            item = sample[2]
                            item[j] = item[j] + value if value is not None and item[j] is not None else None
                yield entity, index, values
            for group, samples in totals.items():
                for index, (mask, duplicate, values) in sorted(samples.items()):
                    complete = values if mask == masks[group] and not duplicate else [None] * len(fields)
                    if consumption is not None:
                        consumption.record(group, index, dict(zip(fields, complete)), True)
                    yield group, index, complete
        data = indexed_rows(rows(), fields, add, track_fields=track_fields or categories is not None)
        if categories is not None:
            data["categories"] = categories
            data["category_source"] = "Archived bus assignments" if any(key != "unclassified" for key in categories) else "Category not provided"
        return data


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


def archived_assignments(root, snapshot):
    assignments = snapshot.get("assignments")
    if assignments:
        return assignments
    for path in (root / "inputs" / "bus_assignments_used.csv", root / "bus_assignments_used.csv"):
        if path.is_file():
            rows = defaultdict(set)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                for record in csv.DictReader(stream):
                    bus, category = record.get("bus_id", "").strip(), record.get("category", "").strip()
                    if bus and category:
                        rows[bus].add(" ".join(category.lower().split()))
            return {bus: next(iter(labels)) for bus, labels in rows.items() if len(labels) == 1}
    return {}


def catalogue(folder, hours, add, *, root, snapshot, inputs_cache, static=False, simulation=None, topology=None,
              economics=None, descriptor=None):
    stamps = [str(row["timestamp"]).replace("T", " ", 1) for row in hours]
    if not stamps:
        return {}
    counts = defaultdict(int)
    for stamp in stamps:
        counts[stamp] += 1
    times = {stamp: i for i, stamp in enumerate(stamps) if counts[stamp] == 1}
    failed_hours = {i for i, row in enumerate(hours) if row.get("converged") is False}
    from .dashboard_health import FeederHealth
    health = None if static else FeederHealth(hours, stamps, snapshot, simulation or {}, topology or {})
    groups = {}
    raw_categories = archived_assignments(root, snapshot)
    source_buses = snapshot.get("load_bus_ids")
    if source_buses is None:
        source_buses = [load["bus_id"] for load in (topology or {}).get("loads", ())]
    bus_ids = [str(bus) for bus in source_buses]
    known = {str(bus["bus_id"]) for bus in (topology or {}).get("buses", ())}
    if known:
        raw_categories = {bus: name for bus, name in raw_categories.items() if str(bus) in known}
    dt = snapshot.get("dt_hours")
    durations = [value if type(value) in (int, float) and isfinite(value) and value > 0 else None
                 for value in (h.get("dt_hours", dt) for h in hours)]
    if dt is None and durations and all(value == durations[0] for value in durations):
        dt = durations[0]
    consumption_info = None
    voltage_rows = {}
    bus_bits = {bus: 1 << i for i, bus in enumerate(sorted(known))}
    full_voltage_mask = (1 << len(bus_bits)) - 1

    def observe_bus(entity, index, values):
        if health is not None:
            health.update("bus", entity, index, values)
        row = voltage_rows.setdefault(index, [0, 0., False])
        bit = bus_bits.get(entity, 0)
        voltage = values.get("voltage_pu")
        if row[0] & bit or not bit or voltage is None:
            row[2] = True
        else:
            row[0] |= bit
            row[1] += voltage

    for group, name, key in (("bus", "bus_voltages.csv" if static else "buses.csv", "bus_id"),
                              ("line", "line_flows.csv" if static else "branches.csv", "line_id"),
                              ("battery", "fleet_hourly.csv", "bus_id")):
        observe = (observe_bus if group == "bus" and not static else
                   (lambda entity, index, values: health.update("line", entity, index, values))
                   if group == "line" and health is not None else None)
        data = csv_series(folder / name, key, times, add, static=static, failed_hours=failed_hours, observe=observe)
        if data and data["entities"]:
            groups[group] = data
    if not static:
        from .load_consumption import ConsumptionSummary, expected_samples
        tariff = (economics or {}).get("grid_import_tariff_per_kwh")
        if type(tariff) not in (int, float) or not isfinite(tariff) or tariff < 0:
            tariff = None
        expected = (descriptor or {}).get("expected_hours", (snapshot.get("window") or {}).get("hours"))
        consumption = ConsumptionSummary(expected_samples(stamps, dt, expected), tariff)
        categories = load_categories(raw_categories, bus_ids)
        demand = csv_series(folder / "buses.csv", "bus_id", times, add, include=LOAD_OUTPUT,
                            failed_hours=failed_hours, categories=categories, aggregate=True,
                            energy_fields=OUTPUT_ENERGY, durations=durations, consumption=consumption)
        if demand and demand["entities"]:
            groups["load output"] = demand
            consumption_info = consumption.report(categories, stamps)
    audit = csv_series(folder / "battery_daily_audit.csv", "bus_id", times, add, time_key="last_timestamp")
    if audit and audit["entities"]:
        groups["battery daily audit"] = audit
    # Scenarios with the identical time axis share all immutable input blocks.
    axis = tuple(stamps)
    if axis not in inputs_cache:
        shared = {}
        for group, filename, key in (
                ("load input", "load_profile.csv", "bus_id"),
                ("PV input", "pv_profile.csv", "bus_id"),
                ("solar source", "solar_reference.csv", None)):
            categories = load_categories(raw_categories, bus_ids) if group == "load input" and not static else None
            data = csv_series(root / "inputs" / filename, key, times, add, categories=categories,
                              aggregate=key is not None, static=static, durations=durations,
                              energy_fields={"p_kwh": "p_kw"} if group == "load input" and not static else None)
            if data and data["entities"]:
                shared[group] = data
        forecast = csv_series(root / "forecast_comparison.csv", "category", times, add, track_fields=True)
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
        mean_field = "voltage_mean_pu"
        if known and voltage_rows:
            fields.append(mean_field)

        def system_rows():
            for i, row in enumerate(hours):
                mask, total, incomplete = voltage_rows.get(i, (0, 0., True))
                mean = total / len(known) if known and mask == full_voltage_mask and not incomplete else None
                failed = row.get("converged") is False
                retained = ("converged", "diagnostic_only", "fbs_iterations", "feasible", "requested_load_kw",
                            "requested_load_kvar", "available_pv_kw", "dt_hours")
                yield "System", i, [None if failed and field not in retained else
                                    mean if field == mean_field else row.get(field) for field in fields]

        groups["system"] = indexed_rows(system_rows(), fields, add)
    summary = health.report() if health is not None else None
    return {"groups":groups, "timestamps":add(stamps), "controls":control_blocks(folder / "control_decisions.jsonl", times, add),
            "consumption": add(consumption_info) if consumption_info is not None else None,
            "health": add(summary) if summary is not None else None}

