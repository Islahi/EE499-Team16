#!/usr/bin/env python3
"""C2 comparison: per-bus forecasts vs category-aggregate forecasts redistributed to buses.

Inputs are explicit CSV exports; no forecasting models are fitted or test targets leaked.
This evaluates two PREGENERATED one-origin 2021 forecasts on identical 15-bus targets.
Run: python testbench.py --actual actual_load.csv --mapping bus_categories.csv
       --bus-forecasts bus_forecasts.csv --category-forecasts category_forecasts.csv
       --output comparison_results --allocation hour_of_week

Requires: pandas, numpy, matplotlib.
"""
from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path
import re
import json
import sys

import numpy as np
import pandas as pd

TEST_START = pd.Timestamp("2021-01-01 00:00:00")
TEST_END_EXCL = pd.Timestamp("2022-01-01 00:00:00")
TEST_INDEX = pd.date_range(TEST_START, TEST_END_EXCL - pd.Timedelta(hours=1), freq="h")
EPS = 1e-12


def bus_id(value):
    s = str(value).strip()
    s = re.sub(r"^bus[\s_-]*", "", s, flags=re.I)
    try:
        return str(int(float(s)))
    except (ValueError, TypeError):
        return s


def category(value):
    s = str(value).strip().lower()
    aliases = {"industrial": "manufacturing", "industry": "manufacturing",
               "resident": "residential", "commerce": "commercial"}
    return aliases.get(s, s)


def csv_table(path, columns):
    df = pd.read_csv(path)
    missing = set(columns) - set(df.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}. Found {list(df.columns)}")
    if "timestamp" in columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="raise")
        if df["timestamp"].dt.tz is not None:
            raise ValueError(f"{path}: timezone-aware timestamps; normalize timezones explicitly")
        if df["timestamp"].isna().any():
            raise ValueError(f"{path}: invalid timestamps")
    if "bus_id" in columns:
        df["bus_id"] = df["bus_id"].map(bus_id)
    if "category" in columns:
        df["category"] = df["category"].map(category)
    value_cols = [x for x in ("p_kw", "forecast_kw") if x in columns]
    for col in value_cols:
        df[col] = pd.to_numeric(df[col], errors="raise")
        if not np.isfinite(df[col].to_numpy(dtype=float)).all():
            raise ValueError(f"{path}: {col} contains non-finite values")
    return df


def matrix(df, identifier, value):
    if df.duplicated(["timestamp", identifier]).any():
        example = df[df.duplicated(["timestamp", identifier], keep=False)].head(2)
        raise ValueError(f"duplicate timestamp/{identifier} rows: {example.to_dict('records')}")
    return df.pivot(index="timestamp", columns=identifier, values=value).sort_index()


def require_annual(wide, columns, name):
    expected = set(columns)
    missing = expected - set(wide.columns)
    if missing:
        raise ValueError(f"{name}: missing series {sorted(missing)}")
    out = wide.reindex(index=TEST_INDEX, columns=sorted(columns))
    if out.isna().any().any():
        examples = out.stack(dropna=False).loc[lambda x: x.isna()].index[:5].tolist()
        raise ValueError(f"{name}: missing 2021 predictions/observations: {examples}")
    unexpected = wide.index[(wide.index >= TEST_START) & (wide.index < TEST_END_EXCL)]
    if len(unexpected.unique()) != 8760:
        raise ValueError(f"{name}: expected 8760 distinct 2021 hours; saw {len(unexpected.unique())}")
    return out.astype(float)


def trained_shares(history, mapping, alloc):
    """Weights inferred ONLY from observations before 2021; sum=1 within each category."""
    result = {}
    for cat in sorted(set(mapping.values())):
        buses = sorted(b for b, value in mapping.items() if value == cat)
        block = history.loc[:, buses]
        mean = block.mean(axis=0).clip(lower=0)
        if mean.sum() <= EPS:
            raise ValueError(f"category {cat}: no positive historic load; cannot allocate")
        fallback = (mean / mean.sum()).to_numpy(dtype=float)
        if alloc == "constant":
            result[cat] = np.broadcast_to(fallback, (168, len(buses))).copy()
        else:
            how = history.index.dayofweek.to_numpy() * 24 + history.index.hour.to_numpy()
            means = block.groupby(how).mean().reindex(range(168))
            shares = []
            for _, row in means.iterrows():
                vals = row.to_numpy(dtype=float)
                if not np.isfinite(vals).all() or vals.sum() <= EPS:
                    shares.append(fallback)
                else:
                    shares.append(np.maximum(vals, 0.0) / np.maximum(vals, 0.0).sum())
            result[cat] = np.asarray(shares)
        assert np.allclose(result[cat].sum(axis=1), 1, atol=1e-10)
    return result


