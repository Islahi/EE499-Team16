"""Controlled battery-dispatch comparison; never runs GWO or changes source CSVs.

Example:
    python COMPARE_V11_V12_CONTROL.py --folder "C:\\case\\inputs" --hours 168
    python COMPARE_V11_V12_CONTROL.py --folder "C:\\case\\inputs" --hours 8760

Requires network.xlsx, load_profile.csv, pv_profile.csv in --folder.
Reports 8760/8784-hour outcomes as annual only after full chronological coverage; no optimizer.
"""
import argparse
import csv
import json
import os
import sys
from pathlib import Path
from time import perf_counter

# Avoid accidental nested BLAS oversubscription on 16-GB Windows PCs.
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')

from src.bess import BESSConfig
from src.data_loader import ProfileData
from src.fbs import FBSConfig
from src.metrics import EconomicConfig, evaluate_results, with_terminal_policy
from src.network_loader import load_network
from src.sequential_multi import annual_coverage
from src.simulation import SimulationConfig, simulate_timeseries


def main():
    parser = argparse.ArgumentParser(description='Compare V11 24h vs V12 72h predictive dispatch with FIXED BESS locations/sizes')
    parser.add_argument('--folder', type=Path, required=True, help='Folder with network.xlsx, load_profile.csv, pv_profile.csv')
    parser.add_argument('--hours', type=int, default=168, help='Chronological hours from selected offset; use 8760 for complete 2021 annual test')
    parser.add_argument('--offset', type=int, default=0, help='Starting hour offset; simulation SOC begins from initial SOC')
    parser.add_argument('--buses', default='17', help='Comma-separated installation bus IDs')
    parser.add_argument('--power-kw', type=float, default=500.)
    parser.add_argument('--energy-kwh', type=float, default=50000.)
    parser.add_argument('--soc-min', type=float, default=.2)
    parser.add_argument('--soc-max', type=float, default=1.)
    parser.add_argument('--soc-initial', type=float, default=.5)
    parser.add_argument('--eta-charge', type=float, default=.9)
    parser.add_argument('--eta-discharge', type=float, default=.9)
    parser.add_argument('--import-limit-kw', type=float, default=7500.)
    parser.add_argument('--export-limit-kw', type=float, default=0.)
    parser.add_argument('--frequency-hz', type=float, default=60.)
    parser.add_argument('--output', type=Path, default=Path('v12_control_comparison.json'))
    a = parser.parse_args()
    if a.hours <= 0 or a.offset < 0:
        parser.error('--hours must be positive and --offset cannot be negative')
    network = load_network(a.folder / 'network.xlsx', frequency_hz=a.frequency_hz)
    profiles = ProfileData(a.folder/'load_profile.csv', a.folder/'pv_profile.csv')
    if a.offset + a.hours > len(profiles.timestamps):
        parser.error('Requested hour range extends beyond supplied profiles')
    profiles = profiles.slice(profiles.timestamps[a.offset],
                              profiles.timestamps[a.offset+a.hours] if a.offset+a.hours<len(profiles.timestamps) else None)
    ids = tuple(int(s) for s in a.buses.split(','))
    configs = tuple(BESSConfig(bus, a.energy_kwh,a.power_kw,a.soc_min,a.soc_max,
                               a.soc_initial,a.eta_charge,a.eta_discharge) for bus in ids)
    economics = EconomicConfig(grid_import_tariff_per_kwh=.10,grid_export_tariff_per_kwh=0.)
    report = {'source_folder':str(a.folder),'hours_requested':a.hours,'offset':a.offset,
              'controller_comparison':['predictive_24h','predictive'], 'bess_units':[{'bus':x.bus_id,'power_kw':x.power_rating_kw,'energy_kwh':x.energy_capacity_kwh} for x in configs],
              'warnings':['The future PV/load series in the supplied dataset are treated as perfect forecasts; do not equate results with uncertain forecast operation.']}
    for mode in ('predictive_24h','predictive'):
        config = with_terminal_policy(SimulationConfig(fbs_config=FBSConfig(backend='numba'),
                        grid_import_limit_kw=a.import_limit_kw,grid_export_limit_kw=a.export_limit_kw,
                        fleet_dispatch_mode=mode),economics)
        begin=perf_counter()
        sim=simulate_timeseries(network,profiles,config,bess_fleet=configs,capture_dispatch=False)
        coverage=annual_coverage(sim,profiles)
        m=evaluate_results(sim,economics,configs) if coverage['complete'] and sim.converged else None
        report[mode]={
          'elapsed_seconds':perf_counter()-begin,
          'annual_coverage':coverage,
          'simulation_feasible':sim.feasible,
          'shed_kwh':sum(step.shedding_kw or 0 for step in sim.steps),
          'pre_shedding_voltage_deficit_pu_hours':sum(max(0.,config.voltage_min_pu-v)
                       for step in sim.steps for v in (step.pre_control_voltage_pu or {}).values()),
          'charged_ac_kwh':sum(max(0.,-x.actual_power_kw) for step in sim.steps for x in step.fleet_steps.values()),
          'discharged_ac_kwh':sum(max(0.,x.actual_power_kw) for step in sim.steps for x in step.fleet_steps.values()),
          'minimum_soc_hours_by_bus':{str(bus):sum(step.fleet_states[bus].soc<=a.soc_min+1e-8 for step in sim.steps) for bus in ids},
          'ending_soc_by_bus':{str(bus):sim.final_fleet_states[bus].soc for bus in ids},
          'annual_total_cost_usd':m.annual_total_cost if m else None,
          'dispatch_diagnostics':sim.dispatch_timing,
        }
        print(f"{mode}: {report[mode]['shed_kwh']/1000:.2f} MWh shed, "
              f"{report[mode]['charged_ac_kwh']/1000:.2f} MWh charged, "
              f"{report[mode]['elapsed_seconds']:.1f} s; full-year={coverage['complete']}",flush=True)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,default=str),encoding='utf8')
    print(f'Wrote {a.output.resolve()}')

if __name__=='__main__':
    main()
