"""Desktop and I/O coverage for the V15.6 cleanup."""
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest
from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QFileDialog, QInputDialog, QTextBrowser, QWidget
from openpyxl import Workbook

from src import dashboard, ui_workflow
from src.bess import BESSConfig, BESSState
from src.data_loader import ProfileData
from src.metrics import EconomicConfig, annual_capital_recovery_factor, evaluate_results
from src.model_information import model_information, settings_information
from src.progress import ProgressEvent, StageReporter, RunCancelled
from src.simulation import SimulationConfig
from src.study_session import StudySession
from src.study_setup import open_study_setup, save_study_setup
from src.ui import ForecastDialog, InformationDialog, LoadDataDialog, MainWindow, SettingsDialog, widget
from src.ui_workflow import DataRequest, RunSettings
from tests.test_fleet_dispatch_backend import _four_bus_radial_case


@pytest.fixture(scope="module")
def qt():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(qt):
    settings = SettingsDialog()
    settings.set_network(_four_bus_radial_case()[0])
    settings.engine_ready = True
    settings.update_compute_status()
    yield settings
    loop = QEventLoop()
    settings.jit_runner.busy_changed.connect(lambda busy: None if busy else loop.quit())
    QTimer.singleShot(0, lambda: None if settings.jit_runner.busy else QTimer.singleShot(100, loop.quit))
    QTimer.singleShot(15000, loop.quit)
    loop.exec()
    assert not settings.jit_runner.busy
    settings.close()


def test_settings_apply_restore_and_cancel(dialog):
    dialog.resize(850, 625)
    dialog.show()
    widget(dialog, "list_settings_pages").setCurrentRow(2)
    checkbox = widget(dialog, "btn_clear_allowed_buses")
    QTest.mouseClick(checkbox, Qt.MouseButton.LeftButton)
    assert dialog.capture_values()["allowed_buses"] == ()
    QTest.mouseClick(widget(dialog, "btn_select_all_buses"), Qt.MouseButton.LeftButton)
    assert dialog.capture_values()["allowed_buses"] == (2, 3, 4)
    buttons = widget(dialog, "buttons_settings")
    dialog.tariffs_confirmed = True
    expected = {"spin_ga_population": 17, "spin_max_generations": 9, "spin_ga_stall_generations": 3,
                "spin_parallel_workers": min(2, widget(dialog, "spin_parallel_workers").maximum())}
    for name, value in expected.items():
        control = widget(dialog, name)
        assert control.isVisible() and control.isEnabled()
        control.setValue(value)
    QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Apply), Qt.MouseButton.LeftButton)
    for name, value in expected.items():
        assert dialog.committed[name] == value
        widget(dialog, name).setValue(value+1 if name != "spin_parallel_workers" else 1)
    QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Cancel), Qt.MouseButton.LeftButton)
    assert all(widget(dialog, name).value() == value for name,value in expected.items())
    active = dialog.read_settings().simulation
    assert active.dispatch_horizon_hours == 24
    assert active.minimum_discharge_pf == .95
    for removed in ("combo_dispatch_horizon", "spin_minimum_discharge_pf", "spin_dispatch_efficiency_percent",
                    "spin_opf_bess_kva_multiplier", "spin_opf_pv_kva_multiplier", "btn_approved_methodology"):
        assert dialog.findChild(QWidget, removed) is None


