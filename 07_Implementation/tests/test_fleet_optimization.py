from dataclasses import replace
import json
from math import hypot

import pandas as pd
import pytest

from src_accelerated.bess import BESSConfig, BESSFleet, FleetUnit
from src_accelerated.data_loader import ProfileData
from src_accelerated.fleet_optimizer import FleetCandidate, FleetCatalog, FleetSearchConfig, rank, run_fleet_experiment
from src_accelerated.metrics import EconomicConfig, evaluate_results
from src_accelerated.network_model import Bus, Line, Load, NetworkModel, PVUnit
from src_accelerated.network_screening import BaselineCache, rank_locations
from src_accelerated.optimizer import BESSCandidate, BESSParameters, OptimizationBounds, OptimizerConfig
from src_accelerated.results import export_results
from src_accelerated.simulation import ConstraintAwareDispatch, SimulationConfig, simulate_timeseries


def feeder(hours=48, *, stress=False):
    network = NetworkModel([Bus(bus, str(bus), .4, bus == 1) for bus in (1, 2, 3, 4)],
        [Line("12", 1, 2, .015, .003), Line("13", 1, 3, .12 if stress else .01, .003), Line("24", 2, 4, .02, .003)],
        [Load("2", 2, 20., 1.), Load("3", 3, 40., 2.), Load("4", 4, 15., .5)],
        [PVUnit("pv", 4, 100.)], 100., 60.)
    stamps = pd.date_range("2021-07-01", periods=hours, freq="h")
    load = {1: [0.] * hours, 2: [20.] * hours, 3: [85. if stress and 17 <= i % 24 <= 22 else 30.
             for i in range(hours)], 4: [15.] * hours}
    pv = {4: [100. if 10 <= i % 24 <= 14 else 0. for i in range(hours)]}
    return network, ProfileData.from_arrays(stamps, load, {bus: [value * .04 for value in values] for bus, values in load.items()},
                                           pv, {4: [0.] * hours})


def settings(**kwargs):
    return replace(SimulationConfig(reserve_fraction=0., voltage_min_pu=.90, voltage_max_pu=1.10,
                      grid_import_limit_kw=250., grid_export_limit_kw=0.), **kwargs)


def econ(**kwargs):
    return EconomicConfig(cost_per_kw=50., cost_per_kwh=75., grid_import_tariff_per_kwh=.12,
                          grid_export_tariff_per_kwh=0., **kwargs)


def unit(bus, power=40., energy=200., *, reactive=0., charge=.9, discharge=.9):
    return FleetUnit(str(bus), BESSConfig(bus, energy, power, .2, .95, .5, charge, discharge), reactive_kvar=reactive)


def test_scalar_and_single_unit_fleet_parity():
    network, profiles = feeder(24)
    config, battery = settings(), unit(4)
    single = simulate_timeseries(network, profiles, config, battery.config)
    fitted = simulate_timeseries(network, profiles, config, BESSFleet((battery,)))
    assert single.feasible == fitted.feasible
    for old, new in zip(single.steps, fitted.steps):
        assert old.power_flow == new.power_flow
        assert old.bess_step.actual_power_kw == new.fleet_units[0].battery.actual_power_kw
    assert evaluate_results(single, econ(), battery.config) == evaluate_results(fitted, econ(), BESSFleet((battery,)))
    empty = simulate_timeseries(network, profiles, config, BESSFleet())
    baseline = simulate_timeseries(network, profiles, config)
    assert [step.operating_point for step in empty.steps] == [step.operating_point for step in baseline.steps]


