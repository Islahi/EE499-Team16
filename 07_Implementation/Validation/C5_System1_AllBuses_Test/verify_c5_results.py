"""Quick integrity checks after `python run_c5.py`."""
from pathlib import Path
import json
import pandas as pd
import c5_settings as S
from prepare_c5_inputs import timespan

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "C5_results"
INPUTS = ROOT / "inputs"


def main():
    a,b,clock=timespan()
    load=pd.read_csv(INPUTS/"load_profile.csv")
    pv=pd.read_csv(INPUTS/"pv_profile.csv")
    v=pd.read_csv(RESULTS/"base_vs_best_voltage_hourly.csv")
    metrics=pd.read_csv(RESULTS/"base_vs_optimized_summary.csv")
    ranked=pd.read_csv(RESULTS/"exhaustive_candidates.csv")
    raw=pd.read_csv(RESULTS/"raw_baseline_voltage_hourly.csv")
    raw_summary=json.loads((RESULTS/"raw_baseline_violation_counts.json").read_text())
    operations=pd.read_csv(RESULTS/"optimized_bess_hourly.csv")
    runs=pd.read_csv(RESULTS/"search_runs.csv")
    record=json.loads((RESULTS/"test_settings.json").read_text(encoding="utf-8"))
    assert record["simulation_hours"]==len(clock),"Results do not match current time-horizon inputs"
    assert len(load)==15*len(clock),"Missing load profile bus/hour rows"
    assert len(raw)==15*len(clock), "Incomplete uncorrected baseline voltages"
    assert set(raw.bus_id)==set(range(1,16)), "Incorrect bus catalog in baseline"
    assert len(pv)==len(clock) and set(pv.bus_id)=={S.PV_BUS},"Invalid PV inputs"
    assert len(v)==2*15*len(clock),"Missing base/BESS voltage rows"
    assert len(operations)==len(clock),"Missing optimized battery operation rows"
    assert len(ranked)==14*len(S.POWER_RATINGS_KW)*len(S.ENERGY_CAPACITIES_KWH),"Catalog size changed"
    assert set(ranked.bess_bus)==set(range(2,16)), "Not every non-slack bus evaluated"
    assert raw_summary["raw_violation_bus_hours"]==int((~raw.voltage_pu.between(S.VOLTAGE_MIN_PU,S.VOLTAGE_MAX_PU)).sum()), "Raw baseline counts disagree"
    assert len(runs)==S.RUN_SEEDS*2,"GA/GWO run count changed"
    eligible=v[v.case.isin(metrics[metrics.feasible].case)]
    assert eligible.voltage_pu.between(S.VOLTAGE_MIN_PU-1e-10,S.VOLTAGE_MAX_PU+1e-10).all(),"Strict voltage failure"
    assert operations.bess_soc.between(S.SOC_MIN-1e-10,S.SOC_MAX+1e-10).all(),"SOC violation"
    if S.DISPATCH_MODE=="scheduled":
        assert (operations.actual_bess_kw < -1e-6).any(),"No BESS charging in scheduled scenario"
        assert (operations.actual_bess_kw > 1e-6).any(),"No BESS discharging in scheduled scenario"
    print(f"PASS: {len(clock)} hours, 15 buses, {len(ranked)} catalog options, {S.RUN_SEEDS} seeds per algorithm.")
    print(f"PASS: Every feasible final voltage is within {S.VOLTAGE_MIN_PU:.2f}–{S.VOLTAGE_MAX_PU:.2f} pu.")
    print(f"PASS: raw base voltage violations {raw_summary['raw_violation_bus_hours']} bus-hours; corrected base isolated.")
    print("PASS: SOC bounds, all 14 locations, file sizes and input/output periods consistent.")


if __name__=="__main__":
    main()