def test_manual_and_optimization_own_separate_bess_settings(dialog):
    widget(dialog, "group_manual_bess").setChecked(True)
    table = widget(dialog, "table_manual_bess")
    location = table.cellWidget(0, 1)
    assert location.findData(1) == -1
    location.setCurrentIndex(location.findData(3))
    table.item(0, 2).setText("25")
    table.item(0, 3).setText("75")
    for name, value in {
        "spin_opt_power_min_kw": 25, "spin_opt_power_max_kw": 250, "spin_opt_power_step_kw": 25,
        "spin_opt_energy_min_kwh": 75, "spin_opt_energy_max_kwh": 750, "spin_opt_energy_step_kwh": 75,
    }.items():
        widget(dialog, name).setValue(value)
    dialog.tariffs_confirmed = True
    manual = dialog.read_settings()
    planned = dialog.read_settings(optimization=True)
    assert manual.manual_bess.bus_id == 3
    assert planned.manual_bess is None
    assert planned.managed_search
    assert planned.economics.power_cost_basis == "kva"
    assert planned.economics.inverter_kva_per_kw >= 1 / planned.simulation.minimum_discharge_pf
    for key in ("spin_ga_mutation", "spin_cpu_workers", "spin_cost_per_kw"):
        assert key not in planned.values
    assert planned.values["fleet_dispatch_mode"] == "daily_milp_dispatch"
    table.item(0, 3).setText("25")
    with pytest.raises(ValueError, match="duration"):
        dialog.read_settings()
    assert dialog.read_settings(optimization=True).manual_bess is None


def test_manual_fleet_applies_and_restores_order_and_disabled_rows(dialog, qt):
    widget(dialog, "group_manual_bess").setChecked(True)
    table = widget(dialog, "table_manual_bess")
    table.setRowCount(0)
    dialog.add_manual_row({"enabled": True, "bus_id": 3, "power_kw": 25, "energy_kwh": 75})
    dialog.add_manual_row({"enabled": False, "bus_id": 3, "power_kw": 25, "energy_kwh": 100})
    dialog.add_manual_row({"enabled": True, "bus_id": 2, "power_kw": 30, "energy_kwh": 120})
    dialog.tariffs_confirmed = True
    assert dialog.apply_settings()
    assert [unit.bus_id for unit in dialog.read_settings().manual_units] == [3, 2]
    assert table.item(2, 4).text() == "4"
    assert "55.000 kW" in widget(dialog, "lbl_manual_fleet_summary").text()
    table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    assert not dialog.apply_settings()
    assert "row 2" in widget(dialog, "lbl_settings_validation").text()
    table.setRowCount(0)
    dialog.reject()
    assert table.rowCount() == 3
    assert table.item(1, 0).checkState() == Qt.CheckState.Unchecked
    original = dialog.network
    from tests.test_multi_v4 import make_network
    dialog.add_manual_row({"enabled": True, "bus_id": 4, "power_kw": 10, "energy_kwh": 40})
    assert dialog.apply_settings()
    dialog.set_network(make_network())
    assert table.cellWidget(3, 1).currentData() == 4
    assert "unavailable" in table.cellWidget(3, 1).currentText()
    with pytest.raises(ValueError, match="row 4"):
        dialog.read_settings()
    dialog.set_network(original)
    assert [unit.bus_id for unit in dialog.read_settings().manual_units] == [3, 2, 4]


def test_corrective_policy_persists_for_simulation_and_does_not_change_optimize(dialog):
    policy = widget(dialog, "combo_corrective_actions")
    assert dialog.read_settings().simulation.corrective_actions
    policy.setCurrentIndex(policy.findData("uncontrolled"))
    dialog.tariffs_confirmed = True
    assert dialog.apply_settings()
    assert not dialog.read_settings().simulation.corrective_actions
    assert dialog.read_settings(optimization=True).simulation.corrective_actions
    policy.setCurrentIndex(policy.findData("compare"))
    assert dialog.read_settings().compare_corrective_actions
    assert not dialog.read_settings(optimization=True).compare_corrective_actions
    dialog.reject()
    assert policy.currentData() == "uncontrolled"


