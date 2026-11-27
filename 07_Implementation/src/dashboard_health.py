"""Compact full-period health statistics derived while indexing the saved results."""
from collections import defaultdict
from math import isfinite


class FeederHealth:
    def __init__(self, hours, stamps, snapshot, simulation, topology):
        self.stamps = stamps
        self.hours = hours
        self.duration = snapshot.get("dt_hours")
        self.expected = (snapshot.get("window") or {}).get("hours")
        self.minimum = simulation.get("voltage_min_pu")
        self.maximum = simulation.get("voltage_max_pu")
        self.ratings = {str(line["line_id"]): line.get("ampacity_a") for line in topology.get("lines", ())}
        self.entities = {"bus": {}, "line": {}}
        self.affected = defaultdict(set)

    def duration_at(self, index):
        value = self.hours[index].get("dt_hours", self.duration)
        return value if isinstance(value, (int, float)) and isfinite(value) and value > 0 else None

    @staticmethod
    def track(row, key, value, duration=None):
        if value is None:
            return
        record = row.setdefault(key, {"samples": 0, "sum": 0., "min": value, "max": value})
        record["samples"] += 1
        record["sum"] += value
        record["min"] = min(record["min"], value)
        record["max"] = max(record["max"], value)
        if duration is not None:
            record["timed"] = record.get("timed", 0) + 1
            record["hours"] = record.get("hours", 0.) + duration
            record["weighted"] = record.get("weighted", 0.) + duration * value

    def violation(self, row, field, value, index, duration, *, flags=None):
        if value is None:
            return
        stats = row.setdefault(field, {"samples": 0, "affected": 0, "observed_hours": 0.,
                                      "affected_hours": 0., "timed_samples": 0})
        stats["samples"] += 1
        stats["affected"] += bool(value)
        if value:
            self.affected[flags or field].add(index)
        if duration is not None:
            stats["timed_samples"] += 1
            stats["observed_hours"] += duration
            if value:
                stats["affected_hours"] += duration

    def update(self, kind, identity, index, values):
        row = self.entities[kind].setdefault(identity, {"attempted": 0})
        row["attempted"] += 1
        duration = self.duration_at(index)
        if kind == "bus":
            voltage = values.get("voltage_pu")
            pre = values.get("uncontrolled_voltage_pu")
            self.track(row, "voltage_pu", voltage, duration)
            self.track(row, "pre_voltage_pu", pre, duration)
            if voltage is not None:
                margin = values.get("voltage_margin_pu")
                if margin is None and None not in (self.minimum, self.maximum):
                    margin = min(voltage - self.minimum, self.maximum - voltage)
                self.track(row, "margin_pu", margin)
                violation = values.get("voltage_violation")
                if violation is None and margin is not None:
                    violation = margin < 0
                self.violation(row, "violation", violation, index, duration)
            if pre is not None and None not in (self.minimum, self.maximum):
                margin = min(pre - self.minimum, self.maximum - pre)
                self.track(row, "pre_margin_pu", margin)
                self.violation(row, "pre_violation", margin < 0, index, duration)
            reference = values.get("pre_control_voltage_pu")
            if reference is not None and None not in (self.minimum, self.maximum):
                self.track(row, "reference_voltage_pu", reference)
                margin = min(reference - self.minimum, self.maximum - reference)
                self.violation(row, "reference_violation", margin < 0, index, duration)
            for key in ("shed_kwh", "curtailed_kwh"):
                self.track(row, key, values.get(key))
        else:
            current = values.get("current_a")
            self.track(row, "current_a", current, duration)
            rating = values.get("ampacity_a")
            if rating is None:
                rating = self.ratings.get(identity)
            if rating is not None and rating > 0:
                row["rated"] = True
                self.track(row, "ampacity_a", rating)
                if current is not None:
                    loading = values.get("loading_percent")
                    self.track(row, "loading_percent", loading if loading is not None else 100 * current / rating)
                    overloaded = values.get("overloaded")
                    if overloaded is None:
                        overloaded = current > rating + 1e-6
                    self.violation(row, "overload", overloaded, index, duration)
            if duration is not None:
                for key, power in (("loss_kwh", "loss_p_kw"), ("loss_kvarh", "loss_q_kvar")):
                    if values.get(power) is not None:
                        self.track(row, key, values[power] * duration)

    def report(self):
        if not any(self.entities.values()):
            return None
        total = len(self.stamps)
        return {"version": 1, "first": self.stamps[0], "last": self.stamps[-1], "samples": total,
                "expected": max(self.expected, total) if isinstance(self.expected, int) else None,
                "converged": sum(hour.get("converged") is True for hour in self.hours),
                "failed": sum(hour.get("converged") is False for hour in self.hours),
                "minimum_pu": self.minimum, "maximum_pu": self.maximum,
                "affected_samples": {key: len(value) for key, value in self.affected.items()},
                "affected_hours": {key: sum(self.duration_at(i) for i in sorted(value))
                                   if all(self.duration_at(i) is not None for i in value) else None
                                   for key, value in self.affected.items()},
                **self.entities}

