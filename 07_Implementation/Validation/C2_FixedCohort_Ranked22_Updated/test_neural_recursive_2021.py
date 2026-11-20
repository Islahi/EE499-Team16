"""Fast neural rollout safety tests; do not need torch/NeuralForecast installed."""
import unittest
import numpy as np
import pandas as pd
from neural_recursive_2021 import (
    HORIZON, FEATURES, _calendar_frame, _config,
    _training_frame, recursive_rollout,
)


class DummyNeuralForecast:
    def __init__(self):
        self.calls = 0
        self.seen_lasts = []

    def predict(self, df, futr_df):
        self.calls += 1
        assert set(FEATURES).issubset(df.columns)
        assert set(FEATURES).issubset(futr_df.columns)
        assert len(futr_df) == HORIZON
        self.seen_lasts.append(float(df.y.iloc[-1]))
        # Artificial model whose next prediction depends on its last input.
        # Shows that chained predictions really feed back into future calls.
        value = float(df.y.iloc[-1] + 1)
        return pd.DataFrame({
            'unique_id': 'C2', 'ds': futr_df.ds, 'AutoNHITS': value,
        })


class NeuralTests(unittest.TestCase):
    def setUp(self):
        self.train_time = pd.date_range('2018-11-01', periods=1700, freq='h')
        self.train = _training_frame(self.train_time, np.ones(len(self.train_time)))
        self.test = pd.date_range(self.train_time[-1] + pd.Timedelta(hours=1), periods=HORIZON * 2 + 24, freq='h')

    def test_recursive_forecast_is_full_and_causal(self):
        stub = DummyNeuralForecast()
        got = recursive_rollout(stub, self.train, self.test)
        self.assertEqual(len(got), len(self.test))
        self.assertEqual(stub.calls, 3)
        np.testing.assert_equal(stub.seen_lasts, [1.0, 2.0, 3.0])
        np.testing.assert_allclose(got[:HORIZON], 2)
        np.testing.assert_allclose(got[HORIZON:2 * HORIZON], 3)
        np.testing.assert_allclose(got[2 * HORIZON:], 4)

    def test_full_2021_horizon_has_53_blocks(self):
        # Use a short synthetic training history and verify all 8,760 output
        # timestamps are supplied by weekly predictions, not actuals.
        start = self.train_time[-1] + pd.Timedelta(hours=1)
        year = pd.date_range(start, periods=8760, freq='h')
        stub = DummyNeuralForecast()
        result = recursive_rollout(stub, self.train, year)
        self.assertEqual(len(result), 8760)
        self.assertEqual(stub.calls, 53)
        self.assertTrue(np.isfinite(result).all())

    def test_calendar_future_known_without_target(self):
        frame = _calendar_frame(self.test)
        self.assertEqual(len(frame), len(self.test))
        self.assertNotIn('y', frame)
        self.assertTrue(np.isfinite(frame[list(FEATURES)].to_numpy()).all())

    def test_discontinuous_test_fails(self):
        bad = self.test.delete(5)
        with self.assertRaisesRegex(ValueError, 'continuous'):
            recursive_rollout(DummyNeuralForecast(), self.train, bad)

    def test_neural_config_bounded(self):
        class Trial:
            def suggest_categorical(self, name, choices):
                return choices[0]
        cfg = _config(Trial())
        self.assertEqual(cfg['input_size'], 672)
        self.assertLessEqual(cfg['max_steps'], 200)
        self.assertEqual(cfg['futr_exog_list'], list(FEATURES))


if __name__ == '__main__':
    unittest.main()
