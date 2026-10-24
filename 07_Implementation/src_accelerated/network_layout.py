"""Topology-based schematic layout; never changes electrical network data."""
from dataclasses import dataclass, field

from .network_model import NetworkModel


@dataclass
class NetworkLayout:
    positions: dict = field(default_factory=dict)
    routes: dict = field(default_factory=dict)
    lateral_roots: list = field(default_factory=list)
    load_sides: dict = field(default_factory=dict)
    bar_halves: dict = field(default_factory=dict)
    bar_extents: dict = field(default_factory=dict)
    equipment_ports: dict = field(default_factory=dict)
    branch_sides: dict = field(default_factory=dict)
    depths: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)
    widths: dict = field(default_factory=dict)


def build_layout(network: NetworkModel, branch_sides=None, *, show_properties=False,
                 show_results=False, bess_bus=None) -> NetworkLayout:
    """Place longest spines first; reserve entire subtree envelopes on each side.

    Overrides are keyed by a lateral's child bus, with 'above'/'below' values
    relative to the unrotated horizontal feeder. IDs only break equal-size ties.
    Envelopes reserve only installed equipment and enabled annotation layers.
    Side allocation is feeder-wide and does not depend on hourly results.
    """
    order = network.radial_order()
    overrides = branch_sides or {}
    forward = [order.slack_bus_id]
    for bus in forward:
        forward.extend(order.children_by_bus[bus])
    layout = NetworkLayout()
    devices = {bus.bus_id: [] for bus in network.buses}
    for load in network.loads:
        if "load" not in devices[load.bus_id]:
            devices[load.bus_id].append("load")
    for unit in network.pv_units:
        if "pv" not in devices[unit.bus_id]:
            devices[unit.bus_id].append("pv")
    if bess_bus in devices:
        devices[bess_bus].append("bess")
    device_counts = {}
    children_sorted = {}
    for bus in reversed(forward):
        children = order.children_by_bus[bus]
        layout.depths[bus] = 1 + max((layout.depths[c] for c in children), default=0)
        layout.counts[bus] = 1 + sum(layout.counts[c] for c in children)
        layout.widths[bus] = sum(layout.widths[c] for c in children) if children else 1
        device_counts[bus] = len(devices[bus]) + sum(device_counts[c] for c in children)
        children_sorted[bus] = sorted(children,
                                     key=lambda c: (-layout.depths[c], -layout.widths[c], -layout.counts[c], c))

    # Allocate every lateral together: a fresh junction must not restart at Above.
    laterals = [child for bus in forward for child in children_sorted[bus][1:]]
    weights = {child: (layout.depths[child] * 120 + layout.widths[child] * 180
                       + layout.counts[child] * 30 + device_counts[child] * 60)
               for child in laterals}
    totals = {"above": 0, "below": 0}
    last_side = "below"
    for child in sorted(laterals, key=lambda c: (-weights[c], c)):
        side = overrides.get(child)
        if side not in totals:
            if totals["above"] == totals["below"]:
                side = "below" if last_side == "above" else "above"
            else:
                side = min(totals, key=totals.get)
        layout.branch_sides[child] = side
        totals[side] += weights[child]
        last_side = side

    annotated = show_properties or show_results
    pitches = {bus: (700.0 if annotated else (280.0 if any(kind != "load" for kind in devices[bus]) else 200.0))
               for bus in forward}
    for bus in forward:
        sides = [layout.branch_sides[c] for c in children_sorted[bus][1:]]
        side = "left" if len(set(sides)) > 1 else ("above" if "below" in sides else "below")
        layout.load_sides[bus] = side
        sign = -1 if side == "above" else 1
        ports = [(kind, sign * (30.0 + index * 55.0), side == "left")
                 for index, kind in enumerate(devices[bus])]
        layout.equipment_ports[bus] = ports
        takeoffs = [0.0] + [port for _, port, _ in ports]
        takeoffs.extend(-30.0 - index * 35.0 for index in range(sides.count("above")))
        takeoffs.extend(30.0 + index * 35.0 for index in range(sides.count("below")))
        top = min(takeoffs) - 16.0
        bottom = max(takeoffs) + 16.0
        layout.bar_extents[bus] = top, bottom
        layout.bar_halves[bus] = max(abs(top), abs(bottom))

    # Build local subtree templates bottom-up, avoiding recursion limits.
    templates = {}
    for bus in reversed(forward):
        pitch = pitches[bus]
        children = children_sorted[bus]
        positions = {bus: (0.0, 0.0)}
        routes = {}
        bar_top, bar_bottom = layout.bar_extents[bus]
        top = min(bar_top - 65, -400.0 if show_properties else -65.0)
        bottom = max(bar_bottom + 50, 430.0 if show_results else 50.0)
        sides = []
        for index, child in enumerate(children):
            child_positions, child_routes, child_top, child_bottom = templates[child]
            if index == 0:
                dx, dy = pitch, 0.0
                route = [(0.0, 0.0), (dx, dy)]
            else:
                side = layout.branch_sides[child]
                if side == "above":
                    dy = top - 80.0 - child_bottom
                    port = -30.0 - sides.count("above") * 35.0
                else:
                    dy = bottom + 80.0 - child_top
                    port = 30.0 + sides.count("below") * 35.0
                sides.append(side)
                dx = pitch / 2
                # Offset take-off, straight lead, then an orthogonal bend.
                # Outer laterals use an inner corridor, never crossing an
                # earlier lateral's horizontal run on the same side.
                lead = min(140.0, pitch / 3) / index
                route = [(0.0, port), (lead, port), (lead, dy), (dx, dy)]
                layout.lateral_roots.append(child)
            for item, (x, y) in child_positions.items():
                positions[item] = (x + dx, y + dy)
            for line_id, points in child_routes.items():
                routes[line_id] = [(x + dx, y + dy) for x, y in points]
            routes[order.parent_line_by_bus[child]] = route
            top = min(top, dy + child_top)
            bottom = max(bottom, dy + child_bottom)
        templates[bus] = positions, routes, top, bottom
    layout.positions, layout.routes, _, _ = templates[order.slack_bus_id]
    layout.lateral_roots.sort()
    return layout


def arrange_network(network: NetworkModel) -> dict[int, tuple[float, float]]:
    """Backward-compatible coordinate-only interface."""
    return build_layout(network).positions
