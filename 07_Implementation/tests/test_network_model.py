import unittest
from dataclasses import replace
from src.network_cases import build_5_bus_case, build_guide_5_bus_case
from src.network_model import Line, Load, PVUnit


class NetworkTests(unittest.TestCase):
    def test_prepared_case(self):
        n = build_5_bus_case()
        n.validate()
        self.assertEqual(n.base_power_kva, 10000)
        self.assertEqual(n.radial_order().parent_bus_by_bus, {2: 1, 3: 2, 4: 3, 5: 4})
        self.assertEqual(n.loads, [])
        self.assertEqual(n.lines[-1].r_ohm, .5)

    def test_orientation_and_order_independent(self):
        n = build_guide_5_bus_case()
        expected = n.radial_order()
        n.lines = [replace(l, from_bus=l.to_bus, to_bus=l.from_bus) for l in reversed(n.lines)]
        self.assertEqual(n.radial_order(), expected)

    def test_invalid_networks(self):
        mutations = [
            lambda n: n.buses.append(n.buses[0]),
            lambda n: n.buses.__setitem__(1, replace(n.buses[1], is_slack=True)),
            lambda n: n.lines.append(n.lines[0]),
            lambda n: n.lines.__setitem__(0, replace(n.lines[0], to_bus=99)),
            lambda n: n.lines.__setitem__(0, replace(n.lines[0], to_bus=1)),
            lambda n: n.lines.pop(),
            lambda n: n.lines.append(Line("loop", 1, 5, .1, .1)),
            lambda n: n.loads.append(Load("bad", 99, 1, 0)),
            lambda n: n.loads.append(Load("bad", 2, -1, 0)),
            lambda n: n.pv_units.append(PVUnit("bad", 99, 1)),
            lambda n: setattr(n, "base_power_kva", 0),
            lambda n: n.buses.__setitem__(1, replace(n.buses[1], base_kv=12.66)),
            lambda n: n.lines.__setitem__(0, replace(n.lines[0], r_ohm=float("nan"))),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                n = build_5_bus_case()
                mutation(n)
                with self.assertRaises(ValueError):
                    n.validate()
