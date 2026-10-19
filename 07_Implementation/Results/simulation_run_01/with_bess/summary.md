# Results summary

- Type: hourly simulation
- Completed: True
- Converged: True
- Feasible: True
- Recorded steps: 24
- Time step: 1 h
- Message: Completed successfully.
- First timestamp: 2026-01-01 00:00:00
- Last timestamp: 2026-01-01 23:00:00

## Performance

- duration_hours: 24 h
- served_load_energy_kwh: 14040 kWh
- pv_generation_energy_kwh: 1367.2357 kWh
- grid_import_energy_kwh: 12591.474 kWh
- grid_export_energy_kwh: 0 kWh
- loss_energy_kwh: 177.74615 kWh
- peak_grid_import_kw: 686.55913 kW
- voltage_min_pu: 0.96743895 pu
- voltage_max_pu: 1 pu
- voltage_violation_hours: 0 h
- voltage_violation_bus_hours: 0 bus-hours
- reserve_violation_hours: 0 h
- bess_charge_energy_kwh: 456.05255 kWh
- bess_discharge_energy_kwh: 715.08743 kWh
- bess_soc_min: 0.18052632 fraction
- bess_soc_max: 0.9 fraction
- bess_cost: unavailable SAR
- currency: SAR
- curtailment_energy_kwh: 0 kWh
- load_shedding_energy_kwh: 0 kWh
- feasible: True
- notes: BESS cost unavailable: supply both economic coefficients.
- requested_load_energy_kwh: 14040 kWh
- available_pv_energy_kwh: 1367.2357 kWh

## Supplied study context

- arguments: {'hours': 24, 'cost_per_kwh': None, 'cost_per_kw': None, 'currency': 'SAR', 'grid_import_limit_kw': None, 'grid_export_limit_kw': None, 'pv_rating_kw': None, 'output_dir': WindowsPath('07_Implementation/Results/simulation_run_01')}
- candidate_battery_settings: {'bus_id': 4, 'energy_capacity_kwh': 1000.0, 'power_rating_kw': 200.0, 'soc_min': 0.1, 'soc_max': 0.9, 'soc_initial': 0.5, 'eta_charge': 0.95, 'eta_discharge': 0.95, 'max_charge_kw': 200.0, 'max_discharge_kw': 200.0}
- dispatch: net load minus 600 kW; demonstration only
- economics: EconomicConfig(cost_per_kwh=None, cost_per_kw=None, currency='SAR')
- simulation_settings: SimulationConfig(fbs_config=FBSConfig(max_iterations=100, voltage_tolerance_pu=1e-06, slack_angle_deg=0.0, record_history=False), voltage_min_pu=0.95, voltage_max_pu=1.05, reserve_fraction=0.1, reserve_duration_hours=1.0, stop_on_power_flow_failure=True, allow_pv_curtailment=True, allow_load_shedding=True, grid_import_limit_kw=None, grid_export_limit_kw=None, control_max_iterations=30, control_tolerance_kw=1e-06)
- study: Synthetic guide-feeder demo, not real-data validation

- Feasible does not mean all demand was served; inspect shedding and curtailment.
- Blank CSV values mean unavailable/not applicable, not zero.
- No simulation or optimization was rerun during export.

Comparison reductions use (baseline-candidate)/baseline; negative means an increase.
A reduction is not automatically desirable for every quantity (e.g. grid exports).
Matching profiles/settings and aggregation basis must be confirmed by the caller.

Exported tables: metrics.csv, hourly.csv, buses.csv, branches.csv, comparison.csv