def redistribute(category_predictions, mapping, shares):
    """Category forecasts are ex-ante predictions, never actual 2021 category totals."""
    output = pd.DataFrame(0., index=TEST_INDEX, columns=sorted(mapping))
    how = TEST_INDEX.dayofweek.to_numpy() * 24 + TEST_INDEX.hour.to_numpy()
    for cat in sorted(set(mapping.values())):
        buses = sorted(b for b in mapping if mapping[b] == cat)
        weights = shares[cat][how]
        forecast = category_predictions[cat].to_numpy(dtype=float)
        output.loc[:, buses] = weights * forecast[:, None]
        if not np.allclose(output.loc[:, buses].sum(axis=1).to_numpy(), forecast,
                           rtol=1e-9, atol=1e-7):
            raise AssertionError(f"allocation does not preserve {cat} aggregate")
    return output


def metrics(actual, forecast, historical):
    a = np.asarray(actual, float)
    f = np.asarray(forecast, float)
    train = np.asarray(historical, float)
    err = f - a
    scale = np.mean(np.abs(train[168:] - train[:-168])) if len(train) > 168 else np.nan
    return {
        "MAE_kW": float(np.mean(np.abs(err))),
        "RMSE_kW": float(np.sqrt(np.mean(err ** 2))),
        "WAPE_pct": float(100 * np.sum(np.abs(err)) / np.sum(np.abs(a)))
                    if np.sum(np.abs(a)) > EPS else np.nan,
        "MASE_168": float(np.mean(np.abs(err)) / scale) if scale > EPS else np.nan,
        "Bias_pred_minus_actual_kW": float(np.mean(err)),
        "sMAPE_pct": float(np.mean(
            np.divide(200 * np.abs(err), np.abs(a) + np.abs(f),
                      out=np.zeros_like(err), where=(np.abs(a) + np.abs(f)) > EPS))),
        "actual_2021_kWh": float(a.sum()),
        "predicted_2021_kWh": float(f.sum()),
        "yearly_energy_error_pct": float(100 * (f.sum() - a.sum()) / a.sum())
                                   if abs(a.sum()) > EPS else np.nan,
    }


def similarity(wide, mapping, period):
    rows = []
    for cat in sorted(set(mapping.values())):
        buses = sorted(b for b in mapping if mapping[b] == cat)
        for a, b in combinations(buses, 2):
            x = wide[a].to_numpy(dtype=float)
            y = wide[b].to_numpy(dtype=float)
            alpha = float(np.dot(x, y) / np.dot(x, x)) if np.dot(x, x) > EPS else np.nan
            diff = y - alpha * x
            rel_rmse = float(np.linalg.norm(diff) / max(np.linalg.norm(y), EPS))
            is_exact = rel_rmse <= 1e-9
            is_near = rel_rmse <= 1e-3
            sx, sy = float(x.std()), float(y.std())
            corr = float(np.corrcoef(x, y)[0, 1]) if sx > EPS and sy > EPS else np.nan
            rows.append({"period": period, "category": cat, "bus_a": a, "bus_b": b,
                         "correlation": corr, "scale_b_over_a": alpha,
                         "proportional_rel_RMSE": rel_rmse,
                         "verdict": "EXACT_PROPORTIONAL" if is_exact else
                         ("NEAR_PROPORTIONAL" if is_near else "DIFFERENT_SHAPES")})
    return rows


