"""Source-level UI regression checks without a Qt window server."""
from pathlib import Path
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'src_accelerated' / 'ui.py').read_text(encoding='utf-8')


def test_designer_toolbar_is_one_compact_row_and_controls_remain():
    tree = etree.parse(str(ROOT / "src_accelerated" / "assets" / "main_window.ui"))
    panel = tree.xpath('//widget[@name="panel_top_actions"]')[0]
    height = panel.xpath('./property[@name="maximumSize"]/size/height')[0].text
    assert int(height) <= 40
    for name in ('btn_load_data','btn_scenarios','btn_run_simulation',
                 'btn_run_base_case','btn_run_optimization','btn_settings',
                 'btn_fit_network','btn_zoom_in','btn_zoom_out','btn_rotate_network'):
        w = tree.xpath(f'//widget[@name="{name}"]')[0]
        assert w.xpath('./property[@name="toolTip"]')
        assert w.xpath('./property[@name="icon"]')
    assert 'def install_primary_toolbar' not in SRC


def test_load_and_forecast_info_go_to_run_log_not_status_bar():
    assert 'lbl_data_status' not in SRC
    assert 'addPermanentWidget' not in SRC
    assert 'Study loaded:' in SRC
    assert 'Forecast selected:' in SRC
    for text in ('hourly steps', 'self.study.request.load_source',
                 'self.study.request.pv_source', 'self.session.root.name'):
        assert text in SRC
    assert 'widget(self, "run_log").appendPlainText(' in SRC
    ui = etree.parse(str(ROOT / 'src_accelerated' / 'assets' / 'main_window.ui'))
    assert not ui.xpath('//widget[@name="lbl_data_status"]')
