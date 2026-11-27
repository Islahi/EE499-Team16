"""Full-period bus and category totals computed from retained hourly records."""

from datetime import datetime


SUMMARY_FIELDS = {
    "requested_load_kwh": "requested_kwh",
    "served_load_kwh": "served_kwh",
    "shed_kwh": "shed_kwh",
    "requested_load_kw": "peak_kw",
    "shedding_cost": "shedding_penalty",
}


def expected_samples(stamps, dt, expected):
    count = max(len(stamps), expected if isinstance(expected, int) else 0)
    if stamps and isinstance(dt, (int, float)) and dt > 0:
        try:
            elapsed = datetime.fromisoformat(stamps[-1]) - datetime.fromisoformat(stamps[0])
            count = max(count, round(elapsed.total_seconds() / (3600 * dt)) + 1)
        except (ValueError, TypeError):
            pass
    return count


class ConsumptionSummary:
    def __init__(self, expected, tariff):
        self.expected = expected
        self.tariff = tariff
        self.buses = {}
        self.categories = {}

    def record(self, entity, index, values, aggregate):
        records = self.categories if aggregate else self.buses
        stats = records.setdefault(entity, {"last": -1, "broken": False, "demand": False,
                                           "coverage": {}, "values": {}})
        if index <= stats["last"]:
            stats["broken"] = True
        stats["last"] = index
        stats["demand"] |= any((values.get(field) or 0) > 0 for field in
                               ("requested_load_kw", "load_input_kw", "shedding_kw",
                                "requested_load_kvar", "load_input_kvar", "shedding_kvar",
                                "requested_load_kwh", "served_load_kwh", "shed_kwh"))
        for field, key in SUMMARY_FIELDS.items():
            value = values.get(field)
            if value is not None:
                counts, totals = stats["coverage"], stats["values"]
                counts[key] = counts.get(key, 0) + 1
                totals[key] = (max(totals.get(key, value), value) if key == "peak_kw"
                               else totals.get(key, 0.) + value)

    def report(self, categories, stamps):
        if not self.buses:
            return None
        total = self.categories.get("Total", {})
        complete = lambda row, field: not row.get("broken") and row.get("coverage", {}).get(field) == self.expected
        denominator = total.get("values", {}).get("requested_kwh") if complete(total, "requested_kwh") else None
        memberships = {bus: key for key, category in categories.items() for bus in category["buses"]}
        if not any(stats["demand"] for stats in self.buses.values()) and not complete(total, "requested_kwh"):
            return None

        def normalized(key, stats, category):
            row = {field: stats["values"][field] if complete(stats, field) else None for field in SUMMARY_FIELDS.values()}
            requested = row["requested_kwh"]
            served = row["served_kwh"]
            return {"id": key, "category": category, **row,
                    "share_percent": 100 * requested / denominator if requested is not None and denominator else None,
                    "tariff_estimate": served * self.tariff if served is not None and self.tariff is not None else None,
                    "coverage": {} if stats["broken"] else stats["coverage"]}

        buses = [normalized(bus, stats, memberships.get(bus, "unclassified"))
                 for bus, stats in self.buses.items() if stats["demand"]]
        counts = {}
        for row in buses:
            counts[row["category"]] = counts.get(row["category"], 0) + 1
        groups = []
        for key, stats in self.categories.items():
            if key == "Total" or counts.get(key) or (key in categories and key != "unclassified"):
                row = normalized(key, stats, key)
                row["bus_count"] = len(buses) if key == "Total" else counts.get(key, 0)
                groups.append(row)
        return {"categories": groups, "buses": buses,
                "labels": {key: value["label"] for key, value in categories.items()},
                "expected": self.expected, "start": stamps[0], "last": stamps[-1],
                "tariff": self.tariff}