def plot_hourly(actual, bus_forecast, allocated, output, mapping):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.dates import DateFormatter
    out = output / "PNG"
    out.mkdir(parents=True, exist_ok=True)
    lo, hi = "2021-07-01", "2021-07-14 23:00"
    def plot_one(key, actual_s, ind_s, agg_s):
        fig, ax = plt.subplots(figsize=(12, 4.5), dpi=140)
        for label, vec in [("Actual", actual_s), ("Bus-by-bus", ind_s),
                           ("Category aggregate redistributed", agg_s)]:
            z = vec.loc[lo:hi]
            ax.plot(z.index, z.to_numpy(), label=label, linewidth=1.0)
        ax.set(title=f"{key}: hourly load forecast, 1–14 July 2021",
               ylabel="Active power (kW)", xlabel="Date")
        ax.legend(fontsize=8, loc="best")
        ax.grid(alpha=.2)
        ax.xaxis.set_major_formatter(DateFormatter("%d %b"))
        fig.tight_layout()
        fig.savefig(out / f"{key}_Hourly_14Days.png", bbox_inches="tight")
        plt.close(fig)
    for bus in actual.columns:
        plot_one(f"Bus_{bus}_{mapping[bus]}", actual[bus],
                 bus_forecast[bus], allocated[bus])
    for cat in sorted(set(mapping.values())):
        buses = [b for b in mapping if mapping[b] == cat]
        plot_one(f"Category_{cat}", actual[buses].sum(axis=1),
                 bus_forecast[buses].sum(axis=1), allocated[buses].sum(axis=1))
    plot_one("Feeder", actual.sum(axis=1), bus_forecast.sum(axis=1),
             allocated.sum(axis=1))


