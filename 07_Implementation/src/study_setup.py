"""Save a reusable study setup with immutable source fingerprints."""
from dataclasses import asdict
from hashlib import file_digest
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd

from .data_loader import ProfileData
from .study_session import _json_value, study_fingerprint
from .ui_workflow import DataRequest, prepare_study
from .approved_methodology import methodology_record


_PATH_FIELDS = ("network_path", "pv_path", "load_path", "dataset_folder", "solar_cache")
_DATASET_FILES = ("load_profile.csv", "pv_profile.csv", "bus_assignments_used.csv", "bus_summary.csv", "manifest.json")


def _hash(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def _sources(request, forecast):
    files = [Path(value).resolve() for name, value in request.items()
             if value and name in ("network_path", "pv_path", "load_path") and Path(value).is_file()]
    if request.get("load_source") == "imported" and request.get("load_path"):
        sidecar = Path(request["load_path"]).resolve().with_suffix(".json")
        if sidecar.is_file():
            files.append(sidecar)
    if request.get("dataset_folder"):
        folder = Path(request["dataset_folder"]).resolve()
        files.extend(folder / name for name in _DATASET_FILES if (folder / name).is_file())
    if forecast.get("output_folder"):
        output = Path(forecast["output_folder"]).resolve()
        files.extend(output / name for name in ("load_profile.csv", "pv_profile.csv"))
    return {str(path): _hash(path) for path in files}


def save_study_setup(path, study, controls, stage=lambda _: None):
    stage("Saving study settings and source fingerprints")
    path = Path(path)
    request = asdict(study.request)
    for name in _PATH_FIELDS:
        if request[name] is not None:
            request[name] = str(Path(request[name]).resolve())
    if request["start"] is not None:
        request["start"] = str(request["start"])
    forecast = study.forecast_info or {}
    document = {"schema_version": 1, "request": request, "source_sha256": _sources(request, forecast),
                "study_fingerprint": study_fingerprint(study), "controls": controls,
                "window": study.simulation_window, "forecast": forecast,
                "installed_pv": [asdict(unit) for unit in study.network.pv_units],
                "assignments": study.assignments,
                "fixed_methodology": methodology_record(controls.get("fleet_dispatch_mode"))}
    with NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(_json_value(document), stream, indent=2, allow_nan=False)
        except BaseException:
            stream.close()
            temporary.unlink()
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def open_study_setup(path, stage=lambda _: None):
    stage("Checking saved study sources")
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Unsupported study setup version")
    for name, expected in document["source_sha256"].items():
        source = Path(name)
        if not source.is_file():
            raise ValueError(f"Saved study source is missing: {source}")
        if _hash(source) != expected:
            raise ValueError(f"Saved study source changed: {source}. Import the inputs again to use the new version.")
    values = document["request"]
    for name in _PATH_FIELDS:
        if values.get(name) is not None:
            values[name] = Path(values[name])
    start = values.get("start")
    values["start"] = pd.Timestamp(start) if start not in (None, "None") else None
    values["pv_ratings_kw"] = {int(bus): kw for bus, kw in values.get("pv_ratings_kw", {}).items()}
    study = prepare_study(DataRequest(**values), stage)
    # Older study setups may need historical overrides to reproduce their
    # source fingerprints. Never rewrite those inputs silently.
    legacy_critical = values.get("critical_irradiance")
    if legacy_critical not in (None, 0, 120.0):
        study.context["Historical irradiance override"] = (
            f"Saved study uses {legacy_critical} W/m2; new imported studies use "
            "the approved 120 W/m2 default. Reopening does not edit historical inputs.")
    if (study_fingerprint(study) != document["study_fingerprint"] or
            [asdict(unit) for unit in study.network.pv_units] != document["installed_pv"]):
        raise ValueError("Prepared study differs from the saved input fingerprints or PV installation rows")
    window, forecast = document["window"], document["forecast"]
    if forecast.get("output_folder"):
        directory = Path(forecast["output_folder"])
        study.forecast_profiles = ProfileData(directory / "load_profile.csv", directory / "pv_profile.csv")
        study.forecast_info = forecast
    if window:
        study.select_source(window["mode"], window["start"], window["end_exclusive"])
    from .saved_schema import upgrade_saved_fields
    return study, upgrade_saved_fields({"spin_ga_stall_generations": 6, **document["controls"]})
