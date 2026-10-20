"""Designer-backed PySide6 desktop; see README_ui.md for launch and inputs."""
from copy import deepcopy
from datetime import datetime, time
from functools import partial
from pathlib import Path
import os
import sys
import traceback
from time import perf_counter

from PySide6.QtCore import QFile, QIODevice, QObject, QSize, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QGraphicsScene,
    QGroupBox, QLabel, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QSpinBox, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .bess import BESSConfig
from .dispatch import NetLoadTargetPolicy
from .fbs import FBSConfig
from .accelerated_fbs import backend_available, backend_status
from .metrics import EconomicConfig
from .network_diagram import NetworkScene, NetworkView
from .network_icons import network_icon
from .network_loader import load_network
from .optimizer import BESSParameters, OptimizationResult
from .simulation import SimulationConfig, TimeSeriesSimulationResult
from .progress import StageReporter, format_duration
from .study_session import StudySession, study_fingerprint
from .ui_workflow import DataRequest, RunSettings, prepare_study, run_and_export, run_base_case_and_export, size_catalog


ASSETS = Path(__file__).resolve().parent / "assets"
REPO = Path(__file__).resolve().parents[2]


class FormLoader(QUiLoader):
    """Populate a concrete root class rather than create a second window."""
    def __init__(self, root):
        super().__init__()
        self.root = root

    def createWidget(self, class_name, parent=None, name=""):
        if parent is None:
            return self.root
        if class_name == "QGraphicsView" and name == "network_view":
            view = NetworkView(parent)
            view.setObjectName(name)
            return view
        return super().createWidget(class_name, parent, name)


def load_form(root, filename):
    source = QFile(str(ASSETS / filename))
    if not source.open(QIODevice.OpenModeFlag.ReadOnly):
        raise RuntimeError(f"Cannot open form {filename}: {source.errorString()}")
    loader = FormLoader(root)
    try:
        if loader.load(source) is None:
            raise RuntimeError(f"Cannot load {filename}: {loader.errorString()}")
    finally:
        source.close()


def widget(root, name):
    result = root.findChild(QWidget, name)
    if result is None:
        raise RuntimeError(f"Missing Designer object {name!r} in {root.objectName()}")
    return result


class Worker(QObject):
    stage = Signal(str)
    progress = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str, str)
    finished = Signal()

    def __init__(self, task):
        super().__init__()
        self.task = task

    @Slot()
    def run(self):
        try:
            reporter = StageReporter(self.stage.emit, self.progress.emit)
            self.succeeded.emit(self.task(reporter))
        except Exception as error:
            # Boundary catch: restore UI state and retain unexpected error details.
            self.failed.emit(str(error), traceback.format_exc())
        finally:
            self.finished.emit()


class JobRunner(QObject):
    stage = Signal(str)
    progress = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str, str)
    busy_changed = Signal(bool)

    def __init__(self, parent):
        super().__init__(parent)
        self.thread = None
        self.worker = None
        self.result = None
        self.failure = None

    @property
    def busy(self):
        return self.thread is not None

    def start(self, task):
        if self.busy:
            raise RuntimeError("A job is already running")
        self.result, self.failure = None, None
        self.thread = QThread(self)
        self.worker = Worker(task)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.stage.connect(self.stage)
        self.worker.progress.connect(self.progress)
        self.worker.succeeded.connect(self.store_result)
        self.worker.failed.connect(self.store_failure)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.finish, Qt.ConnectionType.QueuedConnection)
        self.busy_changed.emit(True)
        self.thread.start()

    @Slot(object)
    def store_result(self, result):
        self.result = result

    @Slot(str, str)
    def store_failure(self, message, details):
        self.failure = (message, details)

    @Slot()
    def finish(self):
        # finished() can precede native thread-local cleanup. Poll without
        # blocking the GUI, retaining both wrappers until the OS thread exits.
        if not self.thread.wait(0):
            QTimer.singleShot(5, self.finish)
            return
        self.thread.deleteLater()
        self.thread, self.worker = None, None
        self.busy_changed.emit(False)
        if self.failure is not None:
            self.failed.emit(*self.failure)
        else:
            self.succeeded.emit(self.result)


class LoadDataDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        load_form(self, "load_data_dialog.ui")
        self.runner = JobRunner(self)
        self.study = None
        self.pending_action = ""
        source = widget(self, "combo_pv_source")
        source.clear()
        for title, key in (("Open-Meteo irradiance CSV", "open_meteo"),
                           ("NASA POWER irradiance CSV", "nasa_power"),
                           ("Prepared irradiance CSV", "prepared"),
                           ("Prepared PV power CSV", "power"), ("No PV", "none")):
            source.addItem(title, key)
        source.setCurrentIndex(2)
        for name in ("edit_network_path", "edit_pv_source_path", "edit_load_path"):
            widget(self, name).setReadOnly(True)
        date = widget(self, "date_study_start")
        if not isinstance(date, QDateTimeEdit):
            raise RuntimeError("date_study_start must be QDateEdit or QDateTimeEdit")
        if date.metaObject().className() == "QDateEdit":
            date.setDisplayFormat("yyyy-MM-dd")
        self.connect_events()
        self.update_modes()

    def connect_events(self):
        widget(self, "btn_browse_network").clicked.connect(self.browse_network)
        widget(self, "btn_browse_pv_source").clicked.connect(self.browse_pv)
        widget(self, "btn_browse_load").clicked.connect(self.browse_load)
        widget(self, "btn_load_network").clicked.connect(self.load_network_preview)
        widget(self, "edit_network_path").textChanged.connect(self.update_network_button)
        widget(self, "combo_pv_source").currentIndexChanged.connect(self.update_modes)
        widget(self, "combo_load_source").currentIndexChanged.connect(self.update_modes)
        widget(self, "btn_add_pv_row").clicked.connect(self.add_pv_row)
        widget(self, "btn_remove_pv_row").clicked.connect(self.remove_pv_row)
        widget(self, "buttons_load_data").accepted.connect(self.prepare_data)
        self.runner.busy_changed.connect(self.set_busy)
        self.runner.stage.connect(widget(self, "lbl_load_validation").setText)
        self.runner.failed.connect(self.show_failure)
        self.runner.succeeded.connect(self.job_succeeded)

    def browse_network(self):
        path, _ = QFileDialog.getOpenFileName(self, "Network workbook", str(REPO), "Excel workbook (*.xlsx)")
        if path:
            widget(self, "edit_network_path").setText(path)
            widget(self, "lbl_network_summary").setText("Load this network to inspect its buses and PV installations.")

    def browse_pv(self):
        path, _ = QFileDialog.getOpenFileName(self, "PV / irradiance CSV", str(REPO), "CSV files (*.csv)")
        if path:
            widget(self, "edit_pv_source_path").setText(path)

    def browse_load(self):
        path, _ = QFileDialog.getOpenFileName(self, "Prepared load CSV", str(REPO), "CSV files (*.csv)")
        if path:
            widget(self, "edit_load_path").setText(path)

    def update_network_button(self):
        widget(self, "btn_load_network").setEnabled(bool(widget(self, "edit_network_path").text()) and not self.runner.busy)

    def update_modes(self):
        mode = widget(self, "combo_pv_source").currentData()
        for name in ("edit_pv_source_path", "btn_browse_pv_source", "group_pv_conversion"):
            widget(self, name).setEnabled(mode != "none")
        widget(self, "group_pv_conversion").setTitle("PV Installations and Irradiance Conversion")
        for name in ("spin_critical_irradiance", "spin_standard_irradiance"):
            widget(self, name).setEnabled(mode not in ("none", "power"))
        imported = widget(self, "combo_load_source").currentIndex() == 1
        widget(self, "panel_load_import").setEnabled(imported)
        widget(self, "group_synthetic_load").setEnabled(not imported)

    def add_pv_row(self):
        table = widget(self, "table_pv_installations")
        table.insertRow(table.rowCount())

    def remove_pv_row(self):
        table = widget(self, "table_pv_installations")
        if table.currentRow() >= 0:
            table.removeRow(table.currentRow())

    def network_arguments(self):
        path = widget(self, "edit_network_path").text().strip()
        if not path:
            raise ValueError("Choose a network workbook")
        frequency = widget(self, "spin_frequency_hz").value()
        format_name = ("auto", "project", "ieee33")[widget(self, "combo_network_format").currentIndex()]
        return Path(path), frequency or None, format_name

    def load_network_preview(self):
        try:
            path, frequency, format_name = self.network_arguments()
            def task(stage):
                stage("Reading network workbook")
                return load_network(path, workbook_format=format_name, frequency_hz=frequency)
            self.pending_action = "network"
            self.runner.start(task)
        except (ValueError, OSError) as error:
            self.show_failure(str(error), "")

    def read_request(self):
        path, frequency, format_name = self.network_arguments()
        ratings = {}
        table = widget(self, "table_pv_installations")
        row_count = 0 if widget(self, "combo_pv_source").currentData() == "none" else table.rowCount()
        for row in range(row_count):
            cells = [table.item(row, col).text().strip() if table.item(row, col) else "" for col in (0, 1)]
            if not any(cells):
                continue
            try:
                bus, rating = int(cells[0]), float(cells[1])
            except ValueError as error:
                raise ValueError(f"PV row {row + 1}: supply an integer bus ID and numeric kW") from error
            if bus in ratings:
                raise ValueError(f"Duplicate PV bus {bus}; enter one total rating per bus")
            ratings[bus] = rating
        date_widget = widget(self, "date_study_start")
        start = datetime.combine(date_widget.date().toPython(), time())
        if date_widget.metaObject().className() != "QDateEdit":
            start = date_widget.dateTime().toPython()
        pv_path = widget(self, "edit_pv_source_path").text().strip()
        load_path = widget(self, "edit_load_path").text().strip()
        return DataRequest(
            network_path=path, frequency_hz=frequency, workbook_format=format_name,
            start=start, months=widget(self, "spin_study_months").value(),
            pv_source=widget(self, "combo_pv_source").currentData(), pv_path=Path(pv_path) if pv_path else None,
            pv_ratings_kw=ratings, critical_irradiance=widget(self, "spin_critical_irradiance").value(),
            standard_irradiance=widget(self, "spin_standard_irradiance").value(),
            load_source="imported" if widget(self, "combo_load_source").currentIndex() == 1 else "synthetic",
            load_path=Path(load_path) if load_path else None, load_seed=widget(self, "spin_load_seed").value())

    def prepare_data(self):
        try:
            request = self.read_request()
            self.pending_action = "prepare"
            self.runner.start(partial(prepare_study, request))
        except (ValueError, OSError) as error:
            self.show_failure(str(error), "")

    def set_busy(self, busy):
        for name in ("tabs_data", "group_study_period", "buttons_load_data"):
            widget(self, name).setEnabled(not busy)
        self.update_network_button()

    def show_failure(self, message, details):
        widget(self, "lbl_load_validation").setText(f"Error: {message}")
        widget(self, "lbl_load_validation").setToolTip(details)

    def job_succeeded(self, result):
        if self.pending_action == "prepare":
            self.study = result
            widget(self, "lbl_load_validation").setText("Data prepared and validated")
            self.accept()
            return
        widget(self, "lbl_network_summary").setText(
            f"{len(result.buses)} buses, {len(result.lines)} lines; slack {result.slack_bus_id()}; "
            f"base load {sum(load.p_base_kw for load in result.loads):g} kW; frequency {result.frequency_hz:g} Hz")
        table = widget(self, "table_pv_installations")
        ratings = {}
        for unit in result.pv_units:
            ratings[unit.bus_id] = ratings.get(unit.bus_id, 0.0) + unit.p_rated_kw
        table.setRowCount(max(1, len(ratings)))
        table.clearContents()
        for row, (bus, rating) in enumerate(sorted(ratings.items())):
            table.setItem(row, 0, QTableWidgetItem(str(bus)))
            table.setItem(row, 1, QTableWidgetItem(str(rating)))
        widget(self, "lbl_load_validation").setText("Network inspected. Configure PV/load inputs, then press OK.")

    def reject(self):
        if self.runner.busy:
            widget(self, "lbl_load_validation").setText("A job is running. Wait for completion; cancellation is not implemented.")
        else:
            super().reject()

    def closeEvent(self, event):
        if self.runner.busy:
            event.ignore()
            widget(self, "lbl_load_validation").setText("A job is running. Wait for completion; cancellation is not implemented.")
        else:
            super().closeEvent(event)


