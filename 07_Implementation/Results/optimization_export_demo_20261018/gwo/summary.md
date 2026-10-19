# Results summary

Type: optimization
Success: True
Message: Best feasible candidate found.
Iterations: 8
Evaluator calls retained: 7
Best raw WSM: 2141.4034
Selected bus: 2
Battery power: 100 kW
Battery energy: 500 kWh
Optimizer algorithm: GWO
Optimizer cache_evaluations: True
Optimizer catalog_size: 8
Optimizer evaluations: 7
Optimizer history_axis: generation
Optimizer population_size: 8
Optimizer seed: 42
Optimizer unique_candidates: 7
Raw WSM mixes cost and energy units; this is not a normalized economic cost.
The chosen battery is best among evaluated candidates, not a global-optimum guarantee.

## Performance

duration_hours: 24 h
served_load_energy_kwh: 11470.583 kWh
pv_generation_energy_kwh: 5718.708 kWh
grid_import_energy_kwh: 5914.7487 kWh
grid_export_energy_kwh: 4.59513e-06 kWh
loss_energy_kwh: 104.58554 kWh
peak_grid_import_kw: 400 kW
voltage_min_pu: 0.97737451 pu
voltage_max_pu: 1 pu
voltage_violation_hours: 0 h
voltage_violation_bus_hours: 0 bus-hours
reserve_violation_hours: 0 h
bess_charge_energy_kwh: 336.28809 kWh
bess_discharge_energy_kwh: 278 kWh
bess_soc_min: 0.26105263 fraction
bess_soc_max: 0.9 fraction
bess_cost: 1300 SAR
currency: SAR
curtailment_energy_kwh: 3396.1969 kWh
load_shedding_energy_kwh: 2569.4167 kWh
feasible: True
notes: none
requested_load_energy_kwh: 14040 kWh
available_pv_energy_kwh: 9114.9049 kWh

## Supplied study context

arguments: {'cost_per_kwh': 2.0, 'cost_per_kw': 3.0, 'currency': 'SAR', 'hours': 24, 'bus_ids': [2, 4], 'power_ratings_kw': [100, 200], 'energy_capacities_kwh': [500, 1000], 'population_size': 8, 'iterations': 8, 'seed': 42, 'pv_rating_kw': 1200, 'grid_import_limit_kw': 400, 'grid_export_limit_kw': 0, 'dispatch_target_kw': 400, 'eta_charge': 0.95, 'eta_discharge': 0.95, 'compare_exhaustive': True, 'output_dir': WindowsPath('07_Implementation/Results/optimization_export_demo_20261018')}
battery_parameters: BESSParameters(eta_charge=0.95, eta_discharge=0.95, soc_min=0.1, soc_max=0.9, soc_initial=0.5)
bounds: OptimizationBounds(allowed_bus_ids=(2, 4), power_ratings_kw=(100, 200), energy_capacities_kwh=(500, 1000))
dispatch: net load minus --dispatch-target-kw
economics: EconomicConfig(cost_per_kwh=2.0, cost_per_kw=3.0, currency='SAR')
simulation_settings: SimulationConfig(fbs_config=FBSConfig(max_iterations=100, voltage_tolerance_pu=1e-06, slack_angle_deg=0.0, record_history=False), voltage_min_pu=0.95, voltage_max_pu=1.05, reserve_fraction=0.1, reserve_duration_hours=1.0, stop_on_power_flow_failure=True, allow_pv_curtailment=True, allow_load_shedding=True, grid_import_limit_kw=400, grid_export_limit_kw=0, control_max_iterations=30, control_tolerance_kw=1e-06)
study: Synthetic guide-feeder demo, not a storage recommendation
weights: ObjectiveWeights(cost=0.5, curtailment=0.25, shedding=0.25)

Feasible does not mean all demand was served; inspect shedding and curtailment.
Blank CSV values mean unavailable/not applicable, not zero.
No simulation or optimization was rerun during export.

Comparison reductions use (baseline-candidate)/baseline; negative means an increase.
A reduction is not automatically desirable for every quantity (e.g. grid exports).
Matching profiles/settings and aggregation basis must be confirmed by the caller.

Exported tables: metrics.csv, evaluations.csv, convergence.csv, comparison.csv
