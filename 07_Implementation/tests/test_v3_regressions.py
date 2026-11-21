"""Production regression checks using real models and archived fixtures."""
import json
import os
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src_accelerated.bess import BESSConfig
from src_accelerated.data_loader import ProfileData
from src_accelerated.distributed_dataset import discover_cases, summary_pv_ratings
from src_accelerated.fbs import FBSConfig, OperatingPoint, run_fbs
from src_accelerated.forecast_models import FeatureCache
from src_accelerated.forecasting import ForecastConfig, _pv_predict, generate_forecast
from src_accelerated.metrics import EconomicConfig, validate_annual_inputs
from src_accelerated.network_loader import load_network
from src_accelerated.optimizer import (BESSCandidate, BESSParameters, OptimizationBounds,
    OptimizerConfig, SimulationEvaluator, exhaustive_search, genetic_optimize, optimize)
from src_accelerated.simulation import GridAwareDispatchPolicy, SimulationConfig, simulate_timeseries
from src_accelerated.solar_source import PVReference, SolarSite, daylight
from src_accelerated.study_session import StudySession, migrate_inputs
from src_accelerated.ui_workflow import DataRequest, prepare_study
from test_integrated_upgrade import simple_network, source_data


ROOT = Path(os.environ.get("EE499_VALIDATION_ROOT", Path(__file__).resolve().parents[1] / "Validation"))
C1 = ROOT / "EE499_C1_Benchmark"
C2 = ROOT / "C2_Final_Test_Sector_Aggregation_Testbench"
PV = ROOT / "C2_FixedCohort_Ranked22_Updated"
FEEDER = "T04_15-Bus_System_1"
WORKBOOK = C1 / "C1_Simple_Test" / "Working_RDS" / (FEEDER + ".xlsx")


def require(*paths):
    for path in paths:
        if not path.is_file():
            pytest.skip(f"Archived fixture missing: {path}. Set EE499_VALIDATION_ROOT to its Validation directory.")


def economics(**kwargs):
    return EconomicConfig(grid_import_tariff_per_kwh=.2, grid_export_tariff_per_kwh=.03, **kwargs)


def test_archived_c1_numba_voltages():
    path = C1 / "results" / "bus_voltages.csv"
    require(WORKBOOK, path)
    network = load_network(WORKBOOK, frequency_hz=60)
    zero = dict.fromkeys((bus.bus_id for bus in network.buses), 0.)
    p, q = zero.copy(), zero.copy()
    for load in network.loads:
        p[load.bus_id] += load.p_base_kw
        q[load.bus_id] += load.q_base_kvar
    point = OperatingPoint(p, q, zero, zero, zero, zero)
    result = run_fbs(network, point, FBSConfig())
    assert result.converged
    archive = pd.read_csv(path).query("network == @FEEDER and solver == 'fbs_numba'").set_index("bus_id")
    assert set(archive.index) == set(zero)
    assert result.voltage_mag_pu == pytest.approx(archive.v_pu.to_dict(), abs=2e-6, rel=0)
    for backend in ("python", "numpy", "gpu"):
        with pytest.raises(ValueError, match="Only FBS"):
            FBSConfig(backend=backend)


@pytest.fixture(scope="module")
def archived_study():
    data = C2 / "input"
    workbook = ROOT / "C2_Annual_Test" / (FEEDER + ".xlsx")
    require(workbook, data / "manifest.json", data / "load_profile.csv",
            data / "bus_assignments_used.csv")
    return prepare_study(DataRequest(workbook, 60, "auto", None, None, "none",
                                    load_source="distributed", dataset_folder=data, clock="UTC"))


