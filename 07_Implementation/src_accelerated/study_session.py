"""Reproducible input snapshots and numbered outputs for one accepted study."""
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import csv
import json
from pathlib import Path
import re
import shutil


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
                    timestamp.isoformat(), bus_id,
                    active[bus_id][index], reactive[bus_id][index],
                ])


def study_fingerprint(study):
    """Identify accepted inputs without depending on their original paths."""
    digest = sha256()
    for key in ("Network SHA256", "Load source SHA256", "PV source SHA256",
                "History interval", "PV ratings (kW)", "Demand", "PV source"):
        digest.update(str(study.context.get(key, "")).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


class StudySession:
    """Own one session folder and its manifest updates."""
    def __init__(self, root, manifest):
        self.root = Path(root)
        self.manifest = dict(manifest)

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

        network_source = Path(study.request.network_path)
        network_snapshot = inputs / f"network{network_source.suffix.lower()}"
        shutil.copy2(network_source, network_snapshot)
        _write_profile(
            inputs / "load_profile.csv", study.profiles.timestamps,
            study.profiles.load_p_kw, study.profiles.load_q_kvar,
        )
        _write_profile(
            inputs / "pv_profile.csv", study.profiles.timestamps,
            study.profiles.pv_p_kw, study.profiles.pv_q_kvar,
        )

        source_files = {}
        for label, source in (("load_source", study.request.load_path),
                              ("pv_source", study.request.pv_path)):
            if source is not None and Path(source).is_file():
                destination = inputs / f"{label}{Path(source).suffix.lower()}"
                shutil.copy2(source, destination)
                source_files[label] = str(destination.relative_to(root))

        manifest = {
            "format_version": 1,
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
            "active_scenario_set": None,
            "scenario_sets": [],
            "simulation_runs": [],
            "optimization_runs": [],
        }
        session = cls(root, manifest)
        session.save()
        session.append_log("Session created from accepted and validated study inputs")
        return session

    def save(self):
        path = self.root / "session.json"
        path.write_text(json.dumps(_json_value(self.manifest), indent=2), encoding="utf-8")

    def append_log(self, message):
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        with (self.root / "session.log").open("a", encoding="utf-8") as stream:
            stream.write(f"[{stamp}] {message}\n")

    def next_path(self, category, prefix):
        parent = self.root / category
        parent.mkdir(exist_ok=True)
        index = 1
        while (parent / f"{prefix}_{index:03d}").exists():
            index += 1
        return parent / f"{prefix}_{index:03d}"

    def next_scenario_path(self):
        return self.next_path("scenarios", "set")

    def next_run_path(self, optimization):
        return self.next_path("optimization" if optimization else "simulation", "run")

    def record_scenario_set(self, path, metadata):
        relative = str(Path(path).relative_to(self.root))
        self.manifest["scenario_sets"].append({
            "path": relative,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            **_json_value(metadata),
        })
        self.manifest["active_scenario_set"] = relative
        self.save()
        self.append_log(f"Scenario set saved and activated: {relative}")

    def activate_scenario_set(self, path):
        path = Path(path).resolve()
        try:
            relative = str(path.relative_to(self.root.resolve()))
        except ValueError:
            relative = str(path)
        self.manifest["active_scenario_set"] = relative
        self.save()
        self.append_log(f"Scenario set activated: {relative}")

    def record_run(self, path, optimization):
        key = "optimization_runs" if optimization else "simulation_runs"
        relative = str(Path(path).relative_to(self.root))
        self.manifest[key].append({
            "path": relative,
            "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        })
        self.save()
        self.append_log(f"{'Optimization' if optimization else 'Simulation'} stored: {relative}")
