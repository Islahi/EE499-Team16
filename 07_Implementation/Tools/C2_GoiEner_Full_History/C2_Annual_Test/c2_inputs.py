"""Input preparation for C2. The forecasting model is not implemented here.

EE499 Team 16 — source: https://github.com/Islahi/EE499-Team16.git
"""
from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from src_accelerated.data_loader import ProfileData
from src_accelerated.network_loader import load_network as load_project_network
from GoiEner_Load_Distributor_Simple.distribution_engine import (
    load_profiles, load_network as load_distributor_network,
    demo_cycle, normalized_multipliers,
)

ROOT = Path(__file__).resolve().parent
CLEAN = ROOT / 'Data' / 'GoiEner_Cleaned_Profiles'
NETWORK = ROOT / 'T04_15-Bus_System_1.xlsx'


def require_continuous(times, name):
    t = pd.DatetimeIndex(pd.to_datetime(times))
    if len(t) < 2 or t.hasnans or t.tz is not None or not t.is_unique:
        raise ValueError(f'{name}: invalid timestamps')
    if not t.is_monotonic_increasing or not np.all(np.diff(t.asi8) == pd.Timedelta(hours=1).value):
        raise ValueError(f'{name}: expected consecutive hourly timestamps')
    return t


def write_profile(path, times, p_by_bus, q_by_bus=None):
    """Write exact project ProfileData CSV schema: timestamp,bus_id,p_kw,q_kvar."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    q_by_bus = q_by_bus or {}
    times = pd.DatetimeIndex(times)
    p_by_bus = {int(k): np.asarray(v, dtype=float) for k,v in p_by_bus.items()}
    for bus, values in p_by_bus.items():
        if len(values) != len(times) or not np.all(np.isfinite(values)):
            raise ValueError(f'Invalid P series for bus {bus}')
        if bus in q_by_bus and len(q_by_bus[bus]) != len(times):
            raise ValueError(f'Invalid Q series for bus {bus}')
    with path.open('w', newline='', encoding='utf-8') as file:
        w = csv.writer(file)
        w.writerow(['timestamp', 'bus_id', 'p_kw', 'q_kvar'])
        for i, timestamp in enumerate(times):
            s = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            for bus in sorted(p_by_bus):
                q = float(q_by_bus[bus][i]) if bus in q_by_bus else 0.0
                w.writerow([s, bus, f'{p_by_bus[bus][i]:.10f}', f'{q:.10f}'])


def make_profile(directory, times, p_by_bus, q_by_bus=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    load_path = directory / 'load_profile.csv'
    pv_path = directory / 'pv_profile.csv'
    write_profile(load_path, times, p_by_bus, q_by_bus)
    # The original forecasting API expects a PV profile even for load-only tests.
    write_profile(pv_path, times, {min(p_by_bus): np.zeros(len(times))})
    return ProfileData(load_path, pv_path)


def prepare_total_load(prepared_folder):
    """Three cleaned sector *totals*, not average-customer series."""
    data = load_profiles(CLEAN, value_choice='sum')
    times = require_continuous(data.frame.timestamp, 'Whole GoiEner')
    sectors = ('residential', 'commercial', 'manufacturing')
    active = {i+1: data.frame[s].to_numpy(dtype=float) for i,s in enumerate(sectors)}
    if any((v < 0).any() for v in active.values()):
        raise ValueError('GoiEner includes negative power')
    return make_profile(prepared_folder, times, active), {
        'source': 'Cleaned GoiEner sector total load_kw',
        'bus_ids': {str(i+1):s for i,s in enumerate(sectors)},
        'note': 'Bus IDs 1–3 represent sectors, not physical feeder buses.',
    }


def prepare_distributed_15bus(prepared_folder, train_start, test_start):
    """Original distributor formula with calibration strictly before test_start."""
    data = load_profiles(CLEAN, value_choice='average')
    times = require_continuous(data.frame.timestamp, 'GoiEner average-customer profiles')
    net = load_distributor_network(NETWORK, frequency_hz=60.0)
    project = load_project_network(NETWORK, frequency_hz=60.0)
    if {b.bus_id for b in project.buses} != set(net.loads.bus_id):
        raise ValueError('15-bus loader assignments do not match')
    categories = demo_cycle(net)
    mask = (times >= pd.Timestamp(train_start)) & (times < pd.Timestamp(test_start))
    train = data.frame.loc[mask].copy()
    if train.empty:
        raise ValueError('No historical observations for normalization')
    normalized_multipliers(replace(data, frame=train), 'mean')
    sectors = ('residential', 'commercial', 'manufacturing')
    means = {s: float(train[s].mean()) for s in sectors}
    if any(v <= 0 or not np.isfinite(v) for v in means.values()):
        raise ValueError('Invalid training-only sector means')
    multipliers = {s: data.frame[s].to_numpy(float) / means[s] for s in sectors}
    active, reactive = {}, {}
    for row in net.loads.itertuples(index=False):
        bus = int(row.bus_id)
        sector = categories.get(bus)
        factor = multipliers[sector] if sector else np.zeros(len(times))
        active[bus] = float(row.p_base_kw) * factor
        reactive[bus] = float(row.q_base_kvar) * factor
    folder = Path(prepared_folder)
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{'bus_id': b, 'assigned_category': s} for b,s in sorted(categories.items())]).to_csv(
        folder/'bus_assignments.csv', index=False)
    return make_profile(folder, times, active, reactive), {
        'source': 'Cleaned GoiEner average-customer profiles and T04_15-Bus_System_1.xlsx',
        'allocation': 'demo_cycle categories, original P/Q nominal-load multiplier formula',
        'normalization': 'Only historical observations before test_start',
        'category_training_means': means,
        'note': 'Illustrative constructed load; NOT actual metered 15-bus consumption.',
    }