def test_c2_archive_and_history_windows(archived_study):
    study = archived_study
    history = study.historical_profiles
    assert len(study.profiles.timestamps) == 24
    with pytest.raises(ValueError, match="complete calendar year"):
        validate_annual_inputs(study.profiles.timestamps, economics())
    study.select_source("historical", "2020-01-01", "2021-01-01")
    assert len(validate_annual_inputs(study.profiles.timestamps, economics())) == 8784
    assert study.historical_profiles is history
    forecast = generate_forecast(history, ForecastConfig(horizon_hours=48, forecast_start="2021-01-01"),
                                 assignments=study.assignments, network=study.network)
    assert forecast.model_info["training_hours"] == 31440
    assert "fit_skipped" in forecast.model_info["pv"]
    for sector, predicted in forecast.sector_predictions.items():
        fixture = C2 / "results" / f"{sector}_hourly.csv"
        require(fixture)
        reference = pd.read_csv(fixture, nrows=48)
        assert pd.DatetimeIndex(forecast.profiles.timestamps).equals(pd.DatetimeIndex(pd.to_datetime(reference.timestamp)))
        np.testing.assert_allclose(predicted, reference.forecast_B_kw, rtol=2e-4, atol=.02)
        members = [bus for bus, name in study.assignments.items() if name == sector]
        np.testing.assert_allclose(sum(np.asarray(forecast.profiles.load_p_kw[b]) for b in members),
                                   predicted, rtol=1e-12)
    study.forecast_profiles = forecast.profiles
    study.select_source("forecast")
    assert len(study.profiles.timestamps) == 48
    study.select_source("historical")
    assert len(study.profiles.timestamps) == len(history.timestamps)


def test_pv_c2_reference_and_physical_forecast():
    prepared = PV / "prepared_cases" / "Bilbao_Modeled_PV.npz"
    archive = PV / "results/pv/Bilbao_Modeled_PV/XGBoost__daily_weekly_monthly_yearly/hourly_comparison.csv"
    require(prepared, archive)
    old = pd.read_csv(archive)
    future = pd.DatetimeIndex(pd.to_datetime(old.timestamp))
    with np.load(prepared) as arrays:
        history, actual = arrays["train"], arrays["actual"]
    np.testing.assert_allclose(old.actual, actual)
    times = pd.date_range(end=future[0] - pd.Timedelta(hours=1), periods=len(history), freq="h")
    site = SolarSite(43.26, -2.94, "UTC")
    capacity = float(max(history.max(), actual.max()))
    with pytest.raises(ValueError, match="placeholder"):
        PVReference(times, np.zeros(len(times)), capacity, site, {})
    ref = PVReference(times, history, capacity, site, {"source": "archived Bilbao modeled kW"})
    factors, metadata = _pv_predict(ref, times, future, FeatureCache(times, future))
    assert metadata["model"].startswith("XGBoost")
    assert 0 < factors.max() <= 1
    assert not factors[~daylight(future, site)].any()
    archive_mae = np.mean(np.abs(actual - old.forecast))
    # Production applies physical postprocessing and reselects parameters on history.
    assert np.mean(np.abs(actual - factors * capacity)) <= 1.25 * archive_mae


def test_window_policy_and_annual_candidate_paths():
    network = simple_network()
    profile = source_data(hours=8760, start="2021-01-01")
    settings = SimulationConfig(reserve_fraction=0)
    bounds = OptimizationBounds((2,), (20.,), (100.,))
    parameters = BESSParameters(.9, .9)
    evaluator = SimulationEvaluator(economics(), parameters, GridAwareDispatchPolicy(), settings)
    config = OptimizerConfig(3, 1, seed=42)
    reference = exhaustive_search(network, profile, bounds, evaluator)
    assert reference.success and np.isfinite(reference.best_objective)
    assert reference.metrics.final_soc_deviation == pytest.approx(0)
    for search in (genetic_optimize, optimize):
        result = search(network, profile, bounds, evaluator, config)
        assert result.best_candidate == reference.best_candidate
        assert result.best_objective == pytest.approx(reference.best_objective)
    # With no spare PCC headroom, the rule cannot recharge the initial discharge.
    capped = SimulationConfig(reserve_fraction=0, grid_import_limit_kw=100.01, terminal_soc_tolerance=1e-6)
    battery = BESSConfig(2, 100, 20, .1, .9, .5, .9, .9)
    failed = simulate_timeseries(network, source_data(hours=24), capped, battery, GridAwareDispatchPolicy())
    assert failed.completed and not failed.feasible and "Terminal SOC" in failed.message
    capped_eval = SimulationEvaluator(economics(), parameters, GridAwareDispatchPolicy(), capped)
    candidate = BESSCandidate(2, 20., 100.)
    capped_profile = ProfileData.from_arrays(profile.timestamps, {2: [100.] * 8760}, profile.load_q_kvar,
                                             profile.pv_p_kw, profile.pv_q_kvar)
    assert capped_eval(network, capped_profile, candidate).objective == float("inf")
    priced = SimulationEvaluator(economics(terminal_policy="priced_energy", terminal_energy_price_per_kwh=.2),
                                 parameters, GridAwareDispatchPolicy(), capped)
    paid = priced(network, capped_profile, candidate)
    assert paid.feasible and paid.metrics.annual_terminal_energy_cost > 0
    with pytest.raises(ValueError, match="positive replacement"):
        economics(terminal_policy="priced_energy")


