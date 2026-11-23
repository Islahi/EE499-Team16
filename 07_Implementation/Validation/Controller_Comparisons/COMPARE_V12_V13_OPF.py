"""Compare fixed-fleet controllers with identical input network/load/PV, no GWO.

Examples (Windows):
  py -3.14 COMPARE_V12_V13_OPF.py --folder "C:\\Study\\Inputs" --hours 168
  py -3.14 COMPARE_V12_V13_OPF.py --folder "C:\\Study\\Inputs" --hours 8760 \
      --bess "8:1750:33250,29:250:250,16:250:250"

PV site ratings must already be reflected in pv_profile.csv; the script does
NOT silently overwrite network ratings or forecast PV profiles.
"""
import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

from src.bess import BESSConfig
from src.data_loader import ProfileData, profile_at
from src.fbs import FBSConfig, prepare_fbs
from src.metrics import EconomicConfig, evaluate_results, with_terminal_policy
from src.network_loader import load_network
from src.simulation import SimulationConfig, simulate_timeseries, _operating_point


def parse_fleet(text):
    units = []
    if not text.strip():
        return ()
    for token in text.split(','):
        parts = token.split(':')
        if len(parts) != 3:
            raise ValueError('BESS format is bus:kW:kWh,bus:kW:kWh')
        bus, power, energy = map(float, parts)
        if int(bus) != bus or power <= 0 or energy <= 0:
            raise ValueError('Bus must be integer and power/energy positive')
        units.append(BESSConfig(int(bus),energy,power,.2,1.,.5,.9,.9))
    if len({c.bus_id for c in units}) != len(units):
        raise ValueError('Battery buses must be unique')
    return tuple(units)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',required=True,help='Folder containing network.xlsx, load_profile.csv, pv_profile.csv')
    parser.add_argument('--hours',type=int,default=168,help='First N continuous hours; use 8760 for annual')
    parser.add_argument('--bess',default='8:1750:33250,29:250:250,16:250:250',
                        help='comma-separated bus:kW:kWh; pass empty string for No-BESS control comparison')
    parser.add_argument('--import-limit',type=float,default=7500.)
    parser.add_argument('--export-limit',type=float,default=0.)
    parser.add_argument('--bess-kva-multiplier',type=float,default=1.0)
    parser.add_argument('--pv-kva-multiplier',type=float,default=1.0)
    parser.add_argument('--output',default='V13_FIXED_FLEET_COMPARISON.json')
    args=parser.parse_args()
    folder=Path(args.folder)
    network=load_network(folder/'network.xlsx',frequency_hz=60.)
    original=ProfileData(folder/'load_profile.csv',folder/'pv_profile.csv')
    if not 1 <= args.hours <= len(original.timestamps):
        parser.error(f'--hours must be between 1 and {len(original.timestamps)}')
    profile=ProfileData.from_arrays(original.timestamps[:args.hours],
        {bus:v[:args.hours] for bus,v in original.load_p_kw.items()},
        {bus:v[:args.hours] for bus,v in original.load_q_kvar.items()},
        {bus:v[:args.hours] for bus,v in original.pv_p_kw.items()},
        {bus:v[:args.hours] for bus,v in original.pv_q_kvar.items()})
    fleet=parse_fleet(args.bess)
    # Warm JIT outside both timed runs for a fairer comparison.
    fbs=prepare_fbs(network,FBSConfig(backend='numba'))
    fbs(_operating_point(network,profile_at(profile,0)))
    economics=EconomicConfig(grid_import_tariff_per_kwh=.10,grid_export_tariff_per_kwh=0.,
        cost_per_kwh=385.,cost_per_kw=770.,curtailment_penalty_per_kwh=.07,
        shedding_penalty_per_kwh=12.,lifetime_years=10,annual_om_fraction=.02)
    output={'study':{'folder':str(folder.resolve()),'hours':args.hours,
           'fleet':[{'bus':c.bus_id,'power_kw':c.power_rating_kw,
                     'energy_kwh':c.energy_capacity_kwh} for c in fleet],
           'inverter_assumptions':{'bess_kva_multiplier':args.bess_kva_multiplier,
                                  'pv_kva_multiplier':args.pv_kva_multiplier},
           'perfect_foresight':True},'results':{}}
    for mode in ('predictive','opf'):
        sim_settings=with_terminal_policy(SimulationConfig(
            fbs_config=FBSConfig(backend='numba'),grid_import_limit_kw=args.import_limit,
            grid_export_limit_kw=args.export_limit,fleet_dispatch_mode=mode,
            opf_bess_kva_multiplier=args.bess_kva_multiplier,
            opf_pv_kva_multiplier=args.pv_kva_multiplier),economics)
        start=time.perf_counter()
        result=simulate_timeseries(network,profile,sim_settings,bess_fleet=fleet,
                                   capture_dispatch=False)
        elapsed=time.perf_counter()-start
        metrics=evaluate_results(result,economics,fleet or None) if result.completed and result.converged else None
        output['results'][mode]={'runtime_seconds':elapsed,'completed':result.completed,
            'converged':result.converged,'feasible':result.feasible,'hours_completed':len(result.steps),
            'load_shedding_kwh':metrics.load_shedding_energy_kwh if metrics else None,
            'curtailment_kwh':metrics.curtailment_energy_kwh if metrics else None,
            'battery_charge_kwh':metrics.bess_charge_energy_kwh if metrics else None,
            'battery_discharge_kwh':metrics.bess_discharge_energy_kwh if metrics else None,
            'annual_total_cost_usd':metrics.annual_total_cost if metrics else None,
            'bess_reactive_dispatch_kvarh':sum(abs(v) for step in result.steps
                     for v in step.operating_point.q_bess_kvar.values()),
            'pv_reactive_dispatch_kvarh':sum(abs(v) for step in result.steps
                     for v in step.operating_point.q_pv_kvar.values()),
            'dispatch_timing':result.dispatch_timing}
        print(f'{mode}: {elapsed:.2f}s, shedding={output["results"][mode]["load_shedding_kwh"]}, '
              f'feasible={result.feasible}, completed={result.completed}',flush=True)
    destination=Path(args.output)
    destination.write_text(json.dumps(output,indent=2,default=str),encoding='utf-8')
    print('Saved:',destination.resolve())

if __name__=='__main__': main()
