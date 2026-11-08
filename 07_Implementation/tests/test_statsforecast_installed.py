"""Optional live-library smoke test, executed if Nixtla StatsForecast is installed.

This is intentionally distinct from the fast API-mock tests so that a missing
StatsForecast package does not create a misleading 'full integration passed'.
"""
from io import StringIO
import pandas as pd
import pytest

pytest.importorskip('statsforecast')
from src_accelerated.data_loader import ProfileData
from src_accelerated.forecasting import ForecastConfig, generate_forecast


def test_real_statsforecast_produces_hourly_csv_profiles():
    hours = pd.date_range('2018-03-01', periods=150, freq='h')
    rows_load = [dict(timestamp=t,bus_id=2,p_kw=110.0 + 12.0*(9 <= t.hour < 19),q_kvar=45.0)
                 for t in hours]
    rows_pv = [dict(timestamp=t,bus_id=2,p_kw=0.0,q_kvar=0.0) for t in hours]
    profiles = ProfileData(StringIO(pd.DataFrame(rows_load).to_csv(index=False)),
                           StringIO(pd.DataFrame(rows_pv).to_csv(index=False)))
    config = ForecastConfig(horizon_hours=6, train_hours=96, validation_hours=24,
                            method='arima', max_p=1,max_q=1,max_P=0,max_Q=0,nmodels=6)
    report = generate_forecast(profiles, config)
    assert len(report.profiles.timestamps) == 6
    assert len(report.profiles.load_p_kw[2]) == 6
    assert report.model_info['estimator'] == 'statsforecast.models.AutoARIMA'
    assert report.scores['load']['autoarima']['mae'] >= 0
