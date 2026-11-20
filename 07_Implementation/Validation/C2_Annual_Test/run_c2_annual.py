"""C2 — year-ahead forecast (ONE 8,784-hour forecast; NO daily refits).

Run: python run_c2_annual.py
Edit SETTINGS below. Uses project forecasting functions unchanged.
https://github.com/Islahi/EE499-Team16.git
"""
from __future__ import annotations

import json
import importlib.util
from copy import copy
from datetime import datetime
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

from src_accelerated.forecasting import ForecastConfig, generate_forecast, _fit_predict, _hourly_baseline
from src_accelerated.pv_model import read_irradiance
from c2_inputs import prepare_total_load, prepare_distributed_15bus, write_profile, require_continuous

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / 'C2_annual_results'
DATA_SOLAR = ROOT / 'Data' / 'NASA_POWER'

# --------------------------- SETTINGS ---------------------------------
TRAIN_START = '2017-06-01 00:00:00'
TEST_START  = '2019-03-01 00:00:00'
TEST_END    = '2020-02-29 23:00:00'
SEASONAL_PERIOD = 24
VALIDATION_HOURS = 24       # Original generate_forecast() internal check
RUN_GOIENER_TOTAL = True
RUN_DISTRIBUTED_15BUS = True
RUN_IRRADIANCE = True
SOLAR_SITES = 'all'         # 'all', or 1/2/3/... for first N sites
PREPARE_ONLY = False       # True: prepare actual CSV files without model fit
# ----------------------------------------------------------------------

# Calculate the training length with standard Python datetime (no NumPy timedelta).
# The last training timestamp must be one hour BEFORE TEST_START.
train_duration = datetime.fromisoformat(TEST_START) - datetime.fromisoformat(TRAIN_START)
train_duration_hours = train_duration.total_seconds() / 3600
if train_duration_hours <= 0 or not train_duration_hours.is_integer():
    raise ValueError('TRAIN_START and TEST_START must define whole training hours')
TRAIN_HOURS = int(train_duration_hours)
TRAIN_CLOCK = pd.date_range(start=TRAIN_START, periods=TRAIN_HOURS, freq='h')
TEST_CLOCK = pd.date_range(start=TEST_START, end=TEST_END, freq='h')
FORECAST_HOURS = len(TEST_CLOCK)


def subset_profile(full, wanted):
    """Return only the explicitly requested timestamps for the existing forecast API."""
    clock = require_continuous(full.timestamps, 'ProfileData')
    wanted = pd.DatetimeIndex(wanted)
    index = clock.get_indexer(wanted)
    if (index < 0).any():
        raise ValueError(f'Profile missing required timestamp: {wanted[np.where(index < 0)[0][0]]}')
    view = copy(full)
    view.timestamps = list(wanted.to_pydatetime())
    for key in ('load_p_kw','load_q_kvar','pv_p_kw','pv_q_kvar'):
        setattr(view, key, {bus: np.asarray(values, dtype=float)[index].tolist()
                            for bus,values in getattr(full,key).items()})
    return view


def save_load_profiles(profiles, destination, file_prefix):
    write_profile(destination/f'{file_prefix}_load_profile.csv', profiles.timestamps,
                  profiles.load_p_kw, profiles.load_q_kvar)
    write_profile(destination/f'{file_prefix}_pv_profile.csv', profiles.timestamps,
                  profiles.pv_p_kw, profiles.pv_q_kvar)


def metrics(actual, predicted, unit):
    actual, predicted = np.asarray(actual, float), np.asarray(predicted, float)
    if len(actual) != len(predicted) or not len(actual):
        raise ValueError('Forecast length does not match observed test period')
    if not np.all(np.isfinite(predicted)) or not np.all(np.isfinite(actual)):
        raise ValueError('Actual/forecast has non-finite values')
    error = predicted - actual
    denom = np.maximum(abs(actual) + abs(predicted), 1e-8)
    rmse = float(np.sqrt(np.mean(error**2)))
    mean_actual = float(np.mean(actual))
    return {'hours':len(actual), 'unit':unit, 'mae':float(np.mean(abs(error))),
            'rmse':rmse, 'nrmse_percent':100*rmse/mean_actual if mean_actual > 0 else None,
            'smape_percent':float(np.mean(200*abs(error)/denom))}


