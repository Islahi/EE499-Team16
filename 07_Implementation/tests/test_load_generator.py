"""Synthetic load statistics, reproducibility, units and base-P/Q assumptions."""
from copy import deepcopy
from pathlib import Path
from random import getstate
import sys
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.load_generator import LoadGenerationConfig, SINDI_MEAN_PERCENT, SINDI_SD_PERCENT, generate_load_profile
from src.network_cases import build_guide_5_bus_case
from src.network_model import Load


class LoadGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.network = build_guide_5_bus_case()
        self.times = pd.date_range("2024-01-01", periods=48, freq="h")

    def test_source_values_and_units(self):
        self.assertEqual(len(SINDI_MEAN_PERCENT), 24)
        self.assertEqual(len(SINDI_SD_PERCENT), 24)
        self.assertEqual(SINDI_MEAN_PERCENT[0], 65.177)
        self.assertEqual(SINDI_MEAN_PERCENT[12], 82.103)
        self.assertEqual(SINDI_MEAN_PERCENT[23], 69.979)
        self.assertEqual(SINDI_SD_PERCENT[23], 5.167)

    def test_constant_half_base_hand_calculation(self):
        settings = LoadGenerationConfig(mean_percent=(50,) * 24, sd_percent=(0,) * 24)
        frame = generate_load_profile(self.network, self.times, settings)
        for load in self.network.loads:
            bus = frame[frame.bus_id == load.bus_id]
            self.assertTrue((bus.p_kw == load.p_base_kw * 0.5).all())
            self.assertTrue((bus.q_kvar == load.q_base_kvar * 0.5).all())

    def test_hour_mapping_uses_clock_not_row_index(self):
        settings = LoadGenerationConfig(mean_percent=tuple(range(24)), sd_percent=(0,) * 24)
        times = pd.date_range("2024-01-01T17:00", periods=2, freq="h")
        frame = generate_load_profile(self.network, times, settings)
        load = self.network.loads[0]
        self.assertAlmostEqual(frame[frame.bus_id == load.bus_id].p_kw.iloc[0], load.p_base_kw * 0.17)

    def test_shared_multiplier_preserves_pq_and_bus_proportions(self):
        frame = generate_load_profile(self.network, self.times)
        for timestamp, rows in frame.groupby("timestamp"):
            ratios = []
            for row in rows.itertuples():
                base = next(load for load in self.network.loads if load.bus_id == row.bus_id)
                ratios.append(row.p_kw / base.p_base_kw)
                self.assertAlmostEqual(row.q_kvar / base.q_base_kvar, ratios[-1])
            self.assertLess(max(ratios) - min(ratios), 1e-12)

    def test_aggregate_multiple_base_loads_per_bus(self):
        load = self.network.loads[0]
        self.network.loads.append(Load("extra", load.bus_id, 10, 5))
        config = LoadGenerationConfig(mean_percent=(100,) * 24, sd_percent=(0,) * 24)
        frame = generate_load_profile(self.network, self.times, config)
        self.assertEqual(frame[frame.bus_id == load.bus_id].p_kw.iloc[0], load.p_base_kw + 10)
        self.assertFalse(frame.duplicated(["timestamp", "bus_id"]).any())

    def test_seed_reproducibility_and_global_random_unchanged(self):
        before = getstate()
        first = generate_load_profile(self.network, self.times)
        second = generate_load_profile(self.network, self.times)
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(before, getstate())
        different = generate_load_profile(self.network, self.times, LoadGenerationConfig(seed=43))
        self.assertFalse(first.p_kw.equals(different.p_kw))

    def test_input_network_and_times_are_not_mutated(self):
        before = deepcopy(self.network)
        times = self.times.copy()
        generate_load_profile(self.network, self.times)
        self.assertEqual(self.network, before)
        self.assertTrue(self.times.equals(times))

    def test_negative_samples_clipped_and_reported(self):
        with patch("src.load_generator.Random.gauss", return_value=-5):
            frame = generate_load_profile(self.network, self.times)
        self.assertTrue((frame.p_kw == 0).all())
        self.assertTrue((frame.q_kvar == 0).all())
        self.assertEqual(frame.attrs["negative_samples_clipped"], 48)

    def test_load_not_capped_at_base(self):
        config = LoadGenerationConfig(mean_percent=(150,) * 24, sd_percent=(0,) * 24)
        frame = generate_load_profile(self.network, self.times, config)
        self.assertEqual(frame.p_kw.iloc[0], self.network.loads[0].p_base_kw * 1.5)

    def test_bad_configuration(self):
        for kwargs in [{"seed": -1}, {"seed": True}, {"seed": 1.5}, {"mean_percent": (50,) * 23},
                       {"sd_percent": (1,) * 25}, {"mean_percent": (-1,) * 24},
                       {"sd_percent": (float("nan"),) * 24}, {"sd_percent": (float("inf"),) * 24}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                LoadGenerationConfig(**kwargs)

    def test_bad_timestamps(self):
        for times in [[], ["2024-01-01"], ["2024-01-01", "2024-01-01"],
                      ["2024-01-01T01:00", "2024-01-01"], ["2024-01-01", "2024-01-01T02:00"],
                      ["bad", "data"], [None, None],
                      pd.date_range("2024-01-01", periods=2, freq="h", tz="Asia/Riyadh")]:
            with self.subTest(times=times), self.assertRaises(ValueError):
                generate_load_profile(self.network, times)

    def test_missing_and_q_only_base_loads_rejected(self):
        self.network.loads = []
        with self.assertRaises(ValueError):
            generate_load_profile(self.network, self.times)
        self.network.loads = [Load("reactive", 2, 0, 10)]
        with self.assertRaises(ValueError):
            generate_load_profile(self.network, self.times)

    def test_reordered_devices_do_not_change_seeded_output(self):
        first = generate_load_profile(self.network, self.times)
        self.network.loads.reverse()
        pd.testing.assert_frame_equal(first, generate_load_profile(self.network, self.times))

    def test_three_calendar_months_and_leap_day(self):
        times = pd.date_range("2024-01-01", "2024-04-01", inclusive="left", freq="h")
        frame = generate_load_profile(self.network, times)
        self.assertEqual(len(times), 2184)
        self.assertEqual(len(frame), 2184 * len(self.network.loads))
        self.assertIn(pd.Timestamp("2024-02-29T12:00"), set(frame.timestamp))

    def test_large_sample_matches_hourly_mean_and_sd(self):
        frame = generate_load_profile(self.network, pd.date_range("2024-01-01", periods=24000, freq="h"))
        load = self.network.loads[0]
        values = frame[frame.bus_id == load.bus_id]
        hour = values[values.timestamp.dt.hour == 12].p_kw / load.p_base_kw * 100
        self.assertAlmostEqual(hour.mean(), SINDI_MEAN_PERCENT[12], delta=0.8)
        self.assertAlmostEqual(hour.std(), SINDI_SD_PERCENT[12], delta=0.6)


if __name__ == "__main__":
    unittest.main()
