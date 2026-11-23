"""UI-neutral preparation/run orchestration; the numerical modules own physics."""
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from io import StringIO
from hashlib import sha256
from math import isclose, isfinite
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

import pandas as pd

from .bess import BESSConfig
from .data_loader import ProfileData
from .fbs import OperatingPoint, run_fbs
from .forecasting import generate_forecast
from .metrics import EconomicConfig, annual_capital_recovery_factor, evaluate_results, validate_annual_inputs, with_terminal_policy
from .network_loader import load_network
from .network_model import NetworkModel, PVUnit
from .optimizer import BESSParameters, OptimizationBounds, OptimizerConfig, SimulationEvaluator, optimize, genetic_optimize
from .pv_model import PVModelConfig, make_pv_profile, read_irradiance, irradiance_to_power, read_nasa_csv
from .distributed_dataset import load_distributed
from .solar_source import SolarSite, PVReference, convert_clock, reference_from_file, fetch_irradiance
import numpy as np
import json
from .results import export_results, format_summary
from .simulation import ConstraintAwareDispatch, SimulationConfig, simulate_timeseries
from .single_bess_search import optimize_fast_verified
from .progress import ProgressEvent, format_duration
from .approved_methodology import methodology_record, resolve_solar_location
from .planning_policy import DEFAULT_DISPATCH_EFFICIENCY, desktop_worker_limit, effective_joint_search
from .model_information import dispatch_information, model_reference, study_information


@dataclass
class DataRequest:
    network_path: Path
    frequency_hz: float | None
    workbook_format: str
    start: object
    months: int
    pv_source: str
    pv_path: Path | None = None
    pv_ratings_kw: dict[int, float] = field(default_factory=dict)
    critical_irradiance: float = 0.0
    standard_irradiance: float = 1000.0
    load_source: str = "synthetic"
    load_path: Path | None = None
    load_seed: int = 42
    dataset_folder: Path | None = None
    pv_override: bool = False
    pv_rating_selection: str = ""
    latitude: float | None = None
    longitude: float | None = None
    clock: str | None = None
    solar_source_clock: str | None = None
    reference_capacity_kw: float | None = None
    solar_cache: Path | None = None


@dataclass
class PreparedStudy:
    network: NetworkModel
    profiles: ProfileData
    request: DataRequest
    context: dict[str, str]
    historical_profiles: ProfileData | None = None
    forecast_info: dict | None = None
    forecast_profiles: ProfileData | None = None
    assignments: dict = field(default_factory=dict)
    dataset_metadata: dict = field(default_factory=dict)
    pv_reference: object = None
    input_mode: str = "historical"
    simulation_window: dict = field(default_factory=dict)

    source_irradiance: object = None

    def select_source(self, mode, start=None, end=None):
        raw = self.historical_profiles if mode == "historical" else self.forecast_profiles if mode == "forecast" else None
        if raw is None:
            raise ValueError("Selected input source is unavailable; import history or generate forecast first")
        self.profiles = raw.slice(start,end)
        self.input_mode = mode
        self.simulation_window = {"mode":mode,"start":str(self.profiles.timestamps[0]),
                                  "end_exclusive":str(pd.Timestamp(self.profiles.timestamps[-1])+pd.Timedelta(hours=1)),
                                  "hours":len(self.profiles.timestamps)}


@dataclass
class RunSettings:
    simulation: SimulationConfig
    economics: EconomicConfig
    manual_bess: BESSConfig | None
    values: dict
    dispatch: object | None = field(default_factory=ConstraintAwareDispatch)
    managed_search: bool = False


def select_default_history(study):
    """Select the first 24 imported hours without changing the retained history."""
    raw = study.historical_profiles or study.profiles
    study.historical_profiles = raw
    times = pd.DatetimeIndex(raw.timestamps)
    start,end = times[0],times[-1]+pd.Timedelta(hours=1)
    end = min(end,start+pd.Timedelta(hours=24))
    study.select_source("historical",start,end)


def first_calendar_year(timestamps):
    """Return the first January-to-January window in a continuous hourly source."""
    start = pd.Timestamp(timestamps[0])
    end = pd.Timestamp(timestamps[-1]) + pd.Timedelta(hours=1)
    january = pd.Timestamp(year=start.year, month=1, day=1)
    if january < start:
        january = pd.Timestamp(year=start.year + 1, month=1, day=1)
    following = pd.Timestamp(year=january.year + 1, month=1, day=1)
    return (january, following) if following <= end else None


@dataclass
class RunReport:
    result: object
    metrics: object
    context: dict[str, str]
    alternatives: dict = field(default_factory=dict)
    dashboard_path: Path | None = None
    persistence_warning: str | None = None
    saved: bool = False

    def summary(self, detailed=False):
        context = self.context if detailed else {
            key: value for key, value in self.context.items()
            if key in ("Network", "History interval", "Dispatch", "Forecast interval", "Run duration")
        }
        return format_summary(self.result, metrics=self.metrics, context=context)


@dataclass
class StaticResultStep:
    """One displayable electrical snapshot for the static base-case run."""
    timestamp: str
    operating_point: OperatingPoint
    power_flow: object
    shedding_by_bus_kw: dict[int, float]
    curtailment_by_bus_kw: dict[int, float]


@dataclass
class BaseCaseReport:
    """Static, one-sweep feeder check using the network's original base values."""
    result: object
    context: dict[str, str]
    step: object
    metrics: object = None
    dashboard_path: Path | None = None

    def summary(self, detailed=False):
        lines = ["Static Base-Case FBS", f"Status: {self.result.message}",
                 f"FBS iterations: {self.result.iterations}",
                 f"Voltage range: {min(self.result.voltage_mag_pu.values()):.5f} to {max(self.result.voltage_mag_pu.values()):.5f} pu",
                 f"Real power loss: {self.result.total_loss_p_kw:.4f} kW"]
        if detailed:
            lines.extend(f"{key}: {value}" for key, value in self.context.items())
        return "\n".join(lines)