def test_two_units_one_point_reserve_and_terminal_energy(tmp_path):
    network, profiles = feeder(2)
    config = settings(reserve_fraction=.1, terminal_soc_tolerance=1e-6)
    fleet = BESSFleet((unit(2, reactive=8.), unit(3, 50., 210., reactive=-5., charge=.8, discharge=.88)))

    def dispatch(index, profile, states):
        return {"2": 12. if index == 0 else -12. / .81, "3": 8. if index == 0 else -8. / (.88 * .8)}

    result = simulate_timeseries(network, profiles, config, fleet, dispatch)
    assert result.feasible
    first = result.steps[0]
    assert first.operating_point.p_bess_kw == pytest.approx({1: 0., 2: 12., 3: 8., 4: 0.})
    assert first.operating_point.q_bess_kvar == {1: 0., 2: 8., 3: -5., 4: 0.}
    assert first.dispatch.after_bess_kw == pytest.approx(20.)
    assert first.dispatch.final.violations == {}
    assert first.reserve_power_kw == pytest.approx(6.5)
    assert sum(record.reserve_kw for record in first.fleet_units) == pytest.approx(6.5)
    assert all(hypot(record.battery.actual_power_kw, record.reactive_kvar) <= 40 for record in first.fleet_units)
    assert all(state.soc == pytest.approx(.5) for state in result.final_fleet_states.values())
    no_fee = evaluate_results(result, econ(), fleet)
    fee = evaluate_results(result, econ(fixed_installation_cost=900.), fleet)
    assert fee.bess_cost - no_fee.bess_cost == 1800.
    assert fee.bess_discharge_energy_kwh == pytest.approx(20.)
    files = export_results(result, tmp_path / "saved", metrics=fee, context={"Economic inputs": vars(econ(fixed_installation_cost=900.))})
    assert len(pd.read_csv(files["bess_units_hourly.csv"])) == 4
    assert pd.read_csv(files["bess_units.csv"]).capex_usd.sum() == fee.bess_cost
    event = json.loads(files["dispatch_events.jsonl"].read_text(encoding="utf8").splitlines()[0])
    assert {item["bus_id"] for item in event["fleet_units"]} == {2, 3}


def test_uneven_energy_allocation_retains_only_one_global_reserve():
    network, profiles = feeder(2)
    fleet = BESSFleet((unit(2, 25., 10.), unit(4, 40., 90.)))
    result = simulate_timeseries(network, profiles, settings(reserve_fraction=.2), fleet, None)
    assert result.feasible
    records = result.steps[0].fleet_units
    assert records[0].reserve_kw <= 2.7
    assert sum(record.reserve_kw for record in records) == pytest.approx(13.)


def test_canonical_catalog_has_exact_totals_and_unique_sites():
    bounds = OptimizationBounds((2, 3, 4), (10., 20., 30.), (25., 50., 75.))
    search = FleetSearchConfig(total_kw=30., total_kwh=75.)
    forward = FleetCandidate((BESSCandidate(2, 10., 25.), BESSCandidate(3, 20., 50.)))
    assert forward == FleetCandidate(tuple(reversed(forward.units)))
    for count in (1, 2, 3):
        catalog = FleetCatalog(bounds, bounds.allowed_bus_ids, count, search, {})
        candidate = catalog.decode([1.] * (3 * count))
        assert len({item.bus_id for item in candidate.units}) == count
        assert candidate.power_rating_kw == 30 and candidate.energy_capacity_kwh == 75
        assert catalog.decode(catalog.encode(candidate)) == candidate
    with pytest.raises(ValueError, match="cannot satisfy"):
        FleetCatalog(bounds, bounds.allowed_bus_ids, 3, replace(search, total_kw=20.), {})
    flexible = FleetCatalog(bounds, bounds.allowed_bus_ids, 2, replace(search, capacity_mode="flexible"), {})
    assert flexible.decode([1.] * 6).power_rating_kw <= search.total_kw
    assert flexible.decode([1.] * 6).energy_capacity_kwh <= search.total_kwh


