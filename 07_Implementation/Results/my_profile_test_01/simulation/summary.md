# Results summary

- Type: hourly simulation
- Completed: True
- Converged: True
- Feasible: True
- Recorded steps: 24
- Time step: 1 h
- Message: Completed successfully.
- First timestamp: 2024-01-01 00:00:00
- Last timestamp: 2024-01-01 23:00:00

## Performance

- duration_hours: 24 h
- served_load_energy_kwh: 55357.241 kWh
- pv_generation_energy_kwh: 4385.8083 kWh
- grid_import_energy_kwh: 52568.981 kWh
- grid_export_energy_kwh: 0 kWh
- loss_energy_kwh: 1597.5529 kWh
- peak_grid_import_kw: 2276.4515 kW
- voltage_min_pu: 0.95 pu
- voltage_max_pu: 1 pu
- voltage_violation_hours: 0 h
- voltage_violation_bus_hours: 0 bus-hours
- reserve_violation_hours: 0 h
- bess_charge_energy_kwh: 0 kWh
- bess_discharge_energy_kwh: 0 kWh
- bess_soc_min: unavailable fraction
- bess_soc_max: unavailable fraction
- bess_cost: 0 SAR
- currency: SAR
- curtailment_energy_kwh: 0 kWh
- load_shedding_energy_kwh: 10971.408 kWh
- feasible: True
- notes: none
- requested_load_energy_kwh: 66328.649 kWh
- available_pv_energy_kwh: 4385.8083 kWh

## Supplied study context

- Demand: Literature-based synthetic demand; not measured
- Input preparation: preparation.json
- Study: No-BESS integration check; not storage sizing or independent validation

- Feasible does not mean all demand was served; inspect shedding and curtailment.
- Blank CSV values mean unavailable/not applicable, not zero.
- No simulation or optimization was rerun during export.

Exported tables: metrics.csv, hourly.csv, buses.csv, branches.csv
