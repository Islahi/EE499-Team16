"""Regression checks for removal of out-of-scope dispatch/transformer options."""
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from src_accelerated.simulation import GridAwareDispatchPolicy, SimulationConfig


def _slice(load_kw, pv_kw):
    return SimpleNamespace(p_load_kw={2: load_kw}, p_pv_kw={2: pv_kw})


def test_removed_policy_and_transformer_constraint_from_config():
    from src_accelerated import simulation
    assert not hasattr(simulation, 'NetLoadTargetPolicy')
    assert 'transformer_limit_kva' not in {f.name for f in fields(SimulationConfig)}
    assert 'target_kw' not in {f.name for f in fields(GridAwareDispatchPolicy)}


def test_grid_aware_dispatch_requests_are_preserved():
    policy = GridAwareDispatchPolicy()
    assert policy(0, _slice(100, 160), None) == -60
    assert policy(1, _slice(100, 35), None) == 65
    assert policy(2, _slice(100, 100), None) == 0
    with_import_cap = GridAwareDispatchPolicy(import_limit_kw=30)
    assert with_import_cap(0, _slice(100, 35), None) == 35
    with_export_cap = GridAwareDispatchPolicy(export_limit_kw=10)
    assert with_export_cap(0, _slice(100, 160), None) == -50


def test_out_of_scope_controls_removed_from_active_gui():
    source = (Path(__file__).parents[1] / 'src_accelerated/ui.py').read_text()
    assert 'spin_dispatch_target_kw' not in source
    assert 'spin_transformer_kva' not in source
    assert 'Net-load target' not in source
    settings = (Path(__file__).parents[1] / 'src_accelerated' / 'assets' / 'settings_dialog.ui').read_text()
    assert 'Grid-aware rule' in settings