def size_catalog(minimum: float, maximum: float, step: float) -> tuple[float, ...]:
    for value in (minimum, maximum, step):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
            raise ValueError("Battery min/max/step must be finite positive numbers")
    low, high, increment = (Decimal(str(value)) for value in (minimum, maximum, step))
    if high < low:
        raise ValueError("Battery maximum must be at least its minimum")
    if high - low > increment * 9999:
        raise ValueError("A sizing axis exceeds 10,000 entries; increase its explicit step")
    count = int((high - low) // increment) + 1
    extra_endpoint = low + (count - 1) * increment != high
    if count + extra_endpoint > 10000:
        raise ValueError("A sizing axis exceeds 10,000 entries; increase its explicit step")
    values = [float(low + index * increment) for index in range(count)]
    if extra_endpoint:
        values.append(float(high))
    if len(set(values)) != len(values):
        raise ValueError("Size step is too small to represent distinct floating-point values")
    return tuple(values)


def _read_power_table(source, times, network, kind):
    if source is None:
        raise ValueError(f"Choose a prepared {kind} CSV or Excel workbook")
    if isinstance(source, pd.DataFrame):
        frame = source
    elif Path(source).suffix.lower() == ".xlsx":
        frame = pd.read_excel(source)
    else:
        frame = pd.read_csv(source, encoding="utf-8-sig")
    columns = ["timestamp", "bus_id", "p_kw", "q_kvar"]
    if not set(columns).issubset(frame.columns):
        raise ValueError(f"{kind} profile requires {', '.join(columns)}")
    frame = frame[columns].copy()
    frame["timestamp"] = pd.to_datetime(frame.timestamp, format="ISO8601", errors="raise")
    if frame.timestamp.isna().any() or frame.timestamp.dt.tz is not None:
        raise ValueError(f"{kind} CSV needs valid timestamps in one timezone-naive source clock")
    for name in columns[1:]:
        frame[name] = pd.to_numeric(frame[name], errors="raise")
        if any(not isfinite(v) for v in frame[name]) or pd.api.types.is_bool_dtype(frame[name]):
            raise ValueError(f"{kind} {name} must contain finite numeric values")
    if any(value != int(value) for value in frame.bus_id):
        raise ValueError(f"{kind} bus IDs must be integers")
    frame["bus_id"] = frame.bus_id.astype(int)
    unknown = set(frame.bus_id) - {bus.bus_id for bus in network.buses}
    if unknown:
        raise ValueError(f"{kind} CSV references unknown buses: {sorted(unknown)}")
    if frame.duplicated(["timestamp", "bus_id"]).any():
        raise ValueError(f"{kind} CSV has duplicate timestamp/bus rows")
    if (frame.p_kw < 0).any() or (kind == "load" and (frame.q_kvar < 0).any()):
        raise ValueError(f"{kind} CSV contains negative demand/generation")
    frame = frame[frame.timestamp.isin(times)].copy()
    required = {load.bus_id for load in network.loads} if kind == "load" else {unit.bus_id for unit in network.pv_units}
    missing = required - set(frame.bus_id)
    if missing:
        raise ValueError(f"{kind} CSV is missing configured buses: {sorted(missing)}")
    if frame.empty:
        raise ValueError(f"{kind} CSV does not cover the requested study interval")
    for bus, rows in frame.groupby("bus_id"):
        if set(rows.timestamp) != set(times):
            raise ValueError(f"{kind} CSV has missing study hours at bus {bus}; no interpolation is applied")
    if kind == "PV":
        ratings = {}
        for unit in network.pv_units:
            ratings[unit.bus_id] = ratings.get(unit.bus_id, 0.0) + unit.p_rated_kw
        for row in frame.itertuples():
            if row.p_kw > ratings.get(row.bus_id, 0.0) + 1e-6:
                raise ValueError(f"PV output at bus {row.bus_id} exceeds its explicit installed rating; fill the PV table")
    return frame.sort_values(["timestamp", "bus_id"]).reset_index(drop=True)


def prepare_study(request: DataRequest, stage=lambda message: None) -> PreparedStudy:
    started = perf_counter()
    stage(f"Loading network: {Path(request.network_path).name}")
    network = load_network(request.network_path, workbook_format=request.workbook_format,
                           frequency_hz=request.frequency_hz)
    stage(f"Network validated: {len(network.buses)} buses, {len(network.lines)} branches, "
          f"slack bus {network.slack_bus_id()}")
    if request.load_source == "distributed":
        study = _prepare_distributed(request, network, stage)
        stage(f"Study preparation completed in {perf_counter() - started:.2f} s")
        return study
    # Imported CSV timestamps are the authority: no study-window settings.
    # A synthetic-only load has no timestamps to infer, so the preparation
    # interface requires a dated imported load CSV in this application mode.
    if request.load_source != "imported" or request.load_path is None:
        raise ValueError("Select an imported hourly load CSV to infer the study interval")
    source = Path(request.load_path)
    stage(f"Loading demand: {source.name}")
    demand = (pd.read_excel(source) if source.suffix.lower() == ".xlsx"
              else pd.read_csv(source, encoding="utf-8-sig"))
    if "timestamp" not in demand:
        raise ValueError("Load profile requires a timestamp column")
    times = pd.DatetimeIndex(pd.to_datetime(demand["timestamp"], format="ISO8601", errors="raise").unique()).sort_values()
    if len(times) < 2 or times.hasnans or times.tz is not None:
        raise ValueError("Load CSV must have at least two timezone-naive hourly timestamps")
    if any(times[i] - times[i-1] != pd.Timedelta(hours=1) for i in range(1, len(times))):
        raise ValueError("The load CSV must contain consecutive hourly timestamps")
    start, end = times[0], times[-1] + pd.Timedelta(hours=1)
    if request.pv_source == "none":
        network = replace(network, pv_units=[])
    else:
        units = []
        for bus, rating in sorted(request.pv_ratings_kw.items()):
            if isinstance(bus, bool) or not isinstance(bus, int):
                raise ValueError("PV bus IDs must be integers")
            if isinstance(rating, bool) or not isfinite(rating) or rating < 0:
                raise ValueError("PV ratings must be finite nonnegative kW")
            old = [unit for unit in network.pv_units if unit.bus_id == bus]
            if old and sum(unit.p_rated_kw for unit in old) == rating:
                units.extend(old)
            else:
                q_cap = sum(unit.q_capability_kvar for unit in old) if old and all(unit.q_capability_kvar is not None for unit in old) else None
                units.append(PVUnit(f"study_pv_{bus}", bus, rating, q_cap))
        network = replace(network, pv_units=units)
    network.validate()
    stage("Preparing PV profile")
    if request.pv_source == "power":
        if request.clock and request.solar_source_clock != request.clock:
            raise ValueError("Declare the same clock for the aligned bus-level PV power and load sources")
        pv = _read_power_table(request.pv_path, times, network, "PV")
    elif request.pv_source == "none":
        pv = pd.DataFrame({"timestamp": times, "bus_id": network.slack_bus_id(), "p_kw": 0.0, "q_kvar": 0.0})
    elif request.pv_source in ("open_meteo", "nasa_power", "prepared"):
        if request.pv_path is None or not network.pv_units:
            raise ValueError("Irradiance conversion needs a source CSV and explicit PV installations")
        weather = read_irradiance(request.pv_path, source=request.pv_source)
        if request.clock:
            source_clock = request.solar_source_clock
            if request.pv_source == "nasa_power":
                _, meta = read_nasa_csv(request.pv_path)
                declared = meta.get("source_clock")
                if declared and source_clock and declared != source_clock:
                    raise ValueError("NASA POWER metadata and the supplied solar clock disagree")
                source_clock = declared or source_clock
            weather["timestamp"] = convert_clock(weather.timestamp, source_clock, request.clock)
        weather = weather[weather.timestamp.isin(times)].reset_index(drop=True)
        if not pd.DatetimeIndex(weather.timestamp).equals(times):
            raise ValueError("Irradiance source does not cover every requested study hour")
        pv = make_pv_profile(network, weather, PVModelConfig(request.critical_irradiance, request.standard_irradiance))
    elif request.pv_source in ("auto_nasa_power", "auto_open_meteo"):
        if request.latitude is None or request.longitude is None or not network.pv_units:
            raise ValueError("Automatic irradiance needs declared site coordinates and explicit PV installations")
        site = SolarSite(request.latitude, request.longitude, request.clock)
        weather, _ = fetch_irradiance(
            request.pv_source.removeprefix("auto_"), times, site,
            request.solar_cache or Path(request.network_path).parent / "solar_cache")
        pv = make_pv_profile(network, weather, PVModelConfig(request.critical_irradiance, request.standard_irradiance))
    else:
        raise ValueError("Unsupported PV input mode")
    stage("Preparing load profile")
    demand = _read_power_table(demand, times, network, "load")
    stage("Checking prepared profiles")
    profiles = ProfileData(StringIO(demand.to_csv(index=False)), StringIO(pv.to_csv(index=False)))
    network_label = "Guide 5-Bus radial test" if len(network.buses) == 5 else f"{len(network.buses)}-bus radial network"
    context = {
        "Network": network_label,
        "PV source": "No PV" if request.pv_source == "none" else request.pv_source.replace("_", " "),
        "Demand": "Imported load profile",
        "History interval": f"{start.isoformat()} to {end.isoformat()} (exclusive); {len(times)} hours",
        "Study scope": "Complete timestamps inferred from imported load CSV",
        "Clock": request.clock,
        "PV ratings (kW)": str({unit.pv_id: unit.p_rated_kw for unit in network.pv_units}),
        "Preparation": "GHI proxy if converting; imported demand timestamps preserved",
        "Network SHA256": sha256(Path(request.network_path).read_bytes()).hexdigest(),
        "Network import": f"Format {request.workbook_format}; frequency {network.frequency_hz:g} Hz",
    }
    if request.pv_source != "none" and request.pv_path is not None:
        context["PV source SHA256"] = sha256(Path(request.pv_path).read_bytes()).hexdigest()
    if request.pv_source in ("open_meteo", "nasa_power", "prepared"):
        context["PV conversion (W/m2)"] = f"Critical {request.critical_irradiance:g}; standard {request.standard_irradiance:g}"
    if request.load_source == "imported" and request.load_path is not None:
        context["Load source SHA256"] = sha256(Path(request.load_path).read_bytes()).hexdigest()
    study = PreparedStudy(network, profiles, request, context)
    select_default_history(study)
    stage(f"Demand and PV profiles validated: {len(profiles.timestamps):,} aligned hourly timestamps")
    stage(f"Study preparation completed in {perf_counter() - started:.2f} s")
    return study


def _prepare_distributed(request, network, stage):
    if request.dataset_folder is None:
        raise ValueError("Choose a GoiEner distributed case folder")
    stage(f"Loading prepared demand case: {Path(request.dataset_folder).name}")
    dataset = load_distributed(request.dataset_folder,network,request.network_path,request.clock)
    meta = dataset.metadata
    clock = meta.get("clock")
    if not clock:
        raise ValueError("Dataset clock is unspecified in manifest.json. Declare its actual IANA/UTC source clock in dataset metadata before import")
    workbook_ratings = {}
    for unit in network.pv_units:
        workbook_ratings[unit.bus_id] = workbook_ratings.get(unit.bus_id, 0.) + unit.p_rated_kw
    imported = workbook_ratings or dataset.ratings
    ratings = dict(request.pv_ratings_kw) if request.pv_override else dict(imported)
    if request.pv_source == "none":
        ratings = {}
    ids = {b.bus_id for b in network.buses}
    if (any(type(bus) is not int or bus not in ids for bus in ratings)
            or any(isinstance(r, bool) or not np.isfinite(r) or r < 0 for r in ratings.values())):
        raise ValueError("Final PV ratings must reference network buses and finite nonnegative nameplates")
    units = []
    for bus, rating in sorted(ratings.items()):
        if rating <= 0:
            continue
        original = [unit for unit in network.pv_units if unit.bus_id == bus]
        if rating == workbook_ratings.get(bus):
            units.extend(original)
        else:
            units.append(PVUnit(f"study_pv_{bus}", bus, rating, None))
    network = replace(network, pv_units=units)
    network.validate()
    raw = dataset.profiles
    times = pd.DatetimeIndex(raw.timestamps)
    pvref = None
    if request.pv_source == "dataset" and not ratings and not request.pv_override and any(
            np.any(values) for values in raw.pv_p_kw.values()):
        raise ValueError(dataset.pv_reason + ". Select installed PV ratings or choose No PV study.")
    if sum(ratings.values()) > 0:
        if request.pv_source == "dataset" and not dataset.pv_valid:
            raise ValueError(dataset.pv_reason + ". Enable Use fallback solar source or choose No PV study.")
        site_meta = meta.get("site") or (meta.get("pv_reference") or {}).get("site") or {}
        source_meta = {}
        if not dataset.pv_valid and request.pv_path is not None and request.pv_source == "nasa_power":
            _,source_meta = read_nasa_csv(request.pv_path)
        elif not dataset.pv_valid and request.pv_path is not None and request.pv_source in ("power","prepared","open_meteo"):
            head = pd.read_csv(request.pv_path,nrows=1,encoding="utf-8-sig")
            if len(head): source_meta = head.iloc[0].dropna().to_dict()
        named_site = (site_meta.get("latitude", meta.get("site_lat")), site_meta.get("longitude", meta.get("site_lon")))
        file_site = (source_meta.get("site_lat", source_meta.get("latitude")),
                     source_meta.get("site_lon", source_meta.get("longitude")))
        entered_site = (request.latitude, request.longitude)
        resolve_solar_location(
            {"latitude": named_site[0], "longitude": named_site[1]},
            {"latitude": file_site[0], "longitude": file_site[1]})
        sites = (named_site, entered_site) if dataset.pv_valid else (file_site, entered_site, named_site)
        lat, lon = (next((value for value in choices if value is not None), None)
                    for choices in zip(*sites))
        if lat is None or lon is None:
            raise ValueError("Solar CSV or dataset metadata must declare latitude and longitude; automatic retrieval uses the site fields")
        site = SolarSite(float(lat),float(lon),clock)
        if dataset.pv_valid:
            capacity = sum(dataset.ratings.values())
            power = np.sum([raw.pv_p_kw[b] for b in dataset.ratings],axis=0)
            pvref = PVReference(times,power,capacity,site,{"source":"validated distributed common PV", "folder":str(dataset.folder),
                "metadata":meta.get("pv_reference"),"hashes":meta["source_hashes"]})
        else:
            mode = request.pv_source
            conversion = PVModelConfig(request.critical_irradiance or 120.,request.standard_irradiance)
            capacity = (request.reference_capacity_kw if request.reference_capacity_kw is not None
                        else source_meta.get("reference_capacity_kw",source_meta.get("capacity_kw")))
            if capacity is None and mode != "power":
                # Irradiance is normalized against the explicitly installed
                # nameplates, so a separate observed-PV nameplate is unnecessary.
                capacity = sum(ratings.values())
            if capacity is None or not np.isfinite(float(capacity)) or float(capacity) <= 0:
                raise ValueError("Supply the positive nameplate of the common historical PV reference")
            capacity = float(capacity)
            if mode in ("auto_nasa_power","auto_open_meteo"):
                stage("Retrieving historical irradiance; no future observations are requested")
                weather,sources = fetch_irradiance(mode.removeprefix("auto_"),times,site,
                    request.solar_cache or Path(request.network_path).parent/"solar_cache")
                power = [irradiance_to_power(v,capacity,conversion) for v in weather.irradiance_w_m2]
                pvref = PVReference(times,power,capacity,site,{"sources":sources,"conversion":asdict(conversion),"clock":"UTC converted to load clock"}, weather.irradiance_w_m2.to_numpy())
            elif request.pv_path is not None and mode in ("power","prepared","nasa_power","open_meteo"):
                declared_clock = source_meta.get("source_clock", source_meta.get("timezone"))
                if declared_clock and request.solar_source_clock and declared_clock != request.solar_source_clock:
                    raise ValueError("Solar file clock conflicts with the entered clock. Convert the source timestamps before relabeling.")
                source_clock = declared_clock or request.solar_source_clock
                if not source_clock:
                    raise ValueError("Declare the solar file source clock (NASA LST cannot be relabeled as UTC)")
                pvref = reference_from_file(request.pv_path,mode,capacity,site,source_clock,conversion)
            else:
                raise ValueError(dataset.pv_reason+"; choose a manual file or automatic historical provider")
        reference = pd.Series(pvref.p_kw,index=pd.DatetimeIndex(pvref.timestamps)).reindex(times)
        if reference.isna().any():
            raise ValueError("Solar reference must cover all imported history for historical simulation and selectable training")
        cf = reference.to_numpy()/pvref.capacity_kw
        pv = {b:(cf*ratings.get(b,0)).tolist() for b in ids}
    else:
        pv = {b:np.zeros(len(times)).tolist() for b in ids}
    raw = ProfileData.from_arrays(times,raw.load_p_kw,raw.load_q_kvar,pv,{b:np.zeros(len(times)).tolist() for b in ids})
    stage(meta["workbook_provenance"])
    if dataset.pv_valid and ratings != dataset.ratings and pvref:
        stage("PV nameplates differ: applying the validated historical common capacity factor to selected ratings.")
    context = {"Network":f"{len(ids)}-bus radial network","Network SHA256":meta["selected_network_sha256"],
        "Distributor network SHA256":meta["distributor_network_sha256"],
        "Workbook provenance":meta["workbook_provenance"],
        "Load profile buses": len(raw.load_p_kw),
        "Load source SHA256":meta["source_hashes"]["load_profile.csv"],
        "PV source": ("None" if pvref is None else "Validated dataset history" if dataset.pv_valid else request.pv_source),
        "PV source provenance": pvref.provenance if pvref else None,
        "PV ratings (kW)":str(ratings), "Workbook PV ratings (kW)":str(workbook_ratings),
        "Folder PV ratings (kW)":str(dataset.ratings),
        "PV scaling": ("Historical common capacity factor × selected installed kW" if pvref else "No PV"),
        "PV rating selection": ("No PV" if request.pv_source == "none" else
            (request.pv_rating_selection or "Explicit override") if request.pv_override else
            "Workbook" if workbook_ratings else "Dataset folder"),
        "Demand":"GoiEner distributed sector assignments", "Dataset folder":str(dataset.folder),
        "Demand normalization":meta.get("normalization"),
        "History interval":f"{times[0]} through {times[-1]}; {len(times)} hours", "Clock":clock,
        "Classification disclaimer":meta.get("sector_assignment_status","Explicit user scenario; not observed customer labels"),
        "Dataset provenance":json.dumps(meta),"PV history validation":dataset.pv_reason}
    study = PreparedStudy(network,raw,request,context,historical_profiles=raw,assignments=dataset.assignments,
                          dataset_metadata=meta,pv_reference=pvref)
    if pvref is not None and pvref.irradiance_w_m2 is not None:
        study.source_irradiance = pd.Series(pvref.irradiance_w_m2, index=pvref.timestamps)
    source_name = meta.get("pv_conversion_source_file")
    aligned_name = "nasa_irradiance_aligned.csv"
    if not source_name and aligned_name in meta.get("profile_hashes_sha256", {}):
        source_name = aligned_name
    if dataset.pv_valid and source_name and source_name == Path(source_name).name and source_name in meta["source_hashes"]:
        source = pd.read_csv(dataset.folder / source_name)
        aligned_clock = (source.source_clock.eq(clock).all() if "source_clock" in source else
                         source_name == aligned_name and meta.get("solar_source_clock") == clock)
        if {"timestamp", "irradiance_w_m2"} <= set(source) and aligned_clock:
            series = source.set_index(pd.to_datetime(source.timestamp, errors="raise")).irradiance_w_m2
            if series.index.is_unique and series.index.tz is None:
                aligned = pd.to_numeric(series.reindex(times), errors="coerce")
                if np.isfinite(aligned).all() and (aligned >= 0).all():
                    study.source_irradiance = aligned
    select_default_history(study)
    stage(f"Demand and PV profiles validated: {len(times):,} aligned hourly timestamps")
    return study


def finish_report(result, metrics, context, started, started_clock):
    elapsed = perf_counter() - started
    simulation = context.get("Simulation settings", {})
    context["Approved fixed methodology"] = methodology_record(simulation.get("fleet_dispatch_mode"))
    context["Model reference"] = model_reference(context, getattr(result, "metadata", None))
    context["Run started (device clock)"] = started_clock
    context["Run finished (device clock)"] = datetime.now().astimezone().isoformat(timespec="seconds")
    context["Run duration (seconds)"] = f"{elapsed:.3f}"
    context["Run duration"] = format_duration(elapsed)
    return RunReport(result, metrics, context)


def effective_simulation(study, settings, optimization):
    simulation = replace(settings.simulation,
                         shedding_penalty_per_kwh=settings.economics.shedding_penalty_per_kwh,
                         curtailment_penalty_per_kwh=settings.economics.curtailment_penalty_per_kwh)
    if optimization:
        return with_terminal_policy(simulation, settings.economics)
    if settings.manual_bess:
        try:
            validate_annual_inputs(study.profiles.timestamps, settings.economics, study.profiles.dt_hours)
        except ValueError:
            return simulation  # Short technical runs retain their technical SOC settings.
        return with_terminal_policy(simulation, settings.economics)
    return simulation


def run_study(study: PreparedStudy, settings: RunSettings, optimization=False,
              stage=lambda message: None, progress=None) -> RunReport:
    started = perf_counter()
    started_clock = datetime.now().astimezone().isoformat(timespec="seconds")
    if progress is None:
        progress = getattr(stage, "progress", None)
    context = dict(study.context)
    context.update(study_information(study))
    context["Forecast model"] = study.forecast_info if study.input_mode == "forecast" else None
    from .study_session import runtime_provenance
    context["Runtime provenance"] = runtime_provenance()
    context["Numba readiness timing"] = settings.values.get("numba_readiness")
    simulation = effective_simulation(study, settings, optimization)
    settings = replace(settings, simulation=simulation)
    dispatch = settings.dispatch
    if isinstance(dispatch, ConstraintAwareDispatch):
        economics = settings.economics
        dispatch = ConstraintAwareDispatch(
            economics.grid_import_tariff_per_kwh, economics.grid_export_tariff_per_kwh,
            economics.shedding_penalty_per_kwh, economics.curtailment_penalty_per_kwh,
            "forecast inputs only" if study.input_mode == "forecast" else "historical perfect-foresight diagnostic")
        context["Dispatch"] = f"Constraint-aware (24h look-ahead) · {dispatch.source}"
        context["Dispatch policy"] = asdict(dispatch)
    else:
        context["Dispatch"] = "Idle diagnostic" if dispatch is None else "Explicit validation policy"
    context["Simulation settings"] = asdict(settings.simulation)
    context.update(dispatch_information(settings.simulation))
    context["Economic inputs"] = asdict(settings.economics)
    context["Annual capital recovery factor"] = annual_capital_recovery_factor(settings.economics)
    context["Settings controls"] = dict(settings.values)
    if not optimization:
        stage(f"Simulation started: {len(study.profiles.timestamps):,} hourly steps")
        dispatch = dispatch if settings.manual_bess else None
        if settings.manual_bess is None:
            context["Dispatch"] = "No BESS installed; configured dispatch is not applied"
            context["Fleet count"] = 0
        elif simulation.fleet_dispatch_mode == "daily_milp_dispatch":
            context["Dispatch"] = (
                f"Manual BESS · daily MILP dispatch {simulation.dispatch_horizon_hours} h look-ahead, "
                "daily SOC restoration and discharge-linked reactive power"
            )
        result = simulate_timeseries(study.network, study.profiles, simulation,
                                     settings.manual_bess, dispatch, progress=progress)
        metrics = evaluate_results(result, settings.economics, settings.manual_bess) if result.completed and result.converged else None
        stage(f"Simulation {'completed' if result.completed else 'ended early'}: "
              f"{len(result.steps):,}/{len(study.profiles.timestamps):,} hours in {perf_counter() - started:.2f} s")
        if metrics is not None and metrics.annual_total_cost is not None:
            stage("Annual economics calculated")
        if settings.manual_bess:
            context["Manual BESS"] = vars(settings.manual_bess)
        context["Dispatch timing"] = result.dispatch_timing
        if result.dispatch_timing:
            timing = result.dispatch_timing
            plan_time = timing.get('planning_seconds', timing.get('daily_milp_seconds',
                                               timing.get('predictive_lp_seconds', 0.0)))
            fbs_time = timing.get('dispatch_fbs_seconds', timing.get('fbs_seconds', 0.0))
            fbs_calls = timing.get('dispatch_fbs_trials', timing.get('fbs_calls', 0))
            stage(f"Dispatch scheduling {plan_time:.3f}s; trial FBS {fbs_time:.3f}s "
                  f"across {fbs_calls} calls")
            stage(f"Network correction {timing.get('correction_seconds',0.0):.3f}s across "
                  f"{timing.get('correction_hours',0)} hours; "
                  f"{timing.get('correction_fbs_trials',0)} FBS calls, "
                  f"{timing.get('correction_unresolved_hours',0)} unresolved hours")
        return finish_report(result, metrics, context, started, started_clock)
    validate_annual_inputs(study.profiles.timestamps, settings.economics, study.profiles.dt_hours)
    values = settings.values
    if dispatch is None:
        raise ValueError("Select an active BESS dispatch policy before optimization")
    strict = settings.simulation.fleet_dispatch_mode == "daily_milp_dispatch"
    legacy_efficiency = values.get("spin_dispatch_efficiency_percent", DEFAULT_DISPATCH_EFFICIENCY * 100) / 100
    eta_charge = values.get("charge_efficiency", legacy_efficiency) if strict else values["spin_eta_charge_percent"] / 100
    eta_discharge = values.get("discharge_efficiency", legacy_efficiency) if strict else values["spin_eta_discharge_percent"] / 100
    parameters = BESSParameters(eta_charge=eta_charge,
                               eta_discharge=eta_discharge,
                               soc_min=values["spin_soc_min_percent"] / 100,
                               soc_max=values["spin_soc_max_percent"] / 100,
                               soc_initial=values["spin_soc_initial_percent"] / 100)
    context["Fleet battery parameters"] = asdict(parameters)
    bounds = OptimizationBounds(tuple(values["allowed_buses"]),
                                size_catalog(values["spin_opt_power_min_kw"], values["spin_opt_power_max_kw"], values["spin_opt_power_step_kw"]),
                                size_catalog(values["spin_opt_energy_min_kwh"], values["spin_opt_energy_max_kwh"], values["spin_opt_energy_step_kwh"]),
                                min_duration_hours=values.get("spin_opt_duration_min_hours", 2.0),
                                max_duration_hours=values.get("spin_opt_duration_max_hours", 12.0))
    bounds.validate_network(study.network)
    evaluator = SimulationEvaluator(settings.economics, parameters, dispatch, settings.simulation)
    evaluator.progress = progress
    profiles = study.profiles
    if study.forecast_info:
        context["Forecast interval"] = f"{profiles.timestamps[0]} through {profiles.timestamps[-1]}"
        context["Forecast model"] = str(study.forecast_info)
    context["Search catalogs"] = (f"Power {bounds.power_ratings_kw}; energy {bounds.energy_capacities_kwh}; "
                                  f"duration {bounds.min_duration_hours:g}–{bounds.max_duration_hours:g} h; "
                                  f"{bounds.feasible_design_count()} feasible power/energy pairs per eligible bus")
    joint_sess = (values.get("spin_bess_units", 3) >= 1
                  and settings.simulation.fleet_dispatch_mode in ("opf", "daily_milp_dispatch"))
    algorithm = "GA" if joint_sess else values.get("optimizer_algorithm", "GWO")
    context["Optimizer algorithm"] = "Joint GA" if joint_sess else algorithm
    context["Compute backend"] = (f"{settings.simulation.fbs_config.backend}; "
                                  + ("Joint fleet genetic algorithm" if values.get("spin_bess_units", 3) >= 1
                                     and settings.simulation.fleet_dispatch_mode in ("opf", "daily_milp_dispatch")
                                     else algorithm))
    if settings.managed_search and joint_sess:
        policy = effective_joint_search(values)
        if not 8 <= policy.population <= 1000 or not 4 <= policy.generations <= 10000:
            raise ValueError("Set a population of 8–1,000 and a generation limit of 4–10,000")
        if not 1 <= policy.workers <= desktop_worker_limit():
            raise ValueError(f"Set 1–{desktop_worker_limit()} parallel workers on this PC")
        config = OptimizerConfig(
            population_size=policy.population, max_iterations=policy.generations,
            seed=policy.seed, workers=policy.workers,
            convergence_patience=policy.stall_generations,
            convergence_relative_tolerance=policy.relative_tolerance)
        annual_workers = policy.annual_workers
        annual_fallbacks = policy.annual_fallbacks
        crossover, mutation = policy.crossover, policy.mutation
        context["Effective Joint GA settings"] = asdict(policy)
        stage(f"Joint GA settings | population={policy.population}, maximum generations={policy.generations}, "
              f"parallel workers={policy.workers} | {len(bounds.allowed_bus_ids)} eligible buses")
    else:
        config = OptimizerConfig(
            population_size=(values.get("spin_ga_population", values.get("spin_gwo_population", 12))
                             if algorithm == "GA" else values["spin_gwo_population"]),
            max_iterations=(values.get("spin_ga_generations", values.get("spin_gwo_iterations", 20))
                            if algorithm == "GA" else values["spin_gwo_iterations"]),
            seed=values["spin_gwo_seed"],
            workers=values["spin_cpu_workers"] if joint_sess or algorithm == "GWO" else 1)
        annual_workers = values["spin_annual_workers"]
        annual_fallbacks = int(values.get("spin_lateral_annual_finalists", 3))
        crossover = float(values.get("spin_ga_crossover", 0.80))
        mutation = float(values.get("spin_ga_mutation", 0.20))
    if values.get("spin_bess_units", 3) >= 1:
        from .sequential_multi import optimize_sequential_multi
        from .feeder_aware import ImprovementRules
        from .optimizer import BESSCandidate
        maximum_units = int(values.get("spin_bess_units", 3))
        stage((f"Running Joint GA for up to {maximum_units} BESS units"
               if settings.simulation.fleet_dispatch_mode in ('opf','daily_milp_dispatch')
               else f"Running sequential GWO for up to {maximum_units} BESS units"))
        result, baseline_result, selected_series = optimize_sequential_multi(
            study.network, profiles, bounds, evaluator, config,
            max_units=maximum_units, stage=stage, progress=progress,
            annual_workers=annual_workers, finalists_per_stage=annual_fallbacks,
            ga_crossover_rate=crossover, ga_mutation_rate=mutation,
            improvement_rules=ImprovementRules(
                minimum_shedding_percent=float(values.get('spin_min_lateral_shedding_pct', 10.0)),
                minimum_voltage_percent=float(values.get('spin_min_lateral_voltage_pct', 10.0)),
                maximum_worsening_percent=float(values.get('spin_max_lateral_worsening_pct', 1.0)),
                exclude_installed_laterals=bool(values.get('chk_exclude_installed_laterals', False))))
        result.metadata["economic_configuration"] = asdict(settings.economics)
        result.metadata["bess_duration_constraint"] = {
            "minimum_hours": bounds.min_duration_hours, "maximum_hours": bounds.max_duration_hours,
            "definition": "nominal energy kWh / nominal active power kW",
            "feasible_pairs_per_bus": bounds.feasible_design_count()}
        result.metadata["simulation_window"] = dict(study.simulation_window)
        context["Selected BESS fleet"] = result.metadata["fleet"]
        context["Placement stages"] = result.metadata["stages"]
        context["Fleet count"] = len(result.metadata["fleet"])
        context["Dispatch"] = ("Daily MILP dispatch: binary daily charge/discharge/Q schedule, discharge-linked PF, "
                               "verified FBS and daily SOC closure" if strict else
                               "SESS independent P/Q inverter control with FBS verification")
        context["Dispatch policy"] = {"mode": settings.simulation.fleet_dispatch_mode,
                                      "multi_bess": True, "look_ahead_hours": (settings.simulation.dispatch_horizon_hours if strict else 72),
                                      "daily_soc_closure": strict,
                                      "minimum_pf": settings.simulation.minimum_discharge_pf if strict else None,
                                      "perfect_foresight_offline_test": True}
        context["Dispatch timing"] = selected_series.dispatch_timing
        report = finish_report(result, None, context, started, started_clock)
        baseline_metrics = evaluate_results(baseline_result, settings.economics, None)
        report.alternatives["no_bess"] = (baseline_result, baseline_metrics)
        if result.metadata["fleet"]:
            batteries = tuple(parameters.build_config(BESSCandidate(**candidate))
                              for candidate in result.metadata["fleet"])
            selected_metrics = evaluate_results(selected_series, settings.economics, batteries)
            if not selected_metrics.feasible or not isclose(selected_metrics.annual_total_cost, result.best_objective,
                                                      rel_tol=1e-9, abs_tol=1e-6):
                raise RuntimeError("Selected multi-BESS replay failed the final annual consistency check")
            report.alternatives["best_bess"] = (selected_series, selected_metrics)
        return report
    stage(f"Running {algorithm}")
    baseline_result = None
    if algorithm == "GA":
        result = genetic_optimize(study.network, profiles, bounds, evaluator, config,
                                  progress=progress,
                                  crossover_rate=values.get("spin_ga_crossover", 0.8),
                                  mutation_rate=values.get("spin_ga_mutation", 0.12))
    elif values.get("search_mode") in ("quick", "standard"):
        result, baseline_result = optimize_fast_verified(
            study.network, profiles, bounds, evaluator, config, mode=values["search_mode"],
            clock=study.context.get("Clock") or getattr(study.request, "clock", None),
            settings=values, stage=stage, progress=progress)
    else:
        result = optimize(study.network, profiles, bounds, evaluator, config, progress=progress)
        result.metadata["search_mode"] = "thorough full-year"
    result.metadata["objective_formula"] = ("annual_grid_cost + annual_shedding_cost + annual_curtailment_cost "
                                           "+ (initial_BESS_cost / lifetime_years) "
                                           "+ (initial_BESS_cost * annual_om_fraction)")
    result.metadata["bess_duration_constraint"] = {
        "minimum_hours": bounds.min_duration_hours, "maximum_hours": bounds.max_duration_hours,
        "definition": "nominal energy kWh / nominal active power kW",
        "feasible_pairs_per_bus": bounds.feasible_design_count()}
    result.metadata["capex_treatment"] = "upfront purchase displayed separately; annual capital and O&M included in GWO"
    result.metadata["bess_lifetime_years"] = settings.economics.lifetime_years
    result.metadata["annual_om_percent_of_capex"] = settings.economics.annual_om_fraction * 100
    result.metadata["best_bess_feasible"] = result.success
    result.metadata["best_bess_annual_cost"] = result.best_objective if result.success else None
    result.metadata["best_bess_candidate"] = asdict(result.best_candidate) if result.best_candidate else None
    result.metadata["feasible_bess_candidates"] = sum(item.feasible for item in result.evaluations)
    # A feasible no-storage system is an explicit economic alternative.
    if baseline_result is None:
        stage("Evaluating no-BESS annual baseline")
        baseline_started = perf_counter()
        baseline_result = simulate_timeseries(study.network, profiles,
                                             with_terminal_policy(settings.simulation, settings.economics),
                                             bess_config=None, dispatch_policy=None, progress=progress)
        result.metadata.setdefault("stage_wall_seconds", {})["baseline_seconds"] = perf_counter() - baseline_started
    baseline = None
    best_result = best_metrics = None
    if result.success and result.best_candidate:
        battery = parameters.build_config(result.best_candidate)
        stage("Replaying best evaluated feasible battery for hourly export")
        replay_started = perf_counter()
        best_result = simulate_timeseries(
            study.network, profiles, with_terminal_policy(settings.simulation, settings.economics),
            battery, dispatch, progress=progress, hourly_progress_only=True)
        if best_result.completed and best_result.converged:
            best_metrics = evaluate_results(best_result, settings.economics, battery)
        result.metadata.setdefault("stage_wall_seconds", {})["best_replay_seconds"] = perf_counter() - replay_started
        if (best_metrics is None or not best_metrics.feasible or best_metrics.annual_total_cost is None
                or not isclose(best_metrics.annual_total_cost, result.best_objective, rel_tol=1e-9, abs_tol=1e-6)):
            result.metadata["best_bess_replay_mismatch"] = (
                "Replay feasibility or annual cost differs from the optimizer evaluation")
            stage(result.metadata["best_bess_replay_mismatch"])
            result.success = False
            result.best_candidate = None
            result.best_objective = float("inf")
            result.metrics = None
            result.message = result.metadata["best_bess_replay_mismatch"]
            result.metadata["best_bess_feasible"] = False
            result.metadata["best_bess_annual_cost"] = None
        else:
            result.metrics = best_metrics
        context["Best BESS replay dispatch timing"] = best_result.dispatch_timing
    if baseline_result.completed and baseline_result.converged:
        baseline = evaluate_results(baseline_result, settings.economics, None)
        result.metadata["no_bess_feasible"] = baseline.feasible
        result.metadata["no_bess_annual_cost"] = baseline.annual_total_cost
        result.metadata["delta_annual_cost"] = (result.best_objective-baseline.annual_total_cost
            if baseline.feasible and baseline.annual_total_cost is not None and result.success else None)
        if baseline.feasible and baseline.annual_total_cost is not None and (
            not result.success or baseline.annual_total_cost <= result.best_objective):
            result.best_candidate = None
            result.best_objective = baseline.annual_total_cost
            result.metrics = baseline
            result.success = True
            if result.metadata["best_bess_feasible"]:
                result.message = "No BESS has lower or equal annual total cost including straight-line BESS ownership."
            else:
                count = len(result.evaluations)
                result.message = f"No BESS selected because none of the {count} evaluated batteries was feasible."
            result.metadata["no_bess_selected"] = True
            result.metadata["delta_annual_cost"] = 0.
    else:
        result.metadata["no_bess_feasible"] = False
    result.metadata["economic_configuration"] = asdict(settings.economics)
    result.metadata["simulation_window"] = dict(study.simulation_window)
    result.metadata["decision_message"] = result.message
    timing = {key: sum(item.execution_metadata.get(key, 0) for item in result.evaluations)
              for key in ("planning_seconds", "dispatch_fbs_seconds", "dispatch_fbs_trials", "correction_seconds",
                          "correction_fbs_trials", "correction_hours", "correction_unresolved_hours",
                          "fbs_calls", "lp_calls", "lp_seconds", "sensitivity_calls", "sensitivity_seconds",
                          "verified_linear_shortcuts", "candidate_elapsed_seconds", "candidate_cpu_seconds")}
    context["Candidate dispatch timing (summed across workers)"] = timing
    if timing["dispatch_fbs_trials"]:
        stage(f"Candidate scheduling {timing.get('planning_seconds', timing.get('daily_milp_seconds', 0.0)):.3f}s; trial FBS "
              f"{timing['dispatch_fbs_seconds']:.3f}s across {timing['dispatch_fbs_trials']} calls (worker totals)")
    if timing["correction_hours"]:
        stage(f"Candidate network correction {timing['correction_seconds']:.3f}s; "
              f"{timing['correction_fbs_trials']} FBS calls, {timing['correction_unresolved_hours']} unresolved hours (worker totals)")
    report = finish_report(result, None, context, started, started_clock)
    report.alternatives["no_bess"] = (baseline_result, baseline)
    if best_result is not None:
        report.alternatives["best_bess"] = (best_result, best_metrics)
    return report


def run_base_case(study: PreparedStudy, settings: RunSettings, stage=lambda message: None, progress=None):
    """Run one static FBS snapshot with original load/PV and inactive BESS."""
    stage("Running static base-case FBS (one snapshot; no hourly time steps)")
    if progress is None:
        progress = getattr(stage, "progress", None)
    ids = [bus.bus_id for bus in study.network.buses]
    loads = {bus_id: [load for load in study.network.loads if load.bus_id == bus_id] for bus_id in ids}
    pvs = {bus_id: [unit for unit in study.network.pv_units if unit.bus_id == bus_id] for bus_id in ids}
    point = OperatingPoint(
        {bus_id: sum(item.p_base_kw for item in loads[bus_id]) for bus_id in ids},
        {bus_id: sum(item.q_base_kvar for item in loads[bus_id]) for bus_id in ids},
        {bus_id: sum(item.p_rated_kw for item in pvs[bus_id]) for bus_id in ids},
        {bus_id: 0.0 for bus_id in ids}, {bus_id: 0.0 for bus_id in ids}, {bus_id: 0.0 for bus_id in ids},
    )
    result = run_fbs(study.network, point, settings.simulation.fbs_config, progress=progress)
    if progress is not None:
        progress(ProgressEvent("Base case", 1, 1,
                               f"Static snapshot | FBS iterations: {result.iterations} | converged={result.converged}",
                               log=True))
    context = {"Network": study.context["Network"], "Case definition": "Static base loads + installed PV ratings; BESS inactive (0 kW)", "Compute backend": settings.simulation.fbs_config.backend,
               "PV installations": study.context["PV ratings (kW)"]}
    context.update({key: study.context[key] for key in
                    ("Network SHA256", "Distributor network SHA256", "Workbook provenance") if key in study.context})
    from .study_session import runtime_provenance
    context["Runtime provenance"] = runtime_provenance()
    context["FBS settings"] = asdict(settings.simulation.fbs_config)
    context["Approved fixed methodology"] = methodology_record()
    context.update(study_information(study, static=True))
    context["Model reference"] = model_reference(context, kind="base case")
    step = StaticResultStep(
        timestamp="Static base case",
        operating_point=point,
        power_flow=result,
        shedding_by_bus_kw={bus_id: 0.0 for bus_id in ids},
        curtailment_by_bus_kw={bus_id: 0.0 for bus_id in ids},
    )
    return BaseCaseReport(result, context, step)


def export_report(report: RunReport, path, stage=lambda message: None):
    stage("Exporting retained results")
    return export_results(report.result, path, metrics=report.metrics, context=report.context)


def forecast_and_export(study, config, output, stage=lambda message: None, *, network_snapshot=None):
    from .study_session import _write_profile, write_input_snapshot

    history = study.historical_profiles or study.profiles
    report = generate_forecast(history, config, assignments=study.assignments,
                               network=study.network, pv_reference=study.pv_reference)
    if hasattr(stage, "begin_commit"):
        stage.begin_commit()
    stage("Saving forecast and training inputs")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    end = pd.Timestamp(report.historical_end) + pd.Timedelta(hours=1)
    training = history.slice(report.model_info["training_start"], end)
    write_input_snapshot(output, profiles=training, workbook=network_snapshot,
                         metadata={"source": "Forecast training history", "clock": study.context.get("Clock"),
                                   "dt_hours": training.dt_hours, "start": str(training.timestamps[0]),
                                   "end_exclusive": str(end), "hours": len(training.timestamps)})
    for kind in ("load", "pv"):
        _write_profile(output / f"{kind}_profile.csv", report.profiles.timestamps,
                       getattr(report.profiles, f"{kind}_p_kw"), getattr(report.profiles, f"{kind}_q_kvar"))
    pd.DataFrame({"timestamp": report.profiles.timestamps, **report.sector_predictions}).to_csv(
        output / "sector_predictions.csv", index=False)
    pd.DataFrame({"timestamp": report.profiles.timestamps, "capacity_factor": report.pv_capacity_factor}).to_csv(
        output / "pv_reference_forecast.csv", index=False)
    from .forecast_accuracy import save_comparison
    report.scores = {row['category']: row for row in save_comparison(
        output, history, report.profiles, study.assignments,
        training_end=report.historical_end)}
    return report, output


def _save_dashboard(output, study, settings, report, kind, stage, *, defer_html=False, **kwargs):
    from .dashboard import regenerate_dashboard, write_run_metadata
    try:
        if not defer_html:
            stage("Building offline results dashboard")
        # Holdout error metrics belong to the *actual* matching observations,
        # not to training history or invented future values.
        if study.input_mode == 'forecast' and study.forecast_profiles is not None:
            from .forecast_accuracy import save_comparison
            save_comparison(output, study.historical_profiles, study.profiles,
                            study.assignments,
                            training_end=(study.forecast_info or {}).get('training_ends'))
        write_run_metadata(output, study.network, kind, report.context, settings.simulation, **kwargs)
        if defer_html:
            # Persist metadata immediately; a dedicated GUI worker builds the
            # HTML after the simulation has been committed and the GUI is usable.
            stage("Numerical results and dashboard metadata saved")
        else:
            report.dashboard_path = regenerate_dashboard(output)
            stage("Dashboard ready: saved HTML report")
    except Exception as error:
        message = f"Dashboard generation failed after saving numerical results: {error}"
        stage(message)
        try:
            (Path(output) / "dashboard_error.txt").write_text(message, encoding="utf-8")
        except OSError:
            pass


def _save_numerical_run(study, report, optimization, output, network_snapshot, stage):
    started = perf_counter()
    output = Path(output)
    with TemporaryDirectory(prefix=".run-", dir=output.parent) as directory:
        pending = Path(directory) / output.name
        scenarios = _write_numerical_files(study, report, optimization, pending, network_snapshot)
        if output.exists():
            raise FileExistsError(f"Run directory already exists: {output}")
        pending.rename(output)
    report.context["Numerical export seconds"] = round(perf_counter() - started, 4)
    stage(f"Numerical results saved in {report.context['Numerical export seconds']:.3f} s")
    return scenarios


def _write_numerical_files(study, report, optimization, output, network_snapshot):
    label = "Manual BESS" if "Manual BESS" in report.context else "No BESS"
    config = report.context.get("Simulation settings") or {}
    bounds = (config["voltage_min_pu"], config["voltage_max_pu"]) if "voltage_min_pu" in config else None
    export_results(report.result, output, metrics=report.metrics, context={**report.context, "Alternative": label} if not optimization else report.context,
                   network=study.network, voltage_bounds=bounds,
                   input_snapshot={"profiles": study.profiles, "workbook": network_snapshot or getattr(study.request, "network_path", None),
                                   "metadata": {"clock": study.context.get("Clock"),
                                                "selected_network_sha256": study.context.get("Network SHA256"),
                                                "distributor_network_sha256": study.context.get("Distributor network SHA256"),
                                                "dt_hours": study.profiles.dt_hours,
                                                "window": study.simulation_window,
                                                "assignments": study.assignments, "site": study.dataset_metadata.get("site"),
                                                "clock_status":study.dataset_metadata.get("clock_status") or study.dataset_metadata.get("clock_provenance")}})
    if study.input_mode == "historical":
        weather = pd.DataFrame(index=pd.DatetimeIndex(study.profiles.timestamps, name="timestamp"))
        if study.source_irradiance is not None:
            weather["irradiance_w_m2"] = study.source_irradiance.reindex(weather.index)
        if study.pv_reference is not None:
            ref = study.pv_reference
            weather["reference_pv_kw"] = pd.Series(ref.p_kw, index=ref.timestamps).reindex(weather.index)
        if len(weather.columns):
            weather.to_csv(output / "inputs" / "solar_reference.csv")
    scenarios = {".": label}
    if optimization:
        scenarios = {}
        baseline_series = report.alternatives["no_bess"][0]
        for name, (series, metrics) in report.alternatives.items():
            label = ("No BESS" if name == "no_bess" else "Best evaluated feasible BESS")
            scenarios[name] = label
            export_results(series, output / name, metrics=metrics, network=study.network, voltage_bounds=bounds,
                           context={**report.context, "Alternative": label},
                           baseline_series=baseline_series if name == "best_bess" else None)
    return scenarios


def run_and_export(study, settings, optimization, output_path,
                   stage=lambda message: None, progress=None, *, network_snapshot=None,
                   defer_dashboard=False, session_root=None):
    """Run once and commit its numerical exports before the optional HTML."""
    report = run_study(study, settings, optimization, stage=stage, progress=progress)
    report.context["Run ID"] = str(uuid4())
    begin_commit = getattr(stage, "begin_commit", None)
    if begin_commit is not None:
        begin_commit()
    stage("Saving run in active session")
    output = Path(output_path)
    for attempt in range(2):
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            scenarios = _save_numerical_run(study, report, optimization, output, network_snapshot, stage)
            report.saved = True
            break
        except FileExistsError as error:
            report.persistence_warning = f"Numerical results are available in this window. {error}"
            break
        except OSError as error:
            if attempt == 0:
                stage(f"Retrying numerical export after a write error: {error}")
            else:
                report.persistence_warning = f"Numerical results are available in this window. Export failed: {error}"
    if not report.saved:
        stage(report.persistence_warning)
        return report
    _save_dashboard(output_path, study, settings, report, "optimization" if optimization else "simulation",
                    stage, defer_html=defer_dashboard,
                    scenarios=scenarios, optimizer=report.result.metadata if optimization else None)
    if session_root is not None:
        # Durable commit belongs to the worker and is NOT conditional on Qt's
        # final QThread handoff (a failure mode observed in V13/V14.1).
        from .study_session import StudySession
        try:
            session = StudySession.open_for_updates(session_root)
            session.record_run(output_path, optimization, report)
            stage("Run registered in session manifest")
        except (OSError, ValueError, TypeError) as error:
            report.persistence_warning = f"Numerical results saved in {output}. Session registration failed: {error}"
            stage(report.persistence_warning)
    return report


def regenerate_saved_dashboard(output_path, stage=lambda message: None):
    """Run on a separate GUI worker AFTER the numerical job is committed."""
    from .dashboard import regenerate_dashboard
    stage("Building offline results dashboard")
    path = regenerate_dashboard(output_path)
    stage("Dashboard ready: saved HTML report")
    return path


def run_base_case_and_export(study, settings, output_path, stage=lambda message: None, progress=None,
                             *, network_snapshot=None):
    report = run_base_case(study, settings, stage=stage, progress=progress)
    report.context["Run ID"] = str(uuid4())
    if hasattr(stage, "begin_commit"):
        stage.begin_commit()
    output = Path(output_path)
    output.mkdir(parents=True, exist_ok=False)
    from .study_session import write_input_snapshot
    write_input_snapshot(output, point=report.step.operating_point, workbook=network_snapshot or getattr(study.request, "network_path", None),
                         metadata={"source": "Static base case", "selected_network_sha256": study.context.get("Network SHA256"),
                                   "distributor_network_sha256": study.context.get("Distributor network SHA256")})
    rows = [{"bus_id": bus_id, "voltage_pu": voltage, "voltage_angle_deg":report.result.voltage_angle_deg[bus_id],
             "converged": report.result.converged}
            for bus_id, voltage in sorted(report.result.voltage_mag_pu.items())]
    pd.DataFrame(rows).to_csv(output / "bus_voltages.csv", index=False)
    from .electrical_details import branch_readings, line_ends
    ends = line_ends(study.network)
    lines = {line.line_id: line for line in study.network.lines}
    pd.DataFrame([{"line_id": line_id, "p_kw": report.result.branch_p_kw[line_id], "converged": report.result.converged,
                   **branch_readings(report.result, lines[line_id], ends[line_id]),
                   "loss_q_kvar": report.result.line_loss_q_kvar[line_id],
                   "q_kvar": report.result.branch_q_kvar[line_id],
                   "current_a": report.result.branch_current_a[line_id],
                   "loss_kw": report.result.line_loss_p_kw[line_id]}
                  for line_id in report.result.branch_p_kw]).to_csv(output / "line_flows.csv", index=False)
    (output / "summary.txt").write_text(report.summary(detailed=True), encoding="utf-8")
    flow = report.result
    _save_dashboard(output, study, settings, report, "base case", stage,
                    snapshot={"timestamp": "Static base case", "converged": flow.converged,
                              "voltage_min_pu": min(flow.voltage_mag_pu.values(), default=None),
                              "voltage_max_pu": max(flow.voltage_mag_pu.values(), default=None),
                              "slack_p_kw": flow.slack_p_kw, "slack_q_kvar": flow.slack_q_kvar,
                              "loss_p_kw": flow.total_loss_p_kw, "fbs_iterations": flow.iterations,
                              "fbs_message": flow.message})
    return report
