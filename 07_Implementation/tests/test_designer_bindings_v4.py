"""Regression coverage for Windows-only QUiLoader ComboBox data loss."""
from pathlib import Path
import pytest

from src_accelerated.ui_bindings import read_designer_combo_data, restore_designer_combo_data

BASE = Path(__file__).resolve().parents[1] / 'src_accelerated' / 'assets'


class FakeCombo:
    def __init__(self, labels):
        self.labels = list(labels)
        self.data = [None] * len(labels)

    def count(self):
        return len(self.labels)

    def itemText(self, index):
        return self.labels[index]

    def setItemData(self, index, data):
        self.data[index] = data

    def itemData(self, index):
        return self.data[index]


def test_settings_backend_and_algorithm_designer_keys():
    declared = read_designer_combo_data(BASE / 'settings_dialog.ui')
    assert [key for _, key in declared['combo_compute_backend']] == ['python', 'numpy', 'numba']
    assert [key for _, key in declared['combo_optimizer_algorithm']] == ['GWO', 'GA']


def test_forecasting_model_designer_keys():
    declared = read_designer_combo_data(BASE / 'forecast_dialog.ui')
    assert [key for _, key in declared['combo_forecast_method']] == ['autoarima', 'arima', 'sarima', 'sarimax']


@pytest.mark.parametrize('file', ['settings_dialog.ui', 'forecast_dialog.ui'])
def test_ui_loader_combo_binding_restores_semantic_values(file):
    declared = read_designer_combo_data(BASE / file)
    # Emulates QUiLoader's visible labels and missing currentData() values.
    fake = {name: FakeCombo([label for label, _ in items]) for name, items in declared.items()}
    assert all(all(v is None for v in control.data) for control in fake.values())
    restore_designer_combo_data(BASE / file, fake.get)
    for name, pairs in declared.items():
        assert fake[name].data == [data for _, data in pairs]


def test_ui_loader_binding_rejects_unexpected_designer_item_order():
    file = BASE / 'settings_dialog.ui'
    declared = read_designer_combo_data(file)
    fake = {name: FakeCombo([label for label, _ in items]) for name, items in declared.items()}
    fake['combo_compute_backend'].labels.reverse()
    with pytest.raises(RuntimeError, match='changed'):
        restore_designer_combo_data(file, fake.get)


def test_ui_loader_binding_rejects_missing_combo():
    with pytest.raises(RuntimeError, match='was not loaded'):
        restore_designer_combo_data(BASE / 'forecast_dialog.ui', lambda _name: None)


def test_designer_binding_works_without_any_ui_changes():
    source = (BASE.parent / 'ui.py').read_text(encoding='utf-8')
    assert 'restore_designer_combo_data(ASSETS / filename' in source
    assert 'self.method.currentData()' in source
    assert 'backend = widget(self, "combo_compute_backend").currentData()' in source
