"""C2 2021 neural benchmark: causal recursive weekly NHITS/NBEATSx rollout.

Only train targets dated before 2021-01-01 are given to NeuralForecast.fit.
At each forecast step the model receives past training targets and its OWN earlier
predictions; it never receives an actual target from the 2021 holdout.
Future exogenous inputs are deterministic calendar coordinates only.

Compatible with neuralforecast==3.1.9, Python 3.12 (CPU).
Project: https://github.com/Islahi/EE499-Team16.git
"""
from __future__ import annotations

from time import perf_counter
import sys
import numpy as np
import pandas as pd

HORIZON = 168  # 7 days
INPUT_SIZE = 672  # 28 days
VALIDATION_HOURS = 120 * 24
TRIALS = 2
NEURAL_IMPL_VERSION = 'C2_NEURAL_RECURSIVE_W168_V1'
FEATURES = (
    'cal_daily_sin', 'cal_daily_cos',
    'cal_weekly_sin', 'cal_weekly_cos',
    'cal_monthly_sin', 'cal_monthly_cos',
    'cal_yearly_sin', 'cal_yearly_cos',
)


def _calendar_frame(times: pd.DatetimeIndex) -> pd.DataFrame:
    """Causal deterministic features; no historical or future load/PV readings."""
    ix = pd.DatetimeIndex(times)
    if ix.tz is not None:
        raise ValueError('The C2 prepared dataset uses timezone-naive timestamps')
    base = (ix - pd.Timestamp('2017-01-01')).total_seconds().to_numpy() / 3600.0
    phase = {
        'daily': (ix.hour.to_numpy() / 24.0),
        'weekly': ((ix.dayofweek.to_numpy() * 24 + ix.hour.to_numpy()) / 168.0),
        'monthly': (base / (365.2425 * 24 / 12)),
        'yearly': ((ix.dayofyear.to_numpy() - 1 + ix.hour.to_numpy() / 24.0)
                   / np.where(ix.is_leap_year, 366.0, 365.0)),
    }
    out = pd.DataFrame({'ds': ix})
    for period, fraction in phase.items():
        angle = 2 * np.pi * fraction
        out[f'cal_{period}_sin'] = np.sin(angle).astype('float32')
        out[f'cal_{period}_cos'] = np.cos(angle).astype('float32')
    return out


def _training_frame(dates, y):
    ix = pd.DatetimeIndex(dates)
    values = np.asarray(y, dtype=np.float64)
    if len(ix) != len(values) or not np.isfinite(values).all():
        raise ValueError('Neural training timestamps/targets are invalid')
    if (ix.to_series().diff().dropna() != pd.Timedelta(hours=1)).any():
        raise ValueError('Training observations must be consecutive hourly values')
    return _calendar_frame(ix).assign(unique_id='C2', y=values)


def _config(trial):
    """Small, feasible Optuna search shared across AutoNHITS and AutoNBEATSx."""
    return {
        'input_size': INPUT_SIZE,
        'futr_exog_list': list(FEATURES),
        'max_steps': trial.suggest_categorical('max_steps', [120, 200]),
        'learning_rate': trial.suggest_categorical('learning_rate', [0.001, 0.0003]),
        'step_size': 24,
        'batch_size': 32,
        'windows_batch_size': 128,
        'scaler_type': 'standard',
        'random_seed': 16,
        'val_check_steps': 60,
        'num_lr_decays': 1,
        'mlp_units': [[128, 128], [128, 128], [128, 128]],
        'enable_progress_bar': False,
        'enable_model_summary': False,
        'logger': False,
        'accelerator': 'cpu',
        'devices': 1,
    }