def test_initial_main_window_actions(qt):
    from src.app_log import desktop_log

    window = MainWindow()
    window.resize(1280, 720)
    window.show()
    loop = QEventLoop()
    window.settings_dialog.jit_runner.busy_changed.connect(lambda busy: None if busy else loop.quit())
    QTimer.singleShot(15000, loop.quit)
    loop.exec()
    assert window.settings_dialog.engine_ready
    for name in ("btn_run_optimization", "btn_run_simulation", "btn_scenarios"):
        assert not widget(window, name).isEnabled()
    for name in ("btn_load_data", "btn_settings", "btn_dashboard"):
        assert widget(window, name).isEnabled()
    assert widget(window, "btn_stop_run").isHidden()
    assert window.findChild(QWidget, "lbl_workspace_subtitle") is None
    assert widget(window, "btn_open_setup").isVisible()
    assert widget(window, "btn_save_setup").isVisible()
    assert not widget(window, "btn_save_setup").isEnabled()
    assert "[INFO] BESS Planning Tool started" in widget(window, "run_log").toPlainText()
    window.append_log("test warning", level="WARNING")
    window.append_log("test traceback", level="DEBUG")
    saved = Path(desktop_log.handlers[0].baseFilename).read_text(encoding="utf-8")
    assert "[INFO] BESS Planning Tool started" in saved
    assert "[WARNING] test warning" in saved and "[DEBUG] test traceback" in saved
    assert "test traceback" not in widget(window, "run_log").toPlainText()
    window.close()


def test_information_button_and_pending_contexts(qt):
    window = MainWindow()
    window.show()
    loop = QEventLoop()
    window.settings_dialog.jit_runner.busy_changed.connect(lambda busy: None if busy else loop.quit())
    QTimer.singleShot(15000, loop.quit)
    loop.exec()
    assert window.settings_dialog.engine_ready
    information = widget(window, "btn_information")
    assert information.text() == "\u24d8"
    assert information.accessibleName() == "Information"
    opened = []

    def inspect(reference):
        opened.append(reference.context_picker.currentText())
        assert all(browser.isReadOnly() for browser in reference.findChildren(QTextBrowser))
        assert len(reference.findChildren(QTextBrowser)) == 3
        assert "Convergence:" in widget(reference, "information_equations").toPlainText()
        return QDialogButtonBox.StandardButton.Close

    with patch.object(InformationDialog, "exec", inspect):
        QTest.mouseClick(information, Qt.MouseButton.LeftButton)
        settings = window.settings_dialog
        settings.show()
        settings.activateWindow()
        qt.processEvents()
        QTest.keyClick(settings, Qt.Key.Key_F1)
    assert opened == ["Confirmed settings — no study prepared", "Pending settings — current edits"]
    assert window.findChild(QWidget, "btn_approved_methodology") is None
    settings.set_network(_four_bus_radial_case()[0])
    population = widget(settings, "spin_ga_population")
    confirmed_population = population.value()
    population.setValue(37)
    widget(settings, "spin_grid_import_tariff").setValue(.317)
    contexts, selected = window.information_contexts()
    assert selected == 1
    confirmed = contexts[0][1]["context"]
    pending = contexts[1][1]["context"]
    assert confirmed["Effective Joint GA settings"]["population"] == confirmed_population
    assert pending["Effective Joint GA settings"]["population"] == 37
    assert "Proposed tariffs" not in confirmed
    assert pending["Proposed tariffs"][0] == .317
    settings.tariffs_confirmed = True
    assert settings.apply_settings()
    assert window.information_contexts()[0][0][1]["context"]["Effective Joint GA settings"]["population"] == 37

    settings.hide()
    effective = settings_information(None, settings.read_settings(optimization=True), "optimization")
    window.running_information = {"kind": "optimization", "context": effective}
    window.completed_information = {"kind": "optimization", "context": confirmed}
    contexts, selected = window.information_contexts()
    assert contexts[selected][0].startswith("Effective settings")
    assert contexts[selected][1]["context"]["Effective Joint GA settings"]["population"] == 37
    assert contexts[-1][0].startswith("Frozen settings")
    assert contexts[-1][1]["context"]["Effective Joint GA settings"]["population"] == confirmed_population
    window.close()


