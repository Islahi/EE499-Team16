"""Designer-backed PySide6 desktop; see README_ui.md for launch and inputs."""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime
from functools import partial
import logging
from pathlib import Path
import sys
import traceback
import json
from math import isfinite
import pandas as pd
from time import perf_counter

from PySide6.QtCore import QDateTime, QDir, QFile, QIODevice, QObject, QSize, QThread, QTimer, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QKeySequence, QPainter, QPainterPath, QPalette, QPen, QShortcut
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QGraphicsScene, QHeaderView, QAbstractItemView,
    QGroupBox, QInputDialog, QLabel, QLineEdit, QListWidgetItem, QPlainTextEdit, QTextEdit, QMainWindow, QMenu, QMessageBox,
    QPushButton, QSizePolicy, QSpinBox, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .electrical_details import battery_ratings
from .manual_fleet import manual_rows, positive, row_number, validate_manual_fleet
from .app_log import configure_desktop_log, desktop_log
from .fbs import FBSConfig, warm_numba
from .ga_fleet_policy import ga_fleet_limit
from .metrics import EconomicConfig, validate_annual_inputs
from .model_information import model_information, settings_information, study_information
from .information_provenance import display_detail, provenance_records
from .network_diagram import NetworkScene, NetworkView
from .network_loader import load_network
from .optimizer import BESSParameters, OptimizationBounds, OptimizationResult
from .simulation import ConstraintAwareDispatch, SimulationConfig, TimeSeriesSimulationResult
from .forecasting import ForecastConfig
from .progress import (RUN_HEARTBEAT_SECONDS, RUN_LOG_INTERVAL_SECONDS, RunCancelled,
                       StageReporter, format_duration)
from .ui_presentation import compact_summary
from .ui_bindings import restore_designer_combo_data
from .study_session import StudySession, study_fingerprint, migrate_inputs
from .study_setup import open_study_setup, save_study_setup
from .distributed_dataset import discover_cases, summary_pv_ratings
from .pv_model import read_nasa_csv
from .approved_methodology import (
    CURRENCY, FIXED_WIDGET_SETTINGS,
    PV_CRITICAL_IRRADIANCE_W_M2, PV_STANDARD_IRRADIANCE_W_M2,
    SYNTHETIC_SEED, FORECAST_METHOD,
    read_manifest_assumptions,
)
from .planning_policy import (DEFAULT_DISPATCH_EFFICIENCY, DEFAULT_DISPATCH_HORIZON_HOURS,
                              DEFAULT_MINIMUM_DISCHARGE_PF, desktop_worker_limit, joint_search_policy, effective_joint_search)
from .ui_workflow import (
    BaseCaseReport, DataRequest, RunSettings, prepare_study, run_and_export, regenerate_saved_dashboard,
    effective_simulation, first_calendar_year, forecast_and_export, run_base_case_and_export, size_catalog,
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
    cancelled = Signal()
    finished = Signal()
    hourly_log = Signal(object)

    def __init__(self, task, log_hours=False):
        super().__init__()
        self.task = task
        self.log_hours = log_hours

    @Slot()
    def run(self):
        reporter = StageReporter(self.stage.emit, self.progress.emit,
                                 hourly_log=self.hourly_log.emit if self.log_hours else None,
                                 cancelled=QThread.currentThread().isInterruptionRequested)
        try:
            result = self.task(reporter)
            reporter.flush()
            self.succeeded.emit(result)
        except RunCancelled:
            reporter.flush()
            self.cancelled.emit()
        except Exception as error:
            # Boundary catch: restore UI state and retain unexpected error details.
            reporter.flush()
            self.failed.emit(f"{reporter.last_stage} | {type(error).__name__}: {error}",
                             traceback.format_exc())
        finally:
            self.finished.emit()


class JobRunner(QObject):
    stage = Signal(str)
    progress = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str, str)
    cancelled = Signal()
    busy_changed = Signal(bool)
    hourly_log = Signal(object)

    def __init__(self, parent):
        super().__init__(parent)
        self.thread = None
        self.worker = None
        self.result = None
        self.failure = None
        self.was_cancelled = False

    @property
    def busy(self):
        return self.thread is not None

    def start(self, task, *, log_hours=False):
        if self.busy:
            raise RuntimeError("A job is already running")
        self.result, self.failure = None, None
        self.was_cancelled = False
        self.thread = QThread(self)
        self.worker = Worker(task, log_hours)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.stage.connect(self.stage)
        self.worker.progress.connect(self.progress)
        self.worker.hourly_log.connect(self.hourly_log)
        # Store the Python result before termination; the GUI receives the
        # final notification after the QThread has actually exited.
        self.worker.succeeded.connect(self.store_result, Qt.ConnectionType.DirectConnection)
        self.worker.failed.connect(self.store_failure, Qt.ConnectionType.DirectConnection)
        self.worker.cancelled.connect(self.store_cancelled, Qt.ConnectionType.DirectConnection)
        # quit() is thread-safe. DirectConnection prevents the queued main-thread
        # quit callback from being starved by long progress/log event streams.
        self.worker.finished.connect(self.thread.quit, Qt.ConnectionType.DirectConnection)
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
    def store_cancelled(self):
        self.was_cancelled = True

    def cancel(self):
        if self.thread is not None:
            self.thread.requestInterruption()

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
        if self.was_cancelled:
            self.cancelled.emit()
        elif self.failure is not None:
            self.failed.emit(*self.failure)
        else:
            self.succeeded.emit(self.result)


