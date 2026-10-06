import cmath
import unittest
from dataclasses import replace
from math import sqrt
from src.network_model import Bus, Line, Load, NetworkModel
from src.network_cases import build_5_bus_case, build_guide_3_bus_case, build_guide_5_bus_case
from src.main import base_operating_point
from src.fbs import run_fbs, FBSConfig


class FBSTests(unittest.TestCase):
    def solve(self, n, **kwargs):
        return run_fbs(n, base_operating_point(n), FBSConfig(**kwargs))

    def test_manual_first_sweep(self):
        r = self.solve(build_guide_3_bus_case(), max_iterations=1)
        self.assertAlmostEqual(abs(r.voltage_complex_pu[2] - (.99-.0075j)), 0)
        self.assertAlmostEqual(abs(r.voltage_complex_pu[3] - (.986-.0105j)), 0)
        self.assertAlmostEqual(r.max_delta_v_pu, .0175)
        self.assertFalse(r.converged)

    def test_guide_final_answers(self):
        for builder, expected, losses in [
            (build_guide_3_bus_case, [1, .989843, .985780], 3.714509),
            (build_guide_5_bus_case, [1, .97477, .96626, .96342, .96908], 13.963418),
        ]:
            n = builder()
            r = self.solve(n, voltage_tolerance_pu=1e-12)
            self.assertTrue(r.converged)
            for i, value in enumerate(expected, 1):
                self.assertAlmostEqual(r.voltage_mag_pu[i], value, delta=5e-6)
            self.assertAlmostEqual(r.total_loss_p_kw, losses, delta=1e-5)
            op = base_operating_point(n)
            self.assertAlmostEqual(r.slack_p_kw-r.total_loss_p_kw,
                                   sum(op.p_load_kw.values())-sum(op.p_pv_kw.values()), delta=1e-8)
            self.assertAlmostEqual(r.slack_q_kvar-r.total_loss_q_kvar,
                                   sum(op.q_load_kvar.values()), delta=1e-8)

    def test_two_bus_analytic_solution(self):
        # Real-only feeder: V^2 - V + R*P = 0 (high-voltage root).
        n = NetworkModel([Bus(10, "source", 1, True), Bus(40, "load", 1)],
                         [Line("branch", 40, 10, .1, 0)], [Load("d", 40, 200, 0)], [], 1000, 60)
        r = self.solve(n, voltage_tolerance_pu=1e-12)
        self.assertAlmostEqual(r.voltage_mag_pu[40], (1+sqrt(1-4*.1*.2))/2, places=11)

    def test_no_load_and_slack_angle(self):
        r = self.solve(build_5_bus_case(), slack_angle_deg=30)
        self.assertTrue(r.converged)
        self.assertEqual(r.iterations, 1)
        self.assertEqual(r.total_loss_p_kw, 0)
        for angle in r.voltage_angle_deg.values():
            self.assertAlmostEqual(angle, 30)

    def test_reversed_lines(self):
        n = build_guide_5_bus_case()
        expected = self.solve(n)
        n.lines = [replace(l, from_bus=l.to_bus, to_bus=l.from_bus) for l in n.lines[::-1]]
        self.assertEqual(self.solve(n).voltage_complex_pu, expected.voltage_complex_pu)

    def test_pv_export_and_bess_sign(self):
        n = build_5_bus_case([Load("d", 5, 100, 40)])
        op = base_operating_point(n)
        baseline = run_fbs(n, op, FBSConfig())
        op.p_bess_kw[5] = 200
        discharge = run_fbs(n, op, FBSConfig())
        self.assertLess(discharge.slack_p_kw, 0)
        op.p_bess_kw[5] = -100
        charge = run_fbs(n, op, FBSConfig())
        self.assertGreater(charge.slack_p_kw, baseline.slack_p_kw)
        op.p_bess_kw[5] = 0
        op.p_pv_kw[5] = 200
        self.assertEqual(run_fbs(n, op, FBSConfig()).slack_p_kw, discharge.slack_p_kw)

    def test_slack_local_load(self):
        n = build_5_bus_case([Load("source demand", 1, 20, 10)])
        r = self.solve(n)
        self.assertEqual((r.slack_p_kw, r.slack_q_kvar), (20, 10))

    def test_invalid_inputs(self):
        n = build_5_bus_case()
        for config in [FBSConfig(max_iterations=0), FBSConfig(max_iterations=1.5),
                       FBSConfig(voltage_tolerance_pu=float("nan"))]:
            with self.assertRaises(ValueError):
                run_fbs(n, base_operating_point(n), config)
        op = base_operating_point(n)
        del op.p_load_kw[5]
        with self.assertRaises(ValueError):
            run_fbs(n, op, FBSConfig())
        op = base_operating_point(n)
        op.p_load_kw[5] = float("inf")
        with self.assertRaises(ValueError):
            run_fbs(n, op, FBSConfig())

    def test_history_and_failure_guard(self):
        n = NetworkModel([Bus(1, "s", 1, True), Bus(2, "d", 1)],
                         [Line("L", 1, 2, 1, 0)], [Load("d", 2, 1000, 0)], [], 1000, 60)
        r = self.solve(n, record_history=True)
        self.assertFalse(r.converged)
        self.assertIn("Near-zero", r.message)
        self.assertEqual(len(r.voltage_history), 2)
