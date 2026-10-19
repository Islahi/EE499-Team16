"""Published feeder data and separate supplied-guide verification cases."""
from .network_model import Bus, Line, Load, PVUnit, NetworkModel


def build_5_bus_case(loads=None, pv_units=None) -> NetworkModel:
    """Prepared 11 kV / 10 MVA chain; pass study loads/PV explicitly.

    No arguments creates the unloaded topology. The source supplies no bus
    loads or PV ratings; empty defaults are not historical measurements.
    Frequency 60 Hz is a development configuration, not source feeder data.
    """
    network = NetworkModel(
        [Bus(i, f"Bus {i}", 11.0, i == 1) for i in range(1, 6)],
        [Line(f"L{i}", i, i + 1, r, x) for i, (r, x) in enumerate(
            [(0.35, 0.45), (0.40, 0.50), (0.48, 0.52), (0.50, 0.60)], 1)],
        list(loads or []), list(pv_units or []), 10000.0, 60.0)
    network.validate()
    return network


def build_guide_3_bus_case() -> NetworkModel:
    """Guide Example 1: 1 MVA / 1 kV gives Z_base = 1 ohm."""
    return NetworkModel(
        [Bus(i, f"Bus {i}", 1.0, i == 1) for i in range(1, 4)],
        [Line("L1", 1, 2, 0.01, 0.02), Line("L2", 2, 3, 0.01, 0.02)],
        [Load("LD2", 2, 300, 150), Load("LD3", 3, 200, 100)], [], 1000, 60)


def build_guide_5_bus_case() -> NetworkModel:
    """Guide Example 2, distinct from the prepared 11 kV feeder."""
    zbase = 12.66 ** 2
    return NetworkModel(
        [Bus(i, f"Bus {i}", 12.66, i == 1) for i in range(1, 6)],
        [Line(name, a, b, r * zbase, x * zbase) for name, a, b, r, x in
         [("L1", 1, 2, .015, .030), ("L2", 2, 3, .010, .020),
          ("L3", 2, 5, .018, .035), ("L4", 3, 4, .012, .025)]],
        [Load(f"LD{i}", i, p, q) for i, p, q in
         [(2, 250, 120), (3, 300, 150), (4, 200, 100), (5, 150, 80)]],
        [PVUnit("PV4", 4, 180)], 1000, 60)
