"""Test the offline math renderers and their real desktop consumer."""
from html.parser import HTMLParser

import pytest

from src.dashboard import copy_dashboard, regenerate_dashboard, package_dashboard
from src.equation_rendering import math_image
from src.model_information import model_information, model_reference


def context(basis="kva", method="real_crf"):
    return {
        "FBS settings": {"backend": "numba"},
        "Simulation settings": {"fleet_dispatch_mode": "daily_milp_dispatch"},
        "Optimizer algorithm": "Joint GA",
        "Economic inputs": {
            "power_cost_basis": basis, "annualization_method": method,
            "grid_import_tariff_per_kwh": .00004, "currency": "USD",
        },
    }


@pytest.mark.parametrize("basis,method", [("kva", "real_crf"), ("kw", "straight_line"), (None, None)])
def test_complete_equation_catalogue_typesets_offline(basis, method):
    pytest.importorskip("matplotlib")
    records = model_reference(context(basis, method))["equations"]
    assert len(records) == 8
    for record in records:
        for expression in record["latex"]:
            uri, width, height = math_image(expression)
            assert uri.startswith("data:image/png;base64,iVBOR")
            assert width > 0 and height > 0
    static = model_reference(context(), kind="base case")
    assert len(static["equations"]) == 2  # FBS and explicitly recorded optimizer context
    info = model_information({"kind": "simulation", "context": context(basis, method)}, dashboard=True)
    assert "≈0 USD" in info["Current parameters"]
    assert "Equation renderer unavailable" not in info["Mathematical equations"]


def test_unknown_legacy_equation_remains_escaped():
    legacy = {"version": 1, "equations": [["Old solver", "<img src=x>", "Recorded note"]]}
    html = model_information({"kind": "simulation", "context": {"Model reference": legacy}})["Mathematical equations"]
    assert "Archived equation text" in html
    assert "&lt;img src=x&gt;" in html
    assert "<img" not in html


def test_qt_information_equation_images_loaded_and_context_changes():
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QTextDocument
    from PySide6.QtWidgets import QApplication, QTextBrowser
    from src.ui import InformationDialog

    app = QApplication.instance() or QApplication([])
    old = {"Model reference": {"version": 1, "equations": [["Old solver", "Recorded expression", "Note"]]}}
    dialog = InformationDialog([("Current", {"kind": "optimization", "context": context()}, None),
                                ("Archived", {"kind": "simulation", "context": old}, None)])
    dialog.show()
    app.processEvents()
    browser = dialog.findChild(QTextBrowser, "information_equations")
    document = browser.document()
    block = document.begin()
    count = 0
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fmt = it.fragment().charFormat()
            if fmt.isImageFormat():
                url = QUrl(fmt.toImageFormat().name())
                image = document.resource(QTextDocument.ResourceType.ImageResource, url)
                assert image is not None and not image.isNull()
                count += 1
            it += 1
        block = block.next()
    assert count >= 20
    assert "\\frac" not in browser.toPlainText()
    dialog.context_picker.setCurrentIndex(1)
    assert "Recorded expression" in browser.toPlainText()
    assert "Archived equation text" in browser.toPlainText()
    dialog.close()


def test_portable_report_optionally_includes_exact_layout_and_images(tmp_path):
    from zipfile import ZipFile
    from json import loads

    folder = tmp_path / "run"
    folder.mkdir()
    source = folder / "hourly.csv"
    source.write_bytes(b"timestamp,dt_hours,requested_load_kw\n2021-01-01 00:00:00,1,1234.123499\n")
    report = regenerate_dashboard(folder)
    copied = copy_dashboard(folder, tmp_path / "offline.html")
    assert copied.read_bytes() == report.read_bytes()
    with pytest.raises(ValueError, match="canonical"):
        copy_dashboard(folder, source)
    layout = tmp_path / "layout.json"
    layout.write_text('{"version":1,"numeric_evidence":1.00004}', encoding="utf-8")
    archive = package_dashboard(folder, tmp_path / "report.zip", attachments=[layout])
    with ZipFile(archive) as zipped:
        assert zipped.read("dashboard.html") == report.read_bytes()
        assert zipped.read("hourly.csv") == source.read_bytes()
        assert zipped.read("report_exports/layout.json") == layout.read_bytes()
        assert "report_exports/layout.json" not in loads(zipped.read("dashboard_manifest.json"))["files"]
    with pytest.raises(ValueError, match="filename"):
        package_dashboard(folder, tmp_path / "duplicated.zip", attachments=[layout, layout])

