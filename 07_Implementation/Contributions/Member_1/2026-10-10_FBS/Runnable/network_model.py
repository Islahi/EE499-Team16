"""
network_model.py
-----------------
Task #12: Stores the distribution network - buses, lines, loads, and PV units -
and packages everything into a single NetworkModel object that fbs.py consumes.

This module defines a simple, radial 5-bus test feeder you can swap out for
real data (replace the values in build_default_5bus_network(), or construct a
NetworkModel directly from your own bus/line/load/PV tables).

Per-unit convention
--------------------
All impedances, voltages, powers and currents are expressed in per-unit (p.u.)
on a common system base:
    S_base (MVA) and V_base (kV)  ->  Z_base = V_base^2 / S_base (ohms)
    I_base = S_base / (sqrt(3) * V_base)   (for a 3-phase balanced system)

Topology
--------
Bus 1 is the substation / slack bus (voltage fixed, angle = 0).
The feeder is radial (a tree): every other bus has exactly one upstream
("parent") branch feeding it.

    Bus 1 (slack / substation)
      |
    Bus 2
     / \\
  Bus 3  Bus 5   (Bus 5 is a lateral off Bus 2)
    |
  Bus 4

Loads sit on buses 2-5. PV units are modelled as negative (injected) load at
the bus they are connected to.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import cmath


# --------------------------------------------------------------------------- #
# Data containers
# --------------------------------------------------------------------------- #

@dataclass
class Bus:
    """A single network bus."""
    bus_id: int
    name: str = ""
    is_slack: bool = False
    v_slack_pu: Optional[complex] = None   # only set for the slack bus, e.g. 1.0+0j

    def __post_init__(self):
        if not self.name:
            self.name = f"Bus{self.bus_id}"


@dataclass
class Line:
    """A distribution line / branch, identified by its (from, to) buses.

    r_pu, x_pu : positive-sequence series resistance / reactance, in p.u.
    rating_a_pu: optional thermal/ampacity rating in p.u. current (None = unlimited)
    """
    from_bus: int
    to_bus: int
    r_pu: float
    x_pu: float
    rating_a_pu: Optional[float] = None

    @property
    def z_pu(self) -> complex:
        return complex(self.r_pu, self.x_pu)


@dataclass
class Load:
    """Constant-power (PQ) load connected at a bus, in p.u. on the system base."""
    bus_id: int
    p_pu: float
    q_pu: float


@dataclass
class PVUnit:
    """Distributed PV generator connected at a bus.

    Modelled as a constant-power injection (negative load) in p.u.
    power_factor = 1.0 (unity, q_pu = 0) unless q_pu is supplied directly.
    """
    bus_id: int
    p_pu: float                 # PV active power OUTPUT (positive = generation)
    q_pu: float = 0.0           # reactive power output/absorption (0 = unity PF)
    name: str = ""

    def __post_init__(self):
        if not self.name:
            self.name = f"PV@Bus{self.bus_id}"


@dataclass
class NetworkModel:
    """Complete network model passed from network_model.py to fbs.py."""
    base_mva: float
    base_kv: float
    buses: Dict[int, Bus]
    lines: List[Line]
    loads: List[Load]
    pv_units: List[PVUnit] = field(default_factory=list)

    # ---- convenience / derived quantities -------------------------------- #

    @property
    def base_kA(self) -> float:
        """Base current in kA for a 3-phase system."""
        return self.base_mva / (3 ** 0.5 * self.base_kv)

    @property
    def slack_bus_id(self) -> int:
        for b in self.buses.values():
            if b.is_slack:
                return b.bus_id
        raise ValueError("NetworkModel has no slack bus defined.")

    def net_bus_injection_pu(self, bus_id: int) -> complex:
        """Net complex power *demand* at a bus = sum(loads) - sum(PV output),
        in p.u., using load-convention sign (positive = power drawn from the
        network). PV generation therefore reduces (or reverses) this value.
        """
        p = sum(l.p_pu for l in self.loads if l.bus_id == bus_id)
        q = sum(l.q_pu for l in self.loads if l.bus_id == bus_id)
        for pv in self.pv_units:
            if pv.bus_id == bus_id:
                p -= pv.p_pu
                q -= pv.q_pu
        return complex(p, q)

    def lines_from(self, bus_id: int) -> List[Line]:
        """All lines whose 'from_bus' is bus_id (i.e. its direct children)."""
        return [ln for ln in self.lines if ln.from_bus == bus_id]

    def line_to(self, bus_id: int) -> Optional[Line]:
        """The single upstream line feeding bus_id (None for the slack bus)."""
        for ln in self.lines:
            if ln.to_bus == bus_id:
                return ln
        return None

    def validate_radial(self) -> None:
        """Raise ValueError if the topology is not a valid radial tree rooted
        at the slack bus (exactly one upstream line per non-slack bus, no
        cycles, every bus reachable). fbs.py relies on this property.
        """
        slack = self.slack_bus_id
        non_slack = [b for b in self.buses if b != slack]

        # exactly one parent per non-slack bus
        for b in non_slack:
            parents = [ln for ln in self.lines if ln.to_bus == b]
            if len(parents) != 1:
                raise ValueError(
                    f"Bus {b} has {len(parents)} upstream line(s); a radial "
                    f"network requires exactly 1 (except the slack bus)."
                )

        # reachability check (BFS from slack) + no extra/cyclic edges
        visited = {slack}
        frontier = [slack]
        while frontier:
            nxt = []
            for b in frontier:
                for ln in self.lines_from(b):
                    if ln.to_bus in visited:
                        raise ValueError(
                            f"Cycle detected: bus {ln.to_bus} reached twice "
                            f"(not radial)."
                        )
                    visited.add(ln.to_bus)
                    nxt.append(ln.to_bus)
            frontier = nxt

        unreached = set(self.buses) - visited
        if unreached:
            raise ValueError(f"Bus(es) {unreached} are not connected to the slack bus.")


# --------------------------------------------------------------------------- #
# Default 5-bus test network
# --------------------------------------------------------------------------- #

def build_default_5bus_network() -> NetworkModel:
    """Builds an illustrative radial 5-bus distribution feeder with one PV
    unit, for exercising fbs.py. Replace with your own data as needed -- the
    shape (Bus/Line/Load/PVUnit/NetworkModel) is what matters, not these
    specific numbers.

    Base values : 1 MVA, 12.66 kV (typical medium-voltage distribution base)
    Topology    : 1 -> 2 -> 3 -> 4   (main feeder)
                       \\-> 5          (lateral off bus 2)
    """
    base_mva = 1.0
    base_kv = 12.66

    buses = {
        1: Bus(1, name="Substation", is_slack=True, v_slack_pu=complex(1.0, 0.0)),
        2: Bus(2, name="Bus2"),
        3: Bus(3, name="Bus3"),
        4: Bus(4, name="Bus4"),
        5: Bus(5, name="Bus5"),
    }

    # r_pu, x_pu already expressed in per-unit on the 1 MVA / 12.66 kV base
    lines = [
        Line(from_bus=1, to_bus=2, r_pu=0.0150, x_pu=0.0300, rating_a_pu=2.0),
        Line(from_bus=2, to_bus=3, r_pu=0.0100, x_pu=0.0200, rating_a_pu=1.5),
        Line(from_bus=3, to_bus=4, r_pu=0.0120, x_pu=0.0250, rating_a_pu=1.0),
        Line(from_bus=2, to_bus=5, r_pu=0.0180, x_pu=0.0350, rating_a_pu=1.0),
    ]

    # Loads in p.u. on the 1 MVA base (e.g. 0.25 p.u. = 250 kW @ unity-ish PF)
    loads = [
        Load(bus_id=2, p_pu=0.25, q_pu=0.12),
        Load(bus_id=3, p_pu=0.30, q_pu=0.15),
        Load(bus_id=4, p_pu=0.20, q_pu=0.10),
        Load(bus_id=5, p_pu=0.15, q_pu=0.08),
    ]

    # One rooftop/feeder-connected PV unit at Bus 4, generating at unity PF
    pv_units = [
        PVUnit(bus_id=4, p_pu=0.18, q_pu=0.0, name="PV_Bus4"),
    ]

    model = NetworkModel(
        base_mva=base_mva,
        base_kv=base_kv,
        buses=buses,
        lines=lines,
        loads=loads,
        pv_units=pv_units,
    )
    model.validate_radial()
    return model


if __name__ == "__main__":
    # Quick smoke test / usage example
    net = build_default_5bus_network()
    print(f"Base: {net.base_mva} MVA, {net.base_kv} kV  |  base current = {net.base_kA:.4f} kA")
    print(f"Slack bus: {net.slack_bus_id}")
    for b in net.buses.values():
        s = net.net_bus_injection_pu(b.bus_id)
        print(f"  {b.name:12s} net demand = {s.real:+.3f} + j{s.imag:+.3f} p.u.")
    print("Topology OK (radial, validated).")