def recursive_rollout(fitted_nf, history, test_times, context_hours=INPUT_SIZE * 2, horizon=HORIZON):
    """Forecast every holdout hour, extending history with predictions only.

    This helper is separated from model fitting to allow tests that verify no
    true future observations enter the recursive state.
    """
    expected = pd.DatetimeIndex(test_times)
    if not len(expected):
        raise ValueError('Empty forecast index')
    if expected[0] != pd.Timestamp(history.ds.iloc[-1]) + pd.Timedelta(hours=1):
        raise ValueError('First forecast hour must immediately follow the training history')
    if len(expected) > 1 and (expected[1:] - expected[:-1] != pd.Timedelta(hours=1)).any():
        raise ValueError('Forecast must have continuous hourly timestamps')
    hist = history.copy()
    results = []
    for start in range(0, len(expected), horizon):
        # The final call may forecast beyond the holdout; only needed timestamps are used.
        block_times = pd.date_range(expected[start], periods=horizon, freq='h')
        future = _calendar_frame(block_times)
        future.insert(0, 'unique_id', 'C2')
        context = hist.iloc[-context_hours:].copy()
        fc = fitted_nf.predict(df=context, futr_df=future)
        if hasattr(fc, 'to_pandas'):
            fc = fc.to_pandas()
        fc = pd.DataFrame(fc).sort_values('ds').reset_index(drop=True)
        fc_dates = pd.DatetimeIndex(pd.to_datetime(fc.ds))
        if len(fc) != horizon or not fc_dates.equals(block_times):
            raise RuntimeError('NeuralForecast returned unexpected forecast timestamps')
        columns = [c for c in fc.columns if c not in ('unique_id', 'ds', 'cutoff')]
        if len(columns) != 1:
            raise RuntimeError(f'Expected one neural point forecast column, got {columns}')
        pred = fc[columns[0]].to_numpy(dtype=float)
        if not np.isfinite(pred).all():
            raise FloatingPointError(f'Non-finite recursive forecast at {block_times[0]}')
        # Nonnegative electricity demand/solar output; the main worker separately
        # performs its usual physical checks before scoring all model families.
        take = min(horizon, len(expected) - start)
        used = np.maximum(pred[:take], 0.0)
        results.extend(used.tolist())
        add = future.iloc[:take].copy()
        add['y'] = used  # Never append actual 2021 observations.
        hist = pd.concat((hist, add), ignore_index=True)
    if len(results) != len(expected):
        raise RuntimeError('Incomplete neural full-year forecast')
    return np.asarray(results, dtype=float)


def run_neural_recursive(name, y, periods, train_times, test_times):
    """NeuralForecast 3.1.9 AutoNHITS/AutoNBEATSx, tuned only before 2021."""
    if name not in ('AutoNHITS', 'AutoNBEATSx'):
        raise ValueError(f'Unsupported neural model: {name}')
    if tuple(periods) != (24, 168, 720, 8760):
        raise ValueError('Current neural benchmark requires the full calendar feature configuration')
    import torch
    import optuna
    import neuralforecast
    from neuralforecast import NeuralForecast
    from neuralforecast.auto import AutoNHITS, AutoNBEATSx

    major_minor = tuple(int(x) for x in neuralforecast.__version__.split('.')[:2])
    if major_minor != (3, 1):
        raise RuntimeError('This tested neural configuration requires neuralforecast==3.1.9')
    torch.set_num_threads(2)
    torch.manual_seed(16)
    data = _training_frame(train_times, y)
    if len(data) < INPUT_SIZE + VALIDATION_HOURS + HORIZON:
        raise ValueError('Insufficient training history for 120-day neural validation')

    cls = AutoNHITS if name == 'AutoNHITS' else AutoNBEATSx
    model = cls(
        h=HORIZON,
        backend='optuna',
        config=_config,
        num_samples=TRIALS,
        search_alg=optuna.samplers.TPESampler(seed=16),
        verbose=False,
        # cpus/gpus are *not* passed: they were removed in NeuralForecast 3.2.
        # The torch/Lightning config explicitly selects CPU.
    )
    nf = NeuralForecast(models=[model], freq='h')
    start = perf_counter()
    nf.fit(df=data, val_size=VALIDATION_HOURS)
    fit_time = perf_counter() - start
    start = perf_counter()
    forecast = recursive_rollout(nf, data, test_times)
    rollout_time = perf_counter() - start
    best = getattr(model, 'results', None)
    best_trial = getattr(best, 'best_trial', None)
    best_params = getattr(best_trial, 'params', {}) if best_trial is not None else {}
    info = {
        'neural_strategy_version': NEURAL_IMPL_VERSION,
        'model_family': name,
        'neuralforecast_version': neuralforecast.__version__,
        'pytorch_version': torch.__version__,
        'python_major_minor': f'{sys.version_info.major}.{sys.version_info.minor}',
        'device': 'cpu',
        'forecast_strategy': '168-hour direct blocks, recursively chained for the full 2021 holdout',
        'forecast_horizon_per_block_hours': HORIZON,
        'forecast_context_hours': INPUT_SIZE,
        'forecast_hours': len(test_times),
        'forecast_blocks': int(np.ceil(len(test_times) / HORIZON)),
        'validation_hours': VALIDATION_HOURS,
        'validation_source': 'last 120 days of training only',
        'optuna_trials': TRIALS,
        'selected_optuna_params': best_params,
        'calendar_features': list(FEATURES),
        'monthly_cycle_note': '365.2425/12 day approximation, not exact calendar months',
        'uses_2021_actuals_for_fitting_or_rollout': False,
        'recursive_updates': 'append own predictions, never actual 2021 readings',
        'training_and_tuning_seconds': round(fit_time, 3),
        'rollout_seconds': round(rollout_time, 3),
        'comparability_note': 'Same full-year 2021 held-out evaluation; recursive neural strategy differs from direct-year classical regressions',
    }
    return forecast, nf, info
