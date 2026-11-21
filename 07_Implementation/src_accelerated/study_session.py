"""Reproducible input snapshots and numbered outputs for one accepted study."""
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import csv
import json
from pathlib import Path
import re
import shutil
import sys
import subprocess
from importlib.metadata import version, PackageNotFoundError


def _json_value(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _slug(value):
    text = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    return text or "study"


def _write_profile(path, timestamps, active, reactive):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["timestamp", "bus_id", "p_kw", "q_kvar"])
        for bus_id in sorted(active):
            for index, timestamp in enumerate(timestamps):
                writer.writerow([
                    timestamp if isinstance(timestamp, str) else timestamp.isoformat(), bus_id,
                    active[bus_id][index], reactive[bus_id][index],
                ])


def write_input_snapshot(output, *, metadata, profiles=None, point=None, workbook=None):
    """Save the profiles actually used by a run and their alignment metadata."""
    root = Path(output) / "inputs"
    root.mkdir(exist_ok=False)
    paths = {}
    for kind in ("load", "pv"):
        if profiles is not None:
            timestamps = profiles.timestamps
            active = getattr(profiles, f"{kind}_p_kw")
            reactive = getattr(profiles, f"{kind}_q_kvar")
        else:
            timestamps = ("Static base case",)
            active = {bus: [value] for bus, value in getattr(point, f"p_{kind}_kw").items()}
            reactive = {bus: [value] for bus, value in getattr(point, f"q_{kind}_kvar").items()}
        name = f"{kind}_profile.csv"
        _write_profile(root / name, timestamps, active, reactive)
        paths[f"inputs/{name}"] = root / name
    if workbook is not None:
        name = "network" + Path(workbook).suffix.lower()
        shutil.copy2(workbook, root / name)
        paths[f"inputs/{name}"] = root / name
    manifest = root / "input_snapshot.json"
    manifest.write_text(json.dumps(_json_value(metadata), indent=2), encoding="utf-8")
    paths["inputs/input_snapshot.json"] = manifest
    return paths


