from pathlib import Path
import json
import numpy as np
import pandas as pd

cache = Path("cache")
cache.mkdir(exist_ok=True)
for path in Path("C2_Analysis").rglob("hourly_forecasts.csv"):
    data = pd.read_csv(path, float_precision="round_trip")
    dataset = data["dataset"].iloc[0]
    values = data.drop(columns=["timestamp", "dataset"])
    assert values.columns[0] == "actual" and len(values) == 8760
    np.save(cache / (dataset + ".npy"), values.to_numpy().T)
    (cache / (dataset + ".json")).write_text(json.dumps(["Actual", *values.columns[1:]]))
