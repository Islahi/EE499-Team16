"""CSV/JSON storage for generated and selected uncertainty scenarios."""
import csv
import json
from io import StringIO
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


def _scenario_filename(scenario_id, number):
    return f"S{number:03d}_{str(scenario_id).replace(' ', '_')}.csv"


def _write_scenario(path, scenario):
    profile = scenario.profiles
    bus_ids = sorted(set(profile.load_p_kw) | set(profile.pv_p_kw))
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["scenario_id", "timestamp", "bus_id", "load_p_kw", "load_q_kvar", "pv_p_kw", "pv_q_kvar"])
        for bus_id in bus_ids:
            for index, timestamp in enumerate(profile.timestamps):
                writer.writerow([scenario.scenario_id, timestamp.isoformat(), bus_id,
                                 profile.load_p_kw.get(bus_id, np.zeros(len(profile.timestamps)))[index],
                                 profile.load_q_kvar.get(bus_id, np.zeros(len(profile.timestamps)))[index],
                                 profile.pv_p_kw.get(bus_id, np.zeros(len(profile.timestamps)))[index],
                                 profile.pv_q_kvar.get(bus_id, np.zeros(len(profile.timestamps)))[index]])


def _write_validation(path, metadata):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["kind", "bus_id", "selected_method", "fit_status", "model_rmse_kw", "model_mape_percent", "repeat_last_day_rmse_kw", "repeat_last_day_mape_percent", "warnings"])
        for kind, by_bus in metadata.get("validation", {}).items():
            for bus_id, values in by_bus.items():
                model = metadata.get("models", {}).get(kind, {}).get(bus_id, metadata.get("models", {}).get(kind, {}).get(str(bus_id), {}))
                writer.writerow([kind, bus_id, model.get("model", ""), model.get("fit_status", ""), values.get("arima", {}).get("rmse_kw"), values.get("arima", {}).get("mape_percent"), values.get("repeat_last_day", {}).get("rmse_kw"), values.get("repeat_last_day", {}).get("mape_percent"), " | ".join(values.get("training_warnings", []))])


def _write_ranking(path, generated, selected):
    chosen = {item.scenario_id: item.metadata.get("selection_group", "selected") for item in selected.scenarios}
    scores = selected.metadata.get("stress_scores", {})
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["scenario_id", "stress_score", "selection_group", "selected"])
        for scenario in generated.scenarios:
            writer.writerow([scenario.scenario_id, scores.get(scenario.scenario_id, ""), chosen.get(scenario.scenario_id, ""), scenario.scenario_id in chosen])


def save_scenario_package(generated, selected, output_path, package_context=None):
    """Save every generated scenario as a separate inspectable CSV."""
    generated.validate()
    selected.validate()
    output = Path(output_path)
    if output.exists():
        raise FileExistsError(f"Scenario folder already exists: {output}")
    scenario_folder = output / "all_scenarios"
    scenario_folder.mkdir(parents=True)
    files = {}
    for number, scenario in enumerate(generated.scenarios, start=1):
        relative = Path("all_scenarios") / _scenario_filename(scenario.scenario_id, number)
        _write_scenario(output / relative, scenario)
        files[scenario.scenario_id] = str(relative)
    _write_validation(output / "validation.csv", generated.metadata)
    _write_ranking(output / "scenario_ranking.csv", generated, selected)
    manifest = {"format_version": 2, "generated_count": len(generated.scenarios),
                "selected_count": len(selected.scenarios),
                "selected_ids": [item.scenario_id for item in selected.scenarios],
                "scenario_files": files, "generation": _json_value(generated.metadata),
                "selection": _json_value(selected.metadata), "context": _json_value(package_context or {})}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output


def _read_single_scenario(path, expected_id):
    with Path(path).open("r", newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    required = {"scenario_id", "timestamp", "bus_id", "load_p_kw", "load_q_kvar", "pv_p_kw", "pv_q_kvar"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"Scenario file {Path(path).name} is incomplete")
    if any(row["scenario_id"] != expected_id for row in rows):
        raise ValueError(f"Scenario file {Path(path).name} has a mismatched scenario ID")
    load_rows = [["timestamp", "bus_id", "p_kw", "q_kvar"]]
    pv_rows = [["timestamp", "bus_id", "p_kw", "q_kvar"]]
    for row in rows:
        load_rows.append([row["timestamp"], row["bus_id"], row["load_p_kw"], row["load_q_kvar"]])
        pv_rows.append([row["timestamp"], row["bus_id"], row["pv_p_kw"], row["pv_q_kvar"]])
    load_stream, pv_stream = StringIO(), StringIO()
    csv.writer(load_stream, lineterminator="\n").writerows(load_rows)
    csv.writer(pv_stream, lineterminator="\n").writerows(pv_rows)
    load_stream.seek(0)
    pv_stream.seek(0)
    return ProfileData(load_stream, pv_stream)


def load_scenario_package(path):
    folder = Path(path)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if int(manifest.get("format_version", 1)) < 2:
        raise ValueError("Legacy scenario package: generate a new set to use separate scenario CSV files.")
    selected_ids = list(manifest.get("selected_ids", []))
    files = manifest.get("scenario_files", {})
    if not selected_ids:
        raise ValueError("Scenario manifest has no selected scenario IDs")
    ranking_path = folder / "scenario_ranking.csv"
    ranking = {}
    if ranking_path.exists():
        with ranking_path.open("r", newline="", encoding="utf-8-sig") as stream:
            ranking = {row["scenario_id"]: row for row in csv.DictReader(stream)}
    scenarios = []
    for scenario_id in selected_ids:
        relative = files.get(scenario_id)
        if not relative:
            raise ValueError(f"Scenario manifest has no file for {scenario_id}")
        row = ranking.get(scenario_id, {})
        scenarios.append(Scenario(scenario_id, _read_single_scenario(folder / relative, scenario_id), metadata={"selection_group": row.get("selection_group", "selected"), "stress_score": float(row.get("stress_score") or 0.0)}))
    result = ScenarioSet(scenarios, manifest.get("selection", {}))
    result.validate()
    return result, manifest