class LoadDataDialog(QDialog):
    solar_csv_modes = ("nasa_power", "prepared", "power")

    def __init__(self, parent=None):
        super().__init__(parent)
        load_form(self, "load_data_dialog.ui")
        self.runner = JobRunner(self)
        self.study = None
        self.pending_action = ""
        self.preview_network = None
        self.preview_path = None
        self.ratings_seed = ()
        self.preparation_log = []
        for name in ("edit_network_path", "edit_pv_source_path", "edit_load_path"):
            widget(self, name).setReadOnly(True)
        table = widget(self,"table_pv_installations")
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().hide()
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        buttons = widget(self,"buttons_load_data")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Prepare study")
        self.connect_events()
        self.update_modes()
    def connect_events(self):
        widget(self, "btn_browse_network").clicked.connect(self.browse_network)
        widget(self, "btn_browse_pv_source").clicked.connect(self.browse_pv)
        widget(self, "btn_browse_load").clicked.connect(self.browse_load)
        widget(self, "btn_browse_load_file").clicked.connect(self.browse_load_file)
        widget(self, "btn_load_network").clicked.connect(self.load_network_preview)
        widget(self, "edit_network_path").textChanged.connect(self.update_network_button)
        widget(self, "combo_pv_source").currentIndexChanged.connect(self.update_modes)
        widget(self, "chk_no_pv").toggled.connect(self.update_modes)
        widget(self, "chk_pv_fallback").toggled.connect(self.update_modes)
        widget(self, "btn_add_pv_row").clicked.connect(self.add_pv_row)
        widget(self, "btn_remove_pv_row").clicked.connect(self.remove_pv_row)
        widget(self, "buttons_load_data").accepted.connect(self.prepare_data)
        self.runner.busy_changed.connect(self.set_busy)
        self.runner.stage.connect(self.show_preparation_stage)
        self.runner.failed.connect(self.show_failure)
        self.runner.cancelled.connect(lambda: set_status(
            widget(self, "lbl_load_validation"), "Preparation cancelled.", "info"))
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
                self.update_modes()
            except (ValueError,OSError) as error:
                self.show_failure(str(error), "")

    def browse_load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Hourly load profile", str(REPO), "Load profiles (*.csv *.xlsx)")
        if path:
            widget(self, "edit_load_path").setText(path)
            widget(self, "lbl_load_status").setText(Path(path).name)
            self.populate_folder_metadata()
            self.update_modes()

    def pv_rows(self):
        table = widget(self, "table_pv_installations")
        rows = [[table.item(row, col).text().strip() if table.item(row, col) else ""
                 for col in (0, 1)] for row in range(table.rowCount())]
        return tuple(tuple(row) for row in rows if any(row))

    def populate_folder_metadata(self):
        folder = Path(widget(self,"edit_load_path").text())
        manifest = folder / "manifest.json"
        meta = json.loads(manifest.read_text(encoding="utf-8-sig")) if manifest.is_file() else {}
        conflicts = ""
        summary = folder/"bus_summary.csv"
        network = self.preview_network if self.preview_path == widget(self, "edit_network_path").text() else None
        ids = {b.bus_id for b in network.buses} if network else None
        folder_ratings = summary_pv_ratings(pd.read_csv(summary), ids) if manifest.is_file() and summary.is_file() else {}
        workbook_ratings = {}
        if network:
            for unit in network.pv_units:
                workbook_ratings[unit.bus_id] = workbook_ratings.get(unit.bus_id, 0.) + unit.p_rated_kw
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
        clock_note = ("Source clock found in dataset metadata. " if meta.get("clock") or meta.get("timezone") or meta.get("time_zone")
                      else "Missing source clock in dataset manifest.json; correct the metadata. ")
        set_status(widget(self,"lbl_load_validation"),clock_note+"Review installed PV ratings, then choose Prepare study.",
                   "warning" if conflicts or "Missing" in clock_note else "info")

    def update_network_button(self):
        widget(self, "btn_load_network").setEnabled(bool(widget(self, "edit_network_path").text()) and not self.runner.busy)

    def solar_source_mode(self):
        if widget(self, "chk_no_pv").isChecked():
            return "none"
        load = widget(self, "edit_load_path").text()
        if widget(self, "chk_pv_fallback").isChecked() or (load and Path(load).is_file()):
            return widget(self, "combo_pv_source").currentData()
        return "dataset"

    def update_modes(self):
        mode = self.solar_source_mode()
        load = widget(self, "edit_load_path").text()
        standalone = bool(load and Path(load).is_file())
        manual = mode in self.solar_csv_modes
        installed = mode != "none"
        fallback = installed and mode != "dataset"
        widget(self, "chk_pv_fallback").setVisible(installed and not standalone)
        widget(self, "panel_pv_source_fields").setVisible(fallback)
        widget(self, "panel_pv_source_fields").setEnabled(fallback)
        for name in ("panel_pv_source_file","label_5","edit_solar_clock","lbl_edit_solar_clock"):
            widget(self,name).setVisible(manual)
        widget(self, "group_pv_conversion").setVisible(installed)
        widget(self, "group_solar_metadata").setVisible(manual)
        if not installed:
            message = "No PV study: no solar source or site metadata is required."
        elif standalone:
            message = "Provide the solar source and installed PV ratings, or select No PV study."
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
        # Approved study: do not read the removed workbook-format selector.
        return Path(path), frequency or None, "auto"

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
        load_path = widget(self, "edit_load_path").text().strip()
        if not load_path:
            raise ValueError("Choose a GoiEner case or multi-case output folder")
        load_input = Path(load_path)
        standalone = load_input.is_file()
        manifest = load_input.with_suffix(".json") if standalone else load_input / "manifest.json"
        if not standalone and not manifest.is_file():
            raise ValueError("The selected GoiEner case has no manifest.json; it must declare a source clock")
        try:
            source = (read_manifest_assumptions(json.loads(manifest.read_text(encoding="utf-8-sig")))
                      if manifest.is_file() else
                      {"clock": None, "latitude": None, "longitude": None, "reference_capacity_kw": None})
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Could not read source metadata in {manifest.name}") from error
        if standalone and mode != "none" and source["clock"] is None:
            raise ValueError(f"Declare the load source clock in {manifest.name} before aligning solar data")
        # A separate modeled-PV electrical-power file must declare its own
        # reference capacity. For irradiance sources the nameplate can be
        # derived from the explicitly installed PV table instead.
        reference_capacity = source.get("reference_capacity_kw")
        if not standalone and manual and pv_path and mode == "power":
            header = pd.read_csv(pv_path, nrows=1, encoding="utf-8-sig")
            if header.empty:
                raise ValueError("The modeled-PV source contains no data")
            metadata = header.iloc[0].dropna().to_dict()
            declared = metadata.get("reference_capacity_kw", metadata.get("capacity_kw"))
            if declared is not None:
                reference_capacity = float(declared)
            if reference_capacity is None:
                raise ValueError("The modeled-PV power CSV requires a declared reference_capacity_kw (kW) "
                                 "in its source metadata or a trusted study manifest")
        if reference_capacity is None and mode not in ("none", "dataset", "power"):
            reference_capacity = sum(ratings.values()) if ratings else None
        return DataRequest(
            network_path=path, frequency_hz=frequency, workbook_format=format_name,
            start=None, months=None,
            pv_source=mode, pv_path=Path(pv_path) if manual and pv_path else None,
            pv_ratings_kw=ratings, critical_irradiance=PV_CRITICAL_IRRADIANCE_W_M2,
            standard_irradiance=PV_STANDARD_IRRADIANCE_W_M2,
            load_source="imported" if standalone else "distributed",
            dataset_folder=None if standalone else load_input, pv_override=self.pv_rows() != self.ratings_seed,
            pv_rating_selection="Edited PV table" if self.pv_rows() != self.ratings_seed else "",
            latitude=source["latitude"] if mode != "none" else None,
            longitude=source["longitude"] if mode != "none" else None,
            clock=source["clock"],
            solar_source_clock=(widget(self,"edit_solar_clock").text().strip() or None) if manual else None,
            reference_capacity_kw=reference_capacity,
            load_path=Path(load_path), load_seed=SYNTHETIC_SEED)

    def prepare_data(self):
        try:
            request = self.read_request()
            self.preparation_log.clear()
            self.pending_action = "prepare"
            self.runner.start(partial(prepare_study, request))
        except (ValueError, OSError) as error:
            self.show_failure(str(error), "")

    def set_busy(self, busy):
        widget(self, "tabs_data").setEnabled(not busy)
        buttons = widget(self, "buttons_load_data")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not busy)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Stop preparation" if busy else "Cancel")
        self.update_network_button()

    def show_failure(self, message, details):
        set_status(widget(self, "lbl_load_validation"),message,"error")
        widget(self, "lbl_load_validation").setToolTip(details)
        desktop_log.error("Load Data | %s", message)
        if details:
            desktop_log.debug("%s", details)

    def show_preparation_stage(self, message):
        self.preparation_log.append(message)
        desktop_log.info("Load Data | %s", message)
        widget(self, "lbl_load_validation").setText(message)

    def job_succeeded(self, result):
        if self.pending_action == "prepare":
            self.study = result
            details = result.context
            status = " · ".join(str(value) for value in (details.get("Network"),
                details.get("History interval"), details.get("Workbook provenance")) if value)
            set_status(widget(self,"lbl_load_validation"), status or "Data prepared and validated", "success")
            widget(self,"lbl_load_validation").setToolTip("")
            self.accept()
            return
        widget(self, "lbl_network_summary").setText(
            f"Network loaded: {len(result.buses)} buses, {len(result.lines)} branches; slack {result.slack_bus_id()}; "
            f"base load {sum(load.p_base_kw for load in result.loads):g} kW; frequency {result.frequency_hz:g} Hz")
        self.preview_network = result
        widget(self, "lbl_load_validation").setText("Select demand and solar inputs.")
        try:
            self.populate_folder_metadata()
        except (ValueError, OSError) as error:
            self.show_failure(str(error), "")

    def reject(self):
        if self.runner.busy:
            self.runner.cancel()
            widget(self, "lbl_load_validation").setText("Stopping at the next preparation step.")
        else:
            super().reject()

    def closeEvent(self, event):
        if self.runner.busy:
            event.ignore()
            self.reject()
        else:
            super().closeEvent(event)