def save_comparison(destination, actual, predicted, label, unit):
    """Detailed comparison and monthly accuracy; *pair files* remain unchanged-format CSVs."""
    table = pd.DataFrame({'timestamp':TEST_CLOCK, 'actual':actual, 'forecast':predicted})
    table['error'] = table.forecast-table.actual
    table.to_csv(destination/f'{label}_hourly_comparison.csv', index=False)
    table['month'] = table.timestamp.dt.to_period('M')
    monthly = []
    for month, part in table.groupby('month',sort=True):
        monthly.append({'month':str(month),**metrics(part.actual,part.forecast,unit)})
    pd.DataFrame(monthly).to_csv(destination/f'{label}_monthly_metrics.csv',index=False)
    return metrics(actual,predicted,unit)


def save_json(path, value):
    path.write_text(json.dumps(value,indent=2,default=str),encoding='utf-8')


def run_load(name, prepared, context):
    destination = RESULTS/name
    destination.mkdir(parents=True,exist_ok=True)
    observed = subset_profile(prepared,TEST_CLOCK)
    historical = subset_profile(prepared,TRAIN_CLOCK)
    save_load_profiles(observed,destination,'actual')
    print(f'[{name}] Saved observed year: {FORECAST_HOURS:,} hours, {len(observed.load_p_kw)} buses')
    if PREPARE_ONLY:
        return {'test':name,'status':'PREPARED_ONLY','hours':FORECAST_HOURS}

    # Validation fits the first 15,288 hours and checks the final 24 hours;
    # the production fit uses ALL 15,312 historical hours, and forecasts
    # 8,784 hours in one call. NO actual test-year observations enter fitting.
    cfg = ForecastConfig(horizon_hours=FORECAST_HOURS,
                         train_hours=TRAIN_HOURS,
                         validation_hours=VALIDATION_HOURS,
                         seasonal_period=SEASONAL_PERIOD,
                         method='autoarima')
    started = perf_counter()
    report = generate_forecast(historical,cfg)  # ORIGINAL PROJECT FUNCTION
    duration = perf_counter()-started
    predicted = report.profiles
    if not pd.DatetimeIndex(predicted.timestamps).equals(TEST_CLOCK):
        raise ValueError('Forecast timestamp range differs from entire held-out year')
    save_load_profiles(predicted,destination,'forecast')
    buses = sorted(observed.load_p_kw)
    obs_total = sum(np.asarray(observed.load_p_kw[b],float) for b in buses)
    pred_total = sum(np.asarray(predicted.load_p_kw[b],float) for b in buses)
    summary = {'test':name, 'status':'OK','prediction_mode':'single_year_ahead',
               'train_hours':TRAIN_HOURS,'forecast_hours':FORECAST_HOURS,
               'runtime_seconds':round(duration,2),
               'aggregate':save_comparison(destination,obs_total,pred_total,'total_load','kW'),
               'internal_24h_scores':report.scores['load'],
               'source_context':context}
    per_bus=[]
    for bus in buses:
        s=metrics(observed.load_p_kw[bus],predicted.load_p_kw[bus],'kW')
        per_bus.append({'bus_id':bus,**s})
    pd.DataFrame(per_bus).to_csv(destination/'bus_metrics.csv', index=False)
    save_json(destination/'summary.json',summary)
    print(f'[{name}] RMSE={summary["aggregate"]["rmse"]:.3f} kW, '
          f'NRMSE={summary["aggregate"]["nrmse_percent"]:.2f}%, runtime={duration:.1f}s')
    return {'test':name, 'status':'OK','rmse':summary['aggregate']['rmse'],
            'nrmse_percent':summary['aggregate']['nrmse_percent'],
            'hours':FORECAST_HOURS,'runtime_seconds':round(duration,2)}


