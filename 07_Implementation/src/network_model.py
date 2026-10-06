"""Static balanced radial feeder entities; engineering units at boundaries."""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class Bus:
    bus_id: int
    name: str
    base_kv: float
    is_slack: bool = False
    v_set_pu: float = 1.0


@dataclass(frozen=True)
class Line:
    line_id: str
    from_bus: int
    to_bus: int
    r_ohm: float
    x_ohm: float
    ampacity_a: float | None = None


@dataclass(frozen=True)
class Load:
    load_id: str
    bus_id: int
    p_base_kw: float
    q_base_kvar: float


@dataclass(frozen=True)
class PVUnit:
    pv_id: str
    bus_id: int
    p_rated_kw: float
    q_capability_kvar: float | None = None


@dataclass
class RadialOrder:
    slack_bus_id: int
    parent_bus_by_bus: dict[int, int]
    parent_line_by_bus: dict[int, str]
    children_by_bus: dict[int, list[int]]
    forward_line_ids: list[str]
    backward_line_ids: list[str]


def _finite(value, name, minimum=None, positive=False):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value):
        raise ValueError(f"{name} must be finite numeric data")
    if (minimum is not None and value < minimum) or (positive and value <= 0):
        raise ValueError(f"{name} is outside its physical range")


@dataclass
class NetworkModel:
    buses: list[Bus]
    lines: list[Line]
    loads: list[Load]
    pv_units: list[PVUnit]
    base_power_kva: float
    frequency_hz: float

    def slack_bus_id(self):
        slacks = [b.bus_id for b in self.buses if b.is_slack]
        if len(slacks) != 1:
            raise ValueError("Network must have exactly one slack bus")
        return slacks[0]

    def loads_by_bus(self):
        return {b.bus_id: [x for x in self.loads if x.bus_id == b.bus_id] for b in self.buses}

    def pv_by_bus(self):
        return {b.bus_id: [x for x in self.pv_units if x.bus_id == b.bus_id] for b in self.buses}

    def validate(self):
        _finite(self.base_power_kva, "base_power_kva", positive=True)
        _finite(self.frequency_hz, "frequency_hz", positive=True)
        ids = [b.bus_id for b in self.buses]
        if any(not isinstance(i, int) or isinstance(i, bool) for i in ids):
            raise ValueError("Bus IDs must be integers")
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate bus IDs")
        self.slack_bus_id()
        for b in self.buses:
            _finite(b.base_kv, "base_kv", positive=True)
            _finite(b.v_set_pu, "v_set_pu", positive=True)
            if b.base_kv != self.buses[0].base_kv:
                raise ValueError("Multi-voltage feeders require a transformer model")
        for objects, key in ((self.lines, "line_id"), (self.loads, "load_id"), (self.pv_units, "pv_id")):
            names = [getattr(x, key) for x in objects]
            if any(not isinstance(n, str) or not n for n in names) or len(set(names)) != len(names):
                raise ValueError(f"{key} values must be nonempty and unique")
        adjacency = {i: [] for i in ids}
        for line in self.lines:
            if line.from_bus not in adjacency or line.to_bus not in adjacency:
                raise ValueError(f"Unknown endpoint on line {line.line_id}")
            if line.from_bus == line.to_bus:
                raise ValueError("Self-connected line")
            _finite(line.r_ohm, "r_ohm", minimum=0)
            _finite(line.x_ohm, "x_ohm")
            if line.ampacity_a is not None:
                _finite(line.ampacity_a, "ampacity_a", positive=True)
            adjacency[line.from_bus].append(line.to_bus)
            adjacency[line.to_bus].append(line.from_bus)
        for load in self.loads:
            if load.bus_id not in adjacency:
                raise ValueError("Unknown load bus")
            _finite(load.p_base_kw, "p_base_kw", minimum=0)
            _finite(load.q_base_kvar, "q_base_kvar", minimum=0)
        for pv in self.pv_units:
            if pv.bus_id not in adjacency:
                raise ValueError("Unknown PV bus")
            _finite(pv.p_rated_kw, "p_rated_kw", minimum=0)
            if pv.q_capability_kvar is not None:
                _finite(pv.q_capability_kvar, "q_capability_kvar", minimum=0)
        seen, pending = set(), [self.slack_bus_id()]
        while pending:
            bus = pending.pop()
            if bus not in seen:
                seen.add(bus)
                pending.extend(adjacency[bus])
        if len(seen) != len(ids):
            raise ValueError("Network is disconnected")
        if len(self.lines) != len(self.buses) - 1:
            raise ValueError("Network must be radial (n_lines = n_buses - 1)")

    def radial_order(self):
        self.validate()
        adjacency = {b.bus_id: [] for b in self.buses}
        for line in self.lines:
            adjacency[line.from_bus].append((line.to_bus, line.line_id))
            adjacency[line.to_bus].append((line.from_bus, line.line_id))
        root = self.slack_bus_id()
        parents, parent_lines = {}, {}
        children = {b.bus_id: [] for b in self.buses}
        forward, queue, seen = [], [root], {root}
        for bus in queue:
            for child, line_id in sorted(adjacency[bus]):
                if child in seen:
                    continue
                seen.add(child)
                parents[child], parent_lines[child] = bus, line_id
                children[bus].append(child)
                forward.append(line_id)
                queue.append(child)
        return RadialOrder(root, parents, parent_lines, children, forward, forward[::-1])