class SettingsDialog(QDialog):
    applied = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        load_form(self, "settings_dialog.ui")
        self.network = None
        self.tariffs_confirmed = False
        policy = widget(self, "combo_corrective_actions")
        for label, value in (("Enabled", "controlled"), ("Disabled", "uncontrolled"), ("Compare both", "compare")):
            policy.addItem(label, value)
        worker_control = widget(self, "spin_parallel_workers")
        worker_control.setMaximum(desktop_worker_limit())
        defaults = joint_search_policy(0)
        worker_control.setValue(defaults.workers)
        self.population_automatic = True
        widget(self, "spin_ga_population").setValue(defaults.population)
        self.connect_designer_settings()
        self.restore_manual_rows(manual_rows({}))
        self.committed = self.capture_values()
        buttons = widget(self, "buttons_settings")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save settings")
        buttons.accepted.connect(self.accept_settings)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply_settings)
        buttons.rejected.connect(self.reject)
        self.engine_ready = False
        self.jit_metadata = None
        self.jit_runner = JobRunner(self)
        self.jit_runner.succeeded.connect(self.numba_ready)
        self.jit_runner.failed.connect(self.numba_failed)
        QTimer.singleShot(0, lambda: self.jit_runner.start(lambda stage: warm_numba()))
        self.update_compute_status()
        self.update_optional_controls()
    def mark_tariff_changed(self, *args):
        self.tariffs_confirmed = False

    def use_custom_population(self, _population):
        self.population_automatic = False

    def connect_designer_settings(self):
        widget(self, "spin_ga_population").valueChanged.connect(self.use_custom_population)
        widget(self, "btn_select_all_buses").clicked.connect(self.select_all_allowed_buses)
        widget(self, "btn_clear_allowed_buses").clicked.connect(self.clear_allowed_buses)
        widget(self, "list_allowed_buses").itemSelectionChanged.connect(self.update_allowed_bus_count)
        table = widget(self, "table_manual_bess")
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.itemChanged.connect(self.update_manual_row)
        table.model().rowsRemoved.connect(self.update_manual_summary)
        widget(self, "chk_experimental_multi_bess").toggled.connect(self.update_optional_controls)
        widget(self, "btn_manual_bess_add").clicked.connect(lambda: self.add_manual_row())
        widget(self, "btn_manual_bess_remove").clicked.connect(self.remove_manual_rows)
        widget(self, "btn_manual_bess_clear").clicked.connect(lambda: table.setRowCount(0))
        for name in ("group_manual_bess", "group_import_limit", "group_export_limit", "group_experimental_ga"):
            widget(self, name).toggled.connect(self.update_optional_controls)
        for name in ("spin_grid_import_tariff", "spin_grid_export_tariff"):
            widget(self, name).valueChanged.connect(self.mark_tariff_changed)

    def update_optional_controls(self, *args):
        for name in ("group_manual_bess", "group_import_limit", "group_export_limit", "group_experimental_ga"):
            group = widget(self, name)
            enabled = group.isChecked()
            form = group.layout()
            for row in range(form.rowCount()):
                form.setRowVisible(row, enabled)
            group.setProperty("collapsed", not enabled)
            group.style().unpolish(group)
            group.style().polish(group)
        experimental = widget(self, "chk_experimental_multi_bess").isChecked()
        widget(self, "spin_bess_units").setEnabled(not experimental)
        self.update_allowed_bus_count()
        widget(self, "group_experimental_ga").setTitle(
            "Advanced optimization · Experimental enabled" if experimental else "Advanced optimization")

    def eligible_manual_buses(self):
        return sorted(bus.bus_id for bus in self.network.buses if not bus.is_slack) if self.network else []

    def restore_manual_rows(self, rows):
        table = widget(self, "table_manual_bess")
        table.setRowCount(0)
        for row in rows:
            self.add_manual_row(row)

    def add_manual_row(self, row=None):
        table = widget(self, "table_manual_bess")
        index = table.rowCount()
        row = row or {"enabled": True, "bus_id": None, "power_kw": "", "energy_kwh": ""}
        eligible = self.eligible_manual_buses()
        table.insertRow(index)
        checked = QTableWidgetItem()
        checked.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
        checked.setCheckState(Qt.CheckState.Checked if row["enabled"] else Qt.CheckState.Unchecked)
        table.setItem(index, 0, checked)
        bus = QComboBox(table)
        bus.setAccessibleName(f"Installation bus for manual battery {index + 1}")
        bus.addItem("Select bus", None)
        for bus_id in eligible:
            bus.addItem(f"B{bus_id}", bus_id)
        selected = row.get("bus_id")
        if selected is not None and selected not in eligible:
            bus.addItem(f"B{selected} (unavailable)", selected)
        bus.setCurrentIndex(bus.findData(selected))
        table.setCellWidget(index, 1, bus)
        for column, key in ((2, "power_kw"), (3, "energy_kwh")):
            table.setItem(index, column, QTableWidgetItem(str(row.get(key, ""))))
        duration = QTableWidgetItem()
        duration.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        table.setItem(index, 4, duration)
        self.update_manual_row(table.item(index, 3))

    def remove_manual_rows(self):
        table = widget(self, "table_manual_bess")
        for index in sorted({item.row() for item in table.selectedIndexes()}, reverse=True):
            table.removeRow(index)

    def update_manual_row(self, item):
        table = item.tableWidget()
        power, energy, duration = (table.item(item.row(), col) for col in (2, 3, 4))
        if item.column() in (2, 3) and power is not None and energy is not None and duration is not None:
            p, e = positive(power.text()), positive(energy.text())
            hours = e / p if p and e else None
            duration.setText(f"{hours:.4g}" if hours is not None else "—")
        if item.column() != 4:
            self.update_manual_summary()

    def update_manual_summary(self, *_):
        table = widget(self, "table_manual_bess")
        rows = [i for i in range(table.rowCount()) if table.item(i, 0) is not None
                and table.item(i, 0).checkState() == Qt.CheckState.Checked]
        totals = [sum(positive(item.text()) or 0 for i in rows if (item := table.item(i, col)) is not None)
                  for col in (2, 3)]
        widget(self, "lbl_manual_fleet_summary").setText(
            f"{len(rows)} enabled BESS  |  {totals[0]:,.3f} kW  |  {totals[1]:,.3f} kWh")

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
        selected = len(choices.selectedItems())
        widget(self, "lbl_allowed_bus_count").setText(
            f"{selected} of {choices.count()} eligible buses selected")
        maximum = widget(self, "spin_experimental_bess_units")
        minimum = maximum.minimum()
        enough_buses = selected >= minimum
        maximum.setMaximum(max(minimum, selected))
        maximum.setEnabled(enough_buses and widget(self, "chk_experimental_multi_bess").isChecked())
        maximum.setToolTip(f"Maximum allowed by selected non-slack buses: {selected}" if enough_buses
                           else f"Select at least {minimum} eligible non-slack buses.")

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


    def capture_values(self):
        values = dict(FIXED_WIDGET_SETTINGS)
        values["simulation_control_mode"] = widget(self, "combo_corrective_actions").currentData()
        for cls in (QSpinBox, QDoubleSpinBox, QCheckBox):
            for control in self.findChildren(cls):
                name = control.objectName()
                if name:
                    values[name] = control.isChecked() if isinstance(control, QCheckBox) else control.value()
        for group in self.findChildren(QGroupBox):
            if group.isCheckable():
                values[group.objectName()] = group.isChecked()
        table = widget(self, "table_manual_bess")
        rows = [{
            "enabled": table.item(i, 0).checkState() == Qt.CheckState.Checked,
            "bus_id": table.cellWidget(i, 1).currentData(),
            "power_kw": row_number(table.item(i, 2).text()),
            "energy_kwh": row_number(table.item(i, 3).text()),
        } for i in range(table.rowCount())]
        values["manual_bess_rows"] = rows
        primary = next((row for row in rows if row["enabled"]), {})
        values["bess_bus"] = primary.get("bus_id")
        values["spin_bess_power_kw"] = positive(primary.get("power_kw")) or 0
        values["spin_bess_energy_kwh"] = positive(primary.get("energy_kwh")) or 0
        experimental = values["chk_experimental_multi_bess"]
        values["experimental_enabled"] = experimental
        values["optimization_mode"] = "experimental_4_plus" if experimental else "standard_1_to_3"
        values["requested_max_units"] = values["spin_experimental_bess_units" if experimental else "spin_bess_units"]
        choices = widget(self, "list_allowed_buses")
        values["allowed_buses"] = tuple(item.data(Qt.ItemDataRole.UserRole) for item in choices.selectedItems())
        values.update(
            fleet_dispatch_mode="daily_milp_dispatch", optimizer_algorithm="GA",
            dispatch_horizon_hours=DEFAULT_DISPATCH_HORIZON_HOURS,
            minimum_discharge_pf=DEFAULT_MINIMUM_DISCHARGE_PF,
            charge_efficiency=DEFAULT_DISPATCH_EFFICIENCY,
            discharge_efficiency=DEFAULT_DISPATCH_EFFICIENCY,
            population_automatic=self.population_automatic,
            compute_backend="numba", numba_readiness=getattr(self, "jit_metadata", None),
            chk_tariffs_confirmed=self.tariffs_confirmed,
        )
        return values

    def restore_values(self):
        for name, value in self.committed.items():
            if name == "spin_experimental_bess_units":
                continue
            control = self.findChild(QWidget, name)
            if isinstance(control, (QSpinBox, QDoubleSpinBox)):
                control.setValue(value)
            elif isinstance(control, (QGroupBox, QCheckBox)):
                control.setChecked(value)
        self.tariffs_confirmed = self.committed.get("chk_tariffs_confirmed") is True
        mode = widget(self, "combo_corrective_actions")
        mode.setCurrentIndex(max(0, mode.findData(self.committed.get("simulation_control_mode", "controlled"))))
        self.restore_manual_rows(manual_rows(self.committed))
        choices = widget(self, "list_allowed_buses")
        selected = self.committed.get("allowed_buses", ())
        for index in range(choices.count()):
            item = choices.item(index)
            item.setSelected(item.data(Qt.ItemDataRole.UserRole) in selected)
        self.population_automatic = self.committed.get("population_automatic", True)
        self.update_optional_controls()
        maximum = widget(self, "spin_experimental_bess_units")
        maximum.setValue(self.committed.get("spin_experimental_bess_units", maximum.minimum()))
        self.update_compute_status()

    def set_network(self, network):
        previous_network = self.network
        self.network = network
        eligible = {bus.bus_id for bus in network.buses if not bus.is_slack}
        previous_eligible = ({bus.bus_id for bus in previous_network.buses if not bus.is_slack}
                             if previous_network is not None else set())
        if eligible != previous_eligible:
            self.committed["allowed_buses"] = tuple(sorted(eligible))
            if self.committed.get("population_automatic", True):
                self.committed["spin_ga_population"] = joint_search_policy(len(eligible)).population
        choices = widget(self, "list_allowed_buses")
        choices.clear()
        for bus in sorted(network.buses, key=lambda item: item.bus_id):
            if bus.is_slack:
                continue
            item = QListWidgetItem(f"B{bus.bus_id}")
            item.setData(Qt.ItemDataRole.UserRole, bus.bus_id)
            choices.addItem(item)
        self.restore_values()
        self.update_allowed_bus_count()

    def read_settings(self, optimization=False, *, values=None, require_ready=True, validate_manual=True):
        values = self.capture_values() if values is None else values
        mode = "controlled" if optimization else values.get("simulation_control_mode", "controlled")
        if mode not in ("controlled", "uncontrolled", "compare"):
            raise ValueError("Choose Enabled, Disabled, or Compare both for corrective actions")
        effective_joint_search(values)
        if require_ready and not self.engine_ready:
            raise ValueError("Mandatory Numba solver is not ready: "+widget(self,"lbl_compute_status").text())
        simulation = SimulationConfig(
            voltage_min_pu=values["spin_voltage_min_pu"], voltage_max_pu=values["spin_voltage_max_pu"],
            grid_import_limit_kw=values["spin_import_limit_kw"] if values["group_import_limit"] else None,
            grid_export_limit_kw=values["spin_export_limit_kw"] if values["group_export_limit"] else None,
            allow_pv_curtailment=values["chk_allow_curtailment"], allow_load_shedding=values["chk_allow_shedding"],
            corrective_actions=mode != "uncontrolled",
            shedding_policy=values["shedding_policy"],
            fleet_dispatch_mode=values["fleet_dispatch_mode"],
            minimum_discharge_pf=values["minimum_discharge_pf"],
            dispatch_horizon_hours=values["dispatch_horizon_hours"],
            predictive_grid_tariff_per_kwh=values["spin_grid_import_tariff"] if values["chk_tariffs_confirmed"] else 0.10,
            shedding_tier_edges=tuple(values[f"spin_shed_edge_{i}"] / 100 for i in (1, 2)),
            shedding_tier_weights=tuple(values[f"spin_shed_weight_{i}"] for i in (1, 2, 3)),
            fbs_config=FBSConfig())
        economics = self.economic_config(values, simulation)
        parameters = BESSParameters(values["charge_efficiency"], values["discharge_efficiency"],
                                    values["spin_soc_min_percent"] / 100, values["spin_soc_max_percent"] / 100,
                                    values["spin_soc_initial_percent"] / 100)
        units = validate_manual_fleet(values, self.eligible_manual_buses(), parameters) if not optimization and validate_manual else ()
        if optimization:
            if not values["chk_tariffs_confirmed"]:
                raise ValueError("Save and explicitly acknowledge the grid import/export tariffs before optimizing")
            if not values["allowed_buses"]:
                raise ValueError("Select eligible installation buses in Settings")
            allowed = set(self.eligible_manual_buses()).intersection(values["allowed_buses"])
            ga_fleet_limit(values, allowed, simulation.fleet_dispatch_mode)
            catalogs = []
            for quantity, unit in (("power", "kw"), ("energy", "kwh")):
                try:
                    catalogs.append(size_catalog(*(values[f"spin_opt_{quantity}_{field}_{unit}"]
                                                   for field in ("min", "max", "step"))))
                except ValueError as error:
                    raise ValueError(f"Set a valid battery {quantity} minimum, maximum and step. {error}") from error
            OptimizationBounds(tuple(values["allowed_buses"]), *catalogs,
                               min_duration_hours=values["spin_opt_duration_min_hours"],
                               max_duration_hours=values["spin_opt_duration_max_hours"])
        return RunSettings(simulation, economics, units[0] if len(units) == 1 else None, values,
                           managed_search=True, manual_bess_fleet=units, compare_corrective_actions=mode == "compare")

    @staticmethod
    def economic_config(values, simulation):
        return EconomicConfig(
            values["spin_battery_energy_capex"], values["spin_inverter_capex"],
            CURRENCY,
            curtailment_penalty_per_kwh=values["spin_curtailment_penalty"],
            shedding_penalty_per_kwh=values["spin_shedding_penalty"],
            grid_import_tariff_per_kwh=values["spin_grid_import_tariff"] if values["chk_tariffs_confirmed"] else None,
            grid_export_tariff_per_kwh=values["spin_grid_export_tariff"] if values["chk_tariffs_confirmed"] else None,
            lifetime_years=int(values["spin_bess_lifetime"]),
            annual_om_fraction=values["spin_annual_om_percent"] / 100.0,
            power_cost_basis="kva",
            inverter_kva_per_kw=simulation.effective_bess_inverter_kva_per_kw,
            annualization_method="real_crf", nominal_interest_rate=0.05, annual_inflation_rate=0.01,
            scenario="Daily MILP dispatch annual grid cost, penalties and BESS ownership",
            provenance="Energy and inverter CAPEX, inflation-adjusted real CRF, annual O&M")

    def apply_settings(self):
        try:
            if not self.tariffs_confirmed:
                imp = widget(self, "spin_grid_import_tariff").value()
                exp = widget(self, "spin_grid_export_tariff").value()
                answer = QMessageBox.question(
                    self, "Confirm economic assumptions",
                    f"Use grid import {imp:g} USD/kWh and export {exp:g} USD/kWh "
                    "for the next approved study?\n\nThese are assumed tariffs, "
                    "not automatically measured market prices.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return False
                self.tariffs_confirmed = True
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
        self.status = widget(self, "lbl_forecast_status")
        self.generate_button = widget(self, "btn_generate_forecast")
        self.generate_button.clicked.connect(self.start_forecast)
        widget(self, "btn_cancel_forecast").clicked.connect(self.reject)
        self.runner = JobRunner(self)
        self.runner.succeeded.connect(self.forecast_ready)
        self.runner.failed.connect(self.forecast_failed)
        self.runner.cancelled.connect(lambda: set_status(self.status, "Forecast cancelled.", "info"))
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
        for name in ("combo_horizon_preset","spin_forecast_horizon","date_training_start","date_training_end","date_forecast_origin"):
            widget(self,name).setEnabled(not busy)
        widget(self, "btn_cancel_forecast").setText("Stop forecast" if busy else "Cancel")
        self.generate_button.setText("Generating…" if busy else "Generate forecast")
        if busy:
            self.generate_button.setEnabled(False)
        else:
            self.update_training_status()

    def start_forecast(self):
        if self.runner.busy:
            return
        try:
            method = FORECAST_METHOD
            cfg = ForecastConfig(horizon_hours=self.horizon.value(),
                                 training_start=self.train_start.dateTime().toPython(),
                                 training_end=self.train_end.dateTime().toPython(),
                                 forecast_start=self.origin.dateTime().toPython(),
                                 method=method)
        except ValueError as error:
            self.forecast_failed(str(error), "")
            return
        output = self.session.root / "forecasts" / datetime.now().strftime("forecast_%Y%m%d_%H%M%S_%f")
        self.generate_button.setEnabled(False)
        set_status(self.status, "Training the sector models and preparing the common PV forecast, when installed.", "busy")
        self.runner.start(partial(forecast_and_export, self.study, cfg, output,
                                  network_snapshot=self.session.network_snapshot_path()))

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

    def forecast_ready(self, result):
        try:
            report, output = result
            history = self.study.historical_profiles or self.study.profiles
            self.study.historical_profiles = history
            self.study.forecast_profiles = report.profiles
            self.study.select_source("forecast")
            self.study.forecast_info = {"model": report.model_info, "validation_scores": report.scores,
                                        "training_ends": str(report.historical_end),
                                        "forecast_hours": report.horizon_hours,
                                        "output_folder": str(output)}
            self.session.manifest.setdefault("forecast_runs", []).append(self.study.forecast_info)
            self.session.save()
            self.accept()
        except Exception as error:
            self.forecast_failed(str(error), "")

    def reject(self):
        if self.runner.busy:
            self.runner.cancel()
            self.status.setText("Stopping when the current forecast computation returns.")
            return
        super().reject()

    def closeEvent(self, event):
        if self.runner.busy:
            event.ignore()
            self.reject()
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



class InformationDialog(QDialog):
    def __init__(self, contexts, selected=0, parent=None):
        super().__init__(parent)
        load_form(self, "information_dialog.ui")
        self.contexts = list(contexts)
        self.context_picker = widget(self, "combo_information_context")
        self.context_picker.addItems([label for label, _, _ in self.contexts])
        self.context_picker.setCurrentIndex(selected)
        self.context_picker.currentIndexChanged.connect(self.show_context)
        widget(self, "btn_information_archive").clicked.connect(self.open_archive)
        widget(self, "btn_information_provenance").clicked.connect(self.open_provenance)
        widget(self, "buttons_information").rejected.connect(self.reject)
        self.show_context(selected)

    def show_context(self, index):
        _, metadata, snapshot = self.contexts[index]
        widget(self, "btn_information_provenance").setEnabled(bool(provenance_records(metadata, snapshot)))
        sections = model_information(metadata, snapshot)
        for name, section in (("parameters", "Current parameters"), ("equations", "Mathematical equations"),
                              ("assumptions", "Model assumptions")):
            widget(self, f"information_{name}").setHtml(sections[section])

    def open_provenance(self):
        label, metadata, snapshot = self.contexts[self.context_picker.currentIndex()]
        dialog = QDialog(self)
        dialog.setWindowTitle("Source files and integrity")
        layout = QVBoxLayout(dialog)
        context_label = QLabel(label)
        context_label.setTextFormat(Qt.TextFormat.PlainText)
        context_label.setWordWrap(True)
        layout.addWidget(context_label)
        text = QPlainTextEdit(display_detail(provenance_records(metadata, snapshot)), dialog)
        text.setReadOnly(True)
        text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        copy = buttons.addButton("Copy all", QDialogButtonBox.ButtonRole.ActionRole)
        copy.clicked.connect(lambda: QApplication.clipboard().setText(text.toPlainText()))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.resize(self.size())
        dialog.exec()

    def open_archive(self):
        from .dashboard import read_saved_run
        folder = QFileDialog.getExistingDirectory(self, "Open saved run folder")
        if not folder:
            return
        try:
            metadata, snapshot = read_saved_run(folder)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Saved run unavailable", str(error))
            return
        label = f"Frozen settings — {Path(folder).parent.name}/{Path(folder).name}"
        self.contexts.append((label, metadata, snapshot))
        self.context_picker.addItem(label)
        self.context_picker.setCurrentIndex(len(self.contexts) - 1)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        configure_desktop_log()
        load_form(self, "main_window.ui")
        widget(self, "chk_hide_diagram").hide()
        widget(self, "chk_hide_diagram").setChecked(False)
        self.study = None
        self.session = None
        self.report = None
        self.running_information = None
        self.completed_information = None
        self.result_index = None
        self.pending_action = ""
        self.pending_run_output = None
        self.result_scenario = "."
        self.result_folder = None
        self.dashboard_folder = None
        self.dashboard_job_folder = None
        self.pending_run_optimization = False
        self.runner = JobRunner(self)
        self.dashboard_runner = JobRunner(self)
        self.dashboard_open_after_build = False
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
        self.add_dashboard_actions()
        widget(self, "run_log").setMaximumBlockCount(5000)
        self.connect_events()
        self.connect_source_events()
        self.connect_solver_status()
        self.set_busy(False)
        self.append_log("BESS Planning Tool started")

    def connect_solver_status(self):
        self.settings_dialog.jit_runner.succeeded.connect(lambda *_: self.set_busy(self.runner.busy))
        self.settings_dialog.jit_runner.failed.connect(lambda *_: self.set_busy(self.runner.busy))

    def add_dashboard_actions(self):
        control = widget(self, "btn_dashboard")
        menu = QMenu(control)
        embedded = menu.addAction("Open latest report in the app", lambda: self.open_dashboard("embedded"))
        browser = menu.addAction("Open latest report in browser", lambda: self.open_dashboard("browser"))
        menu.addAction("Open saved report / compare runs", lambda: self.open_dashboard("saved"))
        menu.addAction("Regenerate saved report", lambda: self.open_dashboard("regenerate"))
        menu.addAction("Save offline HTML copy", lambda: self.open_dashboard("save_html"))
        menu.addAction("Export portable ZIP", lambda: self.open_dashboard("package"))
        menu.addAction("Export portable ZIP with layout or charts", lambda: self.open_dashboard("package_exports"))
        def refresh():
            available = self.dashboard_folder is not None and (self.dashboard_folder / "dashboard.html").is_file()
            embedded.setEnabled(available)
            browser.setEnabled(available)
        menu.aboutToShow.connect(refresh)
        control.setMenu(menu)

    def open_dashboard(self, action):
        from .dashboard import HTML_FILE, copy_dashboard, package_dashboard
        if self.dashboard_runner.busy and action in ("regenerate", "save_html", "package", "package_exports"):
            QMessageBox.information(self, "Results dashboard", "A dashboard is being built. Please use the saved numeric results or open an existing report.")
            return
        folder = self.dashboard_folder
        if action in ("saved", "regenerate") or folder is None:
            selected = QFileDialog.getExistingDirectory(self, "Select saved run directory",
                                                         str(folder or REPO))
            if not selected:
                return
            folder = Path(selected)
        try:
            path = folder / HTML_FILE
            if action == "save_html":
                target, _ = QFileDialog.getSaveFileName(
                    self, "Save offline HTML", str(folder / (folder.name + "_dashboard.html")), "HTML reports (*.html)")
                if target:
                    copy_dashboard(folder, target)
                    self.statusBar().showMessage(f"Saved offline HTML to {target}", 7000)
                return
            if action in ("package", "package_exports"):
                attachments = ()
                if action == "package_exports":
                    attachments, _ = QFileDialog.getOpenFileNames(
                        self, "Select exported layout, charts or PDF", str(folder),
                        "Dashboard exports (*.json *.png *.pdf)")
                    if not attachments:
                        return
                target, _ = QFileDialog.getSaveFileName(self, "Export portable report",
                                                       str(folder / "dashboard.zip"), "ZIP archives (*.zip)")
                if not target:
                    return
                package_dashboard(folder, target, attachments=attachments)
                self.statusBar().showMessage(f"Portable report saved to {target}", 7000)
                return
            if action == "regenerate" or not path.is_file():
                self.start_dashboard_build(folder, open_when_ready=True)
                return
            if action == "browser":
                if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                    raise OSError("The system could not open the default browser.")
            else:
                from .dashboard_viewer import show_dashboard
                show_dashboard(self, path)
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Results dashboard", str(error))

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
        group = widget(self, "group_bus_details")
        group.hide()
        self.plot_element = QPushButton("Plot selected element", group)
        self.plot_element.clicked.connect(self.plot_selection)
        group.layout().addRow(self.plot_element)
        self.plot_element.hide()
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
        alternatives = getattr(self.report, "alternatives", {})
        if self.result_scenario in alternatives:
            return alternatives[self.result_scenario][0].steps
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
        fleet_ratings = {}
        if self.report:
            fleet_ratings = {bus: rating[:2] for bus, rating in battery_ratings(self.report.context).items()}
            if not fleet_ratings and isinstance(self.report.result, OptimizationResult):
                fleet_ratings = {unit["bus_id"]: (unit["power_rating_kw"], unit["energy_capacity_kwh"])
                                 for unit in self.report.result.metadata.get("fleet", ())}
                candidate = self.report.result.best_candidate
                if not fleet_ratings and candidate is not None:
                    fleet_ratings[candidate.bus_id] = (candidate.power_rating_kw, candidate.energy_capacity_kwh)
        elif values["group_manual_bess"]:
            eligible = self.settings_dialog.eligible_manual_buses()
            for row in manual_rows(values):
                bus = row.get("bus_id")
                power, energy = positive(row.get("power_kw")), positive(row.get("energy_kwh"))
                if row.get("enabled") and bus in eligible and power and energy:
                    fleet_ratings[bus] = (power, energy)
        step = self.selected_step() if widget(self, "chk_network_results").isChecked() else None
        self.scene.draw_network(
            self.study.network, bounds=(values["spin_voltage_min_pu"], values["spin_voltage_max_pu"]),
            show_properties=widget(self, "chk_network_properties").isChecked(),
            step=step, fleet_ratings=fleet_ratings)
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
        alternatives = getattr(self.report, "alternatives", {})
        scenario = self.result_scenario
        if len(alternatives) > 1:
            names = list(alternatives)
            scenario, ok = QInputDialog.getItem(self, "Retained simulation", "Scenario", names, names.index(scenario), False)
            if not ok:
                return False
            steps = alternatives[scenario][0].steps
        dialog = TimestampDialog(steps, index, self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        if accepted:
            self.result_scenario = scenario
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
        widget(self, "btn_open_setup").clicked.connect(self.open_setup)
        widget(self, "btn_save_setup").clicked.connect(self.save_setup)
        widget(self, "btn_information").clicked.connect(self.open_information)
        self.settings_information_shortcut = QShortcut(QKeySequence("F1"), self.settings_dialog)
        self.settings_information_shortcut.activated.connect(self.open_information)
        widget(self, "btn_scenarios").clicked.connect(self.open_forecasting)
        widget(self, "btn_stop_run").clicked.connect(self.stop_run)
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
        self.runner.cancelled.connect(self.run_cancelled)
        self.dashboard_runner.stage.connect(self.append_log)
        self.dashboard_runner.succeeded.connect(self.dashboard_succeeded)
        self.dashboard_runner.failed.connect(self.dashboard_failed)
        self.scene.bus_selected.connect(self.show_bus)
        self.scene.line_selected.connect(self.show_line)

    def information_contexts(self):
        def preview(values, *, pending=False):
            try:
                settings = self.settings_dialog.read_settings(values=values, require_ready=False)
            except ValueError as error:
                try:
                    settings = self.settings_dialog.read_settings(values=values, require_ready=False, validate_manual=False)
                except ValueError:
                    context = study_information(self.study)
                    context["Settings controls"] = values
                else:
                    context = settings_information(self.study, settings)
                context["Preview note"] = f"These settings could not be resolved. {error}"
                context["Unvalidated inputs"] = {
                    "Lower voltage limit (pu)": values["spin_voltage_min_pu"],
                    "Upper voltage limit (pu)": values["spin_voltage_max_pu"],
                }
                if values["group_manual_bess"]:
                    context["Unvalidated inputs"]["Manual BESS rows"] = manual_rows(values)
            else:
                context = settings_information(self.study, settings)
            if pending and not values["chk_tariffs_confirmed"]:
                context["Proposed tariffs"] = (values["spin_grid_import_tariff"], values["spin_grid_export_tariff"])
            return {"context": context}

        confirmed = "Confirmed settings for the prepared study" if self.study else "Confirmed settings — no study prepared"
        contexts = [(confirmed, preview(self.settings_dialog.committed), None)]
        selected = 0
        if self.settings_dialog.isVisible():
            contexts.append(("Pending settings — current edits", preview(self.settings_dialog.capture_values(), pending=True), None))
            selected = len(contexts) - 1
        if self.running_information is not None:
            contexts.append(("Effective settings — running study", self.running_information, None))
            selected = len(contexts) - 1
        if self.completed_information is not None:
            contexts.append(("Frozen settings — last completed run", self.completed_information, None))
        return contexts, selected

    def open_information(self):
        contexts, selected = self.information_contexts()
        InformationDialog(contexts, selected, self.settings_dialog if self.settings_dialog.isVisible() else self).exec()

    def load_data(self):
        if self.load_dialog.exec() == QDialog.DialogCode.Accepted:
            self.attach_study(self.load_dialog.study)
            if self.session is not None:
                try:
                    self.session.append_log_lines(self.load_dialog.preparation_log)
                except OSError as error:
                    self.append_log(f"Could not copy the preparation log into the session: {error}", level="WARNING")

    def attach_study(self, study, controls=None):
        if self.session is None or study_fingerprint(study) != self.session.manifest["fingerprint"]:
            self.session = StudySession.create(study, Path(__file__).resolve().parent / "Results")
        self.study = study
        self.settings_dialog.set_network(study.network)
        if controls is not None:
            previous = {"spin_ga_stall_generations": 6, **controls}
            previous["manual_bess_rows"] = manual_rows(previous)
            previous.setdefault("chk_experimental_multi_bess", False)
            previous.setdefault("simulation_control_mode", "controlled")
            previous["group_experimental_ga"] = bool(previous.get("group_experimental_ga") or
                                                      previous["chk_experimental_multi_bess"])
            if previous.get("spin_bess_units", 3) > 3:
                self.append_log("Saved standard GA maximum adjusted to three units. Larger fleets require experimental opt-in.",
                                level="WARNING")
                previous["spin_bess_units"] = 3
            if "spin_ga_population" in previous:
                previous.setdefault("population_automatic", False)
            self.settings_dialog.committed.update(previous)
            self.settings_dialog.restore_values()
            effective = self.settings_dialog.capture_values()
            if ("spin_parallel_workers" in previous
                    and previous["spin_parallel_workers"] != effective["spin_parallel_workers"]):
                self.append_log(f"Saved worker count adjusted to {effective['spin_parallel_workers']} "
                                "for this PC", level="WARNING")
            if previous.get("fleet_dispatch_mode", "daily_milp_dispatch") != effective["fleet_dispatch_mode"]:
                self.append_log("This setup used legacy dispatch. New desktop runs use daily MILP dispatch and Joint GA. "
                                "Review the battery and USD/kVA economics before running.")
                self.settings_dialog.tariffs_confirmed = False
            self.settings_dialog.committed = self.settings_dialog.capture_values()
        self.sync_time_controls()
        self.invalidate_results("Study loaded. Open a saved report to review earlier results.")
        self.scene.branch_sides.clear()
        self.arrange_network_view()
        self.append_log(f"Study loaded: {len(study.network.buses)} buses; {len(study.profiles.timestamps)} hourly steps\n"
                        f"Load: {self.study.request.load_source}; PV: {self.study.request.pv_source}\nSession: {self.session.root.name}")
        self.set_busy(False)

    def save_setup(self):
        if self.study is None or self.runner.busy:
            return
        name, _ = QFileDialog.getSaveFileName(self, "Save study setup", "BESS_Study.json", "Study setup (*.json)")
        if name:
            self.pending_action = "save_setup"
            self.runner.start(partial(save_study_setup, Path(name), self.study, deepcopy(self.settings_dialog.committed)))

    def open_setup(self):
        if self.runner.busy:
            return
        name, _ = QFileDialog.getOpenFileName(self, "Open study setup", "", "Study setup (*.json)")
        if name:
            self.pending_action = "open_setup"
            self.runner.start(partial(open_study_setup, Path(name)))

    def open_forecasting(self):
        if self.study is None or self.session is None or self.runner.busy:
            return
        if not self.study.assignments:
            self.statusBar().showMessage("Sector forecasting requires a prepared folder with bus assignments.", 9000)
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
        self.result_folder = None
        self.plot_element.hide()
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
            self.running_information = {"kind": "base case", "context": settings_information(self.study, settings, "base case")}
            self.invalidate_results("Static base-case FBS started; earlier results cleared.")
            self.run_started = perf_counter()
            self.last_worker_update = self.run_started
            self.last_progress_log = self.run_started
            self.last_heartbeat = self.run_started
            self.run_elapsed_seconds = 0.0
            self.run_clock.start()
            self.runner.start(partial(run_base_case_and_export, deepcopy(self.study), deepcopy(settings),
                                      self.pending_run_output, network_snapshot=self.session.network_snapshot_path()))
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
            kind = "optimization" if optimization else "simulation"
            effective = replace(settings, simulation=effective_simulation(self.study, settings, optimization))
            self.running_information = {"kind": kind, "context": settings_information(self.study, effective, kind)}
            self.runner.start(partial(
                run_and_export, self.study, deepcopy(settings), optimization,
                self.pending_run_output, network_snapshot=self.session.network_snapshot_path(),
                defer_dashboard=True, session_root=self.session.root,
            ))
        except ValueError as error:
            self.show_failure(str(error), "")

    def set_busy(self, busy):
        widget(self,"group_simulation_source").setEnabled(not busy)
        widget(self,"btn_input_window").setEnabled(not busy)
        widget(self, "btn_save_setup").setEnabled(self.study is not None and not busy)
        widget(self, "btn_open_setup").setEnabled(not busy)
        ready = self.settings_dialog.engine_ready
        set_status(widget(self,"lbl_engine_status"),"FBS Numba · Ready" if ready else
            "Solver unavailable" if self.settings_dialog.jit_runner.failure else "Preparing solver…",
            "success" if ready else "error" if self.settings_dialog.jit_runner.failure else "busy")
        widget(self,"lbl_engine_status").setToolTip(widget(self.settings_dialog,"lbl_compute_status").text())
        for name in ("btn_load_data", "btn_settings"):
            widget(self, name).setEnabled(not busy)
        can_forecast = self.study is not None and bool(self.study.assignments)
        forecast = widget(self, "btn_scenarios")
        forecast.setEnabled(can_forecast and not busy)
        forecast.setToolTip("Forecast sector demand and PV" if can_forecast else
                            "Import a prepared case with sector assignments to forecast")
        stop = widget(self, "btn_stop_run")
        stopping = busy and self.pending_action == "run"
        stop.setVisible(stopping)
        stop.setEnabled(stopping)
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

    def show_stage(self, message, *, level="INFO"):
        self.last_worker_update = perf_counter()
        self.last_stage_message = message
        self.logged_progress_phase = None
        if self.runner.busy:
            widget(self, "progress_run").setRange(0, 0)
        self.append_log(message, level=level)

    def append_log(self, message, *, level="INFO"):
        self.append_log_lines((message,), level=level)

    def append_log_lines(self, messages, *, level="INFO"):
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        messages = tuple(messages)
        for message in messages:
            desktop_log.log(getattr(logging, level), "%s", message)
        records = tuple(f"[{level}] {message}" for message in messages)
        if level != "DEBUG" and records:
            widget(self, "run_log").appendPlainText("\n".join(f"[{stamp}] {record}" for record in records))
            self.scroll_log_to_latest()
        if self.session is not None:
            try:
                self.session.append_log_lines(records)
            except OSError as error:
                widget(self, "run_log").appendPlainText(f"[{stamp}] [WARNING] Could not write session log: {error}")

    def scroll_log_to_latest(self):
        scroll = widget(self, "run_log").verticalScrollBar()
        scroll.setValue(scroll.maximum())

    def update_run_clock(self):
        now = perf_counter()
        if self.run_started is not None:
            self.run_elapsed_seconds = now - self.run_started
        widget(self, "lbl_run_elapsed").setText(f"Elapsed {format_duration(self.run_elapsed_seconds)}")
        if (self.run_started is not None and now - self.last_worker_update >= RUN_HEARTBEAT_SECONDS
                and now - self.last_heartbeat >= RUN_HEARTBEAT_SECONDS):
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
        if (boundary or phase != getattr(self, "logged_progress_phase", None)
                or perf_counter() - self.last_progress_log >= RUN_LOG_INTERVAL_SECONDS):
            self.append_log(f"Elapsed {format_duration(self.run_elapsed_seconds)} | {details}")
            self.last_progress_log = perf_counter()
            self.logged_progress_phase = phase

    def show_failure(self, message, details):
        if self.pending_action == "run":
            self.running_information = None
            self.finish_run_clock()
            if self.session is not None and self.pending_run_output is not None:
                try:
                    self.session.record_failure(self.pending_run_output,"base_case" if getattr(self,"pending_base_case",False) else
                        "optimization" if self.pending_run_optimization else "simulation",message,getattr(self,"pending_run_provenance",None))
                except (OSError, ValueError, TypeError) as error:
                    self.append_log(f"Could not save the failure in the session: {error}")
            widget(self, "results_text").setPlainText(f"Run failed after {format_duration(self.run_elapsed_seconds)}\n{message}")
        self.pending_action = ""
        self.show_stage(message, level="ERROR")
        if details:
            self.append_log(details, level="DEBUG")
        self.statusBar().showMessage(message)

    def stop_run(self):
        self.runner.cancel()
        widget(self, "btn_stop_run").setEnabled(False)
        self.statusBar().showMessage("Stopping at the next numerical checkpoint.")

    def run_cancelled(self):
        self.finish_run_clock()
        self.running_information = None
        self.pending_action = ""
        self.last_progress = 0
        self.show_stage("Run cancelled.")
        widget(self, "progress_run").setValue(0)
        widget(self, "progress_run").setFormat("Cancelled")
        self.set_busy(False)

    def job_succeeded(self, result):
        if self.pending_action == "open_setup":
            self.pending_action = ""
            self.attach_study(*result)
            return
        if self.pending_action == "save_setup":
            self.pending_action = ""
            self.show_stage(f"Study setup saved to {result}")
            return
        if self.pending_action == "run":
            try:
                self.finish_run_clock()
                self.report = result
                self.result_folder = None
                alternatives = getattr(result, "alternatives", {})
                self.result_scenario = "best_bess" if "best_bess" in alternatives else next(iter(alternatives), ".")
                base_case = getattr(self, "pending_base_case", False)
                kind = "base case" if base_case else "optimization" if self.pending_run_optimization else "simulation"
                self.completed_information = deepcopy({
                    "kind": kind, "context": result.context, "optimizer": getattr(result.result, "metadata", None),
                })
                self.running_information = None
                if self.pending_run_output is not None and self.session is not None and (base_case or result.saved):
                    if base_case:
                        self.session.record_base_case(self.pending_run_output)
                    elif result.persistence_warning is None:
                        self.session = StudySession.open_for_updates(self.session.root)
                    self.append_log(f"Run files saved in {self.pending_run_output}")
                    self.dashboard_folder = self.result_folder = Path(self.pending_run_output)
                    if result.dashboard_path:
                        self.append_log(f"Dashboard saved to {result.dashboard_path}")
                self.show_full_result_details = False
                widget(self, "results_text").setPlainText(compact_summary(result))
                widget(self, "btn_result_details").setText("Show full details")
                widget(self, "tabs_workspace").setCurrentIndex(1)
                self.result_index = len(self.simulation_steps()) - 1 if self.simulation_steps() else None
                self.refresh_network()
                if isinstance(result.result, OptimizationResult) and result.result.metadata.get("fleet"):
                    fleet = result.result.metadata["fleet"]
                    self.append_log(("Jointly selected batteries at buses: " if self.report.context.get("Simulation settings",{}).get("fleet_dispatch_mode") in ("opf","daily_milp_dispatch") else "Sequentially installed batteries at buses: ") +
                                    ", ".join(str(item["bus_id"]) for item in fleet))
                elif isinstance(result.result, OptimizationResult) and result.result.best_candidate:
                    self.append_log(f"Optimized BESS placed at bus {result.result.best_candidate.bus_id}")
                self.show_stage(f"Run finished in {format_duration(self.run_elapsed_seconds)}; inspect convergence, feasibility and shedding in Results")
                if not base_case and result.persistence_warning:
                    self.append_log(result.persistence_warning, level="WARNING")
                    self.statusBar().showMessage(result.persistence_warning, 15000)
                # Do not hold the numerical result hostage to HTML generation.
                # Start report building on its own worker after Qt has updated the GUI.
                completed_folder = Path(self.pending_run_output) if self.pending_run_output else None
                if completed_folder and (completed_folder / "dashboard_run.json").is_file():
                    QTimer.singleShot(0, lambda folder=completed_folder: self.start_dashboard_build(
                        folder, open_when_ready="browser"))
            except Exception as error:
                self.finish_run_clock()
                self.append_log(f"GUI completion handler failed after numerical run was saved: {type(error).__name__}: {error}")
                self.statusBar().showMessage("Numerical run saved, but the GUI could not present it. See session files.", 12000)
        self.last_progress = 100
        self.set_busy(self.runner.busy)
        widget(self, "progress_run").setValue(100)
        widget(self, "progress_run").setFormat("Completed: %p%")

    def start_dashboard_build(self, folder, *, open_when_ready=False):
        """Build HTML separately while the run is already saved and visible."""
        if self.dashboard_runner.busy:
            self.append_log(f"Dashboard job still active; use Regenerate saved report for {folder}")
            return
        self.dashboard_job_folder = folder
        self.dashboard_open_after_build = open_when_ready
        try:
            self.dashboard_runner.start(partial(regenerate_saved_dashboard, folder))
            self.append_log("Results saved; building HTML independently (you can inspect numerical results now)")
        except Exception as error:
            self.dashboard_failed(str(error), "")

    def dashboard_succeeded(self, path):
        self.append_log(f"Dashboard available: {path}")
        self.dashboard_job_folder = None
        if self.dashboard_open_after_build:
            preference = self.dashboard_open_after_build
            self.dashboard_open_after_build = False
            if preference == "browser":
                if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                    self.append_log(f"Could not open the browser. Open the report from the Dashboard menu: {path}")
            else:
                from .dashboard_viewer import show_dashboard
                show_dashboard(self, path)
        if self.dashboard_folder == Path(path).parent:
            self.statusBar().showMessage("Saved results dashboard ready", 9000)

    def dashboard_failed(self, message, details):
        folder = self.dashboard_job_folder
        self.append_log(f"Dashboard build failed (numerical results saved): {message}", level="ERROR")
        if details:
            self.append_log(details, level="DEBUG")
        if folder is not None:
            try:
                (Path(folder) / "dashboard_error.txt").write_text(message + "\n" + details, encoding="utf-8")
            except OSError:
                pass
        self.dashboard_job_folder = None
        self.dashboard_open_after_build = False
        self.statusBar().showMessage("Dashboard failed; numeric results remain available", 10000)

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

    def plot_selection(self):
        from .dashboard_viewer import show_dashboard
        step = self.selected_step()
        if not self.result_folder or not step:
            return
        path = self.result_folder / "dashboard.html"
        if not path.is_file():
            self.statusBar().showMessage("The saved dashboard is still being built.", 6000)
            return
        kind, entity = self.inspected_element
        show_dashboard(self, path, focus={"group":kind, "entity":str(entity), "timestamp":str(step.timestamp),
                                         "scenario":self.result_scenario})

    def inspector_target(self, kind, entity):
        self.inspected_element = kind, entity
        self.plot_element.setText("Plot " + kind)
        self.plot_element.setVisible(bool(self.result_folder and self.selected_step()))

    def show_bus(self, bus_id):
        if self.study is None:
            return
        from .electrical_details import bus_readings
        network = self.study.network
        bus = next(item for item in network.buses if item.bus_id == bus_id)
        rating = sum(unit.p_rated_kw for unit in network.pv_units if unit.bus_id == bus_id)
        base = [load for load in network.loads if load.bus_id == bus_id]
        self.show_detail_rows(False)
        self.inspector_target("bus", bus_id)
        widget(self, "group_bus_details").setTitle(f"Bus B{bus_id}")
        identity = f"B{bus_id} · {bus.base_kv:g} kV"
        identity += f" · Slack at {bus.v_set_pu:g} pu" if bus.is_slack else " · PQ"
        widget(self, "lbl_bus_id").setText(identity)
        step = self.selected_step()
        voltage = "Not calculated"
        load = f"Base {sum(x.p_base_kw for x in base):g} kW / {sum(x.q_base_kvar for x in base):g} kvar"
        pv = f"Installed {rating:g} kW"
        if step:
            flow, point = step.power_flow, step.operating_point
            config = self.report.context.get("Simulation settings") or {}
            bounds = (config["voltage_min_pu"], config["voltage_max_pu"]) if "voltage_min_pu" in config else None
            info = bus_readings(step, bus, rating, bounds, battery_ratings(self.report.context).get(bus_id))
            voltage = f"{step.timestamp} · {flow.message}"
            if flow.converged:
                voltage += f" | {flow.voltage_mag_pu[bus_id]:.6f} pu · {info['voltage_kv']:.5f} kV · {flow.voltage_angle_deg[bus_id]:.6f}°"
                if bounds:
                    voltage += f" | limits {bounds[0]:g}–{bounds[1]:g} pu, margin {info['voltage_margin_pu']:+.6f} pu"
                for label, key in (("Uncontrolled", "uncontrolled_voltage_pu"), ("Before final correction", "before_correction_voltage_pu")):
                    if info[key] is not None:
                        voltage += f" | {label} {info[key]:.6f} pu"
                load = f"Delivered {point.p_load_kw[bus_id]:g} kW / {point.q_load_kvar[bus_id]:g} kvar"
                pv += f" | Output {point.p_pv_kw[bus_id]:g} kW / {point.q_pv_kvar[bus_id]:g} kvar"
                req = getattr(step, "requested_point", None)
                if req:
                    requested = req.p_load_kw[bus_id]
                    shed = requested - point.p_load_kw[bus_id]
                    load += f" | Requested {requested:g} kW / {req.q_load_kvar[bus_id]:g} kvar"
                    load += f" | Shed {shed:g} kW / {req.q_load_kvar[bus_id]-point.q_load_kvar[bus_id]:g} kvar"
                    if requested:
                        load += f" ({100*shed/requested:.2f}%)"
                    pv += f" | Available {req.p_pv_kw[bus_id]:g} kW / {req.q_pv_kvar[bus_id]:g} kvar, curtailed {req.p_pv_kw[bus_id]-point.p_pv_kw[bus_id]:g} kW"
                if info["bess_soc_percent"] is not None:
                    pv += (f"\nBESS {point.p_bess_kw[bus_id]:g} kW / {point.q_bess_kvar[bus_id]:g} kvar / "
                           f"{info['bess_s_kva']:.3f} kVA · SOC {info['bess_soc_percent']:.2f}% · {info['bess_energy_kwh']:.3f} kWh")
                    if info["bess_rating_kw"] is not None:
                        pv += f" | Rated {info['bess_rating_kw']:g} kW / {info['bess_capacity_kwh']:g} kWh"
                    if info["inverter_rating_kva"] is not None:
                        pv += f" | Inverter {info['inverter_rating_kva']:g} kVA ({info['inverter_loading_percent']:.1f}%)"
            elif getattr(step, "requested_point", None):
                load = "Delivered load unavailable (FBS did not converge)"
            event = getattr(step, "dispatch", None)
            if event:
                from .control_audit import decisions
                actions = [a["action"] for a in decisions(step) if a["bus_id"] == bus_id]
                affected = [item["constraint"] for item in event.evidence.get("constraints", [])
                            if item["type"] in ("undervoltage", "overvoltage") and item["entity"] == str(bus_id)]
                if affected:
                    pv += "\nObserved constraints " + ", ".join(affected)
                if actions:
                    pv += "\n" + ", ".join(actions) + " | " + ", ".join(event.reason_codes or ["Reason not recorded"])
        for name, value in (("voltage", voltage), ("load", load), ("pv", pv)):
            label = widget(self, "lbl_bus_" + name)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setText(value)

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
        self.inspector_target("line", line_id)
        lines.append(f"Ampacity {line.ampacity_a:g} A" if line.ampacity_a else "Ampacity not recorded")
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
            from .electrical_details import branch_readings
            details = branch_readings(flow, line, (parent, child))
            lines.extend((f"End voltages {details['from_voltage_pu']:.6f} / {details['to_voltage_pu']:.6f} pu · "
                          f"angles {details['from_angle_deg']:.5f}° / {details['to_angle_deg']:.5f}° "
                          f"(difference {details['angle_difference_deg']:.5f}°)",
                          f"Receiving {details['receiving_p_kw']:.4f} kW / {details['receiving_q_kvar']:.4f} kvar"))
            if details["loading_percent"] is not None:
                lines.append(f"Loading {details['loading_percent']:.2f}% · " +
                             ("ampacity exceeded" if details["overloaded"] else "within rating"))
        self.show_detail_rows(True)
        widget(self, "group_bus_details").setTitle(f"Line {line_id}")
        widget(self, "lbl_line_details").setText("\n".join(lines))

    def closeEvent(self, event):
        if (self.runner.busy or self.dashboard_runner.busy or self.load_dialog.runner.busy
                or self.settings_dialog.jit_runner.busy):
            event.ignore()
            self.statusBar().showMessage("A job is running. Use Stop run when available or wait for the current job.")
        else:
            super().closeEvent(event)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
