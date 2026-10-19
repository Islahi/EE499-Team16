"""Qt-free UI orchestration, generic sizing, dispatch and diagram layout checks."""
from copy import deepcopy
from dataclasses import replace
from io import StringIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dispatch import NetLoadTargetPolicy
from src.network_cases import build_guide_5_bus_case
from src.network_layout import arrange_network
from src.network_model import PVUnit
from src.data_loader import ProfileData
from src.metrics import EconomicConfig
from src.simulation import SimulationConfig
from src.ui_workflow import DataRequest, RunSettings, export_report, prepare_study, run_study, size_catalog


ROOT = Path(__file__).resolve().parents[2]
NETWORK = ROOT / "04_Research/Working_Data/Network_Data/IEEE_33Bus_Network_Data.xlsx"
WEATHER = ROOT / "04_Research/Working_Data/Jeddah_Weather_PV/OpenMeteo_Jeddah_2024_Hourly.csv"


def request(**kwargs):
    values = dict(network_path=NETWORK, frequency_hz=60, workbook_format="auto",
                  start="2024-01-01", months=1, pv_source="none")
    values.update(kwargs)
    return DataRequest(**values)


def short_study():
    network = build_guide_5_bus_case()
    with patch("src.ui_workflow.load_network", return_value=network):
        study = prepare_study(request())
    study.profiles.timestamps = study.profiles.timestamps[:24]
    for name in ("load_p_kw", "load_q_kvar", "pv_p_kw", "pv_q_kvar"):
        setattr(study.profiles, name, {bus: values[:24] for bus, values in getattr(study.profiles, name).items()})
    return study


def optimization_values():
    return dict(spin_eta_charge_percent=95, spin_eta_discharge_percent=95,
                spin_soc_min_percent=10, spin_soc_max_percent=90, spin_soc_initial_percent=50,
                allowed_buses=(4,), spin_opt_power_min_kw=100, spin_opt_power_max_kw=200,
                spin_opt_power_step_kw=100, spin_opt_energy_min_kwh=200, spin_opt_energy_max_kwh=400,
                spin_opt_energy_step_kwh=200, spin_gwo_population=3, spin_gwo_iterations=1,
                spin_gwo_seed=42, group_uncertainty=False)