class SettingsDialog(QDialog):
    applied = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        load_form(self, "settings_dialog.ui")
        self.network = None
        self.add_runtime_controls()
        self.committed = self.capture_values()
        buttons = widget(self, "buttons_settings")
        buttons.accepted.connect(self.accept_settings)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply_settings)
        widget(self, "combo_dispatch_policy").currentIndexChanged.connect(self.update_dispatch)
        widget(self, "combo_compute_backend").currentIndexChanged.connect(self.update_compute_status)
        self.update_dispatch()
        self.update_compute_status()

    def add_runtime_controls(self):
        if self.findChild(QWidget, "combo_dispatch_policy") is None:
            group = QGroupBox("Dispatch", self)
            group.setObjectName("group_dispatch_policy")
            layout = QFormLayout(group)
            combo = QComboBox(group)
            combo.setObjectName("combo_dispatch_policy")
            combo.addItems(["Idle (diagnostic only)", "Net-load target"])
            layout.addRow("Battery operating policy", combo)
            target = QDoubleSpinBox(group)
            target.setObjectName("spin_dispatch_target_kw")
            target.setDecimals(2)
            target.setRange(0, 1e9)
            target.setSuffix(" kW")
            target.setKeyboardTracking(False)
            layout.addRow("Net-load target", target)
            widget(self, "contents_battery").layout().insertWidget(2, group)
        for name, title, suffix in (("spin_opt_power_step_kw", "Power search step", " kW"),
                                     ("spin_opt_energy_step_kwh", "Energy search step", " kWh")):
            if self.findChild(QWidget, name) is None:
                control = QDoubleSpinBox(self)
                control.setObjectName(name)
                control.setDecimals(2)
                control.setRange(0, 1e9)
                control.setSpecialValueText("Set step")
                control.setSuffix(suffix)
                control.setKeyboardTracking(False)
                widget(self, "group_optimization_bounds").layout().addRow(title, control)
        if self.findChild(QWidget, "combo_compute_backend") is None:
            group = QGroupBox("Computation", self)
            group.setObjectName("group_compute_backend")
            layout = QFormLayout(group)
            combo = QComboBox(group)
            combo.setObjectName("combo_compute_backend")
            combo.addItem("Python reference (CPU)", "python")
            combo.addItem("NumPy arrays (CPU)", "numpy")
            combo.addItem("Numba compiled (CPU)", "numba")
            layout.addRow("Power-flow backend", combo)
            logical_threads = max(1, os.cpu_count() or 1)
            layout.addRow("Logical CPU threads", QLabel(str(logical_threads), group))
            layout.addRow("Recommended GWO workers", QLabel(str(max(1, logical_threads - 1)), group))
            workers = QSpinBox(group)
            workers.setObjectName("spin_cpu_workers")
            workers.setRange(1, logical_threads)
            workers.setValue(max(1, logical_threads - 1))
            workers.setKeyboardTracking(False)
            layout.addRow("GWO CPU workers", workers)
            status = QLabel(group)
            status.setObjectName("lbl_compute_status")
            status.setWordWrap(True)
            layout.addRow(status)
            widget(self, "contents_optimization").layout().insertWidget(0, group)
        if self.findChild(QWidget, "btn_select_all_buses") is None:
            controls = QWidget(self)
            controls.setObjectName("panel_allowed_bus_actions")
            layout = QFormLayout(controls)
            select_all = QPushButton("Select all eligible buses", controls)
            select_all.setObjectName("btn_select_all_buses")
            clear = QPushButton("Clear selection", controls)
            clear.setObjectName("btn_clear_allowed_buses")
            count = QLabel("0 eligible buses selected", controls)
            count.setObjectName("lbl_allowed_bus_count")
            layout.addRow(select_all, clear)
            layout.addRow("Selection", count)
            parent_layout = widget(self, "contents_optimization").layout()
            parent_layout.insertWidget(1, controls)
            select_all.clicked.connect(self.select_all_allowed_buses)
            clear.clicked.connect(self.clear_allowed_buses)
            widget(self, "list_allowed_buses").itemSelectionChanged.connect(self.update_allowed_bus_count)
        widget(self, "lbl_optimization_status").setText("Endpoint-inclusive min/max/step grid; generic study sizes, not supplier products.")
        pages = widget(self, "list_settings_pages")
        stack = widget(self, "stack_settings_pages")
        uncertainty_page = widget(self, "page_uncertainty")
        uncertainty_index = stack.indexOf(uncertainty_page)
        if uncertainty_index >= 0:
            stack.removeWidget(uncertainty_page)
            pages.takeItem(uncertainty_index)

    def select_all_allowed_buses(self):
        choices = widget(self, "list_allowed_buses")
        for index in range(choices.count()):
            choices.item(index).setSelected(True)
        self.update_allowed_bus_count()

    def clear_allowed_buses(self):
        widget(self, "list_allowed_buses").clearSelection()
        self.update_allowed_bus_count()

    def update_allowed_bus_count(self):
        choices = widget(self, "list_allowed_buses")
        widget(self, "lbl_allowed_bus_count").setText(
            f"{len(choices.selectedItems())} of {choices.count()} eligible buses selected")

    def update_compute_status(self):
        backend = widget(self, "combo_compute_backend").currentData()
        available, reason = backend_available(backend)
        workers = widget(self, "spin_cpu_workers")
        status = backend_status()
        prefix = "Ready" if available else "Unavailable"
        widget(self, "lbl_compute_status").setText(
            f"{prefix}: {reason}. Detected: Numba {status['numba']}; CPU workers run GWO."
        )

    def update_dispatch(self):
        target_mode = widget(self, "combo_dispatch_policy").currentIndex() == 1
        widget(self, "spin_dispatch_target_kw").setEnabled(target_mode)
        widget(self, "lbl_dispatch_status").setText(
            "Discharge above target; charge below target (may charge from grid)." if target_mode else
            "Idle diagnostic mode: no scheduled charge/discharge request.")

    def capture_values(self):
        values = {control.objectName(): control.value() for cls in (QSpinBox, QDoubleSpinBox) for control in self.findChildren(cls)}
        for control in self.findChildren(QGroupBox):
            if control.isCheckable():
                values[control.objectName()] = control.isChecked()
        for name in ("chk_allow_curtailment", "chk_allow_shedding"):
            values[name] = widget(self, name).isChecked()
        values["edit_currency"] = widget(self, "edit_currency").text().strip()
        values["bess_bus"] = widget(self, "combo_bess_bus").currentData()
        values["allowed_buses"] = tuple(item.data(Qt.ItemDataRole.UserRole) for item in widget(self, "list_allowed_buses").selectedItems())
        values["dispatch_mode"] = widget(self, "combo_dispatch_policy").currentIndex()
        values["compute_backend"] = widget(self, "combo_compute_backend").currentData()
        return values

    def restore_values(self):
        for name, value in self.committed.items():
            control = self.findChild(QWidget, name)
            if isinstance(control, (QSpinBox, QDoubleSpinBox)):
                control.setValue(value)
            elif isinstance(control, QGroupBox):
                control.setChecked(value)
            elif name.startswith("chk_"):
                control.setChecked(value)
        widget(self, "edit_currency").setText(self.committed["edit_currency"])
        combo = widget(self, "combo_bess_bus")
        combo.setCurrentIndex(combo.findData(self.committed["bess_bus"]))
        choices = widget(self, "list_allowed_buses")
        for index in range(choices.count()):
            item = choices.item(index)
            item.setSelected(item.data(Qt.ItemDataRole.UserRole) in self.committed["allowed_buses"])
        widget(self, "combo_dispatch_policy").setCurrentIndex(self.committed["dispatch_mode"])
        compute = widget(self, "combo_compute_backend")
        compute.setCurrentIndex(max(0, compute.findData(self.committed["compute_backend"])))
        self.update_dispatch()
        self.update_compute_status()

    def set_network(self, network):
        self.network = network
        combo = widget(self, "combo_bess_bus")
        choices = widget(self, "list_allowed_buses")
        combo.clear()
        choices.clear()
        for bus in sorted(network.buses, key=lambda item: item.bus_id):
            combo.addItem(f"B{bus.bus_id}", bus.bus_id)
            if bus.is_slack:
                continue
            item = QListWidgetItem(f"B{bus.bus_id}")
            item.setData(Qt.ItemDataRole.UserRole, bus.bus_id)
            choices.addItem(item)
        self.restore_values()
        self.update_allowed_bus_count()

    def read_settings(self, optimization=False):
        values = self.capture_values()
        backend = values["compute_backend"]
        available, reason = backend_available(backend)
        if not available:
            raise ValueError(f"Selected compute backend is unavailable: {reason}")
        simulation = SimulationConfig(
            voltage_min_pu=values["spin_voltage_min_pu"], voltage_max_pu=values["spin_voltage_max_pu"],
            reserve_fraction=values["spin_reserve_percent"] / 100 if values["group_reserve"] else 0,
            reserve_duration_hours=values["spin_reserve_hours"],
            grid_import_limit_kw=values["spin_import_limit_kw"] if values["group_import_limit"] else None,
            grid_export_limit_kw=values["spin_export_limit_kw"] if values["group_export_limit"] else None,
            allow_pv_curtailment=values["chk_allow_curtailment"], allow_load_shedding=values["chk_allow_shedding"],
            fbs_config=FBSConfig(backend=backend))
        economics = EconomicConfig(values["spin_cost_per_kwh"] if values["group_economic_inputs"] else None,
                                   values["spin_cost_per_kw"] if values["group_economic_inputs"] else None,
                                   values["edit_currency"])
        dispatch = NetLoadTargetPolicy(values["spin_dispatch_target_kw"]) if values["dispatch_mode"] == 1 else None
        battery = None
        if values["group_manual_bess"] or optimization:
            parameters = BESSParameters(values["spin_eta_charge_percent"] / 100, values["spin_eta_discharge_percent"] / 100,
                                        values["spin_soc_min_percent"] / 100, values["spin_soc_max_percent"] / 100,
                                        values["spin_soc_initial_percent"] / 100)
            if values["group_manual_bess"] and not optimization:
                if self.network is None or values["bess_bus"] not in {bus.bus_id for bus in self.network.buses}:
                    raise ValueError("Choose an installation bus from the loaded network")
                if values["spin_bess_power_kw"] <= 0 or values["spin_bess_energy_kwh"] <= 0:
                    raise ValueError("Manual battery kW and kWh must be positive")
                battery = BESSConfig(values["bess_bus"], values["spin_bess_energy_kwh"], values["spin_bess_power_kw"],
                                     parameters.soc_min, parameters.soc_max, parameters.soc_initial,
                                     parameters.eta_charge, parameters.eta_discharge)
        if optimization:
            if dispatch is None or economics.cost_per_kw is None or economics.cost_per_kwh is None:
                raise ValueError("Optimization requires target dispatch and both explicit cost coefficients")
            if not values["allowed_buses"]:
                raise ValueError("Select allowed battery buses")
            size_catalog(values["spin_opt_power_min_kw"], values["spin_opt_power_max_kw"], values["spin_opt_power_step_kw"])
            size_catalog(values["spin_opt_energy_min_kwh"], values["spin_opt_energy_max_kwh"], values["spin_opt_energy_step_kwh"])
        return RunSettings(simulation, economics, battery, values, dispatch)

    def apply_settings(self):
        try:
            settings = self.read_settings()
            self.committed = settings.values
            widget(self, "lbl_settings_validation").setText("Settings applied. Runs use these explicit inputs.")
            self.applied.emit(settings)
            return True
        except ValueError as error:
            widget(self, "lbl_settings_validation").setText(f"Error: {error}")
            return False

    def accept_settings(self):
        if self.apply_settings():
            self.accept()

    def reject(self):
        self.restore_values()
        super().reject()


