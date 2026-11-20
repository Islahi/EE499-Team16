#!/usr/bin/env python3
"""Export fixed-cohort category data in the original GoiEner Cleaner's CSV layout.

Only formats already-computed cohort_output CSVs: NO archive reprocessing,
additional interpolation, model fitting, or category reassignment.

Target: GoiEner_Load_Distributor_Simple's directory source loader; it accepts
residential.csv, commercial.csv, manufacturing.csv or the wide ready CSV.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

CATEGORIES = ('residential', 'commercial', 'manufacturing')
WIDE_NAMES = {
    'residential': 'Residential-GoiEner-Aggregate',
    'commercial': 'Commercial-GoiEner-Aggregate',
    'manufacturing': 'Industrial-GoiEner-Aggregate',
}
LEGACY_COLS = (
    'timestamp', 'load_kwh', 'load_kw', 'average_customer_kw',
    'active_customers', 'no_customer_data_hour',
)


def _load_category(src: Path, category: str) -> pd.DataFrame:
    df = pd.read_csv(src)
    required = {'timestamp', 'load_kw', 'average_customer_kw', 'active_customers'}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f'{src}: missing {sorted(missing)}')
    if df.empty:
        raise ValueError(f'{src}: category dataset is empty')
    ts = pd.to_datetime(df['timestamp'], errors='raise')
    if ts.dt.tz is not None:
        raise ValueError(f'{src}: timezone-aware timestamps are not expected')
    if ts.duplicated().any():
        raise ValueError(f'{src}: duplicate timestamps')
    if not ts.is_monotonic_increasing:
        raise ValueError(f'{src}: timestamps must be chronological')
    if (ts.diff().dropna() != pd.Timedelta(hours=1)).any():
        raise ValueError(f'{src}: timestamps must follow a continuous hourly grid')
    out = pd.DataFrame({'timestamp': ts})
    count = pd.to_numeric(df['active_customers'], errors='raise').to_numpy(dtype=float)
    if not np.isfinite(count).all() or (count < 0).any() or not np.allclose(count, np.rint(count)):
        raise ValueError(f'{src}: invalid active-customer counts')
    power = pd.to_numeric(df['load_kw'], errors='raise').to_numpy(dtype=float)
    per_meter = pd.to_numeric(df['average_customer_kw'], errors='raise').to_numpy(dtype=float)
    for name, arr in [('load_kw', power), ('average_customer_kw', per_meter)]:
        if np.isinf(arr).any() or np.nanmin(arr) < 0:
            raise ValueError(f'{src}: invalid {name} values')
    if np.any((count > 0) & (~np.isfinite(power) | ~np.isfinite(per_meter))):
        raise ValueError(f'{src}: active customers but missing power at one or more hours')
    # Hourly GoiEner kWh measurements: hourly consumed kWh and average kW have
    # equal numeric values for each 1-hour interval, as in the original cleaner.
    out['load_kwh'] = power
    out['load_kw'] = power
    out['average_customer_kw'] = per_meter
    out['active_customers'] = count.astype('int64')
    out['no_customer_data_hour'] = (count == 0).astype('int8')
    return out[list(LEGACY_COLS)]


def _choose_continuous_overlap(wide: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Longest continuous all-three-category interval, as original cleaner.

    Do not invent values at gaps: exclude incomplete hours and disclose the count.
    """
    vals = wide[list(WIDE_NAMES.values())].to_numpy(dtype=float)
    valid = np.isfinite(vals).all(axis=1)
    ts = pd.to_datetime(wide['timestamp'])
    best_start, best_end = 0, 0
    start = None
    for pos in range(len(wide) + 1):
        ok = pos < len(wide) and valid[pos]
        contiguous = pos == 0 or (ts.iloc[pos] - ts.iloc[pos - 1] == pd.Timedelta(hours=1)) if pos < len(wide) else False
        if ok and (start is None or contiguous):
            if start is None:
                start = pos
        elif ok and not contiguous:
            if start is not None and pos - start > best_end - best_start:
                best_start, best_end = start, pos
            start = pos
        elif start is not None:
            if pos - start > best_end - best_start:
                best_start, best_end = start, pos
            start = None
    if best_end - best_start < 24:
        raise ValueError('No contiguous 24-hour interval with values for all three categories. Check cohort coverage.')
    # Keep the full valid interval, including any partial first day. The old
    # distributor's folder loader does the same, so folder and wide inputs agree.
    result = wide.iloc[best_start:best_end].copy()
    return result, len(wide) - len(result)


