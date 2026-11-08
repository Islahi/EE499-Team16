"""Live Qt loader smoke test; runs on Windows with PySide6 installed."""
import pytest


def test_real_qt_loader_restores_combo_ids(monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication, QDialog
    from src_accelerated.ui import load_form, widget

    app = QApplication.instance() or QApplication([])
    settings = QDialog()
    load_form(settings, 'settings_dialog.ui')
    compute = widget(settings, 'combo_compute_backend')
    compute.setCurrentIndex(2)
    assert compute.currentText() == 'Numba compiled (CPU)'
    assert compute.currentData() == 'numba'
    algo = widget(settings, 'combo_optimizer_algorithm')
    algo.setCurrentIndex(1)
    assert algo.currentData() == 'GA'

    forecast = QDialog()
    load_form(forecast, 'forecast_dialog.ui')
    chooser = widget(forecast, 'combo_forecast_method')
    assert chooser.currentData() == 'autoarima'
    chooser.setCurrentIndex(3)
    assert chooser.currentData() == 'sarimax'

    settings.deleteLater()
    forecast.deleteLater()
    assert app is not None