class ScenarioGeneratorDialog(QDialog):
    """Generate, inspect and persist scenarios outside the run workflow."""
    def __init__(self, study, session, parent=None):
        super().__init__(parent)
        load_form(self, "scenario_generator.ui")
        self.study = study
        self.session = session
        self.generated = None
        self.selected = None
        self.imported_path = None
        self.pending_action = ""
        self.runner = JobRunner(self)
        widget(self, "tabs_scenarios").setCurrentIndex(0)
        widget(self, "log_scenarios").setMaximumBlockCount(3000)
        self.validation_scene = QGraphicsScene(self)
        self.scenario_scene = QGraphicsScene(self)
        widget(self, "view_validation_plot").setScene(self.validation_scene)
        widget(self, "view_scenario_plot").setScene(self.scenario_scene)
        for name in ("view_validation_plot", "view_scenario_plot"):
            widget(self, name).setRenderHint(QPainter.RenderHint.Antialiasing)
        self.show_sources()
        self.connect_events()

    def show_sources(self):
        profiles = self.study.profiles
        widget(self, "lbl_source_network").setText(
            f"{self.study.request.network_path}\n"
            f"{len(self.study.network.buses)} buses; {len(self.study.network.lines)} lines"
        )
        widget(self, "lbl_source_load").setText(
            f"{self.study.context.get('Demand', self.study.request.load_source)}\n"
            f"{len(profiles.load_p_kw)} bus profile(s); {len(profiles.timestamps)} hourly records"
        )
        pv_rating = sum(unit.p_rated_kw for unit in self.study.network.pv_units)
        pv_text = "No installed PV; zero profile" if pv_rating == 0 else (
            f"{self.study.context.get('PV source', self.study.request.pv_source)}\n"
            f"{len(profiles.pv_p_kw)} bus profile(s); {pv_rating:g} kW installed"
        )
        widget(self, "lbl_source_pv").setText(pv_text)
        widget(self, "lbl_source_session").setText(str(self.session.root))

    def connect_events(self):
        widget(self, "btn_generate_scenarios").clicked.connect(self.generate)
        widget(self, "btn_import_scenarios").clicked.connect(self.import_saved)
        widget(self, "btn_save_use_scenarios").clicked.connect(self.save_and_use)
        widget(self, "btn_close_scenarios").clicked.connect(self.reject)
        self.runner.busy_changed.connect(self.set_busy)
        self.runner.stage.connect(self.show_stage)
        self.runner.progress.connect(self.show_progress)
        self.runner.succeeded.connect(self.job_succeeded)
        self.runner.failed.connect(self.show_failure)

    def generation_settings(self):
        generated = widget(self, "spin_generator_count").value()
        counts = (
            widget(self, "spin_generator_best").value(),
            widget(self, "spin_generator_worst").value(),
            widget(self, "spin_generator_random").value(),
        )
        if not 0 < sum(counts) <= generated:
            raise ValueError("Best + worst + random must be positive and no larger than generated scenarios")
        modes = ("automatic", "arima", "bootstrap")
        return {
            "forecast_hours": widget(self, "spin_scenario_forecast_hours").value(),
            "validation_hours": widget(self, "spin_scenario_validation_hours").value(),
            "scenario_count": generated,
            "generation_seed": widget(self, "spin_generator_seed").value(),
            "selection_seed": widget(self, "spin_generator_selection_seed").value(),
            "selection_counts": counts,
            "arima_order": (
                widget(self, "spin_arima_p").value(),
                widget(self, "spin_arima_d").value(),
                widget(self, "spin_arima_q").value(),
            ),
            "model_mode": modes[widget(self, "combo_scenario_model").currentIndex()],
        }

    def generate(self):
        try:
            values = self.generation_settings()
            self.generated = None
            self.selected = None
            self.imported_path = None
            self.update_save_button()
            profiles = deepcopy(self.study.profiles)
            ratings = {
                bus_id: sum(unit.p_rated_kw for unit in self.study.network.pv_units
                            if unit.bus_id == bus_id)
                for bus_id in profiles.pv_p_kw
            }

            def task(reporter):
                from .uncertainty import (
                    SelectionConfig, UncertaintyConfig, generate_scenarios,
                    select_scenarios,
                )
                reporter("Fitting and validating forecast models")
                generated = generate_scenarios(
                    profiles,
                    UncertaintyConfig(
                        forecast_hours=values["forecast_hours"],
                        pv_capacity_kw=ratings,
                        scenario_count=values["scenario_count"],
                        seed=values["generation_seed"],
                        arima_order=values["arima_order"],
                        validation_hours=values["validation_hours"],
                        model_mode=values["model_mode"],
                    ),
                    progress=reporter.progress,
                )
                reporter("Ranking and selecting stress scenarios")
                best, worst, random_count = values["selection_counts"]
                selected = select_scenarios(
                    generated,
                    SelectionConfig(
                        best_count=best, worst_count=worst,
                        random_count=random_count, seed=values["selection_seed"],
                    ),
                )
                return generated, selected

            self.pending_action = "generate"
            self.runner.start(task)
        except ValueError as error:
            self.show_failure(str(error), "")

    def import_saved(self):
        path = QFileDialog.getExistingDirectory(
            self, "Choose saved scenario set", str(self.session.root / "scenarios"),
        )
        if not path:
            return

        self.generated = None
        self.selected = None
        self.imported_path = None
        self.update_save_button()

        def task(stage):
            from .scenario_store import load_scenario_package
            stage("Reading saved scenario package")
            selected, manifest = load_scenario_package(path)
            package_fingerprint = manifest.get("context", {}).get("study_fingerprint")
            if (package_fingerprint is not None
                    and package_fingerprint != self.session.manifest["fingerprint"]):
                raise ValueError("Saved scenario set was generated for a different accepted study")
            reference = selected.scenarios[0].profiles
            if set(reference.load_p_kw) != set(self.study.profiles.load_p_kw):
                raise ValueError("Saved scenario load buses do not match the current study")
            if set(reference.pv_p_kw) != set(self.study.profiles.pv_p_kw):
                raise ValueError("Saved scenario PV buses do not match the current study")
            return selected, manifest, Path(path)

        self.pending_action = "import"
        self.runner.start(task)

    def save_and_use(self):
        if self.selected is None:
            return
        destination = self.session.next_scenario_path()
        imported_path = self.imported_path
        generated = self.generated
        selected = self.selected

        def task(stage):
            if imported_path is not None:
                import shutil
                stage("Copying imported scenario package into active session")
                shutil.copytree(imported_path, destination)
                return destination
            from .scenario_store import save_scenario_package
            stage("Writing generated scenarios and validation files")
            return save_scenario_package(
                generated, selected, destination,
                package_context={
                    "study_fingerprint": self.session.manifest["fingerprint"],
                    "network_sha256": self.study.context.get("Network SHA256"),
                    "session_id": self.session.root.name,
                },
            )

        self.pending_action = "save"
        self.runner.start(task)

    def populate_validation(self, metadata):
        table = widget(self, "table_scenario_validation")
        rows = []
        plot_rows = []
        validation = metadata.get("validation", {})
        models = metadata.get("models", {})
        for kind, by_bus in validation.items():
            for bus_id, values in sorted(by_bus.items()):
                model = models.get(kind, {}).get(bus_id, {})
                arima = values.get("arima", {})
                naive = values.get("repeat_last_day", {})
                model_rmse = float(arima.get("rmse_kw", 0.0))
                naive_rmse = float(naive.get("rmse_kw", 0.0))
                rows.append((
                    f"{kind.title()} Bus {bus_id}", model.get("model", ""),
                    model.get("fit_status", ""), f"{model_rmse:.4g} kW",
                    f"{naive_rmse:.4g} kW",
                    " | ".join(values.get("training_warnings", [])),
                ))
                plot_rows.append((f"{kind.title()} {bus_id}", model_rmse, naive_rmse))
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()
        fallback_count = sum(1 for values in rows if values[1] == "hourly_residual_bootstrap")
        widget(self, "lbl_validation_summary").setText(
            f"Validated {len(rows)} series; {fallback_count} used the documented residual-bootstrap fallback."
        )
        self.draw_validation_plot(plot_rows)

    def draw_validation_plot(self, rows):
        scene = self.validation_scene
        scene.clear()
        width, height = 900.0, 170.0
        left, top, bottom = 55.0, 18.0, 28.0
        plot_height = height - top - bottom
        text_color = self.palette().color(QPalette.ColorRole.Text)
        axis_color = self.palette().color(QPalette.ColorRole.Mid)
        model_color = self.palette().color(QPalette.ColorRole.Highlight)
        naive_color = QColor("#c47a2c")
        scene.addLine(left, top, left, top + plot_height, QPen(axis_color))
        scene.addLine(left, top + plot_height, width - 10, top + plot_height, QPen(axis_color))
        maximum = max((max(model, naive) for _, model, naive in rows), default=1.0)
        maximum = maximum if maximum > 0 else 1.0
        group_width = (width - left - 20) / max(len(rows), 1)
        bar_width = min(22.0, group_width * 0.28)
        label_stride = max(1, (len(rows) + 11) // 12)
        for index, (label, model, naive) in enumerate(rows):
            center = left + group_width * (index + 0.5)
            for offset, value, color in (
                (-bar_width, model, model_color), (0.0, naive, naive_color),
            ):
                bar_height = plot_height * value / maximum
                scene.addRect(
                    center + offset, top + plot_height - bar_height,
                    bar_width, bar_height, QPen(color), color,
                )
            if index % label_stride == 0:
                label_item = scene.addText(label)
                label_item.setDefaultTextColor(text_color)
                label_item.setScale(0.72)
                label_item.setPos(center - group_width * 0.42, top + plot_height + 2)
        title = scene.addText("Holdout RMSE (kW): selected model / fallback")
        title.setDefaultTextColor(text_color)
        title.setPos(left + 8, 0)
        legend = scene.addText("Blue: selected model    Orange: repeat-last-day")
        legend.setDefaultTextColor(text_color)
        legend.setScale(0.8)
        legend.setPos(width - 330, 0)
        scene.setSceneRect(0, 0, width, height)
        widget(self, "view_validation_plot").fitInView(
            scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio,
        )

    def populate_scenarios(self):
        table = widget(self, "table_scenario_ranking")
        table.setRowCount(len(self.selected.scenarios))
        net_min, net_max = float("inf"), float("-inf")
        net_series = []
        for row, scenario in enumerate(self.selected.scenarios):
            profile = scenario.profiles
            scenario_net = []
            for index in range(len(profile.timestamps)):
                net = (sum(values[index] for values in profile.load_p_kw.values())
                       - sum(values[index] for values in profile.pv_p_kw.values()))
                net_min, net_max = min(net_min, net), max(net_max, net)
                scenario_net.append(net)
            net_series.append((
                scenario.scenario_id,
                scenario.metadata.get("selection_group", "selected"),
                scenario_net,
            ))
            values = (
                scenario.scenario_id,
                f"{scenario.metadata.get('stress_score', 0.0):.5f}",
                scenario.metadata.get("selection_group", "selected"),
                len(profile.timestamps),
            )
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()
        metadata = self.selected.metadata
        counts = metadata.get("selection_counts", {})
        widget(self, "text_scenario_preview").setPlainText(
            f"Generated: {metadata.get('source_scenario_count', len(self.selected.scenarios))}\n"
            f"Selected: {len(self.selected.scenarios)} "
            f"(best {counts.get('best', 0)}, worst {counts.get('worst', 0)}, random {counts.get('random', 0)})\n"
            f"Forecast: {len(self.selected.scenarios[0].profiles.timestamps)} hours\n"
            f"Selected net-load range: {net_min:.3f} to {net_max:.3f} kW\n"
            "Selection is an equal-weight stress portfolio, not a probability-preserving sample."
        )
        self.draw_scenario_plot(net_series, net_min, net_max)

    def draw_scenario_plot(self, series, minimum, maximum):
        scene = self.scenario_scene
        scene.clear()
        width, height = 900.0, 170.0
        left, top, bottom = 55.0, 18.0, 25.0
        plot_width, plot_height = width - left - 12, height - top - bottom
        text_color = self.palette().color(QPalette.ColorRole.Text)
        axis_color = self.palette().color(QPalette.ColorRole.Mid)
        colors = {
            "best": QColor("#2f8f5b"),
            "worst": QColor("#c34c4c"),
            "random": self.palette().color(QPalette.ColorRole.Highlight),
            "selected": self.palette().color(QPalette.ColorRole.Highlight),
        }
        scene.addLine(left, top, left, top + plot_height, QPen(axis_color))
        scene.addLine(left, top + plot_height, left + plot_width, top + plot_height, QPen(axis_color))
        span = maximum - minimum
        if span <= 0:
            span = 1.0
        for _, group, values in series:
            if not values:
                continue
            stride = max(1, len(values) // 500)
            indexes = list(range(0, len(values), stride))
            if indexes[-1] != len(values) - 1:
                indexes.append(len(values) - 1)
            path = QPainterPath()
            for point_index, source_index in enumerate(indexes):
                x = left + plot_width * source_index / max(len(values) - 1, 1)
                y = top + plot_height * (maximum - values[source_index]) / span
                if point_index == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            color = QColor(colors.get(group, colors["selected"]))
            color.setAlpha(145)
            scene.addPath(path, QPen(color, 1.2))
        for value, y in ((maximum, top), (minimum, top + plot_height)):
            label = scene.addText(f"{value:.1f} kW")
            label.setDefaultTextColor(text_color)
            label.setScale(0.75)
            label.setPos(0, y - 9)
        title = scene.addText("Selected scenario net load")
        title.setDefaultTextColor(text_color)
        title.setPos(left + 8, 0)
        legend = scene.addText("Green: best    Red: worst    Blue: random")
        legend.setDefaultTextColor(text_color)
        legend.setScale(0.8)
        legend.setPos(width - 300, 0)
        scene.setSceneRect(0, 0, width, height)
        widget(self, "view_scenario_plot").fitInView(
            scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio,
        )

    def fit_scenario_plots(self):
        for view_name, scene in (
            ("view_validation_plot", self.validation_scene),
            ("view_scenario_plot", self.scenario_scene),
        ):
            if scene.items():
                widget(self, view_name).fitInView(
                    scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio,
                )

    def show_stage(self, message):
        widget(self, "lbl_scenario_status").setText(message)
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        widget(self, "log_scenarios").appendPlainText(f"[{stamp}] {message}")

    def show_progress(self, snapshot):
        events, _ = snapshot
        event = next((events[name] for name in ("ARIMA", "Scenarios") if name in events), None)
        if event is not None:
            progress = widget(self, "progress_scenarios")
            progress.setRange(0, 100)
            progress.setValue(int(event.percent))
            progress.setFormat(f"{event.phase}: %p% ({event.completed}/{event.total})")
            widget(self, "lbl_scenario_status").setText(event.text())

    def set_busy(self, busy):
        for name in ("tabs_scenarios", "btn_generate_scenarios", "btn_import_scenarios",
                     "btn_close_scenarios"):
            widget(self, name).setEnabled(not busy)
        self.update_save_button()
        if busy:
            widget(self, "progress_scenarios").setRange(0, 0)

    def update_save_button(self):
        """Enable saving only after a scenario selection is ready."""
        widget(self, "btn_save_use_scenarios").setEnabled(
            self.selected is not None and not self.runner.busy,
        )

    def show_failure(self, message, details):
        self.show_stage(f"Error: {message}")
        if details:
            widget(self, "log_scenarios").appendPlainText(details)
        widget(self, "progress_scenarios").setRange(0, 100)
        widget(self, "progress_scenarios").setValue(0)

    def job_succeeded(self, result):
        if self.pending_action == "generate":
            self.generated, self.selected = result
            self.imported_path = None
            self.populate_validation(self.generated.metadata)
            self.populate_scenarios()
            widget(self, "tabs_scenarios").setCurrentWidget(widget(self, "tab_scenario_validation"))
            QTimer.singleShot(0, self.fit_scenario_plots)
            self.show_stage("Scenario generation completed; inspect validation before saving")
        elif self.pending_action == "import":
            self.selected, manifest, self.imported_path = result
            self.generated = None
            self.populate_validation(manifest.get("generation", {}))
            self.populate_scenarios()
            self.show_stage(f"Imported saved scenario set from {self.imported_path}")
            QTimer.singleShot(0, self.fit_scenario_plots)
        elif self.pending_action == "save":
            path = Path(result)
            self.study.scenarios = self.selected
            self.study.scenario_path = path
            self.session.record_scenario_set(path, {
                "generated_count": self.selected.metadata.get(
                    "source_scenario_count", len(self.selected.scenarios)),
                "selected_count": len(self.selected.scenarios),
            })
            self.show_stage(f"Saved and activated {path.name}")
            self.accept()
        widget(self, "progress_scenarios").setRange(0, 100)
        widget(self, "progress_scenarios").setValue(100)
        self.update_save_button()

    def reject(self):
        if self.runner.busy:
            self.show_stage("Wait for the current scenario job to finish")
        else:
            super().reject()

    def closeEvent(self, event):
        if self.runner.busy:
            event.ignore()
            self.show_stage("Wait for the current scenario job to finish")
        else:
            super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "validation_scene"):
            QTimer.singleShot(0, self.fit_scenario_plots)


class TimestampDialog(QDialog):
    """Choose one retained simulation step, without inventing missing hours."""
    def __init__(self, steps, selected_index=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose result timestamp")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Display one calculated hour (source clock):", self))
        self.timestamps = QComboBox(self)
        self.timestamps.setObjectName("combo_result_timestamp")
        for index, step in enumerate(steps):
            suffix = "" if step.power_flow.converged else " — NOT CONVERGED"
            self.timestamps.addItem(f"{step.timestamp}{suffix}", index)
        self.timestamps.setCurrentIndex(max(0, min(selected_index, len(steps) - 1)))
        layout.addWidget(self.timestamps)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        load_form(self, "main_window.ui")
        self.study = None
        self.session = None
        self.report = None
        self.result_index = None
        self.pending_action = ""
        self.pending_run_output = None
        self.pending_run_optimization = False
        self.runner = JobRunner(self)
        self.run_started = None
        self.run_elapsed_seconds = 0.0
        self.last_progress = 0
        self.last_stage_message = "Ready"
        self.show_full_result_details = False
        self.last_worker_update = perf_counter()
        self.last_progress_log = 0.0
        self.last_heartbeat = 0.0
        self.run_clock = QTimer(self)
        self.run_clock.setInterval(500)
        self.run_clock.timeout.connect(self.update_run_clock)
        self.settings_dialog = SettingsDialog(self)
        self.load_dialog = LoadDataDialog(self)
        self.scene = NetworkScene(self)
        view = widget(self, "network_view")
        view.setScene(self.scene)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.add_network_controls()
        widget(self, "run_log").setMaximumBlockCount(5000)
        self.connect_events()
        self.set_busy(False)

    def add_network_controls(self):
        self.diagram_status = widget(self, "lbl_diagram_timestamp")
        self.diagram_status.hide()
        widget(self, "group_bus_details").hide()
        widget(self, "lbl_line_details").setTextFormat(Qt.TextFormat.PlainText)
        widget(self, "group_bus_details").layout().setRowVisible(widget(self, "lbl_line_details"), False)
        for name, action in (("btn_fit_network", "fit"), ("btn_zoom_in", "zoom_in"),
                             ("btn_zoom_out", "zoom_out")):
            control = widget(self, name)
            control.setIcon(network_icon(action, self.palette()))
            control.setIconSize(QSize(20, 20))
            control.setFixedSize(36, 32)
        widget(self, "btn_rotate_network").setMaximumWidth(60)
        widget(self, "chk_network_properties").toggled.connect(self.update_network_layers)
        widget(self, "chk_network_results").toggled.connect(self.toggle_network_results)
        widget(self, "btn_result_timestamp").clicked.connect(self.choose_result_timestamp)
        widget(self, "btn_rotate_network").clicked.connect(self.rotate_network)
        widget(self, "chk_hide_diagram").toggled.connect(self.hide_diagram)
        widget(self, "chk_bus_details").toggled.connect(self.show_bus_details)
        widget(self, "btn_clear_results").clicked.connect(self.clear_results)
        widget(self, "btn_clear_workspace").clicked.connect(self.clear_workspace)
        self.resize_fit_timer = QTimer(self)
        self.resize_fit_timer.setSingleShot(True)
        self.resize_fit_timer.setInterval(80)
        self.resize_fit_timer.timeout.connect(self.fit_network)
        widget(self, "chk_show_log").toggled.connect(self.schedule_network_fit)
        widget(self, "tabs_workspace").currentChanged.connect(self.schedule_network_fit)
        widget(self, "btn_result_details").clicked.connect(self.toggle_result_details)

    def schedule_network_fit(self):
        self.resize_fit_timer.start()

    def update_network_layers(self):
        self.refresh_network()
        self.fit_network()

    def show_bus_details(self, visible):
        widget(self, "group_bus_details").setVisible(visible)
        QTimer.singleShot(0, self.fit_network)

    def simulation_steps(self):
        if self.report and isinstance(self.report.result, TimeSeriesSimulationResult):
            return self.report.result.steps
        return []

    def selected_step(self):
        steps = self.simulation_steps()
        if steps:
            index = self.result_index if self.result_index is not None else len(steps) - 1
            return steps[index] if 0 <= index < len(steps) else None
        return None

    def refresh_network(self):
        if self.study is None:
            return
        values = self.settings_dialog.committed
        bess_bus = values["bess_bus"] if values["group_manual_bess"] else None
        bess_ratings = (values["spin_bess_power_kw"], values["spin_bess_energy_kwh"]) if bess_bus is not None else None
        if self.report and isinstance(self.report.result, OptimizationResult) and self.report.result.best_candidate:
            candidate = self.report.result.best_candidate
            bess_bus = candidate.bus_id
            bess_ratings = candidate.power_rating_kw, candidate.energy_capacity_kwh
        step = self.selected_step() if widget(self, "chk_network_results").isChecked() else None
        self.scene.draw_network(
            self.study.network, bounds=(values["spin_voltage_min_pu"], values["spin_voltage_max_pu"]),
            bess_bus=bess_bus, show_properties=widget(self, "chk_network_properties").isChecked(),
            step=step, bess_ratings=bess_ratings)
        if step is None:
            self.diagram_status.setText("Result labels hidden" if self.simulation_steps() else "No retained hourly simulation results")
        else:
            state = "converged" if step.power_flow.converged else "NOT CONVERGED — calculated labels suppressed"
            self.diagram_status.setText(f"Source clock: {step.timestamp} — {state}; BESS + discharge / − charge; line P/Q source-rooted")
        self.diagram_status.setVisible(step is not None)

    def rotate_network(self):
        if self.study is None or self.runner.busy:
            return
        self.scene.turns = (self.scene.turns + 1) % 4
        self.refresh_network()
        self.fit_network()

    def arrange_network_view(self):
        """Automatically choose the initial view on a newly loaded study only."""
        if self.study is None or self.runner.busy:
            return
        self.scene.branch_sides.clear()
        self.scene.turns = 0
        self.refresh_network()
        rect = self.scene.sceneRect()
        view = widget(self, "network_view").viewport()
        normal = min(view.width() / rect.width(), view.height() / rect.height())
        rotated = min(view.width() / rect.height(), view.height() / rect.width())
        if rotated > normal:
            self.scene.turns = 1
            self.refresh_network()
        self.fit_network()

    def toggle_network_results(self, checked):
        if checked:
            if not self.choose_result_timestamp():
                control = widget(self, "chk_network_results")
                control.blockSignals(True)
                control.setChecked(False)
                control.blockSignals(False)
        self.refresh_network()
        self.fit_network()
        self.set_busy(self.runner.busy)

    def choose_result_timestamp(self):
        steps = self.simulation_steps()
        if not steps or self.runner.busy:
            self.statusBar().showMessage("Run Simulation first; optimization summaries do not retain hourly network results.")
            return False
        index = self.result_index if self.result_index is not None else len(steps) - 1
        dialog = TimestampDialog(steps, index, self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        if accepted:
            self.result_index = dialog.timestamps.currentData()
            self.refresh_network()
            self.refresh_selection_details()
        dialog.deleteLater()
        return accepted

    def hide_diagram(self, hidden):
        widget(self, "network_view").setVisible(not hidden)
        if not hidden:
            self.schedule_network_fit()

    def clear_results(self):
        if self.runner.busy:
            return
        self.invalidate_results("Calculated results cleared; loaded inputs retained.")
        self.refresh_network()
        self.set_busy(False)

    def clear_workspace(self):
        if self.runner.busy or self.load_dialog.runner.busy:
            return
        answer = QMessageBox.question(self, "Clear workspace?",
                                      "Discard loaded inputs, calculated results, settings and layout overrides?\nSource files and exported folders will NOT be deleted.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.study = None
        self.session = None
        self.pending_action = ""
        self.invalidate_results("Workspace cleared; source files and exports were not deleted.")
        self.run_elapsed_seconds = 0.0
        self.update_run_clock()
        self.scene.clear()
        self.scene.bus_items.clear()
        self.scene.line_items.clear()
        self.scene.layout = None
        self.scene.branch_sides.clear()
        self.scene.turns = 0
        self.settings_dialog.deleteLater()
        self.load_dialog.deleteLater()
        self.settings_dialog = SettingsDialog(self)
        self.settings_dialog.applied.connect(self.settings_applied)
        self.load_dialog = LoadDataDialog(self)
        widget(self, "chk_network_properties").setChecked(False)
        widget(self, "chk_hide_diagram").setChecked(False)
        widget(self, "chk_bus_details").setChecked(False)
        widget(self, "lbl_data_status").setText("No data loaded")
        self.last_stage_message = "Ready"
        self.diagram_status.setText("No hourly result selected")
        self.set_busy(False)

    def connect_events(self):
        widget(self, "btn_load_data").clicked.connect(self.load_data)
        widget(self, "btn_scenarios").clicked.connect(self.open_scenarios)
        widget(self, "btn_settings").clicked.connect(self.open_settings)
        widget(self, "btn_run_simulation").clicked.connect(self.run_simulation)
        widget(self, "btn_run_base_case").clicked.connect(self.run_base_case)
        widget(self, "btn_run_optimization").clicked.connect(self.run_optimization)
        widget(self, "btn_zoom_in").clicked.connect(self.zoom_in)
        widget(self, "btn_zoom_out").clicked.connect(self.zoom_out)
        widget(self, "btn_fit_network").clicked.connect(self.fit_network)
        self.settings_dialog.applied.connect(self.settings_applied)
        self.runner.busy_changed.connect(self.set_busy)
        self.runner.stage.connect(self.show_stage)
        self.runner.progress.connect(self.show_progress)
        self.runner.succeeded.connect(self.job_succeeded)
        self.runner.failed.connect(self.show_failure)
        self.scene.bus_selected.connect(self.show_bus)
        self.scene.line_selected.connect(self.show_line)

    def load_data(self):
        if self.load_dialog.exec() == QDialog.DialogCode.Accepted:
            next_study = self.load_dialog.study
            new_session = (self.session is None
                           or study_fingerprint(next_study) != self.session.manifest["fingerprint"])
            if new_session:
                self.session = StudySession.create(
                    next_study, REPO / "07_Implementation" / "Results",
                )
            elif self.study is not None:
                next_study.scenarios = self.study.scenarios
                next_study.scenario_path = self.study.scenario_path
            self.study = next_study
            self.settings_dialog.set_network(self.study.network)
            self.invalidate_results("New data loaded; previous results cleared.")
            self.scene.branch_sides.clear()
            self.arrange_network_view()
            widget(self, "lbl_data_status").setText(
                f"{len(self.study.network.buses)} buses; {len(self.study.profiles.timestamps)} hourly steps\n"
                f"Load: {self.study.request.load_source}; PV: {self.study.request.pv_source}\n"
                f"Session: {self.session.root.name}")
            self.set_busy(False)

    def open_scenarios(self):
        if self.study is None or self.session is None or self.runner.busy:
            return
        dialog = ScenarioGeneratorDialog(self.study, self.session, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.invalidate_results("Active scenario set changed; previous results cleared.")
            widget(self, "lbl_data_status").setText(
                f"{len(self.study.network.buses)} buses; {len(self.study.profiles.timestamps)} hourly steps\n"
                f"Load: {self.study.request.load_source}; PV: {self.study.request.pv_source}\n"
                f"Session: {self.session.root.name}; scenarios: {len(self.study.scenarios.scenarios)}"
            )
        dialog.deleteLater()

    def open_settings(self):
        self.settings_dialog.restore_values()
        self.settings_dialog.exec()

    def settings_applied(self, settings):
        self.invalidate_results("Settings applied; previous results cleared.")
        if self.study:
            self.refresh_network()

    def invalidate_results(self, message):
        self.last_progress = 0
        self.show_full_result_details = False
        widget(self, "progress_run").setFormat("%p%")
        self.report = None
        self.runner.result = None
        self.result_index = None
        control = widget(self, "chk_network_results")
        control.blockSignals(True)
        control.setChecked(False)
        control.blockSignals(False)
        widget(self, "results_text").setPlainText(message)
        widget(self, "btn_result_details").setText("Show full details")
        for name in ("lbl_bus_id", "lbl_bus_voltage", "lbl_bus_load", "lbl_bus_pv"):
            widget(self, name).setText("Not selected / not calculated")
        widget(self, "lbl_line_details").clear()
        self.show_detail_rows(False)
        widget(self, "group_bus_details").setTitle("Selected Element")
        widget(self, "btn_result_details").setEnabled(False)
        self.append_log(message)
        self.set_busy(self.runner.busy)

    def run_simulation(self):
        self.start_run(False)

    def run_optimization(self):
        self.start_run(True)

    def run_base_case(self):
        if self.study is None or self.runner.busy:
            return
        try:
            self.settings_dialog.restore_values()
            settings = self.settings_dialog.read_settings(optimization=False)
            self.pending_action = "run"
            self.pending_base_case = True
            self.pending_run_optimization = False
            self.pending_run_output = self.session.next_path("base_case", "run")
            self.invalidate_results("Static base-case FBS started; earlier results cleared.")
            self.run_started = perf_counter()
            self.last_worker_update = self.run_started
            self.last_progress_log = self.run_started
            self.last_heartbeat = self.run_started
            self.run_elapsed_seconds = 0.0
            self.run_clock.start()
            self.runner.start(partial(run_base_case_and_export, deepcopy(self.study), deepcopy(settings), self.pending_run_output))
        except ValueError as error:
            self.show_failure(str(error), "")

    def start_run(self, optimization):
        if self.study is None or self.runner.busy:
            return
        self.pending_action = ""
        self.pending_base_case = False
        try:
            self.settings_dialog.restore_values()
            settings = self.settings_dialog.read_settings(optimization=optimization)
            self.pending_action = "run"
            self.statusBar().clearMessage()
            self.last_progress = 0
            self.invalidate_results("Run started; earlier results cleared.")
            self.refresh_network()
            self.run_started = perf_counter()
            self.last_worker_update = self.run_started
            self.last_progress_log = self.run_started
            self.last_heartbeat = self.run_started
            self.run_elapsed_seconds = 0.0
            self.run_clock.start()
            self.update_run_clock()
            self.pending_run_optimization = optimization
            self.pending_run_output = self.session.next_run_path(optimization)
            self.runner.start(partial(
                run_and_export, deepcopy(self.study), deepcopy(settings), optimization,
                self.pending_run_output,
            ))
        except ValueError as error:
            self.show_failure(str(error), "")

    def set_busy(self, busy):
        for name in ("btn_load_data", "btn_settings"):
            widget(self, name).setEnabled(not busy)
        widget(self, "btn_scenarios").setEnabled(self.study is not None and not busy)
        for name in ("btn_run_simulation", "btn_run_base_case", "btn_run_optimization", "btn_zoom_in", "btn_zoom_out", "btn_fit_network"):
            widget(self, name).setEnabled(self.study is not None and not busy)
        for name in ("chk_network_properties", "chk_hide_diagram", "chk_bus_details", "btn_rotate_network"):
            widget(self, name).setEnabled(self.study is not None and not busy)
        widget(self, "chk_network_results").setEnabled(bool(self.simulation_steps()) and not busy)
        widget(self, "btn_result_timestamp").setEnabled(
            bool(self.simulation_steps()) and widget(self, "chk_network_results").isChecked() and not busy)
        widget(self, "btn_clear_results").setEnabled(self.report is not None and not busy)
        widget(self, "btn_clear_workspace").setEnabled(not busy)
        widget(self, "btn_result_details").setEnabled(self.report is not None and not busy)
        progress = widget(self, "progress_run")
        progress.setRange(0, 0 if busy else 100)
        if not busy:
            progress.setValue(100 if self.report is not None else self.last_progress)

    def show_stage(self, message):
        self.last_worker_update = perf_counter()
        self.last_stage_message = message
        if self.runner.busy:
            widget(self, "progress_run").setRange(0, 0)
        self.append_log(message)

    def append_log(self, message):
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        widget(self, "run_log").appendPlainText(f"[{stamp}] {message}")
        if self.session is not None:
            self.session.append_log(message)

    def update_run_clock(self):
        now = perf_counter()
        if self.run_started is not None:
            self.run_elapsed_seconds = now - self.run_started
        widget(self, "lbl_run_elapsed").setText(f"Elapsed {format_duration(self.run_elapsed_seconds)}")
        if self.run_started is not None and now - self.last_worker_update >= 15 and now - self.last_heartbeat >= 15:
            self.append_log(f"No worker counter update for {int(now - self.last_worker_update)} s; last reported: {self.last_stage_message}; elapsed {format_duration(self.run_elapsed_seconds)}")
            self.last_heartbeat = now

    def finish_run_clock(self):
        self.update_run_clock()
        self.run_clock.stop()
        self.run_started = None

    def show_progress(self, snapshot):
        events, boundary = snapshot
        self.last_worker_update = perf_counter()
        primary = next((events[name] for name in ("GWO", "ARIMA", "Scenarios", "Simulation") if name in events), None)
        if primary is not None:
            bar = widget(self, "progress_run")
            bar.setRange(0, 100)
            self.last_progress = int(primary.percent)
            bar.setValue(self.last_progress)
            bar.setFormat(f"{primary.phase}: %p% ({primary.completed}/{primary.total})")
        details = " | ".join(event.text() for event in events.values())
        self.last_stage_message = details
        if boundary or perf_counter() - self.last_progress_log >= 10:
            self.append_log(f"Elapsed {format_duration(self.run_elapsed_seconds)} | {details}")
            self.last_progress_log = perf_counter()

    def show_failure(self, message, details):
        if self.pending_action == "run":
            self.finish_run_clock()
            widget(self, "results_text").setPlainText(f"Run failed after {format_duration(self.run_elapsed_seconds)}\n{message}")
        self.show_stage(f"Error: {message}")
        if details:
            self.append_log(details)
        self.statusBar().showMessage(message)

    def job_succeeded(self, result):
        if self.pending_action == "run":
            self.finish_run_clock()
            self.report = result
            if self.pending_run_output is not None and self.session is not None:
                if getattr(self, "pending_base_case", False):
                    self.session.record_base_case(self.pending_run_output)
                else:
                    self.session.record_run(
                        self.pending_run_output, self.pending_run_optimization,
                    )
                self.append_log(f"Run files saved in {self.pending_run_output}")
            self.show_full_result_details = False
            widget(self, "results_text").setPlainText(result.summary())
            widget(self, "btn_result_details").setText("Show full details")
            widget(self, "tabs_workspace").setCurrentIndex(1)
            self.result_index = len(self.simulation_steps()) - 1 if self.simulation_steps() else None
            self.refresh_network()
            if isinstance(result.result, OptimizationResult) and result.result.best_candidate:
                self.append_log(f"Optimized BESS placed at bus {result.result.best_candidate.bus_id}")
            self.show_stage(f"Run finished in {format_duration(self.run_elapsed_seconds)}; inspect convergence, feasibility and shedding in Results")
        self.last_progress = 100
        self.set_busy(self.runner.busy)
        widget(self, "progress_run").setValue(100)
        widget(self, "progress_run").setFormat("Completed: %p%")

    def toggle_result_details(self):
        if self.report is None or self.runner.busy:
            return
        self.show_full_result_details = not self.show_full_result_details
        widget(self, "results_text").setPlainText(
            self.report.summary(detailed=self.show_full_result_details))
        widget(self, "btn_result_details").setText(
            "Show summary" if self.show_full_result_details else "Show full details")

    def zoom_in(self):
        widget(self, "network_view").zoom_by(1.25)

    def zoom_out(self):
        widget(self, "network_view").zoom_by(0.8)

    def fit_network(self):
        if self.study is None or not self.scene.items() or widget(self, "network_view").isHidden():
            return
        widget(self, "network_view").fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "resize_fit_timer"):
            self.resize_fit_timer.start()

    def show_bus(self, bus_id):
        if self.study is None:
            return
        self.show_detail_rows(False)
        widget(self, "group_bus_details").setTitle(f"Bus B{bus_id}")
        network = self.study.network
        widget(self, "lbl_bus_id").setText(f"B{bus_id}")
        last = self.selected_step()
        if last:
            prefix = "" if last.power_flow.converged else "Diagnostic only: "
            widget(self, "lbl_bus_voltage").setText(f"{prefix}{last.power_flow.voltage_mag_pu[bus_id]:.5f} pu at {last.timestamp}")
            point = last.operating_point
            load_text = f"{point.p_load_kw[bus_id]:g} kW / {point.q_load_kvar[bus_id]:g} kvar at {last.timestamp}"
            pv_text = f"{point.p_pv_kw[bus_id]:g} kW at {last.timestamp}"
        else:
            widget(self, "lbl_bus_voltage").setText("Not calculated; optimizer retains summary metrics, not hourly bus voltages")
            load_text = f"{sum(load.p_base_kw for load in network.loads if load.bus_id == bus_id):g} kW / {sum(load.q_base_kvar for load in network.loads if load.bus_id == bus_id):g} kvar (base)"
            pv_text = f"{sum(unit.p_rated_kw for unit in network.pv_units if unit.bus_id == bus_id):g} kW (installed rating)"
        widget(self, "lbl_bus_load").setText(load_text)
        widget(self, "lbl_bus_pv").setText(pv_text)

    def show_detail_rows(self, line_selected):
        layout = widget(self, "group_bus_details").layout()
        for name in ("lbl_bus_id", "lbl_bus_voltage", "lbl_bus_load", "lbl_bus_pv"):
            layout.setRowVisible(widget(self, name), not line_selected)
        layout.setRowVisible(widget(self, "lbl_line_details"), line_selected)

    def refresh_selection_details(self):
        selected = self.scene.selectedItems()
        if selected:
            item = selected[0]
            if item.data(1) == "bus":
                self.show_bus(item.data(0))
            elif item.data(1) == "line":
                self.show_line(item.data(2))

    def show_line(self, line_id):
        if self.study is None:
            return
        network = self.study.network
        line = next((item for item in network.lines if item.line_id == line_id), None)
        if line is None:
            return
        order = network.radial_order()
        child = next(bus for bus, name in order.parent_line_by_bus.items() if name == line_id)
        parent = order.parent_bus_by_bus[child]
        lines = [f"{line_id}: {parent} → {child} (source-rooted sending direction)",
                 f"R {line.r_ohm:g} Ω; X {line.x_ohm:g} Ω"]
        step = self.selected_step()
        if step is None:
            lines.append("Not calculated: run Simulation for hourly line results.")
        elif not step.power_flow.converged:
            lines.append(f"{step.timestamp}: NOT CONVERGED — line results unavailable")
        else:
            flow = step.power_flow
            lines.extend((f"{step.timestamp} (source clock)",
                          f"P {flow.branch_p_kw[line_id]:.3f} kW; Q {flow.branch_q_kvar[line_id]:.3f} kvar; I {flow.branch_current_a[line_id]:.3f} A",
                          f"Loss {flow.line_loss_p_kw[line_id]:.4f} kW / {flow.line_loss_q_kvar[line_id]:.4f} kvar"))
        self.show_detail_rows(True)
        widget(self, "group_bus_details").setTitle(f"Line {line_id}")
        widget(self, "lbl_line_details").setText("\n".join(lines))

    def closeEvent(self, event):
        if self.runner.busy or self.load_dialog.runner.busy:
            event.ignore()
            self.statusBar().showMessage("A job is running. Wait for completion; cancellation is not implemented.")
        else:
            super().closeEvent(event)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
