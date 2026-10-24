"""Piecewise PV equations, provider units and unchanged-loader integration."""
from copy import deepcopy
from io import StringIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data_loader import ProfileData
from src.load_generator import LoadGenerationConfig, generate_load_profile
from src.network_cases import build_guide_5_bus_case
from src.network_model import PVUnit
from src.pv_model import PVModelConfig, irradiance_to_power, make_pv_profile, read_irradiance
from src.simulation import SimulationConfig, simulate_timeseries


DATA = Path(__file__).resolve().parents[2] / "04_Research/Working_Data/Jeddah_Weather_PV"


class PVModelTests(unittest.TestCase):
    def setUp(self):
        self.config = PVModelConfig(critical_irradiance_w_m2=120)
        self.network = build_guide_5_bus_case()
        self.weather = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=4, freq="h"),
                                     "irradiance_w_m2": [0, 60, 500, 1200]})

    def read_text(self, text, source):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            path = Path(directory) / "weather.csv"
            path.write_text(text, encoding="utf-8-sig")
            return read_irradiance(path, source=source)

    def test_hand_calculations_and_saturation(self):
        for radiation, expected in [(0, 0), (60, 3), (120, 12), (500, 50), (1000, 100), (1500, 100)]:
            with self.subTest(radiation=radiation):
                self.assertAlmostEqual(irradiance_to_power(radiation, 100, self.config), expected)

    def test_continuity_at_both_thresholds(self):
        for boundary in [120, 1000]:
            left = irradiance_to_power(boundary - 1e-7, 100, self.config)
            right = irradiance_to_power(boundary + 1e-7, 100, self.config)
            self.assertAlmostEqual(left, right, places=6)

    def test_zero_capacity(self):
        self.assertEqual(irradiance_to_power(500, 0, self.config), 0)

    def test_bad_thresholds(self):
        for critical, standard in [(0, 1000), (-1, 1000), (1000, 1000), (1200, 1000), (120, 0), (float("nan"), 1000), (120, float("inf")), (True, 1000)]:
            with self.subTest(values=(critical, standard)), self.assertRaises(ValueError):
                PVModelConfig(critical, standard)

    def test_bad_power_inputs(self):
        for value in [-999, -1, float("nan"), float("inf"), True, "500"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                irradiance_to_power(value, 100, self.config)
            with self.assertRaises(ValueError):
                irradiance_to_power(500, value, self.config)

    def test_prepared_csv(self):
        frame = self.read_text("timestamp,irradiance_w_m2\n2024-01-01T00:00,0\n2024-01-01T01:00,500\n", "prepared")
        self.assertEqual(frame.irradiance_w_m2.tolist(), [0, 500])

    def test_open_meteo_metadata_and_extra_weather(self):
        text = "latitude,longitude\n21,39\n\ntime,shortwave_radiation (W/m²),temperature\n2024-01-01T00:00,0,22\n2024-01-01T01:00,500,25\n"
        self.assertEqual(self.read_text(text, "open_meteo").irradiance_w_m2.tolist(), [0, 500])

    def test_nasa_energy_density_becomes_hourly_mean(self):
        text = "NASA HEADER\n-END HEADER-\nYEAR,MO,DY,HR,ALLSKY_SFC_SW_DWN\n2024,1,1,0,0\n2024,1,1,1,500\n"
        frame = self.read_text(text, "nasa_power")
        self.assertEqual(frame.irradiance_w_m2.tolist(), [0, 500])
        self.assertEqual(frame.timestamp.iloc[1], pd.Timestamp("2024-01-01T01:00"))

    def test_nasa_bad_hours(self):
        for hour in [24, -1, 1.5]:
            text = f"YEAR,MO,DY,HR,ALLSKY_SFC_SW_DWN\n2024,1,1,0,0\n2024,1,1,{hour},500\n"
            with self.subTest(hour=hour), self.assertRaises(ValueError):
                self.read_text(text, "nasa_power")

    def test_missing_headers_and_source_errors(self):
        for source in ["prepared", "open_meteo", "nasa_power", "unknown"]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.read_text("wrong,value\na,1\n", source)

    def test_bad_radiation_rows(self):
        for value in ["", "nan", "inf", "-999", "-1", "text", "True"]:
            text = f"timestamp,irradiance_w_m2\n2024-01-01T00:00,0\n2024-01-01T01:00,{value}\n"
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.read_text(text, "prepared")

    def test_bad_timestamps(self):
        for second in ["2024-01-01T00:00", "2024-01-01T02:00", "2023-12-31T23:00", "bad", ""]:
            text = f"timestamp,irradiance_w_m2\n2024-01-01T00:00,0\n{second},500\n"
            with self.subTest(second=second), self.assertRaises(ValueError):
                self.read_text(text, "prepared")
        with self.assertRaises(ValueError):
            self.read_text("timestamp,irradiance_w_m2\n2024-01-01T00:00+03:00,0\n2024-01-01T01:00+03:00,500\n", "prepared")

    def test_aggregate_units_and_do_not_mutate(self):
        self.network.pv_units.append(PVUnit("extra", 4, 20))
        before = deepcopy(self.network)
        original_weather = self.weather.copy(deep=True)
        result = make_pv_profile(self.network, self.weather, self.config)
        self.assertEqual(result.bus_id.tolist(), [4] * 4)
        self.assertEqual(result.p_kw.tolist(), [0, 6, 100, 200])
        self.assertTrue((result.q_kvar == 0).all())
        self.assertEqual(self.network, before)
        pd.testing.assert_frame_equal(self.weather, original_weather)

    def test_no_pv_produces_compatible_zero_table(self):
        self.network.pv_units.clear()
        result = make_pv_profile(self.network, self.weather, self.config)
        self.assertEqual(set(result.bus_id), {self.network.slack_bus_id()})
        self.assertTrue((result.p_kw == 0).all())

    def test_real_provider_files_full_leap_year(self):
        for name, source in [("OpenMeteo_Jeddah_2024_Hourly.csv", "open_meteo"),
                             ("NASA_POWER_Jeddah_2024_Hourly.csv", "nasa_power")]:
            with self.subTest(source=source):
                frame = read_irradiance(DATA / name, source=source)
                self.assertEqual(len(frame), 8784)
                self.assertEqual(frame.timestamp.iloc[-1], pd.Timestamp("2024-12-31T23:00"))

    def test_loader_and_simulator_integration(self):
        weather = read_irradiance(DATA / "OpenMeteo_Jeddah_2024_Hourly.csv", source="open_meteo").iloc[:24]
        pv = make_pv_profile(self.network, weather, self.config)
        load = generate_load_profile(self.network, weather.timestamp, LoadGenerationConfig())
        profiles = ProfileData(StringIO(load.to_csv(index=False)), StringIO(pv.to_csv(index=False)))
        result = simulate_timeseries(self.network, profiles, SimulationConfig())
        self.assertTrue(result.completed)
        self.assertTrue(result.converged)
        self.assertEqual(len(result.steps), 24)


if __name__ == "__main__":
    unittest.main()
