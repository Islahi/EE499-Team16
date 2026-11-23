# V15.6 refinement · engineering names

| Previous interface | Current interface |
|---|---|
| `sindi_strict.py`, `SindiDailyPlanner` | `daily_milp_dispatch.py`, `DailyMILPPlanner` |
| `sindi_ga.py`, `SindiGAConfig`, `run_sindi_joint_ga` | `fleet_ga_optimizer.py`, `FleetGAConfig`, `run_joint_fleet_ga` |
| `sindi_scenarios.py` | `representative_days.py` |
| Saved `sindi_strict` dispatch mode | `daily_milp_dispatch` |
| Saved `predictive_v11` mode | `predictive_24h` |
| Saved `sindi_horizon_hours`, `sindi_strict_pf_min` | `dispatch_horizon_hours`, `minimum_discharge_pf` |
| `sindi_daily_audit.csv` | `battery_daily_audit.csv` for new results |

`saved_schema.py` covers the historical keys. Report regeneration reads the old keys in memory and uses the original archived file checksums. `SimulationConfig.from_saved_settings` restores the saved operating horizon, PF and inverter assumptions for numerical replay. New GUI studies use the approved defaults. Research attribution remains in the scientific documentation and comments.
