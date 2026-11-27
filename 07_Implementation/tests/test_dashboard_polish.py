import json

import pytest

from src.dashboard_health import FeederHealth
from src.information_provenance import provenance_records
from src.model_information import model_information


def test_annual_health_counts_violations_across_saved_run_and_keeps_unknown_ratings():
    hours = [{"dt_hours": 1., "converged": i != 8758} for i in range(8760)]
    stamps = [str(i) for i in range(len(hours))]
    health = FeederHealth(hours, stamps, {"window": {"hours": 8760}}, {
        "voltage_min_pu": .95, "voltage_max_pu": 1.05,
    }, {})
    for i in range(8760):
        failed = i == 8758
        health.update("bus", "6", i, {
            "voltage_pu": None if failed else .94 if i < 300 else 1.,
            "voltage_violation": None if failed else i < 300,
            "uncontrolled_voltage_pu": .93 if i < 450 else .99, "shed_kwh": 1.5 if i < 450 else None,
        })
        health.update("line", "L1", i, {
            "current_a": None if failed else 160., "loss_p_kw": None if failed else .2,
        })
    result = health.report()
    bus = result["bus"]["6"]
    line = result["line"]["L1"]
    assert result["samples"] == result["expected"] == 8760 and result["converged"] == 8759 and result["failed"] == 1
    assert bus["violation"]["affected_hours"] == 300
    assert bus["violation"]["samples"] == 8759
    assert bus["pre_violation"]["affected_hours"] == 450
    assert bus["shed_kwh"]["sum"] == 675
    assert line["current_a"]["max"] == 160
    assert line["loss_kwh"]["sum"] == pytest.approx(8759*.2)
    assert "loading_percent" not in line and "overload" not in line


def test_ampacity_from_original_topology_uses_recorded_readings():
    health = FeederHealth([{"dt_hours": 0.5, "converged": True}], ["2021-01-01 00:00:00"], {}, {},
                          {"lines": [{"line_id": "L1", "ampacity_a": 10.}]})
    health.update("line", "L1", 0, {"current_a": 20., "loss_p_kw": 0., "loss_q_kvar": 3.})
    result = health.report()["line"]["L1"]
    assert result["loading_percent"]["max"] == 200
    assert result["overload"]["affected_hours"] == .5
    assert result["loss_kvarh"]["sum"] == 1.5
    assert result["loss_kwh"]["sum"] == 0


def solar_fixture():
    paths = [fr"\\laboratory\research archive\Spain\Bilbao\NASA POWER\<script>& irradiance {i}.csv" for i in range(10)]
    return {
        "source": "nasa_power", "target": "modeled electrical kW", "folder": paths[0],
        "site": {"latitude": 43.263481, "longitude": -2.93522, "name": "Bilbao"},
        "source_clock": "UTC", "capacity_kw": 6000, "model": "EE499 piecewise GHI",
        "critical_irradiance_w_m2": 120, "standard_irradiance_w_m2": 1000,
        "verified": False, "hashes": {name: f"{i+16:064x}" for i, name in enumerate(paths)},
    }


def test_nested_provenance_compact_and_raw_preserved(tmp_path):
    solar = solar_fixture()
    context = {"Source files": {"network": r"C:\Test space\IEEE_33Bus.xlsx",
                                "load": r"C:\Archive\GoiEner total load\input.csv", "solar": solar},
               "FBS settings": {"voltage_tolerance_pu": 1e-9},
               "Effective Joint GA settings": {"seed": list(range(80))}}
    metadata = {"kind": "optimization", "context": context}
    encoded = json.dumps(metadata, ensure_ascii=False)
    text = model_information(metadata)["Current parameters"]
    assert "NASA POWER · modeled PV" in text
    assert "PV provenance" in text and "Bilbao" in text and "6000" in text
    assert "GoiEner distributed load" in text and "IEEE_33Bus.xlsx" in text
    assert "1.00e-09" in text
    assert "80 recorded items" in text
    assert "<script>" not in text and "laboratory" not in text
    assert provenance_records(metadata, {})["Source files"]["solar"] == solar
    html = model_information(metadata, dashboard=True)["Current parameters"]
    assert "Source files &amp; integrity" in html and "&lt;script&gt;" in html
    assert next(iter(solar["hashes"].values())) in html
    assert json.dumps(metadata, ensure_ascii=False) == encoded


def test_legacy_source_repr_kept_verbatim_in_detail_without_execution():
    raw = "{'source': '<script>alert(1)</script>', 'files': ['test']}"
    meta = {"kind": "simulation", "context": {"Source files": {"solar": raw}}}
    desktop = model_information(meta)["Current parameters"]
    html = model_information(meta, dashboard=True)["Current parameters"]
    assert "Archived PV provenance" in desktop and "alert" not in desktop
    assert "&lt;script&gt;alert(1)" in html and "<script>" not in html
    assert provenance_records(meta, {})["Source files"]["solar"] == raw


def test_qt_provenance_modal_contains_original_metadata_and_copies_it(monkeypatch):
    from PySide6.QtWidgets import QApplication, QDialog, QPlainTextEdit, QPushButton, QTextBrowser

    from src.ui import InformationDialog

    app = QApplication.instance() or QApplication([])
    solar = solar_fixture()
    meta = {"kind": "simulation", "context": {"Source files": {"solar": solar}}}
    dialog = InformationDialog([("Current", meta, None)])
    compact = dialog.findChild(QTextBrowser, "information_parameters")
    assert "NASA POWER · modeled PV" in compact.toPlainText()
    assert "laboratory" not in compact.toPlainText()

    def inspect(modal):
        text = modal.findChild(QPlainTextEdit)
        assert text.isReadOnly()
        assert json.loads(text.toPlainText())["Source files"]["solar"] == solar
        copy = next(button for button in modal.findChildren(QPushButton) if button.text() == "Copy all")
        copy.click()
        assert app.clipboard().text() == text.toPlainText()
        return 0

    monkeypatch.setattr(QDialog, "exec", inspect)
    dialog.findChild(QPushButton, "btn_information_provenance").click()
    dialog.close()