def run_solar(path):
    site = path.stem.replace('POWER_Point_Hourly_20141101_20201129_', '').replace('_UTC','')
    name = 'C_Irradiance_'+site
    destination = RESULTS/name
    destination.mkdir(parents=True,exist_ok=True)
    solar = read_irradiance(path,source='nasa_power')  # ORIGINAL PROJECT READER
    times = require_continuous(solar.timestamp,name)
    training_index = times.get_indexer(TRAIN_CLOCK)
    testing_index = times.get_indexer(TEST_CLOCK)
    if (training_index<0).any() or (testing_index<0).any():
        raise ValueError(f'{name}: missing annual training or test timestamp')
    history = solar.irradiance_w_m2.to_numpy(float)[training_index]
    actual = solar.irradiance_w_m2.to_numpy(float)[testing_index]
    pd.DataFrame({'timestamp':TEST_CLOCK,'irradiance_w_m2':actual}).to_csv(
        destination/'actual_irradiance.csv',index=False)
    print(f'[{name}] Saved observed irradiance: {FORECAST_HOURS:,} hours')
    if PREPARE_ONLY:
        return {'test':name,'status':'PREPARED_ONLY','hours':FORECAST_HOURS}

    cfg = ForecastConfig(horizon_hours=FORECAST_HOURS, train_hours=TRAIN_HOURS,
                         validation_hours=VALIDATION_HOURS,method='autoarima',
                         seasonal_period=SEASONAL_PERIOD)
    start = perf_counter()
    forecast = _fit_predict(history,TRAIN_CLOCK,TEST_CLOCK,cfg)  # ORIGINAL PROJECT FITTER
    duration = perf_counter()-start
    baseline = _hourly_baseline(history,TRAIN_CLOCK,TEST_CLOCK)
    pd.DataFrame({'timestamp':TEST_CLOCK,'irradiance_w_m2':forecast}).to_csv(
        destination/'forecast_irradiance.csv',index=False)
    score = save_comparison(destination,actual,forecast,'irradiance','W/m²')
    # Unmodified irradiance CSV shape: timestamp,irradiance_w_m2
    daylight = actual>0
    summary={'test':name, 'status':'OK','prediction_mode':'single_year_ahead',
             'train_hours':TRAIN_HOURS,'forecast_hours':FORECAST_HOURS,
             'runtime_seconds':round(duration,2), 'all_hours':score,
             'daylight':metrics(actual[daylight],forecast[daylight],'W/m²'),
             'baseline_rmse':metrics(actual,baseline,'W/m²')['rmse'],
             'source_file':path.name,'source_clock':'UTC',
             'note':'NASA GHI irradiance, not PV electrical output; source forecast fitter unchanged.'}
    save_json(destination/'summary.json',summary)
    print(f'[{name}] RMSE={score["rmse"]:.3f} W/m², '
          f'NRMSE={score["nrmse_percent"]:.2f}%, runtime={duration:.1f}s')
    return {'test':name, 'status':'OK','rmse':score['rmse'],
            'nrmse_percent':score['nrmse_percent'],
            'hours':FORECAST_HOURS,'runtime_seconds':round(duration,2)}


def main():
    print(f'Year-ahead C2: TRAIN {TRAIN_CLOCK[0]} to {TRAIN_CLOCK[-1]} ({TRAIN_HOURS:,} h)')
    print(f'               TEST {TEST_CLOCK[0]} to {TEST_CLOCK[-1]} ({FORECAST_HOURS:,} h)')
    if TRAIN_HOURS != 15312 or FORECAST_HOURS != 8784:
        raise ValueError('C2 annual experiment expects 15,312 train hours and 8,784 test hours')
    if not PREPARE_ONLY and importlib.util.find_spec('statsforecast') is None:
        raise SystemExit('Missing dependency. Install first: python -m pip install -r requirements.txt')
    RESULTS.mkdir(parents=True,exist_ok=True)
    prepared = RESULTS/'prepared_inputs'
    prepared.mkdir(exist_ok=True)
    rows=[]
    if RUN_GOIENER_TOTAL:
        full, context = prepare_total_load(prepared/'A_GoiEner_Total_Load')
        rows.append(run_load('A_GoiEner_Total_Load',full,context))
    if RUN_DISTRIBUTED_15BUS:
        full, context = prepare_distributed_15bus(prepared/'B_GoiEner_Distributed_15Bus',TRAIN_START,TEST_START)
        rows.append(run_load('B_GoiEner_Distributed_15Bus',full,context))
    if RUN_IRRADIANCE:
        sources=sorted(DATA_SOLAR.glob('*.csv'))
        if SOLAR_SITES!='all':sources=sources[:int(SOLAR_SITES)]
        if not sources: raise FileNotFoundError(f'No NASA irradiance CSVs in {DATA_SOLAR}')
        for path in sources:
            rows.append(run_solar(path))
    pd.DataFrame(rows).to_csv(RESULTS/'c2_annual_summary.csv',index=False)
    save_json(RESULTS/'experiment_settings.json',{
        'mode':'single_year_ahead_no_test_year_feedback',
        'train_start':TRAIN_START,'train_end':str(TRAIN_CLOCK[-1]),
        'test_start':TEST_START,'test_end':TEST_END,
        'training_hours':TRAIN_HOURS,'forecast_hours':FORECAST_HOURS,
        'seasonal_period':SEASONAL_PERIOD,'internal_validation_hours':VALIDATION_HOURS,
        'prepare_only':PREPARE_ONLY,
        'note':'No actual observations from test year are passed to AutoARIMA.'})
    print(f'\nCompleted {len(rows)} cases. Files: {RESULTS}')
    if PREPARE_ONLY:
        print('PREPARE_ONLY: observed CSVs prepared, NO forecasts or accuracy metrics measured.')


if __name__=='__main__':
    main()