class UIWorkflowTests(unittest.TestCase):
    def test_five_bus_workbook_matches_guide_case(self):
        path = NETWORK.parent / "Guide_5Bus_Radial_Test.xlsx"
        study = prepare_study(request(network_path=path, months=1))
        self.assertEqual(len(study.profiles.timestamps), 744)
        expected = build_guide_5_bus_case()
        self.assertEqual(study.network.lines, expected.lines)
        self.assertEqual(study.network.loads, expected.loads)
        self.assertEqual(study.network.buses, expected.buses)

    def test_endpoint_grid_and_decimals(self):
        self.assertEqual(size_catalog(100, 250, 100), (100, 200, 250))
        self.assertEqual(size_catalog(0.1, 0.3, 0.1), (0.1, 0.2, 0.3))
        self.assertEqual(size_catalog(50, 50, 10), (50,))

    def test_invalid_grids_and_resource_guard(self):
        for values in [(0, 100, 1), (1, 0, 1), (1, 2, 0), (2, 1, 1),
                       (True, 2, 1), (1, float("inf"), 1), (1, 10001, 1), (1e-308, 1e308, 1e-308)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                size_catalog(*values)

    def test_dispatch_signs_and_zero_target(self):
        from types import SimpleNamespace
        profile = SimpleNamespace(p_load_kw={1: 100}, p_pv_kw={1: 30})
        self.assertEqual(NetLoadTargetPolicy(50)(0, profile, None), 20)
        self.assertEqual(NetLoadTargetPolicy(100)(0, profile, None), -30)
        self.assertEqual(NetLoadTargetPolicy(0)(0, profile, None), 70)

    def test_dispatch_rejects_bad_target(self):
        for value in [-1, float("nan"), float("inf"), True, "100"]:
            with self.assertRaises(ValueError):
                NetLoadTargetPolicy(value)

    def test_layout_preserves_model_and_is_deterministic(self):
        network = build_guide_5_bus_case()
        before = deepcopy(network)
        positions = arrange_network(network)
        self.assertEqual(set(positions), {1, 2, 3, 4, 5})
        self.assertEqual(len(set(positions.values())), 5)
        self.assertLess(positions[1][0], positions[2][0])
        self.assertEqual(positions, arrange_network(network))
        self.assertEqual(network, before)

    def test_no_pv_clears_existing_devices_and_keeps_source(self):
        network = build_guide_5_bus_case()
        before = deepcopy(network)
        with patch("src.ui_workflow.load_network", return_value=network):
            study = prepare_study(request())
        self.assertEqual(study.network.pv_units, [])
        self.assertEqual(network, before)
        self.assertEqual(len(study.profiles.timestamps), 744)
        self.assertEqual(max(study.profiles.pv_p_kw[1]), 0)

    def test_real_weather_and_installed_ratings(self):
        study = prepare_study(request(pv_source="open_meteo", pv_path=WEATHER,
                                      pv_ratings_kw={6: 1000}, critical_irradiance=120))
        self.assertEqual(len(study.profiles.timestamps), 744)
        self.assertEqual(study.network.pv_units[0].p_rated_kw, 1000)
        self.assertLessEqual(max(study.profiles.pv_p_kw[6]), 1000)
        self.assertIn("not measured", study.context["Demand"])

    def test_uncovered_weather_and_unknown_pv_bus(self):
        with self.assertRaises(ValueError):
            prepare_study(request(start="2025-01-01", pv_source="open_meteo", pv_path=WEATHER,
                                  pv_ratings_kw={6: 1000}, critical_irradiance=120))
        with self.assertRaises(ValueError):
            prepare_study(request(pv_source="prepared", pv_ratings_kw={999: 1000}))

    def test_imported_load_and_pv_roundtrip(self):
        study = prepare_study(request())
        times = study.profiles.timestamps
        rows = [(t, bus, values[i], study.profiles.load_q_kvar[bus][i]) for bus, values in study.profiles.load_p_kw.items() for i, t in enumerate(times)]
        demand = pd.DataFrame(rows, columns=["timestamp", "bus_id", "p_kw", "q_kvar"])
        pv = pd.DataFrame({"timestamp": times, "bus_id": 6, "p_kw": 10, "q_kvar": 0})
        with TemporaryDirectory(dir=ROOT / "07_Implementation") as directory:
            load_path, pv_path = Path(directory) / "load.csv", Path(directory) / "pv.csv"
            demand.to_csv(load_path, index=False)
            pv.to_csv(pv_path, index=False)
            imported = prepare_study(request(load_source="imported", load_path=load_path,
                                             pv_source="power", pv_path=pv_path, pv_ratings_kw={6: 100}))
            self.assertAlmostEqual(imported.profiles.load_p_kw[2][0], study.profiles.load_p_kw[2][0])
            for bad in (demand.iloc[1:], pd.concat([demand, demand.iloc[:1]]), demand.assign(bus_id=999), demand.assign(p_kw=float("nan")), demand.assign(bus_id=2.5)):
                bad.to_csv(load_path, index=False)
                with self.assertRaises(ValueError):
                    prepare_study(request(load_source="imported", load_path=load_path))
            with self.assertRaises(ValueError):
                prepare_study(request(pv_source="power", pv_path=pv_path))

    def test_baseline_simulation_and_safe_export(self):
        study = short_study()
        settings = RunSettings(SimulationConfig(reserve_fraction=0), EconomicConfig(), None, {})
        report = run_study(study, settings)
        self.assertTrue(report.result.completed)
        self.assertTrue(report.result.converged)
        self.assertIn("Completed: True", report.summary())
        self.assertGreaterEqual(float(report.context["Run duration (seconds)"]), 0)
        self.assertIn("Run started (device clock)", report.context)
        self.assertIn("Run duration", report.summary())
        with TemporaryDirectory(dir=ROOT / "07_Implementation") as directory:
            path = Path(directory) / "new_export"
            export_report(report, path)
            self.assertTrue((path / "summary.md").exists())
            self.assertIn("Run duration", (path / "summary.md").read_text(encoding="utf-8"))
            with self.assertRaises((ValueError, FileExistsError)):
                export_report(report, path)

    def test_deterministic_optimization_through_existing_engine(self):
        settings = RunSettings(SimulationConfig(reserve_fraction=0), EconomicConfig(2, 3), None,
                               optimization_values(), NetLoadTargetPolicy(600))
        report = run_study(short_study(), settings, optimization=True)
        self.assertTrue(report.result.success)
        self.assertIn(report.result.best_candidate.power_rating_kw, (100, 200))
        self.assertIn("endpoint-inclusive", report.context["Search catalogs"])
        self.assertNotIn("Search catalogs", report.summary())
        self.assertIn("Search catalogs", report.summary(detailed=True))

    def test_no_bess_baseline_does_not_apply_configured_dispatch(self):
        settings = RunSettings(SimulationConfig(reserve_fraction=0), EconomicConfig(), None,
                               {}, NetLoadTargetPolicy(600))
        report = run_study(short_study(), settings)
        self.assertTrue(report.result.completed)
        self.assertIn("not applied", report.context["Dispatch"])
        self.assertIn("Simulation settings", report.context)

    def test_uncertainty_wiring_uses_profile_pv_keys(self):
        study = short_study()
        # Extend history for ARIMA validation; deterministic zero-PV is preserved.
        network = build_guide_5_bus_case()
        with patch("src.ui_workflow.load_network", return_value=network):
            study = prepare_study(request())
        # Deterministic history isolates wiring from stochastic ARIMA fit quality.
        # The existing uncertainty tests separately exercise nonconstant ARIMA.
        for bus, values_for_bus in study.profiles.load_p_kw.items():
            study.profiles.load_p_kw[bus] = [values_for_bus[0]] * len(values_for_bus)
            study.profiles.load_q_kvar[bus] = [study.profiles.load_q_kvar[bus][0]] * len(values_for_bus)
        values = optimization_values()
        values.update(group_uncertainty=True, spin_forecast_hours=2, spin_scenario_count=3,
                      spin_best_count=1, spin_worst_count=1, spin_random_count=1,
                      spin_uncertainty_seed=42, spin_selection_seed=42)
        settings = RunSettings(SimulationConfig(reserve_fraction=0), EconomicConfig(2, 3), None,
                               values, NetLoadTargetPolicy(600))
        report = run_study(study, settings, optimization=True)
        self.assertTrue(report.result.success)
        self.assertIn("Forecast interval", report.context)


if __name__ == "__main__":
    unittest.main()
