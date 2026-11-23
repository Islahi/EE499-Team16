"""Desktop defaults and legacy replay of daily dispatch settings."""
import pytest

from src.saved_schema import upgrade_saved_fields
from src.simulation import SimulationConfig


@pytest.mark.parametrize("hours", [24, 48, 72])
def test_saved_dispatch_config_accepts_historical_horizons(hours):
    settings = {"fleet_dispatch_mode": "sindi_strict", "sindi_horizon_hours": hours,
                "sindi_min_power_factor": .92, "opf_bess_kva_multiplier": 1.22}
    replay = SimulationConfig.from_saved_settings(settings)
    assert replay.dispatch_horizon_hours == hours
    assert replay.minimum_discharge_pf == .92
    assert replay.effective_bess_inverter_kva_per_kw == 1.22
    assert replay.fleet_dispatch_mode == "daily_milp_dispatch"
    assert settings["sindi_horizon_hours"] == hours


def test_legacy_dashboard_and_optimizer_aliases_are_read():
    prior = {"simulation": {"fleet_dispatch_mode": "sindi_strict", "sindi_strict_pf_min": .91},
             "optimizer": {"sindi_ga": {"generations": 3}},
             "spin_ga_generations": 20, "spin_max_generations": 12}
    updated = upgrade_saved_fields(prior)
    assert updated["simulation"] == {"fleet_dispatch_mode": "daily_milp_dispatch", "minimum_discharge_pf": .91}
    assert updated["optimizer"]["fleet_ga_optimizer"]["generations"] == 3
    assert updated["spin_max_generations"] == 12


def test_unknown_horizon_remains_invalid():
    with pytest.raises(ValueError, match="dispatch_horizon_hours"):
        SimulationConfig.from_saved_settings({"sindi_horizon_hours": 36})
