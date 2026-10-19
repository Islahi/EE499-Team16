"""Offscreen Qt tests against Designer forms, never rewritten at runtime."""
from hashlib import sha256
from copy import deepcopy
from dataclasses import replace
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from PySide6.QtCore import QPoint, QPointF, QThread, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QGraphicsItem, QWidget
    HAS_QT = True
except ImportError:
    HAS_QT = False

if HAS_QT:
    from src.ui import ASSETS, JobRunner, MainWindow, TimestampDialog, widget

from src.network_cases import build_guide_5_bus_case
from src.progress import ProgressEvent
from test_ui_workflow import NETWORK, ROOT, short_study


@unittest.skipUnless(HAS_QT, "Install requirements-ui.txt to test the optional desktop")
class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        # Closing one test window must not request termination of later tests.
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.window = MainWindow()
        self.source_hashes = {file: sha256(file.read_bytes()).hexdigest() for file in ASSETS.glob("*.ui")}

    def tearDown(self):
        self.assertFalse(self.window.runner.busy)
        self.assertFalse(self.window.load_dialog.runner.busy)
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.assertEqual(self.source_hashes, {file: sha256(file.read_bytes()).hexdigest() for file in ASSETS.glob("*.ui")})

    def wait_job(self, runner, timeout=20):
        deadline = time.monotonic() + timeout
        while runner.busy and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(5)
        self.app.processEvents()
        self.assertFalse(runner.busy, "Worker did not finish in the test budget")

    def configure_optimization(self):
        dialog = self.window.settings_dialog
        dialog.set_network(build_guide_5_bus_case())
        for name, value in {
            "spin_eta_charge_percent": 95, "spin_eta_discharge_percent": 95,
            "spin_dispatch_target_kw": 600, "spin_opt_power_min_kw": 100,
            "spin_opt_power_max_kw": 200, "spin_opt_power_step_kw": 100,
            "spin_opt_energy_min_kwh": 200, "spin_opt_energy_max_kwh": 400,
            "spin_opt_energy_step_kwh": 200, "spin_gwo_population": 3,
            "spin_gwo_iterations": 1, "spin_cost_per_kwh": 2, "spin_cost_per_kw": 3,
        }.items():
            widget(dialog, name).setValue(value)
        widget(dialog, "group_reserve").setChecked(False)
        widget(dialog, "group_economic_inputs").setChecked(True)
        widget(dialog, "combo_dispatch_policy").setCurrentIndex(1)
        choices = widget(dialog, "list_allowed_buses")
        for index in range(choices.count()):
            choices.item(index).setSelected(choices.item(index).data(Qt.ItemDataRole.UserRole) == 4)
        return dialog

    def test_forms_and_startup_state(self):
        self.assertEqual(self.window.objectName(), "MainWindow")
        self.assertFalse(widget(self.window, "btn_run_simulation").isEnabled())
        self.assertFalse(widget(self.window, "btn_export_results").isEnabled())
        self.assertEqual(widget(self.window.load_dialog, "combo_pv_source").count(), 5)
        self.assertIsNotNone(widget(self.window.settings_dialog, "spin_opt_power_step_kw"))
        self.assertIsNotNone(widget(self.window.settings_dialog, "combo_dispatch_policy"))
        self.assertIsNone(self.window.findChild(QWidget, "lbl_stage"))
        self.assertIsNone(self.window.load_dialog.findChild(QWidget, "chk_diagnostic_hours"))
        self.assertIsNone(self.window.load_dialog.findChild(QWidget, "spin_diagnostic_hours"))

    def test_nested_progress_keeps_gwo_as_percentage(self):
        events = {"GWO": ProgressEvent("GWO", 1, 4),
                  "Candidate": ProgressEvent("Candidate", 2, 3),
                  "FBS": ProgressEvent("FBS", 10, 100, "voltage delta=0.001")}
        self.window.show_progress((events, True))
        self.assertEqual(widget(self.window, "progress_run").value(), 25)
        self.assertIn("FBS 10/100", self.window.last_stage_message)
        log = widget(self.window, "run_log").toPlainText()
        self.assertIn("voltage delta=0.001", log)
        self.assertRegex(log, r"\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}\]")

    def test_clock_freezes_and_reports_missing_worker_updates(self):
        self.window.run_started = time.perf_counter() - 65
        self.window.last_worker_update = time.perf_counter() - 20
        self.window.last_heartbeat = time.perf_counter() - 20
        self.window.update_run_clock()
        self.assertEqual(widget(self.window, "lbl_run_elapsed").text(), "Elapsed 00:01:05")
        self.assertIn("No worker counter update", widget(self.window, "run_log").toPlainText())
        self.window.finish_run_clock()
        self.assertIsNone(self.window.run_started)
        self.assertFalse(self.window.run_clock.isActive())

    def test_worker_reports_progress_on_gui_thread(self):
        received = []
        def receive(snapshot):
            received.append((QThread.currentThread() == self.app.thread(), snapshot))
        runner = JobRunner(self.window)
        runner.progress.connect(receive)
        def task(stage):
            stage("Running test")
            stage.progress(ProgressEvent("GWO", 1, 2, log=True))
            return "finished"
        runner.start(task)
        self.wait_job(runner)
        self.assertEqual(len(received), 1)
        self.assertTrue(received[0][0])
        self.assertEqual(received[0][1][0]["GWO"].completed, 1)

    def test_navigation_and_existing_designer_connections(self):
        dialog = self.window.settings_dialog
        widget(dialog, "list_settings_pages").setCurrentRow(4)
        self.assertEqual(widget(dialog, "stack_settings_pages").currentIndex(), 4)
        self.window.show()
        self.app.processEvents()
        widget(self.window, "chk_show_log").setChecked(False)
        self.assertTrue(widget(self.window, "run_log").isHidden())

    def test_none_limits_are_distinct_from_zero_and_costs(self):
        dialog = self.window.settings_dialog
        settings = dialog.read_settings()
        self.assertIsNone(settings.simulation.grid_import_limit_kw)
        self.assertIsNone(settings.economics.cost_per_kw)
        widget(dialog, "group_import_limit").setChecked(True)
        widget(dialog, "group_economic_inputs").setChecked(True)
        settings = dialog.read_settings()
        self.assertEqual(settings.simulation.grid_import_limit_kw, 0)
        self.assertEqual(settings.economics.cost_per_kw, 0)

    def test_apply_cancel_and_invalid_ok(self):
        dialog = self.window.settings_dialog
        widget(dialog, "spin_voltage_min_pu").setValue(0.94)
        self.assertTrue(dialog.apply_settings())
        widget(dialog, "spin_voltage_min_pu").setValue(0.93)
        dialog.reject()
        self.assertEqual(widget(dialog, "spin_voltage_min_pu").value(), 0.94)
        widget(dialog, "spin_voltage_min_pu").setValue(1.5)
        dialog.accept_settings()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.committed["spin_voltage_min_pu"], 0.94)

    def test_manual_battery_converts_percentages(self):
        dialog = self.configure_optimization()
        widget(dialog, "group_manual_bess").setChecked(True)
        widget(dialog, "combo_bess_bus").setCurrentIndex(widget(dialog, "combo_bess_bus").findData(4))
        widget(dialog, "spin_bess_power_kw").setValue(100)
        widget(dialog, "spin_bess_energy_kwh").setValue(200)
        settings = dialog.read_settings()
        self.assertEqual(settings.manual_bess.eta_charge, 0.95)
        self.assertEqual(settings.manual_bess.soc_min, 0.1)
        self.assertEqual(settings.dispatch.target_kw, 600)
        dialog.apply_settings()
        self.window.study = short_study()
        self.window.run_simulation()
        self.wait_job(self.window.runner)
        self.assertIsNotNone(self.window.report)
        self.assertGreater(self.window.report.metrics.bess_discharge_energy_kwh, 0)

    def test_optimization_guards_and_explicit_settings(self):
        with self.assertRaises(ValueError):
            self.window.settings_dialog.read_settings(optimization=True)
        dialog = self.configure_optimization()
        self.assertEqual(dialog.read_settings(optimization=True).values["allowed_buses"], (4,))
        widget(dialog, "spin_opt_power_step_kw").setValue(0)
        with self.assertRaises(ValueError):
            dialog.read_settings(optimization=True)

    def test_no_pv_ignores_disabled_invalid_table(self):
        dialog = self.window.load_dialog
        widget(dialog, "edit_network_path").setText(str(NETWORK))
        widget(dialog, "combo_pv_source").setCurrentIndex(4)
        self.assertEqual(dialog.read_request().pv_ratings_kw, {})
        self.assertEqual(dialog.read_request().start.hour, 0)
        self.assertFalse(widget(dialog, "group_pv_conversion").isEnabled())

    def test_data_dialog_validation_does_not_close_on_error(self):
        dialog = self.window.load_dialog
        dialog.prepare_data()
        self.assertFalse(dialog.runner.busy)
        self.assertIsNone(dialog.study)
        self.assertIn("Error", widget(dialog, "lbl_load_validation").text())

    def test_real_network_preview_in_worker(self):
        dialog = self.window.load_dialog
        widget(dialog, "edit_network_path").setText(str(NETWORK))
        widget(dialog, "spin_frequency_hz").setValue(60)
        dialog.load_network_preview()
        self.assertTrue(dialog.runner.busy)
        self.assertFalse(widget(dialog, "buttons_load_data").isEnabled())
        self.wait_job(dialog.runner)
        self.assertIn("33 buses", widget(dialog, "lbl_network_summary").text())
        self.assertIsNone(dialog.study)

    def test_prepare_data_worker_and_scene_bus_selection(self):
        dialog = self.window.load_dialog
        widget(dialog, "edit_network_path").setText(str(NETWORK))
        widget(dialog, "spin_frequency_hz").setValue(60)
        widget(dialog, "combo_pv_source").setCurrentIndex(4)
        dialog.prepare_data()
        self.wait_job(dialog.runner)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(len(dialog.study.network.buses), 33)
        self.window.study = dialog.study
        self.window.scene.draw_network(dialog.study.network)
        buses = [item for item in self.window.scene.items()
                 if item.data(1) == "bus" and item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable]
        self.assertEqual(len(buses), 33)
        buses[0].setSelected(True)
        self.assertEqual(widget(self.window, "lbl_bus_id").text(), str(buses[0].data(0)))

    def test_single_line_symbols_preserve_network_and_bus_selection(self):
        network = build_guide_5_bus_case()
        before = deepcopy(network)
        scene = self.window.scene
        scene.draw_network(network, bess_bus=4)
        for role, count in (("bus", 5), ("busbar", 5), ("load", 4),
                            ("pv", 1), ("bess", 1), ("grid", 1), ("line", 4), ("legend", 0)):
            self.assertEqual(len([item for item in scene.items() if item.data(1) == role]), count, role)
        pv = next(item for item in scene.items() if item.data(1) == "pv")
        self.assertEqual(pv.parentItem().data(0), 4)
        selected = []
        scene.bus_selected.connect(selected.append)
        pv.parentItem().setSelected(True)
        self.assertEqual(selected, [4])
        scene.clearSelection()
        selected.clear()
        self.window.show()
        self.app.processEvents()
        self.window.fit_network()
        view = widget(self.window, "network_view")
        point = view.mapFromScene(pv.mapToScene(pv.boundingRect().center()))
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(selected, [4])
        self.assertEqual(network, before)

    def test_symbols_follow_installed_devices_not_voltage_or_output(self):
        network = build_guide_5_bus_case()
        scene = self.window.scene
        scene.draw_network(network, voltages={bus.bus_id: 0.9 for bus in network.buses})
        arrows = [item for item in scene.items() if item.data(1) == "load"]
        self.assertEqual({item.parentItem().data(0) for item in arrows}, {2, 3, 4, 5})
        self.assertTrue(all("not branch-flow direction" in item.toolTip() for item in arrows))
        self.assertEqual(len([item for item in scene.items() if item.data(1) == "pv"]), 1)
        scene.draw_network(replace(network, loads=[], pv_units=[]))
        self.assertFalse(any(item.data(1) in ("load", "pv", "bess") for item in scene.items()))

    def test_pjm_preview_is_rejected_without_changing_workbook(self):
        path = NETWORK.with_name("PJM_5Bus_Network_Data.xlsx")
        before = sha256(path.read_bytes()).hexdigest()
        dialog = self.window.load_dialog
        widget(dialog, "edit_network_path").setText(str(path))
        dialog.load_network_preview()
        self.wait_job(dialog.runner)
        self.assertIn("PJM/generator", widget(dialog, "lbl_load_validation").text())
        self.assertIsNone(dialog.study)
        self.assertEqual(sha256(path.read_bytes()).hexdigest(), before)

    def test_close_is_guarded_and_repeated_workers_clean_up(self):
        release = Event()
        runner = JobRunner(self.window)
        self.window.show()
        self.window.runner.start(lambda stage: release.wait(5))
        try:
            self.assertFalse(self.window.close())
            self.assertTrue(self.window.runner.busy)
        finally:
            release.set()
            # This job tests closing, not the RunReport success handler.
            self.window.runner.succeeded.disconnect(self.window.job_succeeded)
            self.wait_job(self.window.runner)
        for index in range(30):
            runner.start(lambda stage: None)
            self.wait_job(runner)

    def test_export_worker_preserves_report_after_existing_folder_error(self):
        self.window.study = short_study()
        self.window.settings_dialog.set_network(self.window.study.network)
        self.window.run_simulation()
        self.wait_job(self.window.runner)
        original = self.window.report
        with TemporaryDirectory(dir=ROOT / "07_Implementation") as directory:
            path = Path(directory) / "new_ui_export"
            with patch("src.ui.QFileDialog.getSaveFileName", return_value=(str(path), "")):
                self.window.export_results()
                self.wait_job(self.window.runner)
                self.assertTrue((path / "summary.md").is_file())
                self.window.export_results()
                self.wait_job(self.window.runner)
            self.assertIs(self.window.report, original)
            self.assertTrue(widget(self.window, "btn_export_results").isEnabled())
            self.assertIn("Error:", self.window.last_stage_message)

    def test_worker_error_cleanup_and_main_thread_delivery(self):
        runner = self.window.runner
        errors = []
        threads = []
        runner.failed.connect(lambda message, detail: errors.append(message))
        runner.succeeded.connect(lambda value: threads.append(QThread.currentThread()))
        def fail(stage):
            raise ValueError("Expected test failure")
        runner.start(fail)
        self.assertFalse(widget(self.window, "btn_load_data").isEnabled())
        self.wait_job(runner)
        self.assertEqual(errors, ["Expected test failure"])
        self.assertTrue(widget(self.window, "btn_load_data").isEnabled())
        # The raw runner may return any object; MainWindow expects RunReport.
        runner = JobRunner(self.window)
        runner.succeeded.connect(lambda value: threads.append(QThread.currentThread()))
        runner.start(lambda stage: 42)
        self.wait_job(runner)
        self.assertEqual(threads, [self.app.thread()])

    def test_simulation_worker_results_and_stale_invalidation(self):
        self.window.study = short_study()
        self.window.settings_dialog.set_network(self.window.study.network)
        self.window.run_simulation()
        self.wait_job(self.window.runner)
        self.assertIsNotNone(self.window.report)
        self.assertIn("Completed: True", widget(self.window, "results_text").toPlainText())
        self.assertTrue(widget(self.window, "btn_export_results").isEnabled())
        self.window.show_bus(2)
        self.assertIn("pu at", widget(self.window, "lbl_bus_voltage").text())
        self.window.settings_dialog.apply_settings()
        self.assertIsNone(self.window.report)
        self.assertFalse(widget(self.window, "btn_export_results").isEnabled())

    def test_real_optimization_worker_does_not_invent_bus_voltages(self):
        self.window.study = short_study()
        dialog = self.configure_optimization()
        choices = widget(dialog, "list_allowed_buses")
        for index in range(choices.count()):
            choices.item(index).setSelected(
                choices.item(index).data(Qt.ItemDataRole.UserRole) in (2, 4))
        dialog.apply_settings()
        self.window.run_optimization()
        self.wait_job(self.window.runner)
        self.assertTrue(self.window.report.result.success)
        candidate = self.window.report.result.best_candidate
        self.assertIn(candidate.bus_id, (2, 4))
        bess = next(item for item in self.window.scene.items() if item.data(1) == "bess")
        self.assertEqual(bess.parentItem().data(0), candidate.bus_id)
        self.assertIn(f"Selected bus: {candidate.bus_id}", widget(self.window, "results_text").toPlainText())
        self.assertNotIn("Search catalogs", widget(self.window, "results_text").toPlainText())
        widget(self.window, "btn_result_details").click()
        self.assertIn("Search catalogs", widget(self.window, "results_text").toPlainText())
        self.assertEqual(widget(self.window, "btn_result_details").text(), "Show summary")
        widget(self.window, "btn_result_details").click()
        self.assertNotIn("Search catalogs", widget(self.window, "results_text").toPlainText())
        self.window.show_bus(4)
        self.assertIn("Not calculated", widget(self.window, "lbl_bus_voltage").text())
        self.assertFalse(widget(self.window, "chk_network_results").isEnabled())

    def prepare_simulation(self):
        self.window.study = short_study()
        self.window.settings_dialog.set_network(self.window.study.network)
        self.window.run_simulation()
        self.wait_job(self.window.runner)

    def accept_first_timestamp(self, dialog):
        dialog.timestamps.setCurrentIndex(0)
        return QDialog.DialogCode.Accepted

    def test_properties_results_timestamp_and_cancel_are_independent(self):
        self.prepare_simulation()
        props = widget(self.window, 'chk_network_properties')
        results = widget(self.window, 'chk_network_results')
        props.setChecked(True)
        self.assertEqual(len([i for i in self.window.scene.items() if i.data(1) == 'bus_properties']), 5)
        with patch.object(TimestampDialog, 'exec', new=lambda dialog: self.accept_first_timestamp(dialog)):
            results.setChecked(True)
        self.assertTrue(results.isChecked())
        self.assertEqual(self.window.result_index, 0)
        self.assertIn(str(self.window.simulation_steps()[0].timestamp), self.window.diagram_status.text())
        labels = [i.text() for i in self.window.scene.items() if i.data(1) == 'bus_results']
        self.assertEqual(len(labels), 5)
        expected = self.window.simulation_steps()[0].power_flow.voltage_mag_pu[2]
        self.assertTrue(any(f'{expected:.5f} pu' in text for text in labels))
        self.window.show_bus(2)
        self.assertIn(str(self.window.simulation_steps()[0].timestamp), widget(self.window, 'lbl_bus_voltage').text())
        with patch.object(TimestampDialog, 'exec', return_value=QDialog.DialogCode.Rejected):
            self.assertFalse(self.window.choose_result_timestamp())
        self.assertEqual(self.window.result_index, 0)
        results.setChecked(False)
        self.assertTrue(props.isChecked())
        self.assertFalse(any(i.data(1) == 'bus_results' for i in self.window.scene.items()))
        with patch.object(TimestampDialog, 'exec', return_value=QDialog.DialogCode.Rejected):
            results.setChecked(True)
        self.assertFalse(results.isChecked())

    def test_rotation_hide_and_clear_results_preserve_inputs(self):
        self.prepare_simulation()
        study, report = self.window.study, self.window.report
        self.assertEqual(self.window.scene.layout.load_sides[2], 'below')
        positions = dict(self.window.scene.layout.positions)
        for turn in (1, 2, 3, 0):
            self.window.rotate_network()
            self.assertEqual(self.window.scene.turns, turn)
            for node in self.window.scene.bus_items.values():
                labels = [i for i in node.childItems() if i.data(1) in ('label', 'bus_number')]
                self.assertTrue(all((i.rotation() + node.rotation()) % 360 == 0 for i in labels))
        self.assertEqual(self.window.scene.layout.positions, positions)
        widget(self.window, 'chk_hide_diagram').setChecked(True)
        self.assertTrue(widget(self.window, 'network_view').isHidden())
        self.assertIs(self.window.report, report)
        widget(self.window, 'chk_hide_diagram').setChecked(False)
        self.window.clear_results()
        self.assertIs(self.window.study, study)
        self.assertIsNone(self.window.report)
        self.assertFalse(widget(self.window, 'chk_network_results').isEnabled())

    def test_clear_workspace_confirmation_and_fresh_dialogs(self):
        self.prepare_simulation()
        from PySide6.QtWidgets import QMessageBox
        before = self.window.study
        with patch('src.ui.QMessageBox.question', return_value=QMessageBox.StandardButton.No):
            self.window.clear_workspace()
        self.assertIs(self.window.study, before)
        with patch('src.ui.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
            self.window.clear_workspace()
        self.assertIsNone(self.window.study)
        self.assertIsNone(self.window.report)
        self.assertFalse(self.window.scene.items())
        self.assertFalse(self.window.scene.branch_sides)
        self.assertIsNone(self.window.load_dialog.study)
        self.assertFalse(widget(self.window, 'btn_run_simulation').isEnabled())

    def test_failed_hour_is_not_presented_as_valid_diagram_results(self):
        self.prepare_simulation()
        self.window.report.result.steps[0].power_flow.converged = False
        with patch.object(TimestampDialog, 'exec', new=lambda dialog: self.accept_first_timestamp(dialog)):
            widget(self.window, 'chk_network_results').setChecked(True)
        self.assertIn('NOT CONVERGED', self.window.diagram_status.text())
        labels = [i.text() for i in self.window.scene.items() if i.data(1) == 'bus_results']
        self.assertTrue(all('unavailable' in text for text in labels))
        widget(self.window, 'chk_network_properties').setChecked(True)
        self.assertTrue(any(i.data(1) == 'bus_properties' for i in self.window.scene.items()))

    def test_annotation_boxes_do_not_cover_guide_case_busbars_after_rotation(self):
        self.prepare_simulation()
        scene = self.window.scene
        for turn in range(4):
            scene.turns = turn
            scene.draw_network(self.window.study.network, show_properties=True,
                               step=self.window.simulation_steps()[0])
            bars = [item.sceneBoundingRect() for item in scene.items() if item.data(1) == 'busbar']
            annotations = [item for item in scene.items()
                           if item.data(1) in ('bus_properties', 'bus_results', 'line_annotation')]
            for label in annotations:
                self.assertFalse(any(label.sceneBoundingRect().intersects(bar) for bar in bars),
                                 f'Annotation covers a busbar at rotation {turn}: {label.text()}')

    def test_new_display_actions_are_disabled_while_worker_is_busy(self):
        self.window.study = short_study()
        release = Event()
        self.window.runner.succeeded.disconnect(self.window.job_succeeded)
        self.window.runner.start(lambda stage: release.wait(5))
        try:
            for name in ('chk_network_properties', 'chk_network_results', 'btn_result_timestamp',
                         'btn_rotate_network', 'btn_clear_results', 'btn_clear_workspace'):
                self.assertFalse(widget(self.window, name).isEnabled(), name)
            study = self.window.study
            self.window.clear_workspace()
            self.window.clear_results()
            self.assertIs(self.window.study, study)
        finally:
            release.set()
            self.wait_job(self.window.runner)

    def test_compact_designer_controls_and_collapsible_details(self):
        for name in ('btn_auto_arrange', 'combo_layout_branch', 'combo_branch_side', 'panel_network_display'):
            self.assertIsNone(self.window.findChild(QWidget, name), name)
        for name in ('btn_fit_network', 'btn_zoom_in', 'btn_zoom_out'):
            control = widget(self.window, name)
            self.assertEqual(control.text(), '')
            self.assertFalse(control.icon().isNull())
            self.assertTrue(control.toolTip())
            self.assertTrue(control.accessibleName())
            self.assertLessEqual(control.maximumWidth(), 40)
        self.assertEqual(widget(self.window, 'btn_rotate_network').text(), '90°')
        details = widget(self.window, 'group_bus_details')
        self.assertTrue(details.isHidden())
        widget(self.window, 'chk_bus_details').setChecked(True)
        self.assertFalse(details.isHidden())
        widget(self.window, 'chk_bus_details').setChecked(False)
        self.assertTrue(details.isHidden())
        self.assertEqual(widget(self.window, 'frame_action').maximumWidth(), 160)

    def test_display_layers_compact_geometry_without_changing_rotation_or_sides(self):
        self.prepare_simulation()
        self.window.scene.turns = 2
        self.window.refresh_network()
        compact = dict(self.window.scene.layout.positions)
        sides = dict(self.window.scene.layout.branch_sides)
        widget(self.window, 'chk_network_properties').setChecked(True)
        self.assertNotEqual(self.window.scene.layout.positions, compact)
        self.assertEqual(self.window.scene.layout.branch_sides, sides)
        self.assertEqual(self.window.scene.turns, 2)

        widget(self.window, 'chk_network_properties').setChecked(False)
        self.assertEqual(self.window.scene.layout.positions, compact)
        self.window.show()
        self.window.resize(1100, 700)
        self.app.processEvents()
        QTest.qWait(100)
        self.assertEqual(self.window.scene.layout.positions, compact)
        self.assertEqual(self.window.scene.turns, 2)

    def test_bus_numbers_and_necessary_equipment_labels_only(self):
        scene = self.window.scene
        scene.draw_network(build_guide_5_bus_case(), bess_bus=4)
        numbers = [item.text() for item in scene.items() if item.data(1) == 'bus_number']
        self.assertEqual(set(numbers), {'1', '2', '3', '4', '5'})
        labels = [item.text() for item in scene.items() if hasattr(item, 'text')]
        self.assertNotIn('Load', labels)
        self.assertFalse(any(text.startswith('Bus ') for text in labels))
        self.assertIn('PV', labels)
        self.assertIn('BESS', labels)
        self.assertTrue(all(item.toolTip() for item in scene.items() if item.data(1) == 'load'))

    def test_wheel_zoom_in_out_and_limits(self):
        self.window.study = short_study()
        self.window.refresh_network()
        self.window.show()
        self.app.processEvents()
        QTest.qWait(100)
        view = widget(self.window, 'network_view')
        self.window.fit_network()
        original = view.transform().m11()
        point = view.viewport().rect().center()
        for delta, expected in ((120, 1.25), (-120, 1.0)):
            event = QWheelEvent(QPointF(point), QPointF(view.viewport().mapToGlobal(point)),
                                QPoint(), QPoint(0, delta), Qt.MouseButton.NoButton,
                                Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
            QApplication.sendEvent(view.viewport(), event)
            self.assertAlmostEqual(view.transform().m11(), original * expected)
        view.zoom_by(1e30)
        self.assertAlmostEqual(view.transform().m11(), 20)
        view.zoom_by(1e-30)
        self.assertAlmostEqual(view.transform().m11(), .01)

    def test_click_near_thin_line_details_and_selection_survive_redraw(self):
        self.prepare_simulation()
        widget(self.window, 'tabs_workspace').setCurrentIndex(0)
        self.window.show()
        self.app.processEvents()
        QTest.qWait(100)
        self.window.fit_network()
        scene = self.window.scene
        line_id = self.window.study.network.lines[0].line_id
        line = scene.line_items[line_id]
        view = widget(self.window, 'network_view')
        point = view.mapFromScene(line.path().pointAtPercent(.5)) + QPoint(0, 5)
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(scene.selectedItems()[0].data(2), line_id)
        self.assertEqual(widget(self.window, 'group_bus_details').title(), f'Line {line_id}')
        self.assertIn('Loss', widget(self.window, 'lbl_line_details').text())
        scene.clearSelection()
        label = next(item for item in scene.items() if item.data(1) == 'line_id' and item.data(2) == line_id)
        point = view.mapFromScene(label.sceneBoundingRect().center())
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(scene.selectedItems()[0].data(2), line_id)
        self.window.rotate_network()
        self.assertEqual(scene.selectedItems()[0].data(2), line_id)
        with patch.object(TimestampDialog, 'exec', new=lambda dialog: self.accept_first_timestamp(dialog)):
            self.window.choose_result_timestamp()
        self.assertIn(str(self.window.simulation_steps()[0].timestamp), widget(self.window, 'lbl_line_details').text())
        self.window.clear_results()
        self.assertIn('Not calculated', widget(self.window, 'lbl_line_details').text())
        scene.clearSelection()
        scene.bus_items[2].setSelected(True)
        self.assertEqual(widget(self.window, 'lbl_bus_id').text(), '2')
        self.assertEqual(widget(self.window, 'group_bus_details').title(), 'Bus 2')

    def test_failed_hour_line_details_suppress_calculated_values(self):
        self.prepare_simulation()
        step = self.window.simulation_steps()[0]
        step.power_flow.converged = False
        self.window.result_index = 0
        line_id = self.window.study.network.lines[0].line_id
        self.window.scene.line_items[line_id].setSelected(True)
        details = widget(self.window, 'lbl_line_details').text()
        self.assertIn('NOT CONVERGED', details)
        self.assertIn('unavailable', details)
        self.assertNotIn('Loss', details)


if __name__ == "__main__":
    unittest.main()
