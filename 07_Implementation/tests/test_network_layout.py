"""Layout decisions are deterministic presentation rules, not power-flow edits."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.network_cases import build_guide_5_bus_case
from src.network_layout import build_layout
from src.network_model import Bus, Line, NetworkModel
from src.network_loader import load_network


class NetworkLayoutTests(unittest.TestCase):
    def test_longest_spine_offset_branch_and_opposite_load(self):
        network = build_guide_5_bus_case()
        before = deepcopy(network)
        layout = build_layout(network)
        self.assertEqual({layout.positions[i][1] for i in (1, 2, 3, 4)}, {0})
        self.assertLess(layout.positions[5][1], 0)
        line_id = network.radial_order().parent_line_by_bus[5]
        route = layout.routes[line_id]
        self.assertLess(route[0][1], layout.positions[2][1])
        self.assertEqual(route[0][1], route[1][1])
        self.assertEqual(route[1][0], route[2][0])
        self.assertEqual(layout.load_sides[2], 'below')
        lower = build_layout(network, {5: 'below'})
        self.assertGreater(lower.positions[5][1], 0)
        self.assertEqual(lower.load_sides[2], 'above')
        self.assertEqual(network, before)

    def test_order_and_electrical_values_do_not_reposition_buses(self):
        network = build_guide_5_bus_case()
        expected = build_layout(network)
        network.buses.reverse()
        network.lines = [replace(line, from_bus=line.to_bus, to_bus=line.from_bus,
                                 r_ohm=line.r_ohm * 2) for line in reversed(network.lines)]
        network.loads = [replace(load, p_base_kw=load.p_base_kw * 3) for load in network.loads]
        self.assertEqual(build_layout(network), expected)

    def test_wide_tree_balances_laterals_and_preserves_all_edges(self):
        network = NetworkModel(
            buses=[Bus(i, str(i), 11, is_slack=i == 1) for i in range(1, 9)],
            lines=[Line(f'L1-{i}', 1, i, .1, .1) for i in range(2, 9)],
            loads=[], pv_units=[], base_power_kva=1000, frequency_hz=60)
        layout = build_layout(network)
        self.assertEqual(len(set(layout.positions.values())), 8)
        ys = [layout.positions[i][1] for i in layout.lateral_roots]
        self.assertTrue(any(y < 0 for y in ys))
        self.assertTrue(any(y > 0 for y in ys))
        self.assertEqual(layout.load_sides[1], 'left')
        self.assertEqual(layout.counts[1], 8)
        self.assertEqual(layout.widths[1], 7)
        self.assertEqual(layout.depths[1], 2)
        for line in network.lines:
            self.assertEqual(layout.routes[line.line_id][-1], layout.positions[line.to_bus])
        self.assertEqual(build_layout(network), layout)

    def test_ieee33_balances_across_separate_junctions(self):
        source = Path(__file__).resolve().parents[2] / '04_Research/Working_Data/Network_Data/Working_RDS/IEEE_33Bus_Network_Data.xlsx'
        network = load_network(source, frequency_hz=60)
        layout = build_layout(network)
        self.assertEqual(set(layout.branch_sides.values()), {'above', 'below'})
        order = network.radial_order()
        parents = {order.parent_bus_by_bus[c] for c in layout.lateral_roots}
        self.assertGreater(len(parents), 1)
        for child, side in layout.branch_sides.items():
            parent = order.parent_bus_by_bus[child]
            delta = layout.positions[child][1] - layout.positions[parent][1]
            if side == 'above':
                self.assertLess(delta, 0)
            else:
                self.assertGreater(delta, 0)
        self.assertEqual(build_layout(network), layout)

    def test_busbars_follow_real_ports_and_annotations_only_change_spacing(self):
        network = build_guide_5_bus_case()
        bare = replace(network, loads=[], pv_units=[])
        empty = build_layout(bare)
        loaded = build_layout(replace(network, pv_units=[]))
        installed = build_layout(network, bess_bus=4)
        self.assertLess(empty.bar_extents[4][1] - empty.bar_extents[4][0],
                        loaded.bar_extents[4][1] - loaded.bar_extents[4][0])
        self.assertLess(loaded.bar_extents[4][1], installed.bar_extents[4][1])
        for bus, ports in installed.equipment_ports.items():
            top, bottom = installed.bar_extents[bus]
            self.assertTrue(all(top < port < bottom for _, port, _ in ports))
        full = build_layout(network, bess_bus=4, show_properties=True, show_results=True)
        self.assertEqual(full.branch_sides, installed.branch_sides)
        self.assertEqual(full.bar_extents, installed.bar_extents)
        self.assertGreater(full.positions[4][0], installed.positions[4][0])
        self.assertGreater(abs(full.positions[5][1]), abs(installed.positions[5][1]))


if __name__ == '__main__':
    unittest.main()
