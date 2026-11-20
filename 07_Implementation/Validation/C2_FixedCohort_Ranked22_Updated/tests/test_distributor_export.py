"""Synthetic compatibility regression test: python tests/test_distributor_export.py"""
from pathlib import Path
import sys
import tempfile
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from importlib import import_module
exp = import_module('02_export_legacy_cleaner_format')


def test():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        src, out = root / 'cohort_output', root / 'cohort_output' / 'Distributor_Compatible'
        src.mkdir()
        t = pd.date_range('2017-06-01', periods=100, freq='h')
        for cat, scale in [('residential', 1.), ('commercial', 2.), ('manufacturing', 3.)]:
            active = np.full(100, 5)
            per_customer = np.full(100, scale)
            if cat == 'commercial':
                active[10:15] = 0
                per_customer[10:15] = np.nan
            pd.DataFrame({'timestamp': t, 'load_kw': 5*per_customer,
                          'average_customer_kw': per_customer,
                          'active_customers': active}).to_csv(src / f'{cat}.csv', index=False)
        report = exp.export(src, out)
        assert report['distributor_ready_hours'] == 85
        assert report['excluded_from_ready_hours'] == 15
        for cat in exp.CATEGORIES:
            df = pd.read_csv(out / f'{cat}.csv')
            assert list(df.columns) == list(exp.LEGACY_COLS)
            assert df.shape[0] == 100
            assert np.allclose(df.load_kwh, df.load_kw, equal_nan=True)
        w = pd.read_csv(out / 'goiener_distributor_ready.csv')
        assert len(w) == 85
        assert list(w.columns) == ['timestamp', *exp.WIDE_NAMES.values()]
        assert w.iloc[0].timestamp == '2017-06-01 15:00:00'
        assert np.isfinite(w.iloc[:, 1:].to_numpy()).all()
        # Optional old-engine test if original distributor is unpacked next to package
        print('PASS: original six-column headers, all-sector wide ready file, gap handling, report')


if __name__ == '__main__':
    test()
