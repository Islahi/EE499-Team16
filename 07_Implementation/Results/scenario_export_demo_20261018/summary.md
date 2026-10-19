# Results summary

Type: optimization
Success: True
Message: Best feasible candidate found.
Iterations: 2
Evaluator calls retained: 4
Best raw WSM: 1923.1546
Selected bus: 2
Battery power: 100 kW
Battery energy: 500 kWh
Optimizer algorithm: GWO
Optimizer cache_evaluations: True
Optimizer catalog_size: 4
Optimizer evaluations: 4
Optimizer history_axis: generation
Optimizer population_size: 4
Optimizer seed: 42
Optimizer unique_candidates: 4
Raw WSM mixes cost and energy units; this is not a normalized economic cost.
The chosen battery is best among evaluated candidates, not a global-optimum guarantee.

## Performance

duration_hours: 24 h
served_load_energy_kwh: 11031.015 kWh
pv_generation_energy_kwh: 5322.908 kWh
grid_import_energy_kwh: 5858.4331 kWh
grid_export_energy_kwh: 4.4435874e-06 kWh
loss_energy_kwh: 97.688728 kWh
peak_grid_import_kw: 400 kW
voltage_min_pu: 0.9776428 pu
voltage_max_pu: 1 pu
voltage_violation_hours: 0 h
voltage_violation_bus_hours: 0 bus-hours
reserve_violation_hours: 0 h
bess_charge_energy_kwh: 340.38489 kWh
bess_discharge_energy_kwh: 287.74694 kWh
bess_soc_min: 0.24798361 fraction
bess_soc_max: 0.9 fraction
bess_cost: 1300 SAR
currency: SAR
curtailment_energy_kwh: 3134.5868 kWh
load_shedding_energy_kwh: 1958.0318 kWh
feasible: True
notes: Equal-weight scenario means; extrema/peak are worst-case values.
requested_load_energy_kwh: 12989.047 kWh
available_pv_energy_kwh: 8457.4948 kWh

## Supplied study context

aggregation: Equal-weight stress portfolio, not a probability-preserving reduction
arguments: {'history_hours': 168, 'forecast_hours': 24, 'validation_hours': 24, 'arima_order': (1, 0, 0), 'seed': 42, 'pv_rating_kw': 1200, 'optimize': True, 'cost_per_kwh': 2.0, 'cost_per_kw': 3.0, 'eta_charge': 0.95, 'eta_discharge': 0.95, 'grid_import_limit_kw': 400, 'grid_export_limit_kw': 0, 'dispatch_target_kw': 400, 'output_dir': WindowsPath('07_Implementation/Results/scenario_export_demo_20261018')}
battery_parameters: BESSParameters(eta_charge=0.95, eta_discharge=0.95, soc_min=0.1, soc_max=0.9, soc_initial=0.5)
bounds: buses (2,4); kW (100,); kWh (500,1000)
dispatch: net load minus --dispatch-target-kw
forecast_validation: {'load': {2: {'arima': {'rmse_kw': 7.895724104875025, 'mape_percent': 4.117768159069676, 'mape_sample_count': 24}, 'repeat_last_day': {'rmse_kw': 9.637791472435971, 'mape_percent': 5.074065481516475, 'mape_sample_count': 24}, 'training_warnings': ['Setting the shape on a NumPy array has been deprecated in NumPy 2.5.\nAs an alternative, you can create a new view using np.reshape (with copy=False if needed).']}, 3: {'arima': {'rmse_kw': 10.941248527643587, 'mape_percent': 5.50010485819109, 'mape_sample_count': 24}, 'repeat_last_day': {'rmse_kw': 15.890804312856632, 'mape_percent': 7.211110172599831, 'mape_sample_count': 24}, 'training_warnings': ['Setting the shape on a NumPy array has been deprecated in NumPy 2.5.\nAs an alternative, you can create a new view using np.reshape (with copy=False if needed).']}, 4: {'arima': {'rmse_kw': 5.546966013217213, 'mape_percent': 4.055267790273277, 'mape_sample_count': 24}, 'repeat_last_day': {'rmse_kw': 7.836469996256434, 'mape_percent': 5.042329762016054, 'mape_sample_count': 24}, 'training_warnings': ['Setting the shape on a NumPy array has been deprecated in NumPy 2.5.\nAs an alternative, you can create a new view using np.reshape (with copy=False if needed).']}, 5: {'arima': {'rmse_kw': 3.9839203822160556, 'mape_percent': 3.798270417900561, 'mape_sample_count': 24}, 'repeat_last_day': {'rmse_kw': 3.860156439859668, 'mape_percent': 3.581720424378729, 'mape_sample_count': 24}, 'training_warnings': ['Setting the shape on a NumPy array has been deprecated in NumPy 2.5.\nAs an alternative, you can create a new view using np.reshape (with copy=False if needed).']}}, 'pv': {4: {'arima': {'rmse_kw': 30.488849593200428, 'mape_percent': 3.7753544385517266, 'mape_sample_count': 11}, 'repeat_last_day': {'rmse_kw': 39.963206098202086, 'mape_percent': 4.7771313832146305, 'mape_sample_count': 11}, 'training_warnings': ['Setting the shape on a NumPy array has been deprecated in NumPy 2.5.\nAs an alternative, you can create a new view using np.reshape (with copy=False if needed).']}}}
selection: {'best': 15, 'worst': 15, 'random': 15}
simulation_settings: SimulationConfig(fbs_config=FBSConfig(max_iterations=100, voltage_tolerance_pu=1e-06, slack_angle_deg=0.0, record_history=False), voltage_min_pu=0.95, voltage_max_pu=1.05, reserve_fraction=0.1, reserve_duration_hours=1.0, stop_on_power_flow_failure=True, allow_pv_curtailment=True, allow_load_shedding=True, grid_import_limit_kw=400, grid_export_limit_kw=0, control_max_iterations=30, control_tolerance_kw=1e-06)
study: Synthetic guide-feeder uncertainty demo
weights: ObjectiveWeights(cost=0.5, curtailment=0.25, shedding=0.25)

Feasible does not mean all demand was served; inspect shedding and curtailment.
Blank CSV values mean unavailable/not applicable, not zero.
No simulation or optimization was rerun during export.

Only retained/evaluated cases are exported; rejected candidates may stop at the first failed case.

Exported tables: metrics.csv, evaluations.csv, convergence.csv, scenario_evaluations.csv
