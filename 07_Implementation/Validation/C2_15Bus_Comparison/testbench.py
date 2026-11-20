#!/usr/bin/env python3
"""C2: independent bus forecasts vs category-aggregate forecast allocation.

No forecasting models are trained here. This program compares EXISTING unseen-2021
forecasts. All category allocation shares are estimated from pre-2021 history.
See README.md for CSV contracts and leakage protections.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd

START = pd.Timestamp("2021-01-01 00:00:00")
END = pd.Timestamp("2021-12-31 23:00:00")
HOURS = pd.date_range(START, END, freq="h")
EPS = 1e-12


def read_csv(path, cols):
    f = pd.read_csv(path)
    missing = set(cols) - set(f.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    f["timestamp"] = pd.to_datetime(f["timestamp"], errors="raise")
    if f["timestamp"].dt.tz is not None:
        raise ValueError(f"{path}: convert all timestamps to the same naive local timezone first")
    return f


def series_complete(frame, keys, description):
    if frame.duplicated(keys + ["timestamp"]).any():
        raise ValueError(f"{description}: duplicate keys/timestamps")
    periods = frame.groupby(keys, dropna=False)
    for key, group in periods:
        dates = pd.DatetimeIndex(group["timestamp"])
        if len(dates) != 8760 or not dates.sort_values().equals(HOURS):
            raise ValueError(f"{description}: {key} does not have precisely the 8760 hours of 2021")
        if not np.isfinite(group["kw"].to_numpy(dtype=float)).all():
            raise ValueError(f"{description}: {key} contains nonfinite kW values")


def metrics(actual, forecast, mase_denominator):
    a = np.asarray(actual, dtype=float)
    f = np.asarray(forecast, dtype=float)
    e = a - f  # signed bias: positive means UNDERprediction
    den = float(np.sum(np.abs(a)))
    smden = np.abs(a) + np.abs(f)
    return {
        "MAE_kW": float(np.mean(np.abs(e))),
        "RMSE_kW": float(np.sqrt(np.mean(e**2))),
        "WAPE_pct": float(100 * np.sum(np.abs(e)) / den) if den > EPS else np.nan,
        "MASE_24": float(np.mean(np.abs(e)) / mase_denominator) if mase_denominator > EPS else np.nan,
        "Bias_actual_minus_forecast_kW": float(np.mean(e)),
        "sMAPE_pct": float(np.mean(np.divide(
            200 * np.abs(e), smden, out=np.zeros_like(smden), where=smden > EPS
        ))),
    }


def audit_profiles(history, out_dir):
    records = []
    profiles = history.pivot(index="timestamp", columns="bus", values="kw")
    cats = history[["bus", "category"]].drop_duplicates()
    for category, chunk in cats.groupby("category"):
        buses = sorted(chunk["bus"].astype(str).tolist())
        for i, b1 in enumerate(buses):
            for b2 in buses[i + 1:]:
                x = profiles[b1].to_numpy(dtype=float)
                y = profiles[b2].to_numpy(dtype=float)
                valid = np.isfinite(x) & np.isfinite(y)
                x, y = x[valid], y[valid]
                if len(x) < 100:
                    raise ValueError("Insufficient aligned training-history samples")
                scale = float(x @ y / (x @ x)) if x @ x > EPS else np.nan
                relative_rmse = float(np.sqrt(np.mean((y - scale * x)**2)) /
                                      max(np.sqrt(np.mean(y*y)), EPS)) if np.isfinite(scale) else np.nan
                corr = float(np.corrcoef(x, y)[0, 1]) if np.std(x) > EPS and np.std(y) > EPS else np.nan
                # Normalize each time series by its own mean to compare SHAPE, not size.
                xnorm = x / np.mean(x) if abs(np.mean(x)) > EPS else np.full_like(x, np.nan)
                ynorm = y / np.mean(y) if abs(np.mean(y)) > EPS else np.full_like(y, np.nan)
                nrmse = float(np.sqrt(np.nanmean((xnorm - ynorm)**2))) if np.isfinite(xnorm).all() and np.isfinite(ynorm).all() else np.nan
                records.append({
                    "category": category, "bus_1": b1, "bus_2": b2,
                    "correlation": corr, "best_scale_y_over_x": scale,
                    "relative_proportional_RMSE": relative_rmse,
                    "normalized_profile_RMSE": nrmse,
                    "effectively_scaled_same_shape": bool(np.isfinite(relative_rmse) and relative_rmse < 1e-8)
                })
    audit = pd.DataFrame(records)
    audit.to_csv(out_dir / "same_category_profile_audit.csv", index=False)
    return audit


def make_plot(ts, actual, independent, distributed, out, label):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    mask = (ts >= pd.Timestamp("2021-07-01")) & (ts < pd.Timestamp("2021-07-15"))
    fig, ax = plt.subplots(figsize=(15, 5))
    ax.plot(ts[mask], actual[mask], label="Actual", lw=1.1)
    ax.plot(ts[mask], independent[mask], label="Bus-by-bus", lw=1)
    ax.plot(ts[mask], distributed[mask], label="Category aggregate then distribute", lw=1)
    ax.set(title=label + " — July 1–14, 2021", xlabel="Time", ylabel="Power (kW)")
    ax.legend(loc="best")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out, dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, required=True, help="timestamp,bus,category,kw; strictly pre-2021")
    parser.add_argument("--actual", type=Path, required=True, help="timestamp,bus,category,kw; actual 2021")
    parser.add_argument("--bus-forecast", type=Path, required=True, help="timestamp,bus,kw; independent 2021")
    parser.add_argument("--category-forecast", type=Path, required=True, help="timestamp,category,kw; aggregate 2021")
    parser.add_argument("--pv-forecast", type=Path, help="optional: timestamp,actual_kw,predicted_kw,arima_kw")
    parser.add_argument("--out", type=Path, default=Path("results"))
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    history = read_csv(args.history, ["timestamp", "bus", "category", "kw"])
    actual = read_csv(args.actual, ["timestamp", "bus", "category", "kw"])
    bf = read_csv(args.bus_forecast, ["timestamp", "bus", "kw"])
    cf = read_csv(args.category_forecast, ["timestamp", "category", "kw"])
    for f in (history, actual, bf):
        if "bus" in f:
            f["bus"] = f["bus"].astype(str)
    for f in (history, actual, cf):
        if "category" in f:
            f["category"] = f["category"].astype(str)

    if history["timestamp"].max() >= START:
        raise ValueError("Training-history data must end strictly before 2021-01-01")
    if history.duplicated(["bus", "timestamp"]).any():
        raise ValueError("Training-history bus/timestamp duplicates")
    for desc, f in (("history", history), ("actual", actual), ("bus forecast", bf), ("category forecast", cf)):
        if not np.isfinite(f["kw"].to_numpy(dtype=float)).all():
            raise ValueError(f"{desc} contains nonfinite numbers")
    if (history["kw"] < 0).any():
        raise ValueError("History contains negative demand")
    catmap = history[["bus", "category"]].drop_duplicates()
    if catmap["bus"].duplicated().any():
        raise ValueError("A bus has multiple load categories in training history")
    if actual[["bus", "category"]].drop_duplicates().sort_values(["bus","category"]).reset_index(drop=True).equals(
        catmap.sort_values(["bus","category"]).reset_index(drop=True)
    ) is False:
        raise ValueError("Actual bus/category mapping differs from history; omit slack/zero buses consistently")

    actual = actual.sort_values(["bus", "timestamp"])
    bf = bf.sort_values(["bus", "timestamp"])
    cf = cf.sort_values(["category", "timestamp"])
    series_complete(actual, ["bus"], "actual")
    series_complete(bf, ["bus"], "bus forecast")
    series_complete(cf, ["category"], "category forecast")
    if set(actual.bus) != set(bf.bus):
        raise ValueError("Forecast and actual bus identifiers differ")
    if set(actual.category) != set(cf.category):
        raise ValueError("Category forecasts must cover exactly the actual categories")

    # One allocation share per bus derived solely from available training history.
    # Mean power over time is proportional to training energy if timestamps align.
    # Missing history hours are forbidden to prevent biased allocation factors.
    history_counts = history.groupby("bus")["timestamp"].nunique()
    if history_counts.nunique() != 1:
        raise ValueError("Training-history buses have unequal hour counts; align history before calculating shares")
    history = history.merge(catmap, on="bus", suffixes=("", "_check"))
    bus_means = history.groupby(["category", "bus"], as_index=False)["kw"].mean()
    bus_means["category_total"] = bus_means.groupby("category")["kw"].transform("sum")
    if (bus_means["category_total"] <= EPS).any():
        raise ValueError("Zero category training demand: cannot allocate")
    bus_means["training_share"] = bus_means["kw"] / bus_means["category_total"]
    shares = bus_means[["category", "bus", "training_share"]]
    shares.to_csv(out / "training_only_bus_allocation_shares.csv", index=False)

    evaluation = actual.rename(columns={"kw": "actual_kw"})
    evaluation = evaluation.merge(bf.rename(columns={"kw": "independent_kw"}), on=["timestamp", "bus"], how="left", validate="one_to_one")
    evaluation = evaluation.merge(cf.rename(columns={"kw": "category_kw"}), on=["timestamp", "category"], how="left", validate="many_to_one")
    evaluation = evaluation.merge(shares, on=["bus", "category"], validate="many_to_one")
    if evaluation[["independent_kw", "category_kw", "training_share"]].isna().any().any():
        raise ValueError("Unmatched forecast timestamp, category, bus or share")
    evaluation["distributed_kw"] = evaluation["category_kw"] * evaluation["training_share"]
    evaluation = evaluation.sort_values(["bus", "timestamp"]).reset_index(drop=True)
    evaluation.to_csv(out / "aligned_bus_predictions_2021.csv", index=False)

    audit = audit_profiles(history.drop(columns=["category_check"]), out)
    denominators = {}
    for bus, h in history.groupby("bus"):
        h = h.sort_values("timestamp")
        # Seasonal-naive 24h denominator on training data only.
        denominators[bus] = float(np.mean(np.abs(h["kw"].to_numpy()[24:] - h["kw"].to_numpy()[:-24])))

    rows = []
    for bus, group in evaluation.groupby("bus"):
        group = group.sort_values("timestamp")
        for strategy, pred in (("bus_by_bus", "independent_kw"), ("aggregate_then_distribute", "distributed_kw")):
            rows.append({"bus": bus, "category": group.category.iloc[0], "strategy": strategy,
                         **metrics(group.actual_kw, group[pred], denominators[bus])})
        make_plot(group.timestamp.to_numpy(), group.actual_kw.to_numpy(),
                  group.independent_kw.to_numpy(), group.distributed_kw.to_numpy(),
                  out / ("bus_" + "".join(c if c.isalnum() else "_" for c in bus) + "_hourly_14days.png"),
                  f"Bus {bus} ({group.category.iloc[0]})")
    bus_scores = pd.DataFrame(rows)
    bus_scores.to_csv(out / "per_bus_strategy_metrics.csv", index=False)

    # Aggregate forecasts at category and network level, then evaluate their true totals.
    # Aggregation-before-metric is necessary: average of bus MAEs != aggregate MAE.
    for label, by in (("category", ["timestamp", "category"]), ("network", ["timestamp"])):
        agg = evaluation.groupby(by, as_index=False)[["actual_kw","independent_kw","distributed_kw"]].sum()
        agg.to_csv(out / (label + "_predictions_2021.csv"), index=False)
        score = []
        groupby = agg.groupby("category") if label == "category" else [("network", agg)]
        for group_name, g in groupby:
            # MASE for aggregated series uses 24-hour seasonal-naive baseline
            # from the sum of corresponding historical bus loads, not from test observations.
            h = (history[history.category == group_name] if label == "category" else history)
            ht = h.groupby("timestamp")["kw"].sum().sort_index().to_numpy()
            denom = float(np.mean(np.abs(ht[24:] - ht[:-24]))) if len(ht) > 24 else np.nan
            for strategy, field in (("bus_by_bus", "independent_kw"), ("aggregate_then_distribute", "distributed_kw")):
                score.append({"group": group_name, "strategy": strategy,
                              **metrics(g.actual_kw, g[field], denom)})
        pd.DataFrame(score).to_csv(out / (label + "_strategy_metrics.csv"), index=False)

    if args.pv_forecast:
        pv = read_csv(args.pv_forecast, ["timestamp", "actual_kw", "predicted_kw"])
        if pv.duplicated(["timestamp"]).any() or not pd.DatetimeIndex(pv.timestamp.sort_values()).equals(HOURS):
            raise ValueError("PV forecast must have 8760 unique hourly 2021 timestamps")
        pv_scores = [{"strategy": "selected_PV", **metrics(pv.actual_kw, pv.predicted_kw, np.nan)}]
        if "arima_kw" in pv:
            pv_scores.append({"strategy": "ARIMA_PV", **metrics(pv.actual_kw, pv.arima_kw, np.nan)})
        pd.DataFrame(pv_scores).to_csv(out / "pv_forecasting_metrics.csv", index=False)

    print("Completed: " + str(out.resolve()))
    print("Same-shape bus pairs (strict tolerance):", int(audit["effectively_scaled_same_shape"].sum()) if len(audit) else 0)
    print("See per_bus_strategy_metrics.csv, category_strategy_metrics.csv, network_strategy_metrics.csv")


if __name__ == "__main__":
    main()
