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
    assert len(ranked)==len(S.ALLOWED_BUS_IDS)*len(S.POWER_RATINGS_KW)*len(S.ENERGY_CAPACITIES_KWH),"Catalog size changed"
    assert set(ranked.bess_bus)==set(S.ALLOWED_BUS_IDS), "Not every non-slack bus evaluated"
    assert raw_summary["raw_violation_bus_hours"]==int((~raw.voltage_pu.between(S.VOLTAGE_MIN_PU,S.VOLTAGE_MAX_PU)).sum()), "Raw baseline counts disagree"
    assert len(runs)==S.RUN_SEEDS*2,"GA/GWO run count changed"
    assert int((raw.voltage_pu < S.VOLTAGE_MIN_PU).sum()) == raw_summary["raw_undervoltage_bus_hours"]
    assert int((raw.voltage_pu > S.VOLTAGE_MAX_PU).sum()) == raw_summary["raw_overvoltage_bus_hours"]
    # These are acceptance criteria for the published July-2017 month-long stress
    # experiment, not universal assertions for user-selected dates/horizons.
    official_case=(S.START_DATE=="2017-07-01" and S.HORIZON_DAYS is None
                   and S.HORIZON_MONTHS==1 and S.PV_RATING_KW==2000
                   and S.LOAD_MULTIPLIER==1.60)
    if official_case:
        assert raw_summary["raw_undervoltage_bus_hours"] > 0, "Undervoltage stress did not occur"
        assert raw_summary["raw_overvoltage_bus_hours"] > 0, "Overvoltage stress did not occur"
        assert int(record["input_manifest"]["solar_surplus_hours"]) > 0, "No solar surplus"
    assert float(metrics[metrics.case.eq("Base (no BESS)")].iloc[0].pv_curtailment_kwh)>0, "No curtailment in capped baseline"
    assert float(metrics[metrics.case.eq("Base (no BESS)")].iloc[0].load_shedding_kwh)>0, "No shedding in capped baseline"
    assert "Unrestricted export (no BESS)" in set(metrics.case), "Missing export counterfactual"
    assert (RESULTS/"unrestricted_export_baseline_summary.csv").exists(), "Missing unrestricted export check"
    ops_grid = operations.grid_import_kw.to_numpy() - operations.grid_export_kw.to_numpy()
    if S.GRID_IMPORT_LIMIT_KW is not None:
        assert (ops_grid <= S.GRID_IMPORT_LIMIT_KW+1e-3).all(), "Import cap violated"
    if S.GRID_EXPORT_LIMIT_KW is not None:
        assert (ops_grid >= -S.GRID_EXPORT_LIMIT_KW-1e-3).all(), "Export cap violated"
    eligible=v[v.case.isin(metrics[metrics.feasible].case)]
    assert eligible.voltage_pu.between(S.VOLTAGE_MIN_PU-1e-10,S.VOLTAGE_MAX_PU+1e-10).all(),"Strict voltage failure"
    assert operations.bess_soc.between(S.SOC_MIN-1e-10,S.SOC_MAX+1e-10).all(),"SOC violation"
    if S.DISPATCH_MODE in ("scheduled","grid_aware"):
        assert (operations.actual_bess_kw < -1e-6).any(),"No BESS charging in scheduled scenario"
        assert (operations.actual_bess_kw > 1e-6).any(),"No BESS discharging in scheduled scenario"
    print(f"PASS: {len(clock)} hours, 15 buses, {len(ranked)} catalog options, {S.RUN_SEEDS} seeds per algorithm.")
    print(f"PASS: Every feasible final voltage is within {S.VOLTAGE_MIN_PU:.2f}–{S.VOLTAGE_MAX_PU:.2f} pu.")
    print(f"PASS: raw base violations {raw_summary['raw_undervoltage_bus_hours']} undervoltage + {raw_summary['raw_overvoltage_bus_hours']} overvoltage bus-hours.")
    print("PASS: SOC bounds, all 14 locations, file sizes and input/output periods consistent.")


if __name__=="__main__":
    main()
