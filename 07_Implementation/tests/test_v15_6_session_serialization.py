"""Regress the V15.5 full-year run registration error (NumPy boolean)."""
import csv
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.study_session import StudySession, _json_value
from Tools.Recovery.RECOVER_ARCHIVED_RUN import recover


def test_nested_numpy_metadata_is_json_serializable():
    data = {"Placement stages": [{"full_year_candidates": [
        {"economic_acceptable": np.bool_(True), "network_feasible": np.bool_(False),
         "bus_id": np.int64(8), "annual_cost": np.float64(26_489_470.82),
         "features": np.array([1, 2, 3]),
         "missing_float": np.float64(float("nan")),
         "nested": {"some_bus": np.array([np.bool_(True), np.bool_(False)])}}
    ]}]}
    result = json.loads(json.dumps(_json_value(data), allow_nan=False))
    candidate = result["Placement stages"][0]["full_year_candidates"][0]
    assert candidate["economic_acceptable"] is True
    assert candidate["network_feasible"] is False
    assert candidate["features"] == [1, 2, 3]
    assert candidate["missing_float"] is None
    assert candidate["nested"]["some_bus"] == [True, False]


def test_register_realistic_nested_ga_metadata(tmp_path):
    root = tmp_path / "session"
    output = root / "optimization" / "run_001"
    output.mkdir(parents=True)
    (root / "session.json").write_text(json.dumps({"optimization_runs": [], "simulation_runs": []}))
    report = SimpleNamespace(
        context={"Placement stages": [{"full_year_candidates": [
            {"economic_acceptable": np.bool_(True), "technical_acceptable": np.bool_(True)}]}]},
        metrics=None,
        result=SimpleNamespace(metadata={"ga_visited_bus_count": np.int64(32)}, success=True),
    )
    session = StudySession.open_for_updates(root)
    session.record_run(output, True, report)
    saved = json.loads((root / "session.json").read_text())
    assert saved["optimization_runs"][0]["status"] == "success"
    assert saved["optimization_runs"][0]["context"]["Placement stages"][0]["full_year_candidates"][0]["economic_acceptable"] is True
    assert not list(root.glob(".session_*.tmp"))


def test_failing_json_does_not_overwrite_existing_manifest(tmp_path):
    root = tmp_path / "session"
    root.mkdir()
    path = root / "session.json"
    original = '{"optimization_runs": []}'
    path.write_text(original)
    session = StudySession(root, {"broken": object()})
    with pytest.raises(TypeError):
        session.save()
    assert path.read_text() == original


def test_recover_exported_annual_after_json_registration_error(tmp_path):
    root = tmp_path / "session"
    folder = root / "optimization" / "run_001"
    folder.mkdir(parents=True)
    manifest = {"optimization_runs": [{"path": "optimization\\run_001",
        "status": "failed", "error": "Object of type bool is not JSON serializable"}],
        "simulation_runs": []}
    (root / "session.json").write_text(json.dumps(manifest))
    (folder / "summary.md").write_text("# Results\n- Success: True\n")
    (folder / "dashboard_run.json").write_text(json.dumps({"kind": "optimization", "context": {}, "optimizer": {}}))
    with (folder / "metrics.csv").open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['metric', 'value', 'unit'])
        writer.writerows([['duration_hours', '8760', 'h'], ['annual_total_cost', '26489470', 'USD'], ['feasible', 'True', '']])
    assert recover(root) == ["optimization/run_001"]
    recovered = json.loads((root / "session.json").read_text())
    assert len(recovered["optimization_runs"]) == 1
    record = recovered["optimization_runs"][0]
    assert record["status"] == "recovered_complete"
    assert 'not JSON serializable' in record['recovered_from_error']
    assert recover(root) == []
    assert len(list(root.glob('session.json.before_recovery_*'))) == 1


def test_recovery_does_not_convert_physics_failure(tmp_path):
    root = tmp_path / "session"
    folder = root / "optimization" / "run_001"
    folder.mkdir(parents=True)
    (root / "session.json").write_text(json.dumps({"optimization_runs": [
        {"path": "optimization/run_001", "status": "failed", "error": "Network infeasible"}],
        "simulation_runs": []}))
    (folder / "summary.md").write_text("- Success: True\n")
    (folder / "dashboard_run.json").write_text(json.dumps({"kind": "optimization"}))
    (folder / "metrics.csv").write_text('metric,value,unit\nduration_hours,8760,h\nannual_total_cost,10,USD\nfeasible,True,\n')
    assert recover(root) == []
