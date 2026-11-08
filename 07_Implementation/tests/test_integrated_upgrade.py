"""Regression tests for the integrated source upgrade (no GUI required)."""
from dataclasses import replace
from io import StringIO
from pathlib import Path
import pandas as pd
import pytest

from src_accelerated.data_loader import ProfileData
from src_accelerated.bess import BESSConfig
from src_accelerated.fbs import FBSConfig
from src_accelerated.forecasting import ForecastConfig, generate_forecast
from src_accelerated.metrics import EconomicConfig, evaluate_results
from src_accelerated.network_model import Bus, Line, Load, NetworkModel
from src_accelerated.optimizer import (BESSCandidate, CandidateEvaluation, OptimizationBounds,
    OptimizerConfig, SimulationEvaluator, BESSParameters, genetic_optimize, optimize)
from src_accelerated.simulation import (GridAwareDispatchPolicy,
    SimulationConfig, simulate_timeseries)
from src_accelerated.ui_workflow import DataRequest, RunSettings, prepare_study, run_study


def simple_network(ampacity=None):
    return NetworkModel([Bus(1, "slack", 12.66, True), Bus(2, "load", 12.66)],
                        [Line("1-2", 1, 2, 0.03, 0.02, ampacity)],
                        [Load("L2", 2, 100.0, 40.0)], [], 1000.0, 60.0)


def source_data(hours=96, load=100.0, pv=0.0):
    dates = pd.date_range('2017-06-03', periods=hours, freq='h')
    a = pd.DataFrame({'timestamp': dates, 'bus_id': 2,
                      'p_kw': [load + (10 if t.hour in range(12, 18) else 0) for t in dates],
                      'q_kvar': 40.0})
    b = pd.DataFrame({'timestamp': dates, 'bus_id': 1,
                      'p_kw': pv, 'q_kvar': 0.0})
    return ProfileData(StringIO(a.to_csv(index=False)),StringIO(b.to_csv(index=False)))


def test_annual_cost_has_consistent_units_and_known_crf():
    network, profiles = simple_network(), source_data(hours=24)
    settings = SimulationConfig(reserve_fraction=0, fbs_config=FBSConfig())
    battery = BESSConfig(2, 500, 200, .2, 1, .5, .9, .9)
    simulation = simulate_timeseries(network, profiles, settings, battery,
                                     GridAwareDispatchPolicy())
    econ = EconomicConfig(385, 770, 'USD', grid_import_tariff_per_kwh=.20)
    result = evaluate_results(simulation, econ, battery)
    assert result.bess_cost == 385*500+770*200
    crf = .06 * 1.06**10 / (1.06**10-1)
    assert result.annualized_bess_cost == pytest.approx(result.bess_cost * (crf+.02))
    assert result.annual_total_cost == pytest.approx(result.annualized_bess_cost + result.annual_grid_cost
        + result.annual_curtailment_cost + result.annual_shedding_cost
        + result.annual_terminal_energy_cost)


def test_ga_and_gwo_shared_evaluator_and_valid_catalogs():
    network, profile = simple_network(), source_data(hours=24)
    bounds = OptimizationBounds((2,), (50.0,100.0), (100.0,200.0))
    def evaluator(n, p, candidate):
        return CandidateEvaluation(candidate,candidate.power_rating_kw+candidate.energy_capacity_kwh,True)
    conf = OptimizerConfig(4,4,seed=17)
    for fn in (genetic_optimize,optimize):
        outcome = fn(network,profile,bounds,evaluator,conf)
        assert outcome.success
        assert outcome.best_candidate in [BESSCandidate(2,p,e) for p in (50,100) for e in (100,200)]
        assert len(outcome.convergence_history) == 4


def test_importer_uses_full_source_timestamps(tmp_path):
    network_path = Path(__file__).parent.parent/'src_accelerated/Results/Sessions/20261021_214850_guide_5bus_radial_test/inputs/network.xlsx'
    if not network_path.is_file():
        pytest.skip('Optional uploaded sample workbook absent')
    from src_accelerated.network_loader import load_network
    network = load_network(network_path,workbook_format='auto')
    data = source_data(hours=33)
    # Actual workbook has 4 load buses; build a dated CSV for each.
    t = pd.date_range('2017-06-03', periods=33,freq='h')
    rows = [dict(timestamp=ts,bus_id=load.bus_id,p_kw=load.p_base_kw,q_kvar=load.q_base_kvar)
            for ts in t for load in network.loads]
    file = tmp_path/'load.csv';pd.DataFrame(rows).to_csv(file,index=False)
    req = DataRequest(network_path,None,'auto',None,None,'none',load_source='imported',load_path=file)
    prepared = prepare_study(req)
    assert len(prepared.profiles.timestamps) == 33
    assert str(prepared.profiles.timestamps[0]).startswith('2017-06-03')
    assert prepared.context['Study scope'].startswith('Complete timestamps')