def test_demand_browsing_from_empty_dialog(qt, tmp_path):
    dialog = LoadDataDialog()
    dialog.resize(820, 485)
    dialog.show()
    tabs = widget(dialog, "tabs_data")
    tabs.setCurrentWidget(widget(dialog, "tab_load_data"))
    folder_button = widget(dialog, "btn_browse_load")
    file_button = widget(dialog, "btn_browse_load_file")
    assert folder_button.isVisible() and folder_button.isEnabled()
    assert file_button.isVisible() and file_button.isEnabled()
    parent = tmp_path / "cases"
    for name in ("Case A", "Case B"):
        case = parent / name
        case.mkdir(parents=True)
        for filename in ("load_profile.csv", "bus_assignments_used.csv"):
            (case / filename).touch()
        (case / "manifest.json").write_text('{"clock":"UTC","hours":8760}', encoding="utf-8")
    with patch.object(QFileDialog, "getExistingDirectory", return_value=str(parent)), \
         patch.object(QInputDialog, "getItem", return_value=("Case B", True)) as picker:
        QTest.mouseClick(folder_button, Qt.MouseButton.LeftButton)
    assert picker.call_count == 1
    assert widget(dialog, "edit_load_path").text() == str(parent / "Case B")
    demand = tmp_path / "demand.csv"
    demand.touch()
    with patch.object(QFileDialog, "getOpenFileName", return_value=(str(demand), "")):
        QTest.mouseClick(file_button, Qt.MouseButton.LeftButton)
    assert widget(dialog, "edit_load_path").text() == str(demand)
    assert dialog.solar_source_mode() != "dataset"
    dialog.set_busy(True)
    assert not folder_button.isEnabled() and not file_button.isEnabled()
    dialog.set_busy(False)
    assert folder_button.isEnabled() and file_button.isEnabled()
    dialog.close()


def test_desktop_ga_overrides_reach_optimizer(dialog):
    network, _ = _four_bus_radial_case()
    hours = pd.date_range("2021-01-01", periods=8760, freq="h")
    profiles = ProfileData.from_arrays(hours, {2: [25.] * len(hours)},
                                       {2: [5.] * len(hours)}, {}, {})
    study = ui_workflow.PreparedStudy(network, profiles, None, {})
    widget(dialog, "spin_ga_population").setValue(19)
    widget(dialog, "spin_max_generations").setValue(5)
    widget(dialog, "spin_ga_stall_generations").setValue(1)
    workers = min(2, widget(dialog, "spin_parallel_workers").maximum())
    widget(dialog, "spin_parallel_workers").setValue(workers)
    dialog.tariffs_confirmed = True
    settings = dialog.read_settings(optimization=True)
    log = []
    with patch("src.sequential_multi.optimize_sequential_multi",
               side_effect=RuntimeError("optimizer reached")) as run:
        with pytest.raises(RuntimeError, match="optimizer reached"):
            ui_workflow.run_study(study, settings, True, log.append)
    config = run.call_args.args[4]
    assert (config.population_size, config.max_iterations, config.workers) == (19, 5, workers)
    assert config.convergence_patience == 1
    assert run.call_args.kwargs["ga_mutation_rate"] == .20
    assert run.call_args.kwargs["ga_crossover_rate"] == .80
    assert any(f"population=19, maximum generations=5, parallel workers={workers}" in line for line in log)


def _source_workbook(path):
    workbook = Workbook()
    overview = workbook.active
    overview.title = "Overview"
    overview.append(["Base MVA", "1 MVA"])
    overview.append(["Base voltage", "12.66 kV"])
    buses = workbook.create_sheet("Bus Data")
    buses.append(["Bus No.", "Type", "P_load (kW)", "Q_load (kVAr)", "Vm (p.u.) init", "Va (deg) init"])
    buses.append([1, "Slack", 0, 0, 1, 0])
    buses.append([2, "PQ", 25, 5, 1, 0])
    lines = workbook.create_sheet("Branch Data")
    lines.append(["Branch No.", "From Bus", "To Bus", "R (Ohm)", "X (Ohm)",
                  "P_load at To Bus (kW)", "Q_load at To Bus (kVAr)"])
    lines.append([1, 1, 2, 0.4, 0.3, 25, 5])
    workbook.save(path)


@pytest.fixture
def prepared(tmp_path):
    network = tmp_path / "test feeder.xlsx"
    _source_workbook(network)
    load = tmp_path / "hourly input.csv"
    times = pd.date_range("2020-02-28", periods=48, freq="h")
    pd.DataFrame({"timestamp": times, "bus_id": 2, "p_kw": 25, "q_kvar": 5}).to_csv(load, index=False)
    load.with_suffix(".json").write_text('{"clock":"UTC"}', encoding="utf-8")
    request = DataRequest(network, 60, "auto", None, None, "none", load_source="imported", load_path=load, clock="UTC")
    return ui_workflow.prepare_study(request)


