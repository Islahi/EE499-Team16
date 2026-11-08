"""Qt-Designer UI structure checks; no display server required."""
from pathlib import Path
from lxml import etree
import ast

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src_accelerated" / "assets"
MAIN = etree.parse(str(ASSETS / "main_window.ui"))
SETTINGS = etree.parse(str(ASSETS / "settings_dialog.ui"))


def test_no_runtime_primary_toolbar_or_permanent_settings_construction():
    ui_source = (ROOT / 'src_accelerated' / 'ui.py').read_text()
    ast.parse(ui_source)
    assert 'def install_primary_toolbar' not in ui_source
    assert 'def add_runtime_controls' not in ui_source
    assert 'def polish_settings_layout' not in ui_source
    assert 'setWorkingDirectory' in ui_source


def test_single_toolbar_contains_primary_and_network_view_actions():
    panel = MAIN.xpath('//widget[@name="panel_top_actions"]')[0]
    controls = {w.get('name') for w in panel.xpath('.//widget[@class="QPushButton"]')}
    assert controls == {'btn_load_data','btn_scenarios','btn_run_simulation',
                        'btn_run_base_case','btn_run_optimization','btn_settings',
                        'btn_fit_network','btn_zoom_out','btn_zoom_in','btn_rotate_network'}
    assert not MAIN.xpath('//widget[@name="frame_action"]')
    assert not MAIN.xpath('//widget[@name="menubar"]')
    assert not MAIN.xpath('//widget[@name="panel_log_header"]')
    assert MAIN.xpath('//widget[@name="tabs_workspace"]')
    assert MAIN.xpath('//widget[@name="run_log"]')
    for w in panel.xpath('.//widget[@class="QPushButton"]'):
        assert w.xpath('./property[@name="toolTip"]/string')
        icon_file = w.xpath('./property[@name="icon"]/iconset/normaloff')[0].text
        assert (ASSETS / icon_file).exists()


def test_all_live_optimizer_settings_defined_in_designer():
    names = {x.get('name') for x in SETTINGS.xpath('//widget[@name]')}
    needed = {'combo_dispatch_policy','spin_terminal_soc_percent','group_terminal_soc',
              'combo_optimizer_algorithm','spin_ga_population','spin_ga_generations',
              'spin_ga_crossover','spin_ga_mutation','spin_discount_rate',
              'spin_bess_lifetime','spin_annual_om_percent','spin_curtailment_penalty',
              'spin_shedding_penalty','spin_grid_import_tariff','spin_grid_export_tariff',
              'spin_fixed_cost','combo_compute_backend','spin_cpu_workers',
              'spin_opt_power_step_kw','spin_opt_energy_step_kwh',
              'btn_select_all_buses','btn_clear_allowed_buses','lbl_allowed_bus_count'}
    assert needed <= names
    assert len(names)==len(SETTINGS.xpath('//widget[@name]'))
    assert all(t.text in names for t in SETTINGS.xpath('//tabstop'))
    algorithm = SETTINGS.xpath('//widget[@name="combo_optimizer_algorithm"]')[0]
    assert [n.text for n in algorithm.xpath('./item/property[@name="userData"]/string')] == ['GWO','GA']
    backend = SETTINGS.xpath('//widget[@name="combo_compute_backend"]')[0]
    assert [n.text for n in backend.xpath('./item/property[@name="userData"]/string')] == ['python','numpy','numba']


def test_no_number_tag_for_double_spinbox_settings():
    for spin in SETTINGS.xpath('//widget[@class="QDoubleSpinBox"]'):
        for prop in spin.xpath('./property[@name="value" or @name="minimum" or @name="maximum"]'):
            assert prop[0].tag == 'double'


def test_no_broken_widget_references_in_all_designer_forms():
    for filename in ('main_window.ui', 'settings_dialog.ui', 'load_data_dialog.ui'):
        tree = etree.parse(str(ASSETS / filename))
        widgets=[w.get('name') for w in tree.xpath('//widget[@name]')]
        assert len(widgets)==len(set(widgets)), filename
        assert all(stop.text in widgets for stop in tree.xpath('//tabstop')), filename


def test_forecast_dialog_controls_defined_in_designer():
    tree = etree.parse(str(ASSETS / 'forecast_dialog.ui'))
    assert {w.get('name') for w in tree.xpath('//widget[@class="QSpinBox"]')} == {
        'spin_forecast_horizon','spin_forecast_training','spin_forecast_validation'}
    assert tree.xpath('//widget[@name="combo_forecast_method"]')
    assert tree.xpath('//widget[@name="btn_generate_forecast"]')
    source=(ROOT / 'src_accelerated' / 'ui.py').read_text()
    assert 'load_form(self, "forecast_dialog.ui")' in source
