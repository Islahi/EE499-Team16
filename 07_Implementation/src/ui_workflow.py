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
from .dispatch import NetLoadTargetPolicy
from .load_generator import LoadGenerationConfig, generate_load_profile
from .metrics import EconomicConfig, evaluate_results
from .network_loader import load_network
from .network_model import NetworkModel, PVUnit
from .optimizer import BESSParameters, OptimizationBounds, OptimizerConfig, SimulationEvaluator, optimize
from .pv_model import PVModelConfig, make_pv_profile, read_irradiance
from .results import export_results, format_summary
from .simulation import SimulationConfig, simulate_timeseries
from .progress import format_duration


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


@dataclass
class PreparedStudy:
    network: NetworkModel
    profiles: ProfileData
    request: DataRequest
    context: dict[str, str]


@dataclass
class RunSettings:
    simulation: SimulationConfig
    economics: EconomicConfig
    manual_bess: BESSConfig | None
    values: dict
    dispatch: NetLoadTargetPolicy | None = None


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
    if not isinstance(request.months, int) or isinstance(request.months, bool) or request.months < 1:
        raise ValueError("Study months must be a positive integer")
    start = pd.Timestamp(request.start)
    if pd.isna(start) or start.tzinfo is not None or start.minute or start.second or start.microsecond or start.nanosecond:
        raise ValueError("Study start must be an exact hour in one timezone-naive source clock")
    end = start + pd.DateOffset(months=request.months)
    times = pd.date_range(start, end, inclusive="left", freq="h")
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
    context = {
        "Network": str(Path(request.network_path).resolve()),
        "PV source": f"{request.pv_source}: {request.pv_path}",
        "Demand": f"Literature-based synthetic demand; seed {request.load_seed}; not measured" if request.load_source == "synthetic" else str(request.load_path),
        "History interval": f"{start.isoformat()} to {end.isoformat()} (exclusive); {len(times)} hours",
        "Study scope": "Calendar-month study",
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
    return PreparedStudy(network, profiles, request, context)


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
    context["Dispatch"] = "Idle (diagnostic only)" if settings.dispatch is None else f"Net-load target {settings.dispatch.target_kw:g} kW; may charge from grid"
    context["Simulation settings"] = str(asdict(settings.simulation))
    context["Economic inputs"] = str(asdict(settings.economics))
    if not optimization:
        stage("Running hourly simulation")
        dispatch = settings.dispatch if settings.manual_bess else None
        if settings.manual_bess is None:
            context["Dispatch"] = "No BESS installed; configured dispatch is not applied"
        result = simulate_timeseries(study.network, study.profiles, settings.simulation,
                                     settings.manual_bess, dispatch, progress=progress)
        metrics = evaluate_results(result, settings.economics, settings.manual_bess) if result.completed and result.converged else None
        if settings.manual_bess:
            context["Manual BESS"] = str(vars(settings.manual_bess))
        return finish_report(result, metrics, context, started, started_clock)
    values = settings.values
    context["Optimization and scenario settings"] = str(values)
    if settings.dispatch is None:
        raise ValueError("Select net-load target dispatch before optimization")
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
    if values["group_uncertainty"]:
        from .uncertainty import UncertaintyConfig, SelectionConfig, ScenarioEvaluator, generate_scenarios, select_scenarios
        stage("Fitting ARIMA and generating scenarios")
        ratings = {bus: sum(unit.p_rated_kw for unit in study.network.pv_units if unit.bus_id == bus) for bus in profiles.pv_p_kw}
        generated = generate_scenarios(profiles, UncertaintyConfig(
            forecast_hours=values["spin_forecast_hours"], pv_capacity_kw=ratings,
            scenario_count=values["spin_scenario_count"], seed=values["spin_uncertainty_seed"]), progress=progress)
        stage("Selecting stress scenarios")
        profiles = select_scenarios(generated, SelectionConfig(
            best_count=values["spin_best_count"], worst_count=values["spin_worst_count"],
            random_count=values["spin_random_count"], seed=values["spin_selection_seed"]))
        evaluator = ScenarioEvaluator(evaluator, progress=progress)
        scenario_times = profiles.scenarios[0].profiles.timestamps
        context["Forecast interval"] = f"{scenario_times[0]} through {scenario_times[-1]}; equal-weight stress portfolio"
    context["Search catalogs"] = f"Power {bounds.power_ratings_kw}; energy {bounds.energy_capacities_kwh}; endpoint-inclusive grid"
    stage("Running GWO")
    result = optimize(study.network, profiles, bounds, evaluator, OptimizerConfig(
        population_size=values["spin_gwo_population"], max_iterations=values["spin_gwo_iterations"], seed=values["spin_gwo_seed"]), progress=progress)
    return finish_report(result, None, context, started, started_clock)


def export_report(report: RunReport, path, stage=lambda message: None):
    stage("Exporting retained results")
    return export_results(report.result, path, metrics=report.metrics, context=report.context)