def _mock_nixtla(monkeypatch):
    """Strict API test double; not a substitute for testing installed StatsForecast."""
    import sys
    import types
    calls = []

    class FakeAutoARIMA:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            assert kwargs["alias"] == "AutoARIMA"
            assert kwargs["stepwise"] and kwargs["max_p"] >= 0

    class FakeStatsForecast:
        def __init__(self, models, freq, n_jobs):
            assert len(models) == 1 and freq == "h" and n_jobs == 1
            self.model = models[0]

        def forecast(self, df, h, X_df=None):
            assert {"unique_id", "ds", "y"}.issubset(df.columns)
            assert df.unique_id.nunique() == 1
            assert list(df.ds) == list(pd.date_range(df.ds.iloc[0], periods=len(df), freq="h"))
            assert h > 0
            uses_exog = self.model.kwargs.get("seasonal") and X_df is not None
            if X_df is not None:
                assert X_df.columns.tolist() == df.drop(columns="y").columns.tolist()
                assert len(X_df) == h
                assert X_df.ds.iloc[0] == df.ds.iloc[-1] + pd.Timedelta(hours=1)
            calls.append({"seasonal": self.model.kwargs["seasonal"],
                          "season_length": self.model.kwargs["season_length"],
                          "uses_exog": uses_exog, "n_train": len(df), "n_forecast": h})
            return pd.DataFrame({"unique_id": "feeder",
                "ds": pd.date_range(df.ds.iloc[-1] + pd.Timedelta(hours=1), periods=h, freq="h"),
                "AutoARIMA": [float(df.y.mean())] * h})

    fake = types.ModuleType("statsforecast")
    fake_models = types.ModuleType("statsforecast.models")
    fake.StatsForecast = FakeStatsForecast
    fake_models.AutoARIMA = FakeAutoARIMA
    fake.models = fake_models
    monkeypatch.setitem(sys.modules, "statsforecast", fake)
    monkeypatch.setitem(sys.modules, "statsforecast.models", fake_models)
    return calls


@pytest.mark.parametrize("method", ["autoarima", "arima", "sarima", "sarimax"])
def test_forecasting_uses_statsforecast_autoarima_and_holdout(monkeypatch, method):
    calls = _mock_nixtla(monkeypatch)
    data = source_data(hours=180)
    report = generate_forecast(data, ForecastConfig(horizon_hours=8,
        train_hours=100, validation_hours=24, method=method))
    assert report.model_info["estimator"] == "statsforecast.models.AutoARIMA"
    assert report.model_info["order_selection"].startswith("automatic")
    assert len(report.profiles.timestamps) == 8
    assert report.profiles.timestamps[0] > data.timestamps[-1]
    assert report.scores["load"]["autoarima"]["rmse"] >= 0
    assert min(report.profiles.load_p_kw[2]) >= 0
    # The holdout fit cannot see the last 24 observations; the final fit can.
    assert len(calls) == 2  # PV=0, so only load requires two forecast runs.
    assert calls[0]["n_train"] == 100
    assert calls[0]["n_forecast"] == 24
    assert calls[1]["n_train"] == 124
    assert calls[1]["n_forecast"] == 8
    assert all(c["seasonal"] == (method != "arima") for c in calls)
    assert all(c["uses_exog"] == (method == "sarimax") for c in calls)


def test_autoarima_dependency_and_defaults():
    assert ForecastConfig().method == "autoarima"
    assert ForecastConfig().seasonal_period == 24
    requirements = (Path(__file__).parent.parent / "requirements.txt").read_text()
    assert "statsforecast" in requirements
    assert "pmdarima" not in requirements


def test_ampacity_enforced_when_network_has_rating():
    network, profile = simple_network(ampacity=.01), source_data(hours=2)
    result = simulate_timeseries(network,profile,SimulationConfig(reserve_fraction=0))
    assert result.completed and result.converged and not result.feasible
    assert any('Line ampacity exceeded' in m for s in result.steps for m in s.messages)


def test_terminal_soc_optional_strict_limit():
    network, profile = simple_network(),source_data(hours=2)
    bess = BESSConfig(2,200,100,.1,.9,.5,.9,.9)
    result = simulate_timeseries(network,profile,SimulationConfig(reserve_fraction=0,terminal_soc_tolerance=0.001),
                                 bess,GridAwareDispatchPolicy())
    assert result.completed and not result.feasible
    assert any('Terminal SOC' in m for m in result.steps[-1].messages)


def test_no_bess_is_an_economic_option():
    network, profile = simple_network(), source_data(hours=24)
    from types import SimpleNamespace
    study = SimpleNamespace(network=network,profiles=profile,context={'Network':'2-bus'},forecast_info=None)
    values={'spin_eta_charge_percent':90.,'spin_eta_discharge_percent':90.,
      'spin_soc_min_percent':10.,'spin_soc_max_percent':90.,'spin_soc_initial_percent':50.,
      'allowed_buses':(2,), 'spin_opt_power_min_kw':50.,'spin_opt_power_max_kw':100.,
      'spin_opt_power_step_kw':50.,'spin_opt_energy_min_kwh':100.,
      'spin_opt_energy_max_kwh':200.,'spin_opt_energy_step_kwh':100.,
      'spin_cpu_workers':1,'spin_gwo_population':3,'spin_gwo_iterations':2,'spin_gwo_seed':42,
      'spin_ga_population':5,'spin_ga_generations':3,
      'optimizer_algorithm':'GA','spin_ga_crossover':.8,'spin_ga_mutation':.2}
    report=run_study(study,RunSettings(SimulationConfig(reserve_fraction=0),
         EconomicConfig(385,770,'USD',grid_import_tariff_per_kwh=0),None,values,
         GridAwareDispatchPolicy()),optimization=True)
    assert report.result.success
    assert report.result.metadata.get('no_bess_selected')
    assert report.result.best_candidate is None
    assert report.result.best_objective==0.0
    assert report.result.metadata['population_size'] == 5
    assert report.result.metadata['algorithm'] == 'GA'
    assert report.result.iterations == 3
