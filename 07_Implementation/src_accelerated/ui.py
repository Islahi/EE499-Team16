"""Designer-backed PySide6 desktop; see README_ui.md for launch and inputs."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from functools import partial
from pathlib import Path
import os
import sys
import traceback
import json
from math import isfinite
import pandas as pd
from time import perf_counter

from PySide6.QtCore import QDateTime, QDir, QFile, QIODevice, QLocale, QObject, QSize, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QColor, QDoubleValidator, QIcon, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QGraphicsScene, QHeaderView, QAbstractItemView,
    QGroupBox, QInputDialog, QLabel, QLineEdit, QListWidgetItem, QTextEdit, QMainWindow, QMessageBox,
    QPushButton, QSizePolicy, QSpinBox, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .bess import BESSConfig
from .fbs import FBSConfig, warm_numba
from .metrics import EconomicConfig, validate_annual_inputs
from .network_diagram import NetworkScene, NetworkView
from .network_loader import load_network
from .optimizer import BESSParameters, OptimizationResult
from .simulation import GridAwareDispatchPolicy, SimulationConfig, TimeSeriesSimulationResult
from .forecasting import ForecastConfig, generate_forecast
from .study_session import _write_profile
from .progress import StageReporter, format_duration
from .ui_presentation import compact_summary
from .ui_bindings import restore_designer_combo_data
from .study_session import StudySession, study_fingerprint, migrate_inputs
from .distributed_dataset import discover_cases, summary_pv_ratings
from .pv_model import read_nasa_csv
from .ui_workflow import (
    BaseCaseReport, DataRequest, RunSettings, prepare_study, run_and_export,
    first_calendar_year, run_base_case_and_export, size_catalog,
)


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
    loader.setWorkingDirectory(QDir(str(ASSETS)))  # Resolve Qt Designer SVG paths.
    try:
        if loader.load(source) is None:
            raise RuntimeError(f"Cannot load {filename}: {loader.errorString()}")
    finally:
        source.close()
    # QUiLoader can show a ComboBox item's text while discarding its .ui userData.
    # These identifiers remain authored in Designer; only the semantic bridge
    # is restored here, before any dialog captures settings or connects events.
    restore_designer_combo_data(ASSETS / filename,
                                lambda name: root.findChild(QComboBox, name))
    root.setStyleSheet((ASSETS / "theme.qss").read_text(encoding="utf-8").replace("@ASSET@",ASSETS.as_posix()))


def widget(root, name):
    result = root.findChild(QWidget, name)
    if result is None:
        raise RuntimeError(f"Missing Designer object {name!r} in {root.objectName()}")
    return result


def set_status(label, text, state="info"):
    """Consistent, accessible status feedback across the existing dialogs."""
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setText(text)
    label.setProperty("state", state)
    label.style().unpolish(label)
    label.style().polish(label)



class Worker(QObject):
    stage = Signal(str)
    progress = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str, str)
    finished = Signal()
    hourly_log = Signal(object)

    def __init__(self, task, log_hours=False):
        super().__init__()
        self.task = task
        self.log_hours = log_hours

    @Slot()
    def run(self):
        reporter = StageReporter(self.stage.emit, self.progress.emit,
                                 hourly_log=self.hourly_log.emit if self.log_hours else None)
        try:
            result = self.task(reporter)
            reporter.flush()
            self.succeeded.emit(result)
        except Exception as error:
            # Boundary catch: restore UI state and retain unexpected error details.
            reporter.flush()
            self.failed.emit(str(error), traceback.format_exc())
        finally:
            self.finished.emit()


class JobRunner(QObject):
    stage = Signal(str)
    progress = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str, str)
    busy_changed = Signal(bool)
    hourly_log = Signal(object)

    def __init__(self, parent):
        super().__init__(parent)
        self.thread = None
        self.worker = None
        self.result = None
        self.failure = None

    @property
    def busy(self):
        return self.thread is not None

    def start(self, task, *, log_hours=False):
        if self.busy:
            raise RuntimeError("A job is already running")
        self.result, self.failure = None, None
        self.thread = QThread(self)
        self.worker = Worker(task, log_hours)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.stage.connect(self.stage)
        self.worker.progress.connect(self.progress)
        self.worker.hourly_log.connect(self.hourly_log)
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
    solar_csv_modes = ("nasa_power", "open_meteo", "prepared", "power")

    def __init__(self, parent=None):
        super().__init__(parent)
        load_form(self, "load_data_dialog.ui")
        self.runner = JobRunner(self)
        self.study = None
        self.pending_action = ""
        self.preview_network = None
        self.preview_path = None
        self.ratings_seed = ()
        self.preselected_metadata = {}
        for name in ("edit_network_path", "edit_pv_source_path", "edit_load_path"):
            widget(self, name).setReadOnly(True)
        # Imported load timestamps determine the full simulation interval.
        widget(self, "group_study_period").hide()
        widget(self, "combo_load_source").setCurrentIndex(1)
        widget(self, "combo_load_source").setEnabled(False)
        widget(self, "group_synthetic_load").hide()
        for name in ("lbl_load_method",):
            control = self.findChild(QLabel, name)
            if control is not None:
                control.hide()
        table = widget(self,"table_pv_installations")
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().hide()
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for name,low,high in (("edit_site_latitude",-90.,90.),("edit_site_longitude",-180.,180.),("edit_reference_capacity",0.,1e9)):
            validator = QDoubleValidator(low,high,6,self)
            validator.setNotation(QDoubleValidator.Notation.StandardNotation)
            validator.setLocale(QLocale.c())
            widget(self,name).setValidator(validator)
        buttons = widget(self,"buttons_load_data")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Prepare study")
        self.connect_events()
        self.update_modes()

    def connect_events(self):
        widget(self, "btn_browse_network").clicked.connect(self.browse_network)
        widget(self, "btn_browse_pv_source").clicked.connect(self.browse_pv)
        widget(self, "btn_browse_load").clicked.connect(self.browse_load)
        widget(self, "btn_load_network").clicked.connect(self.load_network_preview)
        widget(self, "edit_network_path").textChanged.connect(self.update_network_button)
        widget(self, "combo_pv_source").currentIndexChanged.connect(self.update_modes)
        widget(self, "chk_no_pv").toggled.connect(self.update_modes)
        widget(self, "chk_pv_fallback").toggled.connect(self.update_modes)
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
        path, _ = QFileDialog.getOpenFileName(self, "Historical solar source", str(REPO), "CSV files (*.csv)")
        if path:
            widget(self, "edit_pv_source_path").setText(path)
            if widget(self,"combo_pv_source").currentData()=="nasa_power":
                try:
                    _,metadata = read_nasa_csv(path)
                    if metadata.get("source_clock"):
                        widget(self,"edit_solar_clock").setText(metadata["source_clock"])
                    if "latitude" in metadata and "longitude" in metadata:
                        widget(self,"lbl_pv_status").setText(
                            f"CSV location detected: latitude {metadata['latitude']:g}°, longitude {metadata['longitude']:g}°. "
                            "Coordinates are read from this file; confirm its source clock below.")
                except ValueError as error:
                    self.show_failure(str(error),"")

    def browse_load(self):
        path = QFileDialog.getExistingDirectory(self,"GoiEner case or multi-case parent folder",str(REPO))
        if path:
            try:
                cases = discover_cases(path)
                if len(cases)>1:
                    chosen,ok = QInputDialog.getItem(self,"Select GoiEner case","Case",[p.name for p in cases],0,False)
                    if not ok: return
                    path = str(next(p for p in cases if p.name==chosen))
                else:
                    path = str(cases[0])
                widget(self,"edit_load_path").setText(path)
                self.populate_folder_metadata()
            except (ValueError,OSError) as error:
                self.show_failure(str(error), "")

    def pv_rows(self):
        table = widget(self, "table_pv_installations")
        rows = [[table.item(row, col).text().strip() if table.item(row, col) else ""
                 for col in (0, 1)] for row in range(table.rowCount())]
        return tuple(tuple(row) for row in rows if any(row))

    def populate_folder_metadata(self):
        folder = Path(widget(self,"edit_load_path").text())
        manifest = folder / "manifest.json"
        meta = json.loads(manifest.read_text(encoding="utf-8-sig")) if manifest.is_file() else {}
        reference = meta.get("pv_reference") or {}
        site = meta.get("site") or reference.get("site") or {}
        for name,value in (("edit_site_latitude",site.get("latitude",meta.get("site_lat"))),
                           ("edit_site_longitude",site.get("longitude",meta.get("site_lon"))),
                           ("edit_source_clock",meta.get("clock",meta.get("timezone"))),
                           ("edit_reference_capacity",reference.get("capacity_kw"))):
            control = widget(self, name)
            previous = self.preselected_metadata.get(name, "")
            if control.text().strip() == previous:
                next_value = "" if value is None else str(value)
                control.setText(next_value)
                self.preselected_metadata[name] = next_value
        conflicts = ""
        summary = folder/"bus_summary.csv"
        network = self.preview_network if self.preview_path == widget(self, "edit_network_path").text() else None
        ids = {b.bus_id for b in network.buses} if network else None
        folder_ratings = summary_pv_ratings(pd.read_csv(summary), ids) if manifest.is_file() and summary.is_file() else {}
        workbook_ratings = {}
        if network:
            for unit in network.pv_units:
                workbook_ratings[unit.bus_id] = workbook_ratings.get(unit.bus_id, 0.) + unit.p_rated_kw
            workbook_ratings = {bus: kw for bus, kw in workbook_ratings.items() if kw > 0}
        existing = self.pv_rows()
        if existing == self.ratings_seed:
            # Replace only suggestions. Workbook and edited ratings take precedence.
            seed = workbook_ratings or folder_ratings
            table = widget(self, "table_pv_installations")
            table.setRowCount(max(1, len(seed)))
            table.clearContents()
            for row, (bus, rating) in enumerate(sorted(seed.items())):
                table.setItem(row, 0, QTableWidgetItem(str(bus)))
                table.setItem(row, 1, QTableWidgetItem(str(rating)))
            self.ratings_seed = self.pv_rows()
        if folder_ratings and (workbook_ratings or existing != self.ratings_seed) and folder_ratings != workbook_ratings:
            conflicts = f" Folder ratings {folder_ratings} differ from the workbook or edited table. Review or edit the final table to choose the installed ratings."
        if not manifest.is_file():
            return
        hours = meta.get("hours")
        coverage = f"{int(hours):,} hourly observations" if isinstance(hours,(int,float)) else "Hourly dataset found"
        widget(self,"lbl_load_status").setText(f"{folder.name} · {coverage}")
        placeholder = "placeholder" in str(meta.get("pv_status","")).lower()
        pv_text = ("The dataset contains a zero-PV placeholder. Enable Use fallback solar source if PV is installed."
                   if placeholder else "Dataset PV history will be checked during preparation.")
        widget(self,"lbl_pv_status").setText(pv_text+conflicts)
        widget(self,"lbl_pv_status").setToolTip(str(meta.get("pv_status",""))+conflicts)
        set_status(widget(self,"lbl_load_validation"),"Dataset selected. Review the clock and final PV capacities, then choose Prepare study.",
                   "warning" if conflicts else "info")

    def update_network_button(self):
        widget(self, "btn_load_network").setEnabled(bool(widget(self, "edit_network_path").text()) and not self.runner.busy)

    def solar_source_mode(self):
        if widget(self, "chk_no_pv").isChecked():
            return "none"
        if widget(self, "chk_pv_fallback").isChecked():
            return widget(self, "combo_pv_source").currentData()
        return "dataset"

    def update_modes(self):
        mode = self.solar_source_mode()
        manual = mode in self.solar_csv_modes
        installed = mode != "none"
        fallback = installed and mode != "dataset"
        widget(self, "chk_pv_fallback").setVisible(installed)
        widget(self, "panel_pv_source_fields").setVisible(fallback)
        widget(self, "panel_pv_source_fields").setEnabled(fallback)
        for name in ("edit_reference_capacity", "lbl_edit_reference_capacity"):
            widget(self, name).setVisible(fallback)
        for name in ("panel_pv_source_file","label_5","edit_solar_clock","lbl_edit_solar_clock"):
            widget(self,name).setVisible(manual)
        for name in ("edit_site_latitude","edit_site_longitude","lbl_edit_site_latitude","lbl_edit_site_longitude"):
            widget(self,name).setVisible(installed)
        for name in ("group_pv_conversion","group_solar_metadata"):
            widget(self,name).setVisible(installed)
            widget(self,name).setEnabled(installed)
        widget(self,"edit_solar_clock").setEnabled(manual)
        widget(self,"panel_irradiance_fields").setVisible(fallback and mode != "power")
        widget(self,"edit_reference_capacity").setPlaceholderText(
            "Enter the modeled profile nameplate" if mode == "power" else "Defaults to total installed PV kW")
        widget(self,"panel_load_import").setEnabled(True)
        if not installed:
            message = "No PV study: no solar source or site metadata is required."
        elif not fallback:
            message = "Using PV history from the study folder. Enable Use fallback solar source if you need a CSV or provider."
        elif manual:
            message = ("If the dataset has no valid PV history, supply historical modeled electrical kW, reference kW, site and file clock."
                       if mode == "power" else "If the dataset has no valid PV history, supply a historical irradiance CSV and its source clock. Review the site coordinates.")
        else:
            message = "Validated dataset PV is used when available. Otherwise the selected provider retrieves historical irradiance for this site if PV is installed."
        widget(self,"lbl_pv_status").setText(message)


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
        format_name = ("auto", "project", "reference")[widget(self, "combo_network_format").currentIndex()]
        return Path(path), frequency or None, format_name

    def load_network_preview(self):
        try:
            path, frequency, format_name = self.network_arguments()
            def task(stage):
                stage("Reading network workbook")
                return load_network(path, workbook_format=format_name, frequency_hz=frequency)
            self.pending_action = "network"
            self.preview_path = str(path)
            self.runner.start(task)
        except (ValueError, OSError) as error:
            self.show_failure(str(error), "")

    def read_request(self):
        path, frequency, format_name = self.network_arguments()
        ratings = {}
        mode = self.solar_source_mode()
        for row, cells in enumerate(self.pv_rows() if mode != "none" else ()):
            try:
                bus, rating = int(cells[0]), float(cells[1])
            except ValueError as error:
                raise ValueError(f"PV row {row + 1}: supply an integer bus ID and numeric kW") from error
            if bus in ratings:
                raise ValueError(f"Duplicate PV bus {bus}; enter one total rating per bus")
            if not isfinite(rating) or rating < 0:
                raise ValueError(f"PV row {row + 1}: enter finite nonnegative kW")
            ratings[bus] = rating

        pv_path = widget(self, "edit_pv_source_path").text().strip()
        manual = mode in self.solar_csv_modes
        reference_capacity = widget(self, "edit_reference_capacity").text().strip() if mode not in ("none", "dataset") else ""
        load_path = widget(self, "edit_load_path").text().strip()
        if not load_path:
            raise ValueError("Choose a GoiEner case or multi-case output folder")
        return DataRequest(
            network_path=path, frequency_hz=frequency, workbook_format=format_name,
            start=None, months=None,
            pv_source=mode, pv_path=Path(pv_path) if manual and pv_path else None,
            pv_ratings_kw=ratings, critical_irradiance=widget(self, "spin_critical_irradiance").value(),
            standard_irradiance=widget(self, "spin_standard_irradiance").value(),
            load_source="distributed", dataset_folder=Path(load_path), pv_override=self.pv_rows() != self.ratings_seed,
            pv_rating_selection="Edited PV table" if self.pv_rows() != self.ratings_seed else "",
            latitude=float(widget(self,"edit_site_latitude").text()) if mode != "none" and widget(self,"edit_site_latitude").text().strip() else None,
            longitude=float(widget(self,"edit_site_longitude").text()) if mode != "none" and widget(self,"edit_site_longitude").text().strip() else None,
            clock=widget(self,"edit_source_clock").text().strip() or None,
            solar_source_clock=(widget(self,"edit_solar_clock").text().strip() or None) if manual else None,
            reference_capacity_kw=float(reference_capacity) if reference_capacity else None,
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
        set_status(widget(self, "lbl_load_validation"),message,"error")
        widget(self, "lbl_load_validation").setToolTip(details)

    def job_succeeded(self, result):
        if self.pending_action == "prepare":
            self.study = result
            set_status(widget(self,"lbl_load_validation"),"Data prepared and validated","success")
            widget(self,"lbl_load_validation").setToolTip("")
            self.accept()
            return
        widget(self, "lbl_network_summary").setText(
            f"{len(result.buses)} buses, {len(result.lines)} lines; slack {result.slack_bus_id()}; "
            f"base load {sum(load.p_base_kw for load in result.loads):g} kW; frequency {result.frequency_hz:g} Hz")
        self.preview_network = result
        widget(self, "lbl_load_validation").setText("Network inspected. Configure PV and load, then choose Prepare study.")
        try:
            self.populate_folder_metadata()
        except (ValueError, OSError) as error:
            self.show_failure(str(error), "")

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
        self.connect_designer_settings()
        self.committed = self.capture_values()
        buttons = widget(self, "buttons_settings")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save settings")
        buttons.accepted.connect(self.accept_settings)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply_settings)
        widget(self, "combo_dispatch_policy").currentIndexChanged.connect(self.update_dispatch)
        widget(self, "combo_terminal_policy").currentIndexChanged.connect(self.update_optional_controls)
        self.engine_ready = False
        self.jit_metadata = None
        self.jit_runner = JobRunner(self)
        self.jit_runner.succeeded.connect(self.numba_ready)
        self.jit_runner.failed.connect(self.numba_failed)
        QTimer.singleShot(0, lambda: self.jit_runner.start(lambda stage: warm_numba()))
        self.update_dispatch()
        self.update_compute_status()
        self.update_algorithm_controls()
        self.update_optional_controls()

    def connect_designer_settings(self):
        """Attach behavior to controls declared in settings_dialog.ui.

        Permanent widgets, labels, tooltips and styling are owned by Qt Designer.
        Only live values and conditional visibility are controlled here.
        """
        widget(self, "btn_select_all_buses").clicked.connect(self.select_all_allowed_buses)
        widget(self, "btn_clear_allowed_buses").clicked.connect(self.clear_allowed_buses)
        widget(self, "list_allowed_buses").itemSelectionChanged.connect(self.update_allowed_bus_count)
        widget(self, "combo_optimizer_algorithm").currentIndexChanged.connect(self.update_algorithm_controls)
        for name in ("group_manual_bess","group_reserve","group_import_limit","group_export_limit","group_economic_inputs","group_terminal_soc"):
            widget(self,name).toggled.connect(self.update_optional_controls)
        # A CPU-dependent value is runtime data, not a visual layout change.
        workers = widget(self, "spin_cpu_workers")
        workers.setMaximum(max(1, os.cpu_count() or 1))
        workers.setValue(max(1, (os.cpu_count() or 1) - 1))

    def update_algorithm_controls(self, *args):
        """Collapse inactive rows while keeping both methods in the same form."""
        ga = widget(self,"combo_optimizer_algorithm").currentData() == "GA"
        form = widget(self,"group_ga_settings").layout()
        for name in ("spin_gwo_population","spin_gwo_iterations"):
            form.setRowVisible(widget(self,name),not ga)
        for name in ("spin_ga_population","spin_ga_generations","spin_ga_crossover","spin_ga_mutation"):
            form.setRowVisible(widget(self,name),ga)
        compute = widget(self,"group_compute_backend").layout()
        compute.setRowVisible(widget(self,"spin_cpu_workers"),not ga)

    def update_optional_controls(self, *args):
        for name in ("group_manual_bess","group_reserve","group_import_limit","group_export_limit","group_economic_inputs","group_terminal_soc"):
            group = widget(self,name)
            form = group.layout()
            for row in range(form.rowCount()):
                form.setRowVisible(row,group.isChecked())
            group.setProperty("collapsed",not group.isChecked())
            group.style().unpolish(group)
            group.style().polish(group)
        economic_group = widget(self, "group_economic_inputs")
        economic_group.layout().setRowVisible(widget(self, "spin_terminal_energy_price"),
            economic_group.isChecked() and widget(self, "combo_terminal_policy").currentData() == "priced_energy")


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
        widget(self,"lbl_compute_status").setVisible(True)
        set_status(widget(self,"lbl_compute_status"),"FBS — Numba (CPU) ready" if self.engine_ready else "Preparing the Numba solver. You can continue reviewing settings.",
                   "success" if self.engine_ready else "busy")
        buttons = widget(self,"buttons_settings")
        for button in (QDialogButtonBox.StandardButton.Ok,QDialogButtonBox.StandardButton.Apply):
            buttons.button(button).setEnabled(self.engine_ready)

    def numba_ready(self, metadata):
        self.engine_ready = True
        self.jit_metadata = metadata
        self.update_compute_status()

    def numba_failed(self, message, details):
        self.engine_ready = False
        set_status(widget(self,"lbl_compute_status"),message,"error")
        for button in (QDialogButtonBox.StandardButton.Ok,QDialogButtonBox.StandardButton.Apply):
            widget(self,"buttons_settings").button(button).setEnabled(False)
        widget(self,"lbl_compute_status").setToolTip(details)


    def update_dispatch(self):
        mode = widget(self, "combo_dispatch_policy").currentIndex()
        details = ("Grid-aware: charge from surplus PV and discharge against demand/import caps; no tariff arbitrage."
                   if mode == 1 else "Idle diagnostic mode: no scheduled charge/discharge request.")
        widget(self, "lbl_dispatch_status").setText(details)
        widget(self, "combo_dispatch_policy").setToolTip(details)

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
        values["compute_backend"] = "numba"
        values["numba_readiness"] = getattr(self,"jit_metadata",None)
        values["chk_tariffs_confirmed"] = widget(self,"chk_tariffs_confirmed").isChecked()
        values["optimizer_algorithm"] = widget(self, "combo_optimizer_algorithm").currentData()
        values["terminal_policy"] = widget(self, "combo_terminal_policy").currentData()
        return values

    def restore_values(self):
        for name, value in self.committed.items():
            control = self.findChild(QWidget, name)
            if isinstance(control, (QSpinBox, QDoubleSpinBox)):
                control.setValue(value)
            elif isinstance(control, QGroupBox):
                control.setChecked(value)
            elif isinstance(control,QCheckBox):
                control.setChecked(value)
        widget(self, "edit_currency").setText(self.committed["edit_currency"])
        combo = widget(self, "combo_bess_bus")
        combo.setCurrentIndex(combo.findData(self.committed["bess_bus"]))
        choices = widget(self, "list_allowed_buses")
        for index in range(choices.count()):
            item = choices.item(index)
            item.setSelected(item.data(Qt.ItemDataRole.UserRole) in self.committed["allowed_buses"])
        widget(self, "combo_dispatch_policy").setCurrentIndex(self.committed["dispatch_mode"])
        algorithm = widget(self, "combo_optimizer_algorithm")
        algorithm.setCurrentIndex(max(0, algorithm.findData(self.committed["optimizer_algorithm"])))
        widget(self,"chk_tariffs_confirmed").setChecked(self.committed.get("chk_tariffs_confirmed",False))
        terminal = widget(self, "combo_terminal_policy")
        terminal.setCurrentIndex(max(0, terminal.findData(self.committed.get("terminal_policy", "equal_soc"))))
        self.update_optional_controls()
        self.update_dispatch()
        self.update_compute_status()
        self.update_algorithm_controls()
        self.update_optional_controls()

    def set_network(self, network):
        previous_network = self.network
        self.network = network
        # On initial load, choose eligible installation buses automatically.
        # Do not override a user's explicit Clear action on the same network.
        if previous_network is None and not self.committed["allowed_buses"]:
            self.committed["allowed_buses"] = tuple(
                bus.bus_id for bus in network.buses if not bus.is_slack)
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
        if not self.engine_ready:
            raise ValueError("Mandatory Numba solver is not ready: "+widget(self,"lbl_compute_status").text())
        simulation = SimulationConfig(
            voltage_min_pu=values["spin_voltage_min_pu"], voltage_max_pu=values["spin_voltage_max_pu"],
            reserve_fraction=values["spin_reserve_percent"] / 100 if values["group_reserve"] else 0,
            reserve_duration_hours=values["spin_reserve_hours"],
            grid_import_limit_kw=values["spin_import_limit_kw"] if values["group_import_limit"] else None,
            grid_export_limit_kw=values["spin_export_limit_kw"] if values["group_export_limit"] else None,
            terminal_soc_tolerance=(values["spin_terminal_soc_percent"] / 100
                                    if values["group_terminal_soc"] else None),
            allow_pv_curtailment=values["chk_allow_curtailment"], allow_load_shedding=values["chk_allow_shedding"],
            fbs_config=FBSConfig())
        terminal_policy = values["terminal_policy"] if values["group_economic_inputs"] else "equal_soc"
        economics = EconomicConfig(
            values["spin_cost_per_kwh"] if values["group_economic_inputs"] else None,
            values["spin_cost_per_kw"] if values["group_economic_inputs"] else None,
            values["edit_currency"], discount_rate=values["spin_discount_rate"] / 100,
            lifetime_years=int(values["spin_bess_lifetime"]),
            annual_om_fraction=values["spin_annual_om_percent"] / 100,
            curtailment_penalty_per_kwh=values["spin_curtailment_penalty"],
            shedding_penalty_per_kwh=values["spin_shedding_penalty"],
            grid_import_tariff_per_kwh=values["spin_grid_import_tariff"] if values["chk_tariffs_confirmed"] else None,
            grid_export_tariff_per_kwh=values["spin_grid_export_tariff"] if values["chk_tariffs_confirmed"] else None,
            fixed_installation_cost=values["spin_fixed_cost"],
            terminal_policy=terminal_policy,
            terminal_energy_price_per_kwh=(values["spin_terminal_energy_price"] if terminal_policy == "priced_energy" else None))
        dispatch = (GridAwareDispatchPolicy(simulation.grid_import_limit_kw,
                                            simulation.grid_export_limit_kw)
                    if values["dispatch_mode"] == 1 else None)
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
                raise ValueError("Optimization requires active dispatch and both economic cost coefficients")
            if economics.grid_import_tariff_per_kwh is None or economics.grid_export_tariff_per_kwh is None:
                raise ValueError("Enter import/export tariffs and confirm the explicit values before economic optimization")
            if not values["allowed_buses"]:
                raise ValueError("Select allowed battery buses")
            for quantity, unit in (("power", "kw"), ("energy", "kwh")):
                try:
                    size_catalog(*(values[f"spin_opt_{quantity}_{field}_{unit}"]
                                   for field in ("min", "max", "step")))
                except ValueError as error:
                    label = "power (kW)" if quantity == "power" else "energy capacity (kWh)"
                    raise ValueError(f"Set a valid battery {label} minimum, maximum and step in Settings. {error}") from error
        return RunSettings(simulation, economics, battery, values, dispatch)

    def apply_settings(self):
        try:
            settings = self.read_settings()
            self.committed = settings.values
            set_status(widget(self,"lbl_settings_validation"),"Settings saved. The next run will use these values.","success")
            self.applied.emit(settings)
            return True
        except ValueError as error:
            set_status(widget(self,"lbl_settings_validation"),str(error),"error")
            return False

    def accept_settings(self):
        if self.apply_settings():
            self.accept()

    def reject(self):
        self.restore_values()
        super().reject()


class ForecastDialog(QDialog):
    """Minimal forecasting window; produces deterministic hourly CSV inputs."""
    def __init__(self, study, session, parent=None):
        super().__init__(parent)
        self.study, self.session = study, session
        load_form(self, "forecast_dialog.ui")
        self.method = widget(self, "combo_forecast_method")
        self.horizon = widget(self, "spin_forecast_horizon")
        self.train_start = widget(self,"date_training_start")
        self.train_end = widget(self,"date_training_end")
        self.origin = widget(self,"date_forecast_origin")
        history = study.historical_profiles or study.profiles
        self.history_times = pd.DatetimeIndex(history.timestamps)
        self.train_start.setDateTime(QDateTime(pd.Timestamp(history.timestamps[0]).to_pydatetime()))
        self.train_end.setDateTime(QDateTime(pd.Timestamp(history.timestamps[-1]).to_pydatetime()))
        self.origin.setDateTime(QDateTime((pd.Timestamp(history.timestamps[-1])+pd.Timedelta(hours=1)).to_pydatetime()))
        self.train_end.dateTimeChanged.connect(self.training_end_changed)
        self.origin.dateTimeChanged.connect(self.origin_changed)
        widget(self,"combo_horizon_preset").currentIndexChanged.connect(self.change_horizon)
        self.method.setEnabled(False)
        self.status = widget(self, "lbl_forecast_status")
        self.generate_button = widget(self, "btn_generate_forecast")
        self.generate_button.clicked.connect(self.start_forecast)
        widget(self, "btn_cancel_forecast").clicked.connect(self.reject)
        self.runner = JobRunner(self)
        self.runner.succeeded.connect(self.forecast_ready)
        self.runner.failed.connect(self.forecast_failed)
        self.runner.busy_changed.connect(self.forecast_busy)
        self.train_start.dateTimeChanged.connect(self.update_training_status)
        self.train_end.dateTimeChanged.connect(self.update_training_status)
        self.horizon.valueChanged.connect(self.update_training_status)
        self.horizon.valueChanged.connect(self.sync_horizon_preset)
        first,last = pd.Timestamp(history.timestamps[0]),pd.Timestamp(history.timestamps[-1])
        widget(self,"lbl_forecast_coverage").setText(f"Available history · {len(history.timestamps):,} hours · {first:%d %b %Y} to {last:%d %b %Y}")
        for control in (self.train_start,self.train_end):
            control.setMinimumDateTime(QDateTime(first.to_pydatetime()))
            control.setMaximumDateTime(QDateTime(last.to_pydatetime()))
        self.origin.setMinimumDateTime(QDateTime((first+pd.Timedelta(hours=1)).to_pydatetime()))
        self.origin.setMaximumDateTime(QDateTime((last+pd.Timedelta(hours=1)).to_pydatetime()))
        self.update_training_status()

    def training_end_changed(self, dt):
        self.origin.blockSignals(True)
        self.origin.setDateTime(dt.addSecs(3600))
        self.origin.blockSignals(False)
        if hasattr(self,"runner"): self.update_training_status()

    def origin_changed(self, dt):
        self.train_end.setDateTime(dt.addSecs(-3600))
        expected = self.train_end.dateTime().addSecs(3600)
        if self.origin.dateTime() != expected:
            self.origin.blockSignals(True)
            self.origin.setDateTime(expected)
            self.origin.blockSignals(False)
        if hasattr(self,"runner"): self.update_training_status()

    def update_training_status(self, *args):
        if self.runner.busy: return
        hours = self.train_start.dateTime().secsTo(self.train_end.dateTime())//3600+1
        aligned = (pd.Timestamp(self.train_start.dateTime().toPython()) in self.history_times and
                   pd.Timestamp(self.train_end.dateTime().toPython()) in self.history_times)
        valid = aligned and hours >= 8760
        self.generate_button.setEnabled(valid)
        if not aligned:
            set_status(self.status,"Choose exact hourly observations from the imported history.","warning")
        elif valid:
            set_status(self.status,f"Ready · {hours:,} training hours → {self.horizon.value():,} forecast hours. Historical data is retained.","success")
        else:
            set_status(self.status,f"Select at least one year of hourly history (8,760 hours). Current selection: {max(0,hours):,} hours.","warning")

    def forecast_busy(self, busy):
        for name in ("combo_horizon_preset","spin_forecast_horizon","date_training_start","date_training_end","date_forecast_origin","btn_cancel_forecast"):
            widget(self,name).setEnabled(not busy)
        self.generate_button.setText("Generating…" if busy else "Generate forecast")
        self.generate_button.setEnabled(not busy)

    def start_forecast(self):
        if self.runner.busy:
            return
        try:
            method = self.method.currentData()
            if method is None:
                raise ValueError("Forecast model has no backend identifier; reopen the dialog")
            cfg = ForecastConfig(horizon_hours=self.horizon.value(),
                                 training_start=self.train_start.dateTime().toPython(),
                                 training_end=self.train_end.dateTime().toPython(),
                                 forecast_start=self.origin.dateTime().toPython(),
                                 method=method)
        except ValueError as error:
            self.forecast_failed(str(error), "")
            return
        history = self.study.historical_profiles or self.study.profiles
        self.generate_button.setEnabled(False)
        set_status(self.status,"Training the sector models and preparing the common PV forecast, when installed…","busy")
        self.runner.start(lambda stage: generate_forecast(history, cfg, assignments=self.study.assignments,
            network=self.study.network,pv_reference=self.study.pv_reference))

    def sync_horizon_preset(self, value):
        preset = widget(self,"combo_horizon_preset")
        preset.blockSignals(True)
        index = preset.findData(str(value))
        preset.setCurrentIndex(index if index>=0 else preset.findData("0"))
        preset.blockSignals(False)

    def change_horizon(self):
        value = widget(self,"combo_horizon_preset").currentData()
        if int(value or 0)>0: self.horizon.setValue(int(value))

    def forecast_failed(self, message, details):
        set_status(self.status,f"Forecast failed: {message}","error")
        self.generate_button.setEnabled(True)
        QMessageBox.warning(self, "Forecast error", message)

    def forecast_ready(self, report):
        try:
            forecast_root = self.session.root / "forecasts"
            forecast_root.mkdir(exist_ok=True)
            output = forecast_root / datetime.now().strftime("forecast_%Y%m%d_%H%M%S_%f")
            output.mkdir(exist_ok=False)
            _write_profile(output / "load_profile.csv", report.profiles.timestamps,
                           report.profiles.load_p_kw, report.profiles.load_q_kvar)
            _write_profile(output / "pv_profile.csv", report.profiles.timestamps,
                           report.profiles.pv_p_kw, report.profiles.pv_q_kvar)
            history = self.study.historical_profiles or self.study.profiles
            self.study.historical_profiles = history
            self.study.forecast_profiles = report.profiles
            self.study.select_source("forecast")
            self.study.forecast_info = {"model": report.model_info, "validation_scores": report.scores,
                                        "training_ends": str(report.historical_end),
                                        "forecast_hours": report.horizon_hours,
                                        "output_folder": str(output)}
            pd.DataFrame({"timestamp":report.profiles.timestamps,**report.sector_predictions}).to_csv(output/"sector_predictions.csv",index=False)
            pd.DataFrame({"timestamp":report.profiles.timestamps,"capacity_factor":report.pv_capacity_factor}).to_csv(output/"pv_reference_forecast.csv",index=False)
            self.session.manifest.setdefault("forecast_runs", []).append(self.study.forecast_info)
            self.session.save()
            self.accept()
        except Exception as error:
            self.forecast_failed(str(error), "")

    def reject(self):
        if self.runner.busy:
            self.status.setText("Forecast is running; closing will be available when it finishes.")
            return
        super().reject()

    def closeEvent(self, event):
        if self.runner.busy:
            event.ignore()
        else:
            super().closeEvent(event)


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


class SimulationInputDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent)
        load_form(self,"simulation_input_dialog.ui")
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)



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
        self.input_dialog = SimulationInputDialog(self)
        self.scene = NetworkScene(self)
        view = widget(self, "network_view")
        view.setScene(self.scene)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Toolbar, icons and view layout are defined in main_window.ui.
        self.add_network_controls()
        widget(self, "run_log").setMaximumBlockCount(5000)
        self.connect_events()
        self.connect_source_events()
        self.connect_solver_status()
        self.set_busy(False)

    def connect_solver_status(self):
        self.settings_dialog.jit_runner.succeeded.connect(lambda *_: self.set_busy(self.runner.busy))
        self.settings_dialog.jit_runner.failed.connect(lambda *_: self.set_busy(self.runner.busy))

    def open_input_window(self):
        if self.runner.busy: return
        if self.study is not None: self.sync_time_controls()
        else: self.update_interval_state()
        self.input_dialog.exec()

    def connect_source_events(self):
        widget(self,"combo_simulation_source").currentIndexChanged.connect(self.preview_source_window)
        widget(self,"combo_history_window").currentIndexChanged.connect(self.preview_source_window)
        widget(self,"btn_apply_simulation_window").clicked.connect(self.apply_source_window)
        widget(self,"btn_browse_history").clicked.connect(self.browse_history)
        widget(self,"btn_empty_import").clicked.connect(self.load_data)
        widget(self,"btn_input_window").clicked.connect(self.open_input_window)
        for name in ("date_simulation_start","date_simulation_end"):
            widget(self,name).dateTimeChanged.connect(self.update_interval_state)

    def sync_time_controls(self):
        if self.study is None: return
        combo = widget(self,"combo_simulation_source")
        combo.blockSignals(True)
        combo.setCurrentIndex(combo.findData(self.study.input_mode))
        combo.blockSignals(False)
        widget(self,"date_simulation_start").setDateTime(QDateTime(pd.Timestamp(self.study.profiles.timestamps[0]).to_pydatetime()))
        widget(self,"date_simulation_end").setDateTime(QDateTime((pd.Timestamp(self.study.profiles.timestamps[-1])+pd.Timedelta(hours=1)).to_pydatetime()))
        # Match the preset to the applied range when reopening the dialog.
        start = pd.Timestamp(self.study.profiles.timestamps[0])
        end = pd.Timestamp(self.study.profiles.timestamps[-1])+pd.Timedelta(hours=1)
        raw = self.study.historical_profiles if self.study.input_mode == "historical" else self.study.forecast_profiles
        preset = "-1"
        if raw is not None:
            if (start, end) == first_calendar_year(raw.timestamps):
                preset = "8760"
            elif start == pd.Timestamp(raw.timestamps[0]):
                hours = len(self.study.profiles.timestamps)
                if hours in (24,168,720): preset = str(hours)
                elif hours == len(raw.timestamps): preset = "0"
        window = widget(self,"combo_history_window")
        window.blockSignals(True)
        window.setCurrentIndex(window.findData(preset))
        window.blockSignals(False)
        self.update_interval_state()

    def preview_source_window(self):
        if self.study is None: return
        mode = widget(self,"combo_simulation_source").currentData()
        raw = self.study.historical_profiles if mode=="historical" else self.study.forecast_profiles
        if raw is None:
            widget(self,"lbl_active_source").setText("Generate forecast before selecting this source; active source unchanged")
            return
        preset = int(widget(self,"combo_history_window").currentData() or 0)
        if preset<0:
            self.update_interval_state()
            return
        a = pd.Timestamp(raw.timestamps[0])
        b = pd.Timestamp(raw.timestamps[-1])+pd.Timedelta(hours=1)
        if preset == 8760:
            window = first_calendar_year(raw.timestamps)
            if window is None:
                widget(self,"btn_apply_simulation_window").setEnabled(False)
                widget(self,"lbl_active_source").setText(
                    "This source has no complete January-to-January year. Select a different source, extend the forecast, or choose a shorter simulation interval.")
                return
            a,b = window
        elif preset: b = min(b,a+pd.Timedelta(hours=preset))
        widget(self,"date_simulation_start").setDateTime(QDateTime(a.to_pydatetime()))
        widget(self,"date_simulation_end").setDateTime(QDateTime(b.to_pydatetime()))
        self.update_interval_state()

    def update_interval_state(self, *args):
        has_study = self.study is not None
        available = has_study and not self.runner.busy
        mode = widget(self,"combo_simulation_source").currentData()
        for name in ("combo_simulation_source","date_simulation_start","date_simulation_end"):
            widget(self,name).setEnabled(available)
        widget(self,"combo_history_window").setEnabled(available)
        model = widget(self,"combo_simulation_source").model()
        model.item(1).setEnabled(has_study and self.study.forecast_profiles is not None)
        button = widget(self,"btn_apply_simulation_window")
        if not has_study:
            for name in ("date_simulation_start","date_simulation_end"):
                control = widget(self,name)
                control.blockSignals(True)
                control.setSpecialValueText("Import data first")
                control.setDateTime(control.minimumDateTime())
                control.blockSignals(False)
            button.setEnabled(False)
            widget(self,"lbl_active_source").setText("Import a dataset to select a simulation interval. Full history is kept for forecasting.")
            return
        times = self.study.profiles.timestamps
        start,end = pd.Timestamp(times[0]),pd.Timestamp(times[-1])+pd.Timedelta(hours=1)
        pending = (mode != self.study.input_mode or
            pd.Timestamp(widget(self,"date_simulation_start").dateTime().toPython()) != start or
            pd.Timestamp(widget(self,"date_simulation_end").dateTime().toPython()) != end)
        button.setEnabled(available and pending)
        title = "Historical data" if self.study.input_mode=="historical" else "Generated forecast"
        clock = self.study.context.get("Clock", "source clock")
        summary = f"{title} · {len(times):,} hours · {start:%d %b %Y, %H:%M} → {end:%d %b %Y, %H:%M} · {clock}"
        if pending: summary += "  —  New selection not applied"
        widget(self,"lbl_active_source").setText(summary)

    def apply_source_window(self):
        if self.study is None or self.runner.busy: return
        try:
            self.study.select_source(widget(self,"combo_simulation_source").currentData(),
                widget(self,"date_simulation_start").dateTime().toPython(),widget(self,"date_simulation_end").dateTime().toPython())
            self.sync_time_controls()
            self.invalidate_results("Simulation source/interval changed; full raw history retained")
        except ValueError as error:
            self.show_failure(str(error),"")

    def browse_history(self):
        if self.runner.busy: return
        path = QFileDialog.getExistingDirectory(self,"Select saved study folder",str(REPO))
        if not path: return
        try:
            historical = StudySession.open_read_only(path)
            dialog = QDialog(self)
            dialog.setWindowTitle("Historical study — read-only")
            layout = QVBoxLayout(dialog)
            text = QTextEdit(dialog);text.setReadOnly(True);text.setPlainText(historical.history_text());layout.addWidget(text)
            migrate = QPushButton("Migrate compatible inputs to a new study ID",dialog);layout.addWidget(migrate)
            def create_new():
                if QMessageBox.question(dialog,"Create new study","Copy compatible inputs to a new study with Numba and approved forecasts? Historical outputs remain read-only.") != QMessageBox.StandardButton.Yes: return
                try:
                    self.study,self.session = migrate_inputs(historical,Path(__file__).resolve().parent/"Results")
                    self.settings_dialog.set_network(self.study.network)
                    self.sync_time_controls();self.invalidate_results("Inputs migrated to new study ID; configure economics anew")
                    self.arrange_network_view();self.set_busy(False);dialog.accept()
                except Exception as error:
                    QMessageBox.warning(dialog,"Migration blocked",str(error))
            migrate.clicked.connect(create_new)
            dialog.resize(850,600);dialog.exec();dialog.deleteLater()
        except (ValueError,OSError,KeyError) as error:
            self.show_failure(str(error),"")

    def add_network_controls(self):
        self.diagram_status = widget(self, "lbl_diagram_timestamp")
        self.diagram_status.hide()
        widget(self, "group_bus_details").hide()
        widget(self, "lbl_line_details").setTextFormat(Qt.TextFormat.PlainText)
        widget(self, "group_bus_details").layout().setRowVisible(widget(self, "lbl_line_details"), False)
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
        widget(self, "chk_show_log").toggled.connect(self.scroll_log_to_latest)
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
        if isinstance(self.report, BaseCaseReport):
            return [self.report.step]
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
            self.diagram_status.setText("Result labels hidden" if self.simulation_steps() else "No retained network results")
        else:
            state = "converged" if step.power_flow.converged else "NOT CONVERGED — calculated labels suppressed"
            self.diagram_status.setText(f"{step.timestamp} — {state}; BESS + discharge / − charge; line P/Q source-rooted")
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
            self.statusBar().showMessage("Run Simulation or Base-Case FBS first; optimization summaries do not retain network results.")
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
        if self.runner.busy or self.load_dialog.runner.busy or self.settings_dialog.jit_runner.busy:
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
        self.connect_solver_status()
        self.settings_dialog.applied.connect(self.settings_applied)
        self.load_dialog = LoadDataDialog(self)
        widget(self, "chk_network_properties").setChecked(False)
        widget(self, "chk_hide_diagram").setChecked(False)
        widget(self, "chk_bus_details").setChecked(False)
        self.last_stage_message = "Ready"
        self.diagram_status.setText("No hourly result selected")
        self.set_busy(False)

    def connect_events(self):
        widget(self, "btn_load_data").clicked.connect(self.load_data)
        widget(self, "btn_scenarios").clicked.connect(self.open_forecasting)
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
        self.runner.hourly_log.connect(self.append_log_lines)
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
                    next_study, Path(__file__).resolve().parent / "Results",
                )

            self.study = next_study
            self.settings_dialog.set_network(self.study.network)
            self.sync_time_controls()
            self.invalidate_results("New data loaded; previous results cleared.")
            self.scene.branch_sides.clear()
            self.arrange_network_view()
            self.append_log(
                f"Study loaded: {len(self.study.network.buses)} buses; "
                f"{len(self.study.profiles.timestamps)} hourly steps\n"
                f"Load: {self.study.request.load_source}; PV: {self.study.request.pv_source}\n"
                f"Session: {self.session.root.name}")
            self.set_busy(False)

    def open_forecasting(self):
        if self.study is None or self.session is None or self.runner.busy:
            return
        dialog = ForecastDialog(self.study, self.session, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.sync_time_controls()
            self.invalidate_results("Forecast profiles selected; previous results cleared.")
            self.append_log(
                f"Forecast selected: {len(self.study.network.buses)} buses; "
                f"{len(self.study.profiles.timestamps)} hourly steps\n"
                f"Session: {self.session.root.name}")
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

    def optimization_settings(self):
        times = self.study.profiles.timestamps
        start = pd.Timestamp(times[0])
        end = pd.Timestamp(times[-1]) + pd.Timedelta(hours=1)
        if (start, end) != first_calendar_year(times):
            raise ValueError(
                f"Active interval: {start:%d %b %Y %H:%M} to {end:%d %b %Y %H:%M} (end excluded). "
                "Choose Study interval → Full calendar year → Apply interval. "
                "If the forecast lacks a full January-to-January year, use historical data or extend the forecast."
            )
        settings = self.settings_dialog.read_settings(optimization=True)
        validate_annual_inputs(times, settings.economics, self.study.profiles.dt_hours)
        return settings

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
            settings = self.optimization_settings() if optimization else self.settings_dialog.read_settings()
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
            self.pending_run_provenance = {"input_mode":self.study.input_mode,"simulation_window":self.study.simulation_window,
                "solver":asdict(settings.simulation.fbs_config),"economics":asdict(settings.economics),"controls":settings.values}
            self.pending_run_optimization = optimization
            self.pending_run_output = self.session.next_run_path(optimization)
            self.runner.start(partial(
                run_and_export, self.study, deepcopy(settings), optimization,
                self.pending_run_output,
            ), log_hours=not optimization)
        except ValueError as error:
            self.show_failure(str(error), "")

    def set_busy(self, busy):
        widget(self,"group_simulation_source").setEnabled(not busy)
        widget(self,"btn_input_window").setEnabled(not busy)
        ready = self.settings_dialog.engine_ready
        set_status(widget(self,"lbl_engine_status"),"FBS Numba · Ready" if ready else
            "Solver unavailable" if self.settings_dialog.jit_runner.failure else "Preparing solver…",
            "success" if ready else "error" if self.settings_dialog.jit_runner.failure else "busy")
        widget(self,"lbl_engine_status").setToolTip(widget(self.settings_dialog,"lbl_compute_status").text())
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
        for name in ("btn_run_simulation","btn_run_base_case"):
            widget(self,name).setEnabled(self.study is not None and ready and not busy)
        economic_reason = "Import a study to configure annual economic optimization."
        annual_ready = False
        if self.study is not None and ready:
            try:
                self.optimization_settings()
                annual_ready = True
                economic_reason = "Compare battery options and the no-storage baseline using annual cost."
            except ValueError as error:
                economic_reason = "Annual optimization: "+str(error)
        widget(self,"btn_run_optimization").setEnabled(annual_ready and not busy)
        widget(self,"btn_run_optimization").setToolTip(economic_reason)
        widget(self,"btn_run_optimization").setStatusTip(economic_reason)
        widget(self,"btn_empty_import").setEnabled(not busy)
        widget(self,"panel_empty_state").setVisible(self.study is None)
        widget(self,"network_view").setVisible(self.study is not None and not widget(self,"chk_hide_diagram").isChecked())
        widget(self,"btn_clear_workspace").setEnabled(not busy and not self.settings_dialog.jit_runner.busy)
        self.update_interval_state()
        if self.study is not None and not busy:
            self.schedule_network_fit()
        progress = widget(self, "progress_run")
        progress.setRange(0, 0 if busy else 100)
        if not busy:
            progress.setValue(100 if self.report is not None else self.last_progress)

    def show_stage(self, message):
        self.last_worker_update = perf_counter()
        self.last_stage_message = message
        self.logged_progress_phase = None
        if self.runner.busy:
            widget(self, "progress_run").setRange(0, 0)
        self.append_log(message)

    def append_log(self, message):
        self.append_log_lines((message,))

    def append_log_lines(self, messages):
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        widget(self, "run_log").appendPlainText("\n".join(f"[{stamp}] {message}" for message in messages))
        self.scroll_log_to_latest()
        if self.session is not None:
            self.session.append_log_lines(messages)

    def scroll_log_to_latest(self):
        scroll = widget(self, "run_log").verticalScrollBar()
        scroll.setValue(scroll.maximum())

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
        primary = next((events[name] for name in ("GWO", "GA", "Simulation", "Base case") if name in events), None)
        if primary is not None:
            bar = widget(self, "progress_run")
            bar.setRange(0, 100)
            self.last_progress = int(primary.percent)
            bar.setValue(self.last_progress)
            bar.setFormat(f"{primary.phase}: %p% ({primary.completed}/{primary.total})")
        details = " | ".join(event.text() for event in events.values())
        self.last_stage_message = details
        phase = primary.phase if primary is not None else next(iter(events),None)
        if boundary or phase != getattr(self,"logged_progress_phase",None) or perf_counter() - self.last_progress_log >= 1:
            self.append_log(f"Elapsed {format_duration(self.run_elapsed_seconds)} | {details}")
            self.last_progress_log = perf_counter()
            self.logged_progress_phase = phase

    def show_failure(self, message, details):
        if self.pending_action == "run":
            self.finish_run_clock()
            if self.session is not None and self.pending_run_output is not None:
                self.session.record_failure(self.pending_run_output,"base_case" if getattr(self,"pending_base_case",False) else
                    "optimization" if self.pending_run_optimization else "simulation",message,getattr(self,"pending_run_provenance",None))
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
                        self.pending_run_output, self.pending_run_optimization, self.report,
                    )
                self.append_log(f"Run files saved in {self.pending_run_output}")
            self.show_full_result_details = False
            widget(self, "results_text").setPlainText(compact_summary(result))
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
            (self.report.summary(detailed=True) if self.show_full_result_details
             else compact_summary(self.report)))
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
        if self.runner.busy or self.load_dialog.runner.busy or self.settings_dialog.jit_runner.busy:
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
