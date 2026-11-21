"""Saved dashboard lifecycle, offline rendering and portable export."""
from base64 import b64decode, b64encode
from dataclasses import replace
from gzip import decompress
import json
import os
from pathlib import Path
import re
from subprocess import run as run_subprocess
import sys
from zipfile import ZipFile

import pytest

from src_accelerated.dashboard import MANIFEST_FILE, package_dashboard, regenerate_dashboard
from src_accelerated.metrics import EconomicConfig
from src_accelerated.simulation import SimulationConfig
from src_accelerated.ui_workflow import PreparedStudy, RunSettings, run_and_export, run_base_case_and_export
from test_constraint_dispatch import battery, feeder, profiles


def study_for(values, name="Test feeder"):
    return PreparedStudy(feeder(), profiles(values), None,
                         {"Network": name, "PV ratings (kW)": {}, "Clock": "UTC"})


def run_settings(**changes):
    settings = RunSettings(SimulationConfig(reserve_fraction=0, grid_import_limit_kw=100.),
                           EconomicConfig(grid_import_tariff_per_kwh=.1, grid_export_tariff_per_kwh=0.),
                           battery(), {})
    return replace(settings, **changes)


def payload(path):
    html = path.read_text(encoding="utf-8")
    data = re.search(r'data-bytes="\d+">([A-Za-z0-9+/=]+)</script>', html)
    assert data
    return json.loads(decompress(b64decode(data[1])))


def test_report_lifecycle_and_portable_exports(tmp_path, monkeypatch):
    study = study_for([40.] * 14 + [130.] * 2 + [60.] * 23, '<script>alert("study")</script>')
    base = run_base_case_and_export(study, run_settings(), tmp_path / "base")
    simulation = run_and_export(study, run_settings(), False, tmp_path / "simulation")
    assert payload(base.dashboard_path)["scenarios"]["."]["hours"][0]["timestamp"] == "Static base case"
    unpacked = payload(simulation.dashboard_path)
    assert unpacked["manifest"]["timestamp_count"] == 39
    assert unpacked["manifest"]["clock"] == "UTC"
    assert unpacked["scenarios"]["."]["events"][0]["no_bess_shedding_kw"] is None
    assert unpacked["scenarios"]["."]["events"][0]["run_id"] == unpacked["manifest"]["run_id"]
    assert unpacked["metadata"]["context"]["Network"] == study.context["Network"]
    assert '<script>alert("study")</script>' not in simulation.dashboard_path.read_text(encoding="utf-8")
    root = simulation.dashboard_path.parent
    canonical = (root / "hourly.csv").read_bytes()
    regenerated = regenerate_dashboard(root)
    assert payload(regenerated)["manifest"]["run_id"] == unpacked["manifest"]["run_id"]
    package = package_dashboard(root, tmp_path / "report.zip")
    with ZipFile(package) as files:
        assert files.testzip() is None
        assert files.read("hourly.csv") == canonical
        assert files.read(MANIFEST_FILE) == (root / MANIFEST_FILE).read_bytes()
        assert files.read("inputs/load_profile.csv") == (root / "inputs/load_profile.csv").read_bytes()
        assert files.read("dashboard.html") == regenerated.read_bytes()
    (root / "hourly.csv").write_bytes(canonical + b"\n")
    with pytest.raises(ValueError, match="Canonical result file changed"):
        package_dashboard(root, tmp_path / "tampered.zip")

    def fail(_):
        raise OSError("Test renderer unavailable")

    monkeypatch.setattr("src_accelerated.dashboard.regenerate_dashboard", fail)
    stages = []
    failed = run_and_export(study, run_settings(), False, tmp_path / "failed", stage=stages.append)
    assert failed.result.converged and failed.dashboard_path is None
    assert (tmp_path / "failed/hourly.csv").is_file() and (tmp_path / "failed/summary.md").is_file()
    assert "Test renderer unavailable" in stages[-1]


def test_older_saved_results(tmp_path):
    (tmp_path / "hourly.csv").write_text("step_index,timestamp,converged,voltage_min_pu\n0,2021-01-01 00:00:00,True,0.97\n",
                                        encoding="utf-8")
    data = payload(regenerate_dashboard(tmp_path))
    assert data["metadata"]["legacy"] and data["manifest"]["topology_sha256"] is None
    assert data["scenarios"]["."]["hours"][0]["voltage_min_pu"] == .97
    assert data["scenarios"]["."]["events"] == []


def test_no_bess_selection_preserves_real_battery_replay(tmp_path):
    study = study_for([40.] * 8760)
    values = dict(allowed_buses=(2,), spin_eta_charge_percent=90, spin_eta_discharge_percent=90,
                  spin_soc_min_percent=10, spin_soc_max_percent=90, spin_soc_initial_percent=50,
                  spin_opt_power_min_kw=20, spin_opt_power_max_kw=20, spin_opt_power_step_kw=20,
                  spin_opt_energy_min_kwh=100, spin_opt_energy_max_kwh=100, spin_opt_energy_step_kwh=100,
                  spin_gwo_population=3, spin_gwo_iterations=1, spin_gwo_seed=42, spin_cpu_workers=1)
    settings = replace(run_settings(), values=values)
    report = run_and_export(study, settings, True, tmp_path / "opt")
    assert report.result.metadata["no_bess_selected"]
    assert report.result.metadata["best_bess_candidate"]["bus_id"] == 2
    assert report.result.metadata["best_bess_annual_cost"] > report.result.best_objective
    assert "best_bess_replay_mismatch" not in report.result.metadata
    data = payload(report.dashboard_path)
    assert sorted(data["scenarios"]) == ["best_bess", "no_bess"]
    assert len(data["scenarios"]["best_bess"]["hours"]) == len(data["scenarios"]["no_bess"]["hours"]) == 8760
    assert all(row["avoided_shedding_kw"] == 0. for row in data["scenarios"]["best_bess"]["events"])


