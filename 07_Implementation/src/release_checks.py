"""Exercise a small native release through its actual numerical and Qt paths."""
import csv
from dataclasses import asdict, replace
from hashlib import sha256
import inspect
import json
from pathlib import Path
from time import perf_counter
from zipfile import ZipFile


def numerical_fixture(output, workers=2, level="summary", reports=True):
    import pandas as pd
    from openpyxl import Workbook
    from src.fleet_ga_optimizer import FleetGAConfig, run_joint_fleet_ga
    from src.metrics import EconomicConfig
    from src.optimizer import BESSCandidate, BESSParameters, OptimizationBounds, SimulationEvaluator
    from src.representative_days import RepresentativeDay, ScenarioSet
    from src.simulation import ConstraintAwareDispatch, SimulationConfig
    from src.ui_workflow import DataRequest, RunSettings, prepare_study, run_and_export, run_base_case_and_export

    output.mkdir(parents=True, exist_ok=True)
    source = output / "Prepared folder with spaces"
    source.mkdir(exist_ok=True)
    workbook = output / "Three bus feeder.xlsx"
    book = Workbook()
    book.active.title = "Network"
    book.active.append(("parameter", "value"))
    book.active.append(("base_power_kva", 1000))
    book.active.append(("frequency_hz", 60))
    sheets = {
        "Buses": [("bus_id", "base_kv", "is_slack", "v_set_pu"),
                  (1, 12.66, True, 1), (10, 12.66, False, 1), (2, 12.66, False, 1)],
        "Loads": [("load_id", "bus_id", "p_base_kw", "q_base_kvar"),
                  ("D2", 2, 80, 20), ("D10", 10, 120, 25)],
        "Lines": [("line_id", "from_bus", "to_bus", "r_ohm", "x_ohm", "ampacity_a"),
                  ("Feeder 1-10", 1, 10, .24, .14, 80), ("Lateral 10-2", 10, 2, .45, .1, None)],
    }
    for name, rows in sheets.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    book.save(workbook)
    times = pd.date_range("2020-02-29", periods=24, freq="h")
    profile = source / "load_profile.csv"
    with profile.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("timestamp", "bus_id", "p_kw", "q_kvar"))
        for i, stamp in enumerate(times):
            writer.writerow((stamp, 2, 80 + (i % 7) * 6, 20))
            writer.writerow((stamp, 10, 120 + (i % 9) * 10, 25))
    (source / "bus_assignments_used.csv").write_text("bus_id,category\n2,commercial\n10,manufacturing\n")
    (source / "manifest.json").write_text(json.dumps({
        "clock": "UTC", "network_sha256": sha256(workbook.read_bytes()).hexdigest(),
        "profile_hashes_sha256": {profile.name: sha256(profile.read_bytes()).hexdigest()},
    }))
    study = prepare_study(DataRequest(workbook, None, "auto", None, 1, "none",
                                      load_source="distributed", dataset_folder=source))
    sim = SimulationConfig(fleet_dispatch_mode="daily_milp_dispatch")
    economics = EconomicConfig(cost_per_kwh=200., cost_per_kw=175.,
                               grid_import_tariff_per_kwh=.1, grid_export_tariff_per_kwh=.02)
    battery = BESSParameters(.95, .95)
    settings = RunSettings(sim, economics, None, {}, compare_corrective_actions=True)
    bounds = OptimizationBounds((2, 10), (30., 60.), (60., 120.))
    day = RepresentativeDay(0, 0, times[0], 365., 1., study.profiles, 0.)
    day_set = ScenarioSet((day,), 365, 8760)
    evaluator = SimulationEvaluator(economics, battery, ConstraintAwareDispatch(), sim)
    config = FleetGAConfig(population_size=8, max_generations=4, stall_generation_limit=2, workers=workers, seed=29)
    optional = {"diagnostics_level": level} if "diagnostics_level" in inspect.signature(run_joint_fleet_ga).parameters else {}
    started = perf_counter()
    ga = run_joint_fleet_ga(study.network, day_set, bounds, evaluator, max_units=3, ga_config=config, **optional)
    elapsed = perf_counter() - started
    assert ga["unique_evaluated"] > 1 and ga["ranked"][0].feasible
    assert ga["config"]["workers"] == workers
    ranked = [{k: v for k, v in asdict(item).items() if k != "elapsed_seconds"} for item in ga["ranked"]]
    diagnostic = ga.get("academic_diagnostics")
    if diagnostic:
        assert diagnostic["status"] == "recorded" and diagnostic["effective_workers"] == workers
        assert diagnostic["generations"][-1]["unique_total"] == ga["unique_evaluated"]
        assert all(g["new"] + g["previous"] + g["duplicates"] == g["slots"] for g in diagnostic["generations"])
        assert sum(g["new"] for g in diagnostic["generations"]) == ga["unique_evaluated"]
        assert [g["best_so_far"] for g in diagnostic["generations"]] == ga["history"]
    static_dir, pair_dir, fleet_dir = (output / name for name in ("Static base", "Paired operation", "Manual fleet"))
    paths = []
    if reports:
        report = run_base_case_and_export(study, settings, static_dir)
        assert report.result.converged
        pair = run_and_export(study, settings, False, pair_dir)
        assert all(result.completed and result.converged for result, _ in pair.alternatives.values())
        manual = replace(settings, compare_corrective_actions=False, manual_bess_fleet=(
            battery.build_config(BESSCandidate(2, 30., 60.)), battery.build_config(BESSCandidate(10, 30., 60.)),
        ))
        fleet = run_and_export(study, manual, False, fleet_dir)
        assert fleet.result.completed and fleet.result.converged and len(fleet.result.steps) == 24
        paths = [static_dir / "dashboard.html", pair.dashboard_path, fleet.dashboard_path]
    data_paths = [static_dir / name for name in ("bus_voltages.csv", "line_flows.csv")]
    data_paths += [folder / name for folder in (pair_dir / "uncontrolled", pair_dir / "controlled", fleet_dir)
                   for name in ("hourly.csv", "branches.csv", "buses.csv", "metrics.csv", "fleet_hourly.csv", "battery_daily_audit.csv")]
    data = {p.relative_to(output).as_posix(): sha256(p.read_bytes()).hexdigest() for p in data_paths if p.is_file()}
    signature = {k: ga[k] for k in ("history", "generations", "unique_evaluated", "visited_bus_ids", "stop_reason", "config")}
    signature.update(ranked=ranked, canonical_file_hashes=data)
    result = {"signature": signature, "elapsed_seconds": elapsed, "workers": workers, "dashboard_paths": [str(p) for p in paths],
              "diagnostic_bytes": len(json.dumps(diagnostic, separators=(",", ":"))) if diagnostic else 0}
    (output / "Numerical_Check.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if diagnostic:
        (output / "Recorded_GA.json").write_text(json.dumps(diagnostic, indent=2), encoding="utf-8")
    return result


def browser_fixture(output, paths):
    from PySide6.QtCore import QEventLoop, QTimer, QUrl
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication
    from openpyxl import load_workbook
    from src.ui import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    exports = output / "Browser exports"
    exports.mkdir(exist_ok=True)
    external = []

    class Offline(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, request):
            url = request.requestUrl()
            if url.scheme() in ("http", "https", "ftp"):
                external.append(url.scheme())
                request.block(True)

    profile = QWebEngineProfile()
    guard = Offline(profile)
    profile.setUrlRequestInterceptor(guard)
    view = QWebEngineView(window)
    page = QWebEnginePage(profile, view)
    view.setPage(page)
    view.resize(1180, 800)
    view.show()

    def download(item):
        item.setDownloadDirectory(str(exports.resolve()))
        item.accept()

    profile.downloadRequested.connect(download)

    def wait_for(read, milliseconds=15000):
        loop, timer, schedule = QEventLoop(), QTimer(), QTimer()
        timer.setSingleShot(True)
        result = []

        def receive(value):
            if value:
                result.append(value)
                loop.quit()

        schedule.timeout.connect(lambda: read(receive))
        timer.timeout.connect(loop.quit)
        timer.start(milliseconds)
        schedule.start(100)
        loop.exec()
        schedule.stop()
        return result[0] if result else None

    def js(source, description):
        page.runJavaScript("window.releaseProbe = null; Promise.resolve().then(async()=>{" + source +
                           "}).then(()=>window.releaseProbe='OK', e=>window.releaseProbe='FAIL: '+e.message);")
        value = wait_for(lambda done: page.runJavaScript("window.releaseProbe", done))
        if value != "OK":
            raise RuntimeError(f"{description}: {value or 'Qt check timed out'}")

    def ready(path, size_limit=None):
        assert Path(path).is_file(), str(path)
        if size_limit and Path(path).stat().st_size > size_limit:
            raise RuntimeError("Report is larger than the selected fixture size limit")
        view.load(QUrl.fromLocalFile(str(Path(path).resolve())))
        value = wait_for(lambda done: page.runJavaScript(
            "document.readyState==='complete'&&document.querySelector('#tabs button')?.textContent==='Summary'&&"
            "Boolean(document.querySelector('#content section'))", done), milliseconds=60000)
        if not value:
            raise RuntimeError("Offline report did not render: "+str(path))

    static, pair, fleet = paths
    ready(static)
    js("""
       const tab=id=>document.querySelector('#tabs [data-topic="'+id+'"]');
       if(tab('Summary').getAttribute('aria-selected')!=='true')throw Error('Numerical landing failed');
       if(document.querySelector('#content canvas'))throw Error('Landing rendered unsolicited charts');
       tab('Network').click();
       await new Promise(r=>setTimeout(r,650));
       if(document.querySelector('.academic-body .warning'))throw Error('Network profile warning');
       if(!document.querySelector('.feeder [data-entity="10"]'))throw Error('Feeder bus 10 unavailable');
       const card=document.querySelector('.academic-figure');
       if(!card)throw Error(document.querySelector('.academic-body')?.textContent||'Missing voltage chart');
       const record=card.publicationRecord, data=record.controller.publicationData();
       if(data.axis.join(',')!=='1,2,10')throw Error('Bus order: '+data.axis.join(','));
       if(data.traces[0].data.length!==3||!data.traces[0].data.every(Number.isFinite))throw Error('Bus readings missing');
       const g=publicationGeometry(data,record.meta);
       const base='verified_voltage';
       saveBlob(new Blob([publicationSvg(g)],{type:'image/svg+xml'}),base+'.svg');
       saveBlob(publicationPdf(g),base+'.pdf');
       saveBlob(await publicationPng(g,300),base+'.png');
       const exact=publicationReadout(data,record.meta);
       saveRows(exact.head,exact.rows,base+'.csv');
       saveBlob(publicationXlsx(exact.head,exact.rows),base+'.xlsx');
       saveBlob(new Blob([publicationTex(exact.head,exact.rows)]),base+'.tex');
       const table=document.querySelector('.academic-table').publicationRecord;
       saveBlob(await publicationPackage([record,table], record.meta.ctx,'Network',new Set(['pdf','xlsx','tex'])),
         'verified_academic_package.zip');
       """, "static voltage and academic exports")
    expected = ["verified_voltage."+ext for ext in ("svg", "pdf", "png", "csv", "xlsx", "tex")] + ["verified_academic_package.zip"]
    downloaded = wait_for(lambda done: done(all((exports / name).is_file() for name in expected)))
    if not downloaded:
        raise RuntimeError("Downloads missing: "+", ".join(name for name in expected if not (exports / name).is_file()))
    ready(pair)
    js("""
       document.querySelector('[data-topic="Power & Energy"]').click();
       await new Promise(r=>setTimeout(r,650));
       if(document.querySelectorAll('.academic-figure canvas').length<2)
         throw Error(document.querySelector('.academic-body')?.textContent||'No service plots');
       const selector=document.querySelector('.academic-controls select');
       selector.value='sankey';selector.dispatchEvent(new Event('change'));
       await new Promise(r=>setTimeout(r,550));
       if(!document.querySelector('.publication-preview')?.naturalWidth)
         throw Error(document.querySelector('.academic-body')?.textContent||'Energy flow unavailable');
       """, "paired simulation and energy flow")
    ready(fleet)
    js("""
       document.querySelector('[data-topic="BESS"]').click();
       await new Promise(r=>setTimeout(r,650));
       if(document.querySelectorAll('.academic-figure canvas').length!==2)
         throw Error(document.querySelector('.academic-body')?.textContent||'Battery charts unavailable');
       """, "manual fleet report")

    assert not external, f"Remote requests: {external}"
    assert b"/Subtype /Image" not in (exports / "verified_voltage.pdf").read_bytes()
    assert (exports / "verified_voltage.pdf").read_bytes().startswith(b"%PDF-")
    with (exports / "verified_voltage.png").open("rb") as stream:
        from struct import unpack
        header = stream.read(54)
        assert header[:8] == b"\x89PNG\r\n\x1a\n"
        assert unpack(">II", header[16:24]) == (1890, 1228)
        assert b"pHYs" in header
    workbook = load_workbook(exports / "verified_voltage.xlsx", data_only=True, read_only=True)
    try:
        rows = list(workbook.active.values)
        assert [int(row[0]) for row in rows[1:]] == [1, 2, 10]
    finally:
        workbook.close()
    with ZipFile(exports / "verified_academic_package.zip") as archive:
        assert archive.testzip() is None
        assert {"Figure_Index.csv", "Study_Manifest.json", "README.md"} <= set(archive.namelist())
    page.deleteLater()
    view.close()
    window.close()
    app.processEvents()
    return {"external_requests": len(external), "exports": expected, "reports_verified": 3, "desktop_window_created": True}


def pv_boundary_fixture(output):
    """Exercise PV bounds and the real fallback in the installed executable."""
    from types import SimpleNamespace
    from unittest.mock import patch

    import numpy as np

    from src import joint_opf
    from src.fbs import OperatingPoint, prepare_fbs
    from src.network_model import Bus, Line, NetworkModel, PVUnit
    from src.simulation import SimulationConfig

    network = NetworkModel(
        [Bus(1, "Slack", 12.66, True), Bus(2, "PV", 12.66)],
        [Line("1-2", 1, 2, .12, .05)], [], [PVUnit("PV2", 2, 10.375)], 1000., 60.,
    )
    settings = SimulationConfig(fleet_dispatch_mode="daily_milp_dispatch",
                                allow_load_shedding=False, grid_export_limit_kw=0.)
    zeros = {1: 0., 2: 0.}
    available = 3.125
    point = OperatingPoint(zeros, zeros, {1: 0., 2: available}, zeros, zeros, zeros)
    solve = prepare_fbs(network, settings.fbs_config)
    raw = solve(point)
    diagnostics = []
    for deviation, expected in ((5e-8, "clamped"), (1e-5, "fallback")):
        def solver(cost, **kwargs):
            assert kwargs["bounds"][0] == (0., available)
            values = np.zeros(len(cost))
            values[0] = available + deviation
            return SimpleNamespace(success=True, x=values)

        controller = joint_opf.JointOPFController(network, settings, solve)
        with (patch.object(joint_opf, "linprog", solver),
              patch.object(joint_opf, "record_opf_pv_boundary", diagnostics.append)):
            final, flow, _, _, audit = controller.dispatch(point, raw, (), {}, {})
        assert diagnostics[-1]["action"] == expected
        assert flow.converged and 0. <= final.p_pv_kw[2] <= available
        if expected == "clamped":
            assert final.p_pv_kw[2] == 0. and audit["status"] == "opf_verified_1"
        else:
            assert controller.opf_fallbacks == 1
    (output / "Injected_PV_Boundary_Check.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")


def run_release_check(output):
    """Write a machine-readable report even when windowed stdout is unavailable."""
    import traceback
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    try:
        pv_boundary_fixture(output)
        numeric = numerical_fixture(output, 2, "summary")
        browser = browser_fixture(output, numeric["dashboard_paths"])
        status = {"status": "passed", "injected_pv_boundary_check": "passed", "ga_workers": 2,
                  "unique_candidates": numeric["signature"]["unique_evaluated"], **browser}
        code = 0
    except Exception:
        status = {"status": "failed", "traceback": traceback.format_exc()}
        code = 1
    (output / "Release_Check.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    return code
