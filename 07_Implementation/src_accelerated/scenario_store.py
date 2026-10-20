"""CSV/JSON storage for generated and selected uncertainty scenarios."""
import csv
import json
from pathlib import Path

import numpy as np

from .data_loader import ProfileData
from .uncertainty import Scenario, ScenarioSet


def _json_value(value):
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _write_scenarios(path, scenarios, active_name, reactive_name):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["scenario_id", "timestamp", "bus_id", "p_kw", "q_kvar"])
        for scenario in scenarios:
            profile = scenario.profiles
            active = getattr(profile, active_name)
            reactive = getattr(profile, reactive_name)
            for bus_id in sorted(active):
                for index, timestamp in enumerate(profile.timestamps):
                    writer.writerow([
                        scenario.scenario_id, timestamp.isoformat(), bus_id,
                        active[bus_id][index], reactive[bus_id][index],
                    ])


def _write_validation(path, metadata):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow([
            "kind", "bus_id", "selected_method", "fit_status",
            "model_rmse_kw", "model_mape_percent",
            "repeat_last_day_rmse_kw", "repeat_last_day_mape_percent", "warnings",
        ])
        validation = metadata.get("validation", {})
        models = metadata.get("models", {})
        for kind, by_bus in validation.items():
            for bus_id, values in by_bus.items():
                model = models.get(kind, {}).get(bus_id, models.get(kind, {}).get(str(bus_id), {}))
                arima = values.get("arima", {})
                naive = values.get("repeat_last_day", {})
                writer.writerow([
                    kind, bus_id, model.get("model", ""), model.get("fit_status", ""),
                    arima.get("rmse_kw"), arima.get("mape_percent"),
                    naive.get("rmse_kw"), naive.get("mape_percent"),
                    " | ".join(values.get("training_warnings", [])),
                ])


def _write_ranking(path, generated, selected):
    chosen = {item.scenario_id: item.metadata.get("selection_group", "selected")
              for item in selected.scenarios}
    scores = selected.metadata.get("stress_scores", {})
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["scenario_id", "stress_score", "selection_group", "selected"])
        for scenario in generated.scenarios:
            writer.writerow([
                scenario.scenario_id, scores.get(scenario.scenario_id, ""),
                chosen.get(scenario.scenario_id, ""), scenario.scenario_id in chosen,
            ])


def save_scenario_package(generated, selected, output_path, package_context=None):
    generated.validate()
    selected.validate()
    output = Path(output_path)
    if output.exists():
        raise FileExistsError(f"Scenario folder already exists: {output}")
    output.mkdir(parents=True)
    _write_scenarios(output / "load_scenarios.csv", generated.scenarios,
                     "load_p_kw", "load_q_kvar")
    _write_scenarios(output / "pv_scenarios.csv", generated.scenarios,
                     "pv_p_kw", "pv_q_kvar")
    _write_validation(output / "validation.csv", generated.metadata)
    _write_ranking(output / "scenario_ranking.csv", generated, selected)
    manifest = {
        "format_version": 1,
        "generated_count": len(generated.scenarios),
        "selected_count": len(selected.scenarios),
        "selected_ids": [item.scenario_id for item in selected.scenarios],
        "generation": _json_value(generated.metadata),
        "selection": _json_value(selected.metadata),
        "context": _json_value(package_context or {}),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output


def _read_selected(path, selected_ids):
    data = {scenario_id: {} for scenario_id in selected_ids}
    with Path(path).open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = {"scenario_id", "timestamp", "bus_id", "p_kw", "q_kvar"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"Scenario CSV requires {', '.join(sorted(required))}")
        for row in reader:
            scenario_id = row["scenario_id"]
            if scenario_id not in data:
                continue
            bus_id = int(row["bus_id"])
            values = data[scenario_id].setdefault(bus_id, {"timestamps": [], "p": [], "q": []})
            values["timestamps"].append(row["timestamp"])
            values["p"].append(float(row["p_kw"]))
            values["q"].append(float(row["q_kvar"]))
    return data


def load_scenario_package(path):
    folder = Path(path)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    selected_ids = list(manifest.get("selected_ids", []))
    if not selected_ids:
        raise ValueError("Scenario manifest has no selected scenario IDs")
    load = _read_selected(folder / "load_scenarios.csv", selected_ids)
    pv = _read_selected(folder / "pv_scenarios.csv", selected_ids)
    scenarios = []
    selection = manifest.get("selection", {})
    scores = selection.get("stress_scores", {})
    ranking = {}
    ranking_path = folder / "scenario_ranking.csv"
    if ranking_path.exists():
        with ranking_path.open("r", newline="", encoding="utf-8-sig") as stream:
            ranking = {row["scenario_id"]: row for row in csv.DictReader(stream)}
    for scenario_id in selected_ids:
        if not load[scenario_id] or not pv[scenario_id]:
            raise ValueError(f"Saved scenario {scenario_id} is incomplete")
        first = next(iter(load[scenario_id].values()))
        timestamps = first["timestamps"]
        load_rows = [["timestamp", "bus_id", "p_kw", "q_kvar"]]
        pv_rows = [["timestamp", "bus_id", "p_kw", "q_kvar"]]
        for destination, source in ((load_rows, load[scenario_id]), (pv_rows, pv[scenario_id])):
            for bus_id in sorted(source):
                values = source[bus_id]
                if values["timestamps"] != timestamps:
                    raise ValueError(f"Saved scenario {scenario_id} has inconsistent timestamps")
                destination.extend(zip(timestamps, [bus_id] * len(timestamps), values["p"], values["q"]))
        from io import StringIO
        load_stream, pv_stream = StringIO(), StringIO()
        csv.writer(load_stream, lineterminator="\n").writerows(load_rows)
        csv.writer(pv_stream, lineterminator="\n").writerows(pv_rows)
        load_stream.seek(0)
        pv_stream.seek(0)
        profile = ProfileData(load_stream, pv_stream)
        row = ranking.get(scenario_id, {})
        scenarios.append(Scenario(scenario_id, profile, metadata={
            "selection_group": row.get("selection_group", "selected"),
            "stress_score": float(row.get("stress_score") or scores.get(scenario_id, 0.0)),
        }))
    result = ScenarioSet(scenarios, selection)
    result.validate()
    return result, manifest