def test_qt_webengine_interactions_and_pdf(tmp_path, monkeypatch):
    if not os.environ.get("EE499_WEBENGINE_TEST_CHILD"):
        # A renderer startup failure must not terminate the numerical test suite.
        result = run_subprocess(
            [sys.executable, "-m", "pytest", "-q", f"{__file__}::test_qt_webengine_interactions_and_pdf"],
            env={**os.environ, "EE499_WEBENGINE_TEST_CHILD": "1"}, capture_output=True,
            text=True, timeout=80)
        output = result.stdout + result.stderr
        if "Windows fatal exception: code 0x80000003" in output or "1 skipped" in output:
            pytest.skip("Qt WebEngine Chromium renderer could not start under the test host's sandbox or is unavailable")
        assert result.returncode == 0, output
        return
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWebEngineWidgets", reason="PySide6 Qt WebEngine is required for the embedded dashboard test")
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication, QMainWindow
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from src_accelerated.dashboard_viewer import show_dashboard

    run = run_and_export(study_for([40.] * 27, "<img src=x onerror=alert(1)>"),
                         run_settings(), False, tmp_path / "source")
    different = run_and_export(study_for([35.] * 30, "Different clock period"), run_settings(),
                               False, tmp_path / "incompatible")
    matched = run_and_export(study_for([40.] * 27, "Same physical basis"), run_settings(),
                             False, tmp_path / "matched")
    archive = package_dashboard(matched.dashboard_path.parent, tmp_path / "matched.zip")
    app = QApplication.instance() or QApplication([])
    parent = QMainWindow()
    dialog = show_dashboard(parent, run.dashboard_path)
    assert dialog is not None
    view = dialog.findChild(QWebEngineView)
    page = view.page()

    def js(code):
        result = []
        wait = QEventLoop()
        page.runJavaScript(code, lambda value: (result.append(value), wait.quit()))
        if not result:
            QTimer.singleShot(10000, wait.quit)
            wait.exec()
        return result[0] if result else None

    for _ in range(80):
        wait = QEventLoop()
        QTimer.singleShot(100, wait.quit)
        wait.exec()
        if js("document.documentElement.dataset.ready") == "true":
            break
    assert js("document.documentElement.dataset.ready") == "true", js("document.body.innerText")
    assert js("document.querySelectorAll('nav button').length") == 7
    assert js("document.querySelector('#subtitle').textContent.includes('<img src=x')") is True
    assert js("document.querySelectorAll('img').length") == 0
    assert js("performance.getEntriesByType('resource').length") == 0
    assert js("document.querySelectorAll('nav button')[1].click();"
              "document.querySelector('#hour').value=8; document.querySelector('#hour').dispatchEvent(new Event('input'));"
              "const equipment=document.querySelector('#panel select'); equipment.value='Bus:2';"
              "equipment.dispatchEvent(new Event('change'));"
              "document.querySelector('#panel').textContent.includes('Bus 2')") is True
    assert js("document.querySelector('#timestamp').textContent").endswith("08:00:00")
    for index in (2, 3, 4, 5, 6):
        assert js(f"document.querySelectorAll('nav button')[{index}].click(); document.querySelector('#panel').childElementCount") > 0
    assert js("JSON.stringify(bucketed([['2021-01-31 23:00:00', 2, 1], ['2021-02-01 00:00:00', 4, 1],"
              "['2021-02-01 01:00:00', 6, 1]], 'Monthly', 'energy').map(bin => bin.value))") == "[2,10]"
    assert js("JSON.stringify(bucketed([['2021-01-01 00:00:00', 2, 1], ['2021-01-01 01:00:00', 4, 1]],"
              "'Daily', 'average').map(bin => bin.value))") == "[3]"
    for local in (different.dashboard_path, archive):
        encoded = b64encode(local.read_bytes()).decode("ascii")
        js(f"{{ const importer = document.querySelector('#import'); const transfer = new DataTransfer(); "
           f"transfer.items.add(new File([Uint8Array.from(atob('{encoded}'), c => c.charCodeAt(0))], '{local.name}')); "
           "importer.files = transfer.files; importer.dispatchEvent(new Event('change')); }")
    for _ in range(30):
        wait = QEventLoop()
        QTimer.singleShot(100, wait.quit)
        wait.exec()
        if js("document.querySelector('#run').options.length") == 3:
            break
    assert js("document.querySelector('#run').options.length") == 3
    assert js("document.querySelector('#notice').textContent.includes('timestamp coverage')") is True
    assert js("document.querySelector('#notice').textContent.includes('Matched data and comparison basis')") is True
    assert js("document.querySelectorAll('nav button')[2].click();"
              "document.querySelector('canvas').toDataURL('image/png').startsWith('data:image/png;base64,')") is True
    assert js("preparePrint(); document.querySelector('#print-summary').textContent.includes('Economic results')") is True
    pdf = tmp_path / "summary.pdf"
    wait = QEventLoop()
    results = []
    page.pdfPrintingFinished.connect(lambda _, ok: (results.append(ok), wait.quit()))
    page.printToPdf(str(pdf))
    QTimer.singleShot(15000, wait.quit)
    wait.exec()
    assert results == [True]
    assert pdf.read_bytes().startswith(b"%PDF")
    dialog.close()
    parent.close()
    app.processEvents()