def study_fingerprint(study):
    """Identify accepted inputs without depending on their original paths."""
    digest = sha256()
    for key in ("Network SHA256", "Load source SHA256", "PV source SHA256",
                "History interval", "PV ratings (kW)", "Demand", "PV source"):
        digest.update(str(study.context.get(key, "")).encode("utf-8"))
        digest.update(b"\0")
    reference = getattr(study,"pv_reference",None)
    extras = {"assignments":getattr(study,"assignments",{}),
        "dataset_hashes":getattr(study,"dataset_metadata",{}).get("source_hashes",{}),
        "clock":study.context.get("Clock"),
        "pv_reference":({"capacity_kw":reference.capacity_kw,"site":asdict(reference.site),
                         "provenance":reference.provenance} if reference is not None else None)}
    digest.update(json.dumps(_json_value(extras),sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


class StudySession:
    """Own one session folder and its manifest updates."""
    def __init__(self, root, manifest, read_only=False):
        self.root = Path(root)
        self.manifest = dict(manifest)
        self.read_only = read_only

    @classmethod
    def create(cls, study, results_root):
        created = datetime.now().astimezone()
        network_name = Path(study.request.network_path).stem
        base_name = f"{created:%Y%m%d_%H%M%S}_{_slug(network_name)}"
        root = Path(results_root) / "Sessions" / base_name
        suffix = 2
        while root.exists():
            root = Path(results_root) / "Sessions" / f"{base_name}_{suffix}"
            suffix += 1
        inputs = root / "inputs"
        inputs.mkdir(parents=True)

        raw = study.historical_profiles or study.profiles
        network_source = Path(study.request.network_path)
        network_snapshot = inputs / f"network{network_source.suffix.lower()}"
        shutil.copy2(network_source, network_snapshot)
        _write_profile(
            inputs / "load_profile.csv", raw.timestamps,
            raw.load_p_kw, raw.load_q_kvar,
        )
        _write_profile(
            inputs / "pv_profile.csv", raw.timestamps,
            raw.pv_p_kw, raw.pv_q_kvar,
        )

        source_files = {}
        for label, source in (("load_source", study.request.load_path),
                              ("pv_source", study.request.pv_path)):
            if source is not None and Path(source).is_file():
                destination = inputs / f"{label}{Path(source).suffix.lower()}"
                shutil.copy2(source, destination)
                source_files[label] = str(destination.relative_to(root))

        if study.request.dataset_folder:
            for name in ("bus_assignments_used.csv","bus_summary.csv","manifest.json","IMPORTANT_PV_AND_VOLTAGE.txt"):
                source = Path(study.request.dataset_folder)/name
                if source.is_file():
                    shutil.copy2(source, inputs/name)
        if study.pv_reference is not None:
            ref = study.pv_reference
            import pandas as pd
            pd.DataFrame({"timestamp":ref.timestamps,"p_kw":ref.p_kw}).to_csv(inputs/"common_pv_reference.csv",index=False)
        manifest = {
            "format_version": 2,
            "engines": {"power_flow":"numba", "load":"sector_sum", "pv":"common modeled XGBoost"},
            "runtime": runtime_provenance(),
            "dataset": study.dataset_metadata,
            "assignments": study.assignments,
            "final_pv_ratings": {unit.bus_id:sum(u.p_rated_kw for u in study.network.pv_units if u.bus_id==unit.bus_id) for unit in study.network.pv_units},
            "simulation_window": study.simulation_window,
            "pv_reference": ({"capacity_kw":study.pv_reference.capacity_kw,"site":asdict(study.pv_reference.site),"provenance":study.pv_reference.provenance} if study.pv_reference else None),
            "session_id": root.name,
            "created_at": created.isoformat(timespec="seconds"),
            "fingerprint": study_fingerprint(study),
            "network_name": network_name,
            "network_snapshot": str(network_snapshot.relative_to(root)),
            "load_profile_snapshot": "inputs/load_profile.csv",
            "pv_profile_snapshot": "inputs/pv_profile.csv",
            "source_files": source_files,
            "request": _json_value(asdict(study.request)),
            "context": _json_value(study.context),
            "forecast_runs": [],
            "simulation_runs": [],
            "base_case_runs": [],
            "optimization_runs": [],
        }
        session = cls(root, manifest)
        session.save()
        session.append_log("Session created from accepted and validated study inputs")
        return session

    def save(self):
        self._writable()
        path = self.root / "session.json"
        path.write_text(json.dumps(_json_value(self.manifest), indent=2), encoding="utf-8")

    def append_log(self, message):
        self.append_log_lines((message,))

    def append_log_lines(self, messages):
        self._writable()
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        with (self.root / "session.log").open("a", encoding="utf-8") as stream:
            stream.writelines(f"[{stamp}] {message}\n" for message in messages)

    def next_path(self, category, prefix):
        self._writable()
        parent = self.root / category
        parent.mkdir(exist_ok=True)
        index = 1
        while (parent / f"{prefix}_{index:03d}").exists():
            index += 1
        return parent / f"{prefix}_{index:03d}"

    def next_run_path(self, optimization):
        return self.next_path("optimization" if optimization else "simulation", "run")

    def network_snapshot_path(self):
        relative = self.manifest.get("network_snapshot")
        return self.root / relative if relative else None

    def record_run(self, path, optimization, report=None):
        key = "optimization_runs" if optimization else "simulation_runs"
        relative = str(Path(path).relative_to(self.root))
        self.manifest[key].append({
            "context": report.context if report else None,
            "metrics": asdict(report.metrics or getattr(report.result,"metrics",None)) if report and (report.metrics or getattr(report.result,"metrics",None)) else None,
            "optimizer": getattr(report.result,"metadata",None) if report else None,
            "status": ("success" if getattr(report.result,"completed",getattr(report.result,"success",False)) else "failed") if report else "stored",
            "path": relative,
            "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        })
        self.save()
        self.append_log(f"{'Optimization' if optimization else 'Simulation'} stored: {relative}")

    def record_failure(self, path, category, message, provenance=None):
        self._writable()
        key = {"simulation":"simulation_runs","optimization":"optimization_runs","base_case":"base_case_runs"}[category]
        self.manifest[key].append({"path":str(Path(path).relative_to(self.root)), "status":"failed",
            "error":message,"provenance":provenance,"completed_at":datetime.now().astimezone().isoformat(timespec="seconds")})
        self.save()
        self.append_log(f"{category} failed: {message}")

    def record_base_case(self, path):
        relative = str(Path(path).relative_to(self.root))
        self.manifest["base_case_runs"].append({
            "path": relative,
            "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        })
        self.save()
        self.append_log(f"Static base-case FBS stored: {relative}")


    def _writable(self):
        if self.read_only:
            raise ValueError("Historical study is read-only; migrate inputs to a new study ID for execution")

    @classmethod
    def open_read_only(cls, root):
        root = Path(root)
        manifest = json.loads((root/"session.json").read_text(encoding="utf-8"))
        return cls(root,manifest,read_only=True)

    def history_text(self):
        pieces = [json.dumps(self.manifest,indent=2)]
        for name in ("simulation_runs","optimization_runs","base_case_runs"):
            for record in self.manifest.get(name,[]):
                folder = (self.root/record["path"]).resolve()
                if not folder.is_relative_to(self.root.resolve()):
                    raise ValueError("Historical manifest references an unsafe output path")
                for summary in ("summary.md","summary.txt"):
                    path = folder/summary
                    if path.is_file():
                        pieces.append(path.read_text(encoding="utf-8"))
        return "\n\n".join(pieces)


def runtime_provenance():
    result = {"python_executable":sys.executable,"python_version":sys.version,"backend":"numba"}
    for package in ("numba","llvmlite","numpy","scikit-learn","xgboost","lightgbm"):
        try: result[package] = version(package)
        except PackageNotFoundError: result[package] = "unavailable"
    try:
        result["git_revision"] = subprocess.check_output(["git","rev-parse","HEAD"],cwd=Path(__file__).parent,
                                                      stderr=subprocess.DEVNULL,text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        result["git_revision"] = "unavailable"
    try:
        result["source_dirty"] = bool(subprocess.check_output(["git","status","--porcelain"],cwd=Path(__file__).parent,
            stderr=subprocess.DEVNULL,text=True).strip())
    except (OSError,subprocess.CalledProcessError):
        result["source_dirty"] = None
    return result


def migrate_inputs(historical, results_root):
    """Copy compatible inputs; never resume or edit an archived execution."""
    from .ui_workflow import DataRequest, prepare_study, select_default_history
    def snapshot(key):
        path = (historical.root/historical.manifest[key]).resolve()
        if not path.is_relative_to(historical.root.resolve()) or not path.is_file():
            raise ValueError("Historical input snapshot is missing or unsafe")
        return path
    old = historical.manifest.get("request",{})
    request = DataRequest(network_path=snapshot("network_snapshot"), frequency_hz=old.get("frequency_hz"),
        workbook_format=old.get("workbook_format","auto"),start=None,months=None,pv_source="none" if old.get("pv_source")=="none" else "power",
        pv_path=snapshot("pv_profile_snapshot"),load_source="imported",load_path=snapshot("load_profile_snapshot"),
        pv_ratings_kw={int(b):r for b,r in historical.manifest.get("final_pv_ratings",old.get("pv_ratings_kw",{})).items()})
    study = prepare_study(request)
    study.assignments = {int(b):sector for b,sector in historical.manifest.get("assignments",{}).items()}
    study.dataset_metadata = historical.manifest.get("dataset",{})
    ref_info = historical.manifest.get("pv_reference")
    if ref_info and (historical.root/"inputs/common_pv_reference.csv").is_file():
        import pandas as pd
        from .solar_source import SolarSite, PVReference
        frame = pd.read_csv(historical.root/"inputs/common_pv_reference.csv")
        provenance = ref_info["provenance"]
        site = ref_info.get("site") or provenance.get("site") or study.dataset_metadata.get("site")
        if site:
            study.pv_reference = PVReference(pd.to_datetime(frame.timestamp),frame.p_kw.to_numpy(),
                ref_info["capacity_kw"],SolarSite(**site),provenance)
    select_default_history(study)
    session = StudySession.create(study,results_root)
    session.manifest["migrated_from"] = str(historical.root)
    session.manifest["migration_note"] = "Inputs copied; Numba and approved forecasts only. Configure economics and time window anew. Legacy outputs/settings preserved read-only."
    session.save()
    return study,session