def test_qt_solar_modes_and_case_ratings(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QTableWidgetItem
    from src_accelerated.network_model import PVUnit
    from src_accelerated.ui import LoadDataDialog, widget
    app = QApplication.instance() or QApplication([])
    dialog = LoadDataDialog()
    combo = widget(dialog, "combo_pv_source")
    modes = ("auto_nasa_power", "auto_open_meteo", "nasa_power", "open_meteo", "prepared", "power", "none")
    assert tuple(combo.itemData(i) for i in range(combo.count())) == modes
    for mode in modes:
        combo.setCurrentIndex(combo.findData(mode))
        assert widget(dialog, "panel_pv_source_file").isHidden() == (mode.startswith("auto") or mode == "none")
    combo.setCurrentIndex(combo.findData("power"))
    assert widget(dialog, "panel_irradiance_fields").isHidden()
    for name, rating in (("a-zero", 0), ("b-positive", 50)):
        case = tmp_path / name
        case.mkdir()
        for filename in ("load_profile.csv", "bus_assignments_used.csv", "manifest.json"):
            (case / filename).write_text("{}")
        (case / "bus_summary.csv").write_text(f"bus_id,pv_rated_kw\n2,{rating}\n")
    assert discover_cases(tmp_path / "a-zero") == [tmp_path / "a-zero"]
    assert len(discover_cases(tmp_path)) == 2
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a: str(tmp_path))
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a: ("a-zero", True))
    network = simple_network()
    network.pv_units = [PVUnit("workbook", 2, 25., None)]
    dialog.preview_path = ""
    dialog.job_succeeded(network)
    dialog.browse_load()
    assert dialog.pv_rows() == (("2", "25.0"),)
    widget(dialog, "table_pv_installations").setItem(0, 1, QTableWidgetItem("32"))
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a: ("b-positive", True))
    dialog.browse_load()
    assert dialog.pv_rows() == (("2", "32"),)
    assert "differ" in widget(dialog, "lbl_pv_status").text()
    dialog.populate_folder_metadata()
    assert dialog.pv_rows() == (("2", "32"),)
    assert app is not None