def test_excel_import_and_legacy_setup_null_start(prepared, tmp_path):
    load = prepared.request.load_path
    excel = load.with_suffix(".xlsx")
    pd.read_csv(load).iloc[::-1].to_excel(excel, index=False)
    from_excel = ui_workflow.prepare_study(replace(prepared.request, load_path=excel))
    assert from_excel.profiles.timestamps == prepared.profiles.timestamps
    assert len(from_excel.historical_profiles.timestamps) == 48
    setup = tmp_path / "study.json"
    save_study_setup(setup, prepared, {"sindi_horizon_hours": 48, "spin_sindi_energy_cost": 205})
    data = setup.read_text(encoding="utf-8").replace('"start": null', '"start": "None"')
    setup.write_text(data, encoding="utf-8")
    restored, settings = open_study_setup(setup)
    assert restored.request.start is None
    assert settings["dispatch_horizon_hours"] == 48
    assert settings["spin_battery_energy_capex"] == 205


def test_forecast_dialog_keeps_time_controls_and_requires_one_year(qt, prepared, tmp_path):
    session = StudySession.create(prepared, tmp_path)
    dialog = ForecastDialog(prepared, session)
    assert widget(dialog, "spin_forecast_horizon").value() >= 1
    assert not dialog.generate_button.isEnabled()
    dialog.close()


def test_input_errors_name_missing_or_duplicate_hours(prepared):
    path = prepared.request.load_path
    load = pd.read_csv(path)
    pd.concat([load, load.iloc[[0]]]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="duplicate"):
        ui_workflow.prepare_study(prepared.request)
    load.drop(index=12).to_csv(path, index=False)
    with pytest.raises(ValueError, match="consecutive hourly"):
        ui_workflow.prepare_study(prepared.request)


def test_export_failure_retries_after_computation_and_dashboard_is_recoverable(prepared, tmp_path):
    output = tmp_path / "session"
    session = StudySession.create(prepared, output)
    path = session.next_run_path(False)
    export = ui_workflow.export_results
    calls = []
    def fail_one_write(*args, **kwargs):
        calls.append(args[1])
        if len(calls) == 1:
            args[1].mkdir()
            raise OSError("test write failure")
        return export(*args, **kwargs)
    settings = RunSettings(SimulationConfig(fleet_dispatch_mode="daily_milp_dispatch"), EconomicConfig(), None, {})
    with patch.object(ui_workflow, "run_study", wraps=ui_workflow.run_study) as run, \
         patch.object(ui_workflow, "export_results", side_effect=fail_one_write), \
         patch.object(dashboard, "regenerate_dashboard", side_effect=OSError("test HTML failure")):
        report = ui_workflow.run_and_export(prepared, settings, False, path, session_root=session.root)
    assert run.call_count == 1
    assert report.saved and report.result.completed and report.result.feasible
    assert (path / "dashboard_error.txt").is_file()
    assert not list(path.parent.glob(".run-*"))
    assert StudySession.open_read_only(session.root).manifest["simulation_runs"][0]["status"] == "success"
    assert dashboard.regenerate_dashboard(path).is_file()


def test_annual_metrics_retained_when_session_registration_fails(prepared, tmp_path):
    hours = pd.date_range("2021-01-01", periods=8760, freq="h")
    prepared.profiles = ProfileData.from_arrays(hours, {2: [25.] * len(hours)},
                                                {2: [5.] * len(hours)}, {}, {})
    settings = RunSettings(SimulationConfig(),
                           EconomicConfig(grid_import_tariff_per_kwh=.1, grid_export_tariff_per_kwh=0.),
                           None, {})
    path = tmp_path / "simulation" / "run_001"
    with patch.object(StudySession, "open_for_updates", side_effect=OSError("test session failure")):
        report = ui_workflow.run_and_export(prepared, settings, False, path,
                                            defer_dashboard=True, session_root=tmp_path)
    assert report.saved and report.metrics.duration_hours == 8760
    assert report.metrics.annual_total_cost > 0
    assert "Session registration failed" in report.persistence_warning
    assert (path / "metrics.csv").is_file()
    assert dashboard.regenerate_dashboard(path).is_file()