def test_screened_and_full_reduced_comparisons_record_actual_horizons():
    network, profiles = feeder(72, stress=True)
    simulation = settings(grid_import_limit_kw=110.)
    economics = econ()
    policy = ConstraintAwareDispatch(.12, 0.)
    bounds = OptimizationBounds((2, 3, 4), (20., 40.), (40., 80.))
    search = FleetSearchConfig(counts=(1, 2), total_kw=40., total_kwh=80., top_k=2, exploration=1,
                               window_days=1, window_count=2, trial_kw=20., finalists=1, require_annual=False)
    opts = OptimizerConfig(3, 1, seed=19)
    cache = BaselineCache()
    screened = run_fleet_experiment(network, profiles, simulation, economics, policy, BESSParameters(.9, .9),
                                    bounds, opts, search, clock="UTC", cache=cache)
    full = run_fleet_experiment(network, profiles, simulation, economics, policy, BESSParameters(.9, .9),
                                bounds, opts, replace(search, screened=False), clock="UTC", cache=cache)
    assert screened.baseline is full.baseline
    assert screened.metadata["annual_verified"] is False
    assert {item.hours for item in screened.screened} == {48}
    assert all(item.hours == 72 for item in screened.verified + full.verified)
    assert all(item.stage == "B" for item in full.verified)
    assert len({item.candidate for item in screened.verified}) == len(screened.verified)
    assert any(bus["selection"] == "exploration outside top K" for bus in screened.metadata["bus_severity"].values())
    assert any(probe["direction"] == "charge" and probe["accepted_kw"] < 0
               for bus in screened.metadata["bus_severity"].values() for probe in bus["probes"])
    for objective, rows in screened.winners.items():
        assert all(item is None or item.stage == "B" and rank(item, objective, search)[0] < float("inf") for item in rows.values())
    assert cache.run(network, profiles, simulation, economics, "local") is not full.baseline


def test_voltage_support_is_derived_from_verified_site_trials():
    network, profiles = feeder(24, stress=True)
    simulation = settings()
    baseline = simulate_timeseries(network, profiles, simulation)
    selected, branches, scores, sections, timing = rank_locations(network, profiles, simulation, baseline, (2, 3, 4), 1, 1,
                                                                20., samples=2)
    assert len(selected) == 2 and len({sections[bus] for bus in selected}) == 2
    assert timing["fbs_calls"] > 0
    assert all(branch["pre_control_overload_hours"] is None for branch in branches)
    assert all(row["final_export_kw"] <= 1e-6 for bus in scores.values() for row in bus["probes"] if row["accepted_kw"])


def test_highest_total_shedding_bus_can_miss_the_best_critical_hour_site():
    network, starter = feeder(24)
    network = replace(network, lines=[Line("12", 1, 2, .02, .002), Line("13", 1, 3, .12, .002),
                                     Line("14", 1, 4, .12, .002)])
    load = {1: [0.] * 24, 2: [10.] * 24, 3: [90.] * 22 + [10.] * 2, 4: [10.] * 22 + [160.] * 2}
    profiles = ProfileData.from_arrays(starter.timestamps, load, {bus: [0.] * 24 for bus in load},
                                       {4: [0.] * 24}, {4: [0.] * 24})
    simulation = settings(voltage_min_pu=.95)
    baseline = simulate_timeseries(network, profiles, simulation)
    selected, _, scores, _, _ = rank_locations(network, profiles, simulation, baseline, (2, 3, 4), 1, 1,
                                               20., samples=2)
    assert max(scores, key=lambda bus: scores[bus]["shed_mwh"]) == 3
    assert selected[0] == 4 and scores[4]["shedding_relief_score"] > scores[3]["shedding_relief_score"]


def test_stage_b_verifies_complete_calendar_year():
    network, original = feeder(1)
    stamps = pd.date_range("2021-01-01", periods=8760, freq="h")
    profiles = ProfileData.from_arrays(stamps, {bus: values * 8760 for bus, values in original.load_p_kw.items()},
        {bus: values * 8760 for bus, values in original.load_q_kvar.items()}, {4: [0.] * 8760}, {4: [0.] * 8760})
    search = FleetSearchConfig(counts=(2,), total_kw=40., total_kwh=80., top_k=2, exploration=0,
                               window_days=1, window_count=1, trial_kw=5., finalists=1)
    trial = run_fleet_experiment(network, profiles, settings(), econ(), None, BESSParameters(.9,.9),
                                 OptimizationBounds((2, 3), (20.,), (40.,)), OptimizerConfig(3, 1), search)
    assert trial.metadata["annual_verified"] is True
    assert trial.screened[0].hours == 24
    result = trial.winners["economics"][2]
    assert result.feasible and result.hours == 8760 and result.details["cost_basis"] == "verified annual USD/year"
    assert all(value == pytest.approx(.5) for value in result.details["terminal_soc"].values())