def test_manual_solar_inputs_and_dataset_precedence(tmp_path, monkeypatch):
    require(WORKBOOK)
    network = load_network(WORKBOOK, frequency_hz=60)
    times = pd.date_range("2020-06-01", periods=24, freq="h")
    site = SolarSite(40., -3., "UTC")
    radiation = np.where(daylight(times, site), 500., 0.)
    load = pd.DataFrame([(t, ld.bus_id, ld.p_base_kw, ld.q_base_kvar)
                         for t in times for ld in network.loads],
                        columns=("timestamp", "bus_id", "p_kw", "q_kvar"))
    load.to_csv(tmp_path / "load_profile.csv", index=False)
    pd.DataFrame({"bus_id": sorted({ld.bus_id for ld in network.loads}),
                  "category": "residential"}).to_csv(tmp_path / "bus_assignments_used.csv", index=False)
    summary = tmp_path / "bus_summary.csv"
    pd.DataFrame({"bus_id": [2], "pv_rated_kw": [20.]}).to_csv(summary, index=False)
    manifest = tmp_path / "manifest.json"
    meta = {"clock": "UTC", "site": {"latitude": 40., "longitude": -3.}, "pv_status": "placeholder"}
    manifest.write_text(json.dumps(meta))
    request = DataRequest(WORKBOOK, 60, "auto", None, None, "prepared", load_source="distributed",
                          dataset_folder=tmp_path, pv_override=True, pv_ratings_kw={2: 20.},
                          solar_source_clock="UTC")
    sources = {
        "prepared": pd.DataFrame({"timestamp": times, "irradiance_w_m2": radiation}),
        "open_meteo": pd.DataFrame({"time": times, "shortwave_radiation (W/m²)": radiation}),
        "nasa_power": pd.DataFrame({"timestamp": times, "ghi_wh_m2": radiation}),
        "power": pd.DataFrame({"timestamp": times, "p_kw": radiation / 20., "reference_capacity_kw": 50.}),
    }
    for mode, frame in sources.items():
        file = tmp_path / f"{mode}.csv"
        frame.to_csv(file, index=False)
        study = prepare_study(replace(request, pv_source=mode, pv_path=file))
        assert study.context["PV source"] == mode
        assert max(study.profiles.pv_p_kw[2]) == pytest.approx(10.)
    calls = []

    def fetch(provider, timestamps, site, cache):
        calls.append(provider)
        return sources["prepared"], [{"source": provider}]

    monkeypatch.setattr("src_accelerated.ui_workflow.fetch_irradiance", fetch)
    for provider in ("nasa_power", "open_meteo"):
        study = prepare_study(replace(request, pv_source="auto_" + provider))
        assert max(study.profiles.pv_p_kw[2]) == pytest.approx(10.)
    assert calls == ["nasa_power", "open_meteo"]
    zero_pv = prepare_study(replace(request, pv_source="auto_open_meteo", pv_ratings_kw={}))
    assert zero_pv.pv_reference is None and len(calls) == 2
    meta.update(pv_status="validated", pv_reference={"common_source": True, "units": "kW"})
    manifest.write_text(json.dumps(meta))
    pd.DataFrame({"timestamp": times, "bus_id": 2, "p_kw": radiation / 50.,
                  "q_kvar": 0.}).to_csv(tmp_path / "pv_profile.csv", index=False)
    preferred = prepare_study(replace(request, pv_source="nasa_power", pv_path=tmp_path / "missing.csv"))
    assert preferred.context["PV source"] == "Validated dataset history"
    assert max(preferred.profiles.pv_p_kw[2]) == pytest.approx(10.)


@pytest.mark.parametrize("ids,ratings", [([2,2],[1,2]), ([2.5],[1]), ([9],[1]), ([2],[-1]), ([2],[np.nan])])
def test_invalid_folder_nameplates(ids, ratings):
    with pytest.raises(ValueError):
        summary_pv_ratings(pd.DataFrame({"bus_id": ids, "pv_rated_kw": ratings}), {1,2})


def test_old_study_migration_preserves_history(tmp_path):
    require(WORKBOOK)
    network = load_network(WORKBOOK, frequency_hz=60)
    old = tmp_path / "old"
    old.mkdir()
    net = old / "network.xlsx"
    net.write_bytes(WORKBOOK.read_bytes())
    load = pd.DataFrame([(t, ld.bus_id, ld.p_base_kw, ld.q_base_kvar)
         for t in pd.date_range("2020", periods=40, freq="h") for ld in network.loads],
         columns=("timestamp", "bus_id", "p_kw", "q_kvar"))
    load.to_csv(old / "load.csv", index=False)
    load.assign(p_kw=0, q_kvar=0).to_csv(old / "pv.csv", index=False)
    manifest = old / "session.json"
    manifest.write_text(json.dumps(dict(request={"pv_source": "none", "frequency_hz": 60},
        network_snapshot="network.xlsx", load_profile_snapshot="load.csv", pv_profile_snapshot="pv.csv")))
    original = manifest.read_bytes()
    study, new = migrate_inputs(StudySession.open_read_only(old), tmp_path / "new")
    assert manifest.read_bytes() == original and new.root != old
    assert len(study.profiles.timestamps) == 24 and len(study.historical_profiles.timestamps) == 40
