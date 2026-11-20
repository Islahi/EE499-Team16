"""Verify saved metrics from the hourly exports. Run with Python, pandas and NumPy."""
from pathlib import Path
import numpy as np
import pandas as pd

root = Path(__file__).resolve().parent
metrics = pd.read_csv(root / "Tables" / "Configuration_metrics_and_ranks.csv")
clock = pd.date_range("2019-03-01", periods=8784, freq="h")
weights = {"mae": 5, "rmse": 5, "wape": 5, "mase": 2, "abs_bias": 4, "smape": 3}
for dataset, rows in metrics.groupby("dataset"):
    hourly = pd.read_csv(root / "Hourly_data" / (dataset + ".csv.gz"), index_col="timestamp", parse_dates=True)
    assert hourly.index.equals(clock), dataset
    actual = hourly["Actual"].to_numpy()
    for r in rows.itertuples():
        forecast = hourly[r.config].to_numpy()
        assert np.isfinite(forecast).all() and np.isfinite(actual).all()
        e = actual - forecast
        mae = np.mean(abs(e))
        den = abs(actual) + abs(forecast)
        values = [mae, np.sqrt(np.mean(e**2)), e.mean(), abs(e.mean()),
                  100*mae/np.mean(abs(actual)) if np.any(actual) else np.nan,
                  mae/r.weekly_scale if r.weekly_scale else np.nan,
                  200*np.divide(abs(e), den, out=np.zeros_like(e), where=den>0).mean()]
        assert np.allclose(values, [r.mae,r.rmse,r.bias,r.abs_bias,r.wape,r.mase,r.smape],equal_nan=True), (dataset,r.config)
    if rows.score.notna().all():
        ranks = {m:rows[m].map(lambda v:float(f"{v:.10g}")).rank() for m in weights}
        score = sum(weights[m]*ranks[m] for m in weights)/sum(weights.values())
        assert np.allclose(score,rows.score) and np.array_equal(score.rank(method="min"),rows["rank"])
print("All saved hourly series and eligible configuration scores agree.")