def export(source: Path, target: Path, wide_value: str = 'average') -> dict:
    if wide_value not in ('average', 'sum'):
        raise ValueError('--wide-value must be average or sum')
    source = source.resolve()
    target = target.resolve()
    if source == target:
        raise ValueError('Source and destination must differ to keep cohort originals unchanged')
    pieces = {name: _load_category(source / f'{name}.csv', name) for name in CATEGORIES}
    timestamps = pieces['residential']['timestamp']
    for name in CATEGORIES[1:]:
        if not pieces[name]['timestamp'].equals(timestamps):
            raise ValueError(f'Timestamp grids differ for {name}. Do not merge by row number.')

    # All validation is completed before creating files, so invalid sources
    # cannot leave an incomplete ready file behind.
    value_col = 'average_customer_kw' if wide_value == 'average' else 'load_kw'
    wide = pd.DataFrame({'timestamp': timestamps})
    for name in CATEGORIES:
        wide[WIDE_NAMES[name]] = pieces[name][value_col].to_numpy(dtype=float)
    ready, excluded = _choose_continuous_overlap(wide)
    if (ready[list(WIDE_NAMES.values())].to_numpy(dtype=float) < 0).any():
        raise ValueError('Negative demand values in distributor-ready output')
    target.mkdir(parents=True, exist_ok=True)
    for name in CATEGORIES:
        pieces[name].to_csv(target / f'{name}.csv', index=False, float_format='%.7f', date_format='%Y-%m-%d %H:%M:%S')
    wide.to_csv(target / 'goiener_three_profiles.csv', index=False, float_format='%.7f', date_format='%Y-%m-%d %H:%M:%S')
    ready.to_csv(target / 'goiener_distributor_ready.csv', index=False, float_format='%.7f', date_format='%Y-%m-%d %H:%M:%S')
    coverage = {}
    for name, df in pieces.items():
        count = df['active_customers'].to_numpy(dtype=int)
        coverage[name] = {
            'hours_with_no_active_customer': int((count == 0).sum()),
            'minimum_active_customers': int(count.min()),
            'maximum_active_customers': int(count.max()),
        }
    report = {
        'purpose': 'Compatibility export for original GoiEner Load Distributor',
        'source_fixed_cohort_folder': str(source),
        'original_cleaner_column_order': list(LEGACY_COLS),
        'wide_value_choice': wide_value,
        'source_hours': len(wide),
        'distributor_ready_hours': len(ready),
        'distributor_ready_start': str(ready.timestamp.iloc[0]),
        'distributor_ready_end': str(ready.timestamp.iloc[-1]),
        'excluded_from_ready_hours': excluded,
        'category_coverage': coverage,
        'notes': [
            'Values are copied from the fixed-ID cohort output, not recomputed from raw archives.',
            'The hourly numeric values of load_kwh and load_kw coincide for a one-hour measurement interval.',
            'Customer-hour interpolation occurred upstream; no additional interpolation was applied here.',
            'Choosing Average in the original distributor uses average_customer_kw from sector files.',
            'Choosing Sum in the original distributor uses load_kw from sector files.',
            'Directly opening goiener_distributor_ready.csv uses the wide_value_choice selected here.',
            'Incomplete category hours outside the longest continuous common interval are not filled silently.',
        ],
    }
    (target / 'quality_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (target / 'README_DISTRIBUTOR.txt').write_text(
        'ORIGINAL GOIENER LOAD DISTRIBUTOR COMPATIBILITY OUTPUT\n\n'
        'In the old distributor GUI, select THIS FOLDER as the cleaned profile source.\n'
        'Choose Average for typical per-customer patterns (recommended original setting).\n'
        'Choose Sum only to use total cohort customer consumption.\n'
        'You can also select goiener_distributor_ready.csv directly; it uses '+wide_value+'.\n'
        'Check quality_report.json for start/end dates and excluded hours.\n'
        'Original fixed-cohort outputs and large archives were not modified.\n',
        encoding='utf-8',
    )
    print('\nLegacy GoiEner cleaner format exported to:', target, flush=True)
    print(f'Common ready hours: {len(ready):,}, {ready.timestamp.iloc[0]} to {ready.timestamp.iloc[-1]}', flush=True)
    if excluded:
        print(f'WARNING: {excluded:,} source hours omitted from longest common continuous interval; review quality_report.json.', flush=True)
    print('Original Load Distributor: choose the exported FOLDER, then Average or Sum.', flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('cohort_output'))
    parser.add_argument('--out', type=Path, default=Path('cohort_output/Distributor_Compatible'))
    parser.add_argument('--wide-value', choices=('average', 'sum'), default='average')
    arguments = parser.parse_args()
    export(arguments.source, arguments.out, arguments.wide_value)
