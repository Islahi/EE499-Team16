"""Translate saved V15.6 names at the file boundary without rewriting source files."""

FIELD_ALIASES = {
    "sindi_min_power_factor": "minimum_discharge_pf",
    "sindi_strict_pf_min": "minimum_discharge_pf",
    "sindi_horizon_hours": "dispatch_horizon_hours",
    "sindi_daily_soc_tolerance_kwh": "daily_soc_tolerance_kwh",
    "sindi_strict_daily_soc_tolerance_kwh": "daily_soc_tolerance_kwh",
    "sindi_strict_daily_soc_restored": "daily_soc_restored",
    "sindi_strict_daily_soc_failures": "daily_soc_failures",
    "sindi_strict_days_planned": "daily_milp_days_planned",
    "sindi_strict_milp_failures": "daily_milp_failures",
    "sindi_strict_milp_seconds": "daily_milp_seconds",
    "sindi_strict_forecast_fbs_calls": "daily_milp_forecast_fbs_calls",
    "sindi_strict_soc_policy": "daily_soc_policy",
    "sindi_strict_lookahead": "dispatch_lookahead",
    "sindi_strict_formulation": "daily_milp_formulation",
    "sindi_strict_terminal_soc_closure": "daily_soc_closure",
    "sindi_strict_operating_assumptions": "daily_dispatch_assumptions",
    "sindi_ga": "fleet_ga_optimizer",
    "sindi_scenarios": "representative_days",
    "spin_sindi_energy_cost": "spin_battery_energy_capex",
    "spin_sindi_kva_cost": "spin_inverter_capex",
    "spin_sindi_efficiency_percent": "spin_dispatch_efficiency_percent",
    "spin_sindi_min_pf": "spin_minimum_discharge_pf",
    "spin_ga_generations": "spin_max_generations",
    "spin_cpu_workers": "spin_parallel_workers",
}
MODE_ALIASES = {"sindi_strict": "daily_milp_dispatch", "predictive_v11": "predictive_24h"}


def canonical_dispatch_mode(mode):
    return MODE_ALIASES.get(mode, mode)


def upgrade_saved_fields(value):
    """Use canonical keys in memory. An explicitly saved canonical key wins."""
    if isinstance(value, list):
        return [upgrade_saved_fields(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        current = FIELD_ALIASES.get(key, key)
        if current != key and current in value:
            continue
        result[current] = (canonical_dispatch_mode(item) if key == "fleet_dispatch_mode"
                           else upgrade_saved_fields(item))
    if "spin_max_generations" in result:
        result.setdefault("spin_ga_stall_generations", 6)
    return result
