"""UI-neutral preparation/run orchestration; the numerical modules own physics."""
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from io import StringIO
from hashlib import sha256
from math import isfinite
from pathlib import Path
from time import perf_counter

import pandas as pd

from .bess import BESSConfig
from .data_loader import ProfileData
from .fbs import OperatingPoint, run_fbs
from .forecasting import generate_forecast
from .load_generator import LoadGenerationConfig, generate_load_profile
from .metrics import EconomicConfig, evaluate_results, validate_annual_inputs, with_terminal_policy
from .network_loader import load_network
from .network_model import NetworkModel, PVUnit
from .optimizer import BESSParameters, OptimizationBounds, OptimizerConfig, SimulationEvaluator, optimize, genetic_optimize
from .pv_model import PVModelConfig, make_pv_profile, read_irradiance, irradiance_to_power, read_nasa_csv
from .distributed_dataset import load_distributed
from .solar_source import SolarSite, PVReference, reference_from_file, fetch_irradiance
import numpy as np
import json
from .results import export_results, format_summary
from .simulation import GridAwareDispatchPolicy, SimulationConfig, simulate_timeseries
from .progress import ProgressEvent, format_duration


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
    dispatch: object | None = None


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


def _read_power_csv(path, times, network, kind):
    if path is None:
        raise ValueError(f"Choose a prepared {kind} CSV")
    frame = pd.read_csv(path, encoding="utf-8-sig")
    columns = ["timestamp", "bus_id", "p_kw", "q_kvar"]
    if not set(columns).issubset(frame.columns):
        raise ValueError(f"{kind} CSV requires {', '.join(columns)}")
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
    stage("Reading network")
    network = load_network(request.network_path, workbook_format=request.workbook_format,
                           frequency_hz=request.frequency_hz)
    if request.load_source == "distributed":
        return _prepare_distributed(request,network,stage)
    # Imported CSV timestamps are the authority: no study-window settings.
    # A synthetic-only load has no timestamps to infer, so the preparation
    # interface requires a dated imported load CSV in this application mode.
    if request.load_source != "imported" or request.load_path is None:
        raise ValueError("Select an imported hourly load CSV to infer the study interval")
    stage("Detecting hourly timestamps from load CSV")
    timeline = pd.read_csv(request.load_path, usecols=["timestamp"], encoding="utf-8-sig")
    times = pd.DatetimeIndex(pd.to_datetime(timeline["timestamp"], format="ISO8601", errors="raise").unique()).sort_values()
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
        pv = _read_power_csv(request.pv_path, times, network, "PV")
    elif request.pv_source == "none":
        pv = pd.DataFrame({"timestamp": times, "bus_id": network.slack_bus_id(), "p_kw": 0.0, "q_kvar": 0.0})
    elif request.pv_source in ("open_meteo", "nasa_power", "prepared"):
        if request.pv_path is None or not network.pv_units:
            raise ValueError("Irradiance conversion needs a source CSV and explicit PV installations")
        weather = read_irradiance(request.pv_path, source=request.pv_source)
        weather = weather[weather.timestamp.isin(times)].reset_index(drop=True)
        if not pd.DatetimeIndex(weather.timestamp).equals(times):
            raise ValueError("Irradiance source does not cover every requested study hour")
        pv = make_pv_profile(network, weather, PVModelConfig(request.critical_irradiance, request.standard_irradiance))
    else:
        raise ValueError("Unsupported PV input mode")
    stage("Preparing load profile")
    if request.load_source == "synthetic":
        demand = generate_load_profile(network, times, LoadGenerationConfig(seed=request.load_seed))
    elif request.load_source == "imported":
        demand = _read_power_csv(request.load_path, times, network, "load")
    else:
        raise ValueError("Unsupported load input mode")
    stage("Checking prepared profiles")
    profiles = ProfileData(StringIO(demand.to_csv(index=False)), StringIO(pv.to_csv(index=False)))
    network_label = "Guide 5-Bus radial test" if len(network.buses) == 5 else f"{len(network.buses)}-bus radial network"
    context = {
        "Network": network_label,
        "PV source": "No PV" if request.pv_source == "none" else request.pv_source.replace("_", " "),
        "Demand": f"Synthetic load; seed {request.load_seed}" if request.load_source == "synthetic" else "Imported load profile",
        "History interval": f"{start.isoformat()} to {end.isoformat()} (exclusive); {len(times)} hours",
        "Study scope": "Complete timestamps inferred from imported load CSV",
        "Clock": "Source clock preserved; NASA LST is not automatically converted to civil time",
        "PV ratings (kW)": str({unit.pv_id: unit.p_rated_kw for unit in network.pv_units}),
        "Preparation": "GHI proxy if converting; no temperature/inverter model; synthetic load has no seasonality",
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
    return study


def _prepare_distributed(request, network, stage):
    stage("Validating GoiEner case, assignments and historical profiles")
    if request.dataset_folder is None:
        raise ValueError("Choose a GoiEner distributed case folder")
    dataset = load_distributed(request.dataset_folder,network,request.network_path,request.clock)
    meta = dataset.metadata
    clock = meta.get("clock")
    if not clock:
        raise ValueError("Dataset clock is unspecified; enter the actual IANA/UTC source clock before import")
    workbook_ratings = {}
    for unit in network.pv_units:
        if unit.p_rated_kw > 0:
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
    if sum(ratings.values()) > 0:
        if request.pv_source == "dataset" and not dataset.pv_valid:
            raise ValueError("The study folder has no usable PV history. Enable Use fallback solar source or choose No PV study.")
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
                pvref = PVReference(times,power,capacity,site,{"sources":sources,"conversion":asdict(conversion),"clock":"UTC converted to load clock"})
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
    context = {"Network":f"{len(ids)}-bus radial network","Network SHA256":sha256(Path(request.network_path).read_bytes()).hexdigest(),
        "Load source SHA256":meta["source_hashes"]["load_profile.csv"],
        "PV source": ("None" if pvref is None else "Validated dataset history" if dataset.pv_valid else request.pv_source),
        "PV source provenance": pvref.provenance if pvref else None,
        "PV ratings (kW)":str(ratings), "Workbook PV ratings (kW)":str(workbook_ratings),
        "Folder PV ratings (kW)":str(dataset.ratings),
        "PV rating selection": ("No PV" if request.pv_source == "none" else
            (request.pv_rating_selection or "Explicit override") if request.pv_override else
            "Workbook" if workbook_ratings else "Dataset folder"),
        "Demand":"GoiEner distributed sector assignments", "Dataset folder":str(dataset.folder),
        "History interval":f"{times[0]} through {times[-1]}; {len(times)} hours", "Clock":clock,
        "Classification disclaimer":meta.get("sector_assignment_status","Explicit user scenario; not observed customer labels"),
        "Dataset provenance":json.dumps(meta),"PV history validation":dataset.pv_reason}
    study = PreparedStudy(network,raw,request,context,historical_profiles=raw,assignments=dataset.assignments,
                          dataset_metadata=meta,pv_reference=pvref)
    select_default_history(study)
    return study


def finish_report(result, metrics, context, started, started_clock):
    elapsed = perf_counter() - started
    context["Run started (device clock)"] = started_clock
    context["Run finished (device clock)"] = datetime.now().astimezone().isoformat(timespec="seconds")
    context["Run duration (seconds)"] = f"{elapsed:.3f}"
    context["Run duration"] = format_duration(elapsed)
    return RunReport(result, metrics, context)


def run_study(study: PreparedStudy, settings: RunSettings, optimization=False,
              stage=lambda message: None, progress=None) -> RunReport:
    started = perf_counter()
    started_clock = datetime.now().astimezone().isoformat(timespec="seconds")
    if progress is None:
        progress = getattr(stage, "progress", None)
    context = dict(study.context)
    context["Active input source"] = study.input_mode
    context["Simulation interval"] = dict(study.simulation_window)
    context["Forecast model"] = study.forecast_info if study.input_mode == "forecast" else None
    from .study_session import runtime_provenance
    context["Runtime provenance"] = runtime_provenance()
    context["Numba readiness timing"] = settings.values.get("numba_readiness")
    context["Dispatch"] = ("Idle (diagnostic only)" if settings.dispatch is None
         else f"Grid-aware rule-based dispatch; import cap {settings.dispatch.import_limit_kw} kW")
    context["Simulation settings"] = str(asdict(settings.simulation))
    context["Economic inputs"] = asdict(settings.economics)
    context["Settings controls"] = dict(settings.values)
    if not optimization:
        stage("Running hourly simulation")
        dispatch = settings.dispatch if settings.manual_bess else None
        if settings.manual_bess is None:
            context["Dispatch"] = "No BESS installed; configured dispatch is not applied"
        simulation = settings.simulation
        if settings.manual_bess:
            try:
                validate_annual_inputs(study.profiles.timestamps, settings.economics, study.profiles.dt_hours)
            except ValueError:
                pass  # Short technical runs use the optional technical SOC setting.
            else:
                simulation = with_terminal_policy(simulation, settings.economics)
        context["Simulation settings"] = str(asdict(simulation))
        result = simulate_timeseries(study.network, study.profiles, simulation,
                                     settings.manual_bess, dispatch, progress=progress)
        metrics = evaluate_results(result, settings.economics, settings.manual_bess) if result.completed and result.converged else None
        if settings.manual_bess:
            context["Manual BESS"] = str(vars(settings.manual_bess))
        return finish_report(result, metrics, context, started, started_clock)
    validate_annual_inputs(study.profiles.timestamps, settings.economics, study.profiles.dt_hours)
    values = settings.values
    context["Optimization settings"] = str(values)
    if settings.dispatch is None:
        raise ValueError("Select an active BESS dispatch policy before optimization")
    parameters = BESSParameters(eta_charge=values["spin_eta_charge_percent"] / 100,
                               eta_discharge=values["spin_eta_discharge_percent"] / 100,
                               soc_min=values["spin_soc_min_percent"] / 100,
                               soc_max=values["spin_soc_max_percent"] / 100,
                               soc_initial=values["spin_soc_initial_percent"] / 100)
    bounds = OptimizationBounds(tuple(values["allowed_buses"]),
                                size_catalog(values["spin_opt_power_min_kw"], values["spin_opt_power_max_kw"], values["spin_opt_power_step_kw"]),
                                size_catalog(values["spin_opt_energy_min_kwh"], values["spin_opt_energy_max_kwh"], values["spin_opt_energy_step_kwh"]))
    bounds.validate_network(study.network)
    evaluator = SimulationEvaluator(settings.economics, parameters, settings.dispatch, settings.simulation)
    evaluator.progress = progress
    profiles = study.profiles
    if study.forecast_info:
        context["Forecast interval"] = f"{profiles.timestamps[0]} through {profiles.timestamps[-1]}"
        context["Forecast model"] = str(study.forecast_info)
    context["Search catalogs"] = f"Power {bounds.power_ratings_kw}; energy {bounds.energy_capacities_kwh}; endpoint-inclusive grid"
    algorithm = values.get("optimizer_algorithm", "GWO")
    context["Compute backend"] = f"{settings.simulation.fbs_config.backend}; {algorithm}"
    config = OptimizerConfig(
        population_size=(values.get("spin_ga_population", values["spin_gwo_population"])
                         if algorithm == "GA" else values["spin_gwo_population"]),
        max_iterations=(values.get("spin_ga_generations", values["spin_gwo_iterations"])
                        if algorithm == "GA" else values["spin_gwo_iterations"]),
        seed=values["spin_gwo_seed"], workers=values["spin_cpu_workers"] if algorithm == "GWO" else 1)
    stage(f"Running {algorithm}")
    if algorithm == "GA":
        result = genetic_optimize(study.network, profiles, bounds, evaluator, config,
                                  progress=progress,
                                  crossover_rate=values.get("spin_ga_crossover", 0.8),
                                  mutation_rate=values.get("spin_ga_mutation", 0.12))
    else:
        result = optimize(study.network, profiles, bounds, evaluator, config, progress=progress)
    result.metadata["best_bess_feasible"] = result.success
    result.metadata["best_bess_annual_cost"] = result.best_objective if result.success else None
    result.metadata["feasible_bess_candidates"] = sum(item.feasible for item in result.evaluations)
    result.metadata["reserve_rejected_bess_candidates"] = sum(
        not item.feasible and item.metrics is not None and (item.metrics.reserve_violation_hours or 0) > 0
        for item in result.evaluations
    )
    # A feasible no-storage system is an explicit economic alternative.
    stage("Evaluating no-BESS annual baseline")
    baseline_result = simulate_timeseries(study.network, profiles, settings.simulation,
                                         bess_config=None, dispatch_policy=None, progress=progress)
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
                result.message = "No BESS costs less than or the same as the best feasible battery."
            else:
                count = len(result.evaluations)
                reserve = result.metadata["reserve_rejected_bess_candidates"]
                result.message = f"No BESS selected because none of the {count} evaluated batteries was feasible."
                if reserve:
                    result.message += f" {reserve} had reserve violations."
            result.metadata["no_bess_selected"] = True
            result.metadata["delta_annual_cost"] = 0.
    else:
        result.metadata["no_bess_feasible"] = False
    result.metadata["economic_configuration"] = asdict(settings.economics)
    result.metadata["simulation_window"] = dict(study.simulation_window)
    return finish_report(result, None, context, started, started_clock)


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
    from .study_session import runtime_provenance
    context["Runtime provenance"] = runtime_provenance()
    context["FBS settings"] = asdict(settings.simulation.fbs_config)
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
    return report, output


def run_and_export(study, settings, optimization, output_path,
                   stage=lambda message: None, progress=None, *, network_snapshot=None):
    """Run once and save the retained result inside the active session."""
    report = run_study(study, settings, optimization, stage=stage, progress=progress)
    stage("Saving run in active session")
    export_results(report.result, output_path, metrics=report.metrics, context=report.context,
                   input_snapshot={"profiles": study.profiles, "workbook": network_snapshot,
                                   "metadata": {"clock": study.context.get("Clock"),
                                                "dt_hours": study.profiles.dt_hours,
                                                "window": study.simulation_window}})
    return report


def run_base_case_and_export(study, settings, output_path, stage=lambda message: None, progress=None,
                             *, network_snapshot=None):
    report = run_base_case(study, settings, stage=stage, progress=progress)
    output = Path(output_path)
    output.mkdir(parents=True, exist_ok=False)
    from .study_session import write_input_snapshot
    write_input_snapshot(output, point=report.step.operating_point, workbook=network_snapshot,
                         metadata={"source": "Static base case"})
    rows = [{"bus_id": bus_id, "voltage_pu": voltage}
            for bus_id, voltage in sorted(report.result.voltage_mag_pu.items())]
    pd.DataFrame(rows).to_csv(output / "bus_voltages.csv", index=False)
    pd.DataFrame([{"line_id": line_id, "p_kw": report.result.branch_p_kw[line_id],
                   "q_kvar": report.result.branch_q_kvar[line_id],
                   "current_a": report.result.branch_current_a[line_id],
                   "loss_kw": report.result.line_loss_p_kw[line_id]}
                  for line_id in report.result.branch_p_kw]).to_csv(output / "line_flows.csv", index=False)
    (output / "summary.txt").write_text(report.summary(detailed=True), encoding="utf-8")
    return report