def test_no_pf_timing_key_does_not_prevent_strict_run_export(prepared, tmp_path):
    settings = RunSettings(SimulationConfig(fleet_dispatch_mode="daily_milp_dispatch"),
                           EconomicConfig(), BESSConfig(2, 75., 25., .1, .9, .5, .95, .95), {})
    report = ui_workflow.run_study(prepared, settings)
    report.result.dispatch_timing.pop("minimum_discharge_pf", None)
    out = tmp_path / "strict"
    ui_workflow.export_results(report.result, out, metrics=report.metrics, context=report.context)
    rows = pd.read_csv(out / "battery_daily_audit.csv")
    assert rows["pf_compliant"].all()
    assert rows["soc_restored"].all()


def test_saved_model_information_freezes_effective_parameters_and_offline_math(qt, prepared, tmp_path):
    simulation = SimulationConfig(fleet_dispatch_mode="daily_milp_dispatch", minimum_discharge_pf=.8)
    economics = EconomicConfig(cost_per_kwh=123., cost_per_kw=456., power_cost_basis="kva",
                               inverter_kva_per_kw=simulation.effective_bess_inverter_kva_per_kw,
                               lifetime_years=11, annualization_method="real_crf",
                               nominal_interest_rate=.072, annual_inflation_rate=.02,
                               grid_import_tariff_per_kwh=.28, grid_export_tariff_per_kwh=.06)
    original_battery = BESSConfig(2, 75., 25., .1, .9, .5, .94, .91)
    settings = RunSettings(simulation, economics, original_battery, {})
    path = tmp_path / "run_001"
    report = ui_workflow.run_and_export(prepared, settings, False, path, defer_dashboard=True)
    assert report.saved
    frozen_bytes = (path / dashboard.RUN_FILE).read_bytes()

    # Later inputs can change every affected engineering quantity.
    settings.economics = replace(economics, cost_per_kw=999.)
    settings.simulation = replace(simulation, minimum_discharge_pf=.7)
    settings.manual_bess.power_rating_kw = 70.
    prepared.context["Clock"] = "Asia/Riyadh"
    metadata, snapshot = dashboard.read_saved_run(path)
    sections = model_information(metadata, snapshot)
    browser = QTextBrowser()
    browser.setHtml(sections["Current parameters"])
    table = browser.toPlainText()
    for value in ("456.0 USD", "Inverter CAPEX (per kVA)", "31.25", "0.94", "0.91", "UTC",
                  str(annual_capital_recovery_factor(economics))):
        assert value in table
    assert "999" not in table
    reference = InformationDialog([("Frozen result", metadata, snapshot)])
    browser = widget(reference, "information_equations")
    for term in ("Forward/Backward Sweep", "Battery energy and SOC", "Chronological annual operating cost"):
        assert term in browser.toPlainText()
    assert sections["Mathematical equations"].count("data:image/png;base64,") >= 15
    assert report.metrics.bess_cost == pytest.approx(123 * 75 + 456 * (25 / .8))
    assert report.result.dispatch_timing["minimum_discharge_pf"] == .8
    assert pd.read_csv(path / "battery_daily_audit.csv")["soc_restored"].all()

    html = dashboard.regenerate_dashboard(path).read_text(encoding="utf-8")
    assert (path / dashboard.RUN_FILE).read_bytes() == frozen_bytes
    assert sections["Mathematical equations"] in html
    assert "31.25" in html and "456 USD" in html

    class OfflineReport(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "details" and attrs.get("class") == "model-information":
                assert "open" not in attrs
                self.collapsible_model = True
            if tag in {"script", "link"}:
                assert not attrs.get("src", "").startswith(("http:", "https:", "//"))
                assert not attrs.get("href", "").startswith(("http:", "https:", "//"))

    parser = OfflineReport()
    parser.feed(html)
    assert parser.collapsible_model


def test_information_and_dashboard_open_legacy_archives(qt, tmp_path):
    (tmp_path / "summary.txt").write_text("Archived results", encoding="utf-8")
    html = dashboard.regenerate_dashboard(tmp_path).read_text(encoding="utf-8")
    assert "Model &amp; Assumptions" in html
    assert "Not recorded" in html
    reference = InformationDialog([("Confirmed", {}, None)])
    with patch.object(QFileDialog, "getExistingDirectory", return_value=str(tmp_path)):
        widget(reference, "btn_information_archive").click()
    assert reference.context_picker.currentText().startswith("Frozen settings")
    assert widget(reference, "information_equations").toPlainText() == "Not recorded"
    table = widget(reference, "information_parameters").toPlainText()
    assert "Not recorded" in table
    assert "0.95" not in table


def test_annual_single_battery_metrics_use_the_fleet_terminal_state():
    battery = BESSConfig(2, 75., 25., .1, .9, .5, .95, .95)
    flow = SimpleNamespace(converged=True, slack_p_kw=25., total_loss_p_kw=0., voltage_mag_pu={1:1., 2:.99})
    point = SimpleNamespace(p_load_kw={2:25.}, p_pv_kw={2:0.})
    step = SimpleNamespace(actual_power_kw=0., soc_before=.5, soc_after=.5)
    hours = pd.date_range("2021-01-01", periods=8760, freq="h")
    series = SimpleNamespace(
        dt_hours=1., completed=True, converged=True, feasible=True,
        steps=[SimpleNamespace(timestamp=hour, power_flow=flow, operating_point=point,
              bess_step=None, fleet_steps={2:step}, voltage_violations={}, feasible=True,
              bess_state=None, curtailment_kw=0., shedding_kw=0., requested_point=None) for hour in hours],
        final_bess_state=None, final_fleet_states={2:BESSState(37.5,.5)},
        dispatch_timing={"fleet_dispatch_mode":"daily_milp_dispatch"})
    economics = EconomicConfig(cost_per_kw=175., cost_per_kwh=200., power_cost_basis="kva",
        inverter_kva_per_kw=1/.95, annualization_method="real_crf",
        grid_import_tariff_per_kwh=.1, grid_export_tariff_per_kwh=0.)
    manual = evaluate_results(series, economics, battery)
    fleet = evaluate_results(series, economics, (battery,))
    assert manual.terminal_energy_change_kwh == 0
    assert manual.annual_total_cost == fleet.annual_total_cost
    assert manual.annual_total_cost == pytest.approx(manual.annual_operating_cost + manual.annual_bess_capital_cost + manual.annual_bess_om_cost)
    with pytest.raises(ValueError, match="Missing final BESS states"):
        series.final_fleet_states = {}
        evaluate_results(series, economics, battery)


def test_cooperative_cancel_and_commit_boundary():
    interrupt = False
    stage = StageReporter(lambda _message: None, lambda _event: None, cancelled=lambda: interrupt)
    event = ProgressEvent("Simulation", 1, 3)
    stage.progress(event)
    interrupt = True
    with pytest.raises(RunCancelled):
        stage.progress(event)
    interrupt = False
    stage.begin_commit()
    interrupt = True
    stage("Persisting")


def test_progress_has_actual_hour_counts_and_stage_error_context():
    from src.ui import Worker

    snapshots = []
    reporter = StageReporter(lambda _message: None, snapshots.append, interval=0)
    reporter("Simulation started")
    reporter.progress(ProgressEvent("Simulation", 12, 48))
    assert snapshots[-1][0]["Simulation"].percent == 25
    def fail(stage):
        stage("Reading demand.csv")
        raise ValueError("missing timestamps")
    errors = []
    worker = Worker(fail)
    worker.failed.connect(lambda message, trace: errors.append((message, trace)))
    worker.run()
    assert "Reading demand.csv | ValueError: missing timestamps" == errors[0][0]
    assert "Traceback" in errors[0][1]