def report_verdict(pair_results):
    report = []
    df = pd.DataFrame(pair_results)
    if df.empty:
        return ["No within-category bus pairs were available for similarity testing."]
    test = df[df.period == "2021_test"]
    for cat, part in test.groupby("category"):
        total = len(part)
        exact = int((part.verdict == "EXACT_PROPORTIONAL").sum())
        near = int((part.verdict == "NEAR_PROPORTIONAL").sum())
        varying = total - exact - near
        if exact == total:
            verdict = "SAME normalized time profile; only magnitude differs"
        elif exact + near == total:
            verdict = "NEAR-identical normalized time profiles"
        else:
            verdict = "At least some bus pairs have different temporal shapes"
        report.append(f"{cat}: {exact}/{total} exactly proportional, "
                      f"{near}/{total} nearly proportional, {varying}/{total} different. {verdict}.")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--actual", required=True, type=Path)
    p.add_argument("--mapping", required=True, type=Path)
    p.add_argument("--bus-forecasts", required=True, type=Path)
    p.add_argument("--category-forecasts", required=True, type=Path)
    p.add_argument("--output", type=Path, default=Path("C2_15bus_test_results"))
    p.add_argument("--allocation", choices=["constant", "hour_of_week"], default="hour_of_week")
    p.add_argument("--slack-bus", default="1")
    p.add_argument("--skip-plots", action="store_true")
    args = p.parse_args()

    mapping_df = csv_table(args.mapping, ["bus_id", "category"])
    if mapping_df.bus_id.duplicated().any():
        raise ValueError("bus_categories.csv contains duplicate bus IDs")
    mapping = dict(zip(mapping_df.bus_id, mapping_df.category))
    slack = bus_id(args.slack_bus)
    mapping.pop(slack, None)
    if len(mapping) != 14:
        raise ValueError(f"Expected 14 non-slack buses from a 15-bus network; got {len(mapping)}")
    mapping = dict(sorted(mapping.items()))
    categories = sorted(set(mapping.values()))
    if not categories:
        raise ValueError("Empty category mapping")

    a_raw = csv_table(args.actual, ["timestamp", "bus_id", "p_kw"])
    a_raw = a_raw[a_raw.bus_id.isin(mapping)]
    actual_wide = matrix(a_raw, "bus_id", "p_kw")
    if not set(mapping).issubset(actual_wide.columns):
        raise ValueError("Missing required buses in actual_load.csv")
    train = actual_wide.loc[actual_wide.index < TEST_START, sorted(mapping)]
    if len(train) < 672:
        raise ValueError("Need at least 672 hours of pre-2021 observations to calculate historical shares")
    if train.isna().any().any():
        raise ValueError("Missing historical load values; repair and document them before comparison")
    if train.index.max() >= TEST_START:
        raise AssertionError("Training history includes 2021")
    actual = require_annual(actual_wide, mapping, "Actual load")

    bus_raw = csv_table(args.bus_forecasts, ["timestamp", "bus_id", "forecast_kw"])
    bus_pred = require_annual(matrix(bus_raw, "bus_id", "forecast_kw"),
                              mapping, "Bus-by-bus forecasts")
    cat_raw = csv_table(args.category_forecasts, ["timestamp", "category", "forecast_kw"])
    category_pred = require_annual(matrix(cat_raw, "category", "forecast_kw"),
                                   categories, "Category-aggregate forecasts")
    shares = trained_shares(train, mapping, args.allocation)
    allocated = redistribute(category_pred, mapping, shares)

    args.output.mkdir(parents=True, exist_ok=True)
    bus_rows = []
    for b, cat in mapping.items():
        for approach, forecast in [("bus_by_bus", bus_pred), ("category_aggregate", allocated)]:
            bus_rows.append({"bus_id": b, "category": cat, "approach": approach,
                             **metrics(actual[b], forecast[b], train[b])})
    pd.DataFrame(bus_rows).to_csv(args.output / "bus_metrics.csv", index=False)

    cat_rows = []
    for cat in categories:
        buses = [b for b in mapping if mapping[b] == cat]
        for approach, forecast in [("bus_by_bus", bus_pred), ("category_aggregate", allocated)]:
            cat_rows.append({"category": cat, "approach": approach,
                             **metrics(actual[buses].sum(axis=1), forecast[buses].sum(axis=1),
                                       train[buses].sum(axis=1))})
    pd.DataFrame(cat_rows).to_csv(args.output / "category_metrics.csv", index=False)

    feeder_rows = []
    for approach, forecast in [("bus_by_bus", bus_pred), ("category_aggregate", allocated)]:
        feeder_rows.append({"approach": approach, **metrics(
            actual.sum(axis=1), forecast.sum(axis=1), train.sum(axis=1))})
    pd.DataFrame(feeder_rows).to_csv(args.output / "feeder_metrics.csv", index=False)

    pair_results = similarity(train, mapping, "historical_training")
    pair_results += similarity(actual, mapping, "2021_test")
    pd.DataFrame(pair_results).to_csv(args.output / "profile_similarity.csv", index=False)

    # Produce aligned outputs for power-flow integration, without overwriting existing files.
    result = actual.stack().rename("actual_kw").to_frame()
    result["bus_by_bus_kw"] = bus_pred.stack()
    result["category_aggregate_kw"] = allocated.stack()
    result = result.reset_index().rename(columns={"level_0": "timestamp", "level_1": "bus_id"})
    result["category"] = result["bus_id"].map(mapping)
    result.to_csv(args.output / "aligned_2021_bus_forecasts.csv", index=False)

    if not args.skip_plots:
        plot_hourly(actual, bus_pred, allocated, args.output, mapping)

    verdicts = report_verdict(pair_results)
    feeder_scores = pd.DataFrame(feeder_rows).set_index("approach")
    summary = {"train_first": str(train.index.min()), "train_last": str(train.index.max()),
               "test_first": str(TEST_INDEX[0]), "test_last": str(TEST_INDEX[-1]),
               "test_hours": 8760, "bus_count": len(mapping), "categories": categories,
               "allocation": args.allocation,
               "feeder_WAPE_pct": {k: float(v) for k, v in feeder_scores["WAPE_pct"].items()},
               "verdicts": verdicts,
               "note": "Forecasts supplied by user; this bench does not train models or inspect C2 archives."}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = ["# C2 15-bus forecast comparison",
             "", "Both approaches evaluated on identical actual 2021 bus loads.",
             "Training-derived redistribution weights only; no 2021 leakage.",
             "", "## Load-profile verdicts", *["- " + x for x in verdicts],
             "", "## Feeder accuracy", pd.DataFrame(feeder_rows).to_markdown(index=False),
             "", "Bus-specific and category metrics are in CSV files.",
             "The model configurations used must be documented by the forecast producers."]
    try:
        (args.output / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    except ImportError:
        (args.output / "SUMMARY.md").write_text(
            "\n".join(lines[:7]) + "\nSee feeder_metrics.csv.\n", encoding="utf-8")
    print("\n".join(verdicts))
    print("\nFeeder accuracy:\n", pd.DataFrame(feeder_rows).to_string(index=False))
    print(f"\nSaved outputs: {args.output.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, AssertionError, FileNotFoundError) as error:
        sys.exit(f"TEST BENCH INPUT/VALIDATION ERROR: {error}")
