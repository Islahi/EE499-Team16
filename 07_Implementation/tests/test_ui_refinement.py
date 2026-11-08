"""UI presentation regression tests; no desktop display required."""
from pathlib import Path
from types import SimpleNamespace
from lxml import etree

from src_accelerated.ui_presentation import compact_summary


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src_accelerated" / "assets"


def test_qt_designer_files_are_well_formed_and_scenario_page_removed():
    for name in ("main_window.ui", "settings_dialog.ui", "load_data_dialog.ui"):
        tree = etree.parse(str(ASSETS / name))
        assert tree.getroot().tag == "ui"
    settings = etree.parse(str(ASSETS / "settings_dialog.ui"))
    assert not settings.xpath('//widget[@name="page_uncertainty"]')
    assert not settings.xpath('//widget[@name="lbl_wsm_weights"]')
    assert len(settings.xpath('//widget[@name="stack_settings_pages"]/widget[@name]')) == 4


def test_icons_exist_and_are_valid_svg():
    for name in ("folder", "forecast", "play", "network", "optimize", "settings"):
        path = ASSETS / "icons" / (name + ".svg")
        assert path.is_file()
        assert etree.parse(str(path)).getroot().tag.endswith("svg")


def test_main_toolbar_is_owned_by_designer():
    tree = etree.parse(str(ASSETS / "main_window.ui"))
    assert len(tree.xpath('//widget[@name="panel_top_actions"]')) == 1
    assert not tree.xpath('//widget[@name="frame_action"]')
    source = (ROOT / "src_accelerated" / "ui.py").read_text()
    assert "def install_primary_toolbar" not in source
    assert "setWorkingDirectory" in source
    for button in ("btn_load_data", "btn_scenarios", "btn_run_simulation", "btn_run_base_case",
                   "btn_run_optimization", "btn_settings", "btn_fit_network"):
        assert tree.xpath(f'//widget[@name="panel_top_actions"]//widget[@name="{button}"]')


def test_compact_optimization_summary_keeps_key_data_and_no_bess():
    metrics = SimpleNamespace(feasible=True, annual_total_cost=1100, currency="USD",
                              annual_grid_cost=900, grid_import_energy_kwh=4000,
                              loss_energy_kwh=50, load_shedding_energy_kwh=0,
                              curtailment_energy_kwh=0)
    candidate = SimpleNamespace(bus_id=18, power_rating_kw=250, energy_capacity_kwh=500)
    result = SimpleNamespace(best_candidate=candidate, best_objective=1100,
                             metadata={}, success=True)
    report = SimpleNamespace(result=result, metrics=metrics, context={"Network":"33-bus"})
    summary = compact_summary(report)
    for fragment in ("B18", "250.00 kW", "500.00 kWh", "1,100.00 USD/year", "33-bus"):
        assert fragment in summary
    result.best_candidate = None
    result.metadata = {"no_bess_selected": True}
    assert "No BESS" in compact_summary(report)


def test_compact_hourly_summary_preserves_warning_for_infeasibility():
    simulated = SimpleNamespace(steps=[1,2], dt_hours=1, completed=True, converged=True)
    metrics = SimpleNamespace(feasible=False, annual_total_cost=None, annual_grid_cost=None,
                              currency="USD", grid_import_energy_kwh=0, loss_energy_kwh=0,
                              load_shedding_energy_kwh=20, curtailment_energy_kwh=0)
    result=compact_summary(SimpleNamespace(result=simulated, metrics=metrics, context={}))
    assert "Infeasible" in result and "20.00 kWh" in result
