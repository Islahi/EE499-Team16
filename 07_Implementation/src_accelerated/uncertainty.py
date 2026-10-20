"""Hourly ARIMA paths, stress selection and GWO evaluation. See README_uncertainty.md."""
import csv
from dataclasses import dataclass, field, replace
from io import StringIO
from math import isfinite, sqrt
from numbers import Real
from random import Random
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA

from .data_loader import ProfileData
from .optimizer import BESSCandidate, CandidateEvaluation, SimulationEvaluator
from .progress import ProgressEvent


def _check_integer(value, name, minimum=0):
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _check_number(value, name, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError(f"{name} must be finite")
    if nonnegative and value < 0:
        raise ValueError(f"{name} must be nonnegative")


@dataclass
class UncertaintyConfig:
    forecast_hours: int
    pv_capacity_kw: dict[int, float]
    scenario_count: int = 100
    seed: int = 42
    arima_order: tuple[int, int, int] = (1, 0, 0)
    validation_hours: int = 24
    model_mode: str = "automatic"

    def __post_init__(self):
        _check_integer(self.forecast_hours, "forecast_hours", 2)
        _check_integer(self.scenario_count, "scenario_count", 1)
        _check_integer(self.seed, "seed")
        _check_integer(self.validation_hours, "validation_hours", 1)
        self.arima_order = tuple(self.arima_order)
        if len(self.arima_order) != 3:
            raise ValueError("arima_order must contain p, d and q")
        for value in self.arima_order:
            _check_integer(value, "ARIMA order")
        if self.model_mode not in ("automatic", "arima", "bootstrap"):
            raise ValueError("model_mode must be automatic, arima or bootstrap")
        self.pv_capacity_kw = dict(self.pv_capacity_kw)
        for bus_id, capacity in self.pv_capacity_kw.items():
            _check_integer(bus_id, "PV bus ID")
            _check_number(capacity, "PV capacity", nonnegative=True)


@dataclass(frozen=True)
class SelectionConfig:
    best_count: int = 15
    worst_count: int = 15
    random_count: int = 15
    seed: int = 42

    def __post_init__(self):
        for name in ("best_count", "worst_count", "random_count", "seed"):
            _check_integer(getattr(self, name), name)
        if self.best_count + self.worst_count + self.random_count == 0:
            raise ValueError("Select at least one scenario")


def _validate_profiles(profiles):
    if not isinstance(profiles, ProfileData):
        raise TypeError("Use the existing ProfileData object")
    if len(profiles.timestamps) < 2 or profiles.dt_hours != 1.0:
        raise ValueError("Scenarios require at least two hourly timestamps")
    times = [pd.Timestamp(value) for value in profiles.timestamps]
    if any(pd.isna(value) for value in times):
        raise ValueError("Profile timestamps cannot be missing")
    if any(times[i] - times[i - 1] != pd.Timedelta(hours=1) for i in range(1, len(times))):
        raise ValueError("Profile timestamps must be continuous and hourly")
    for active, reactive in ((profiles.load_p_kw, profiles.load_q_kvar),
                             (profiles.pv_p_kw, profiles.pv_q_kvar)):
        if not active or set(active) != set(reactive):
            raise ValueError("Each profile needs matching active/reactive bus keys")
        for bus_id, values in active.items():
            _check_integer(bus_id, "Profile bus ID")
            if len(values) != len(times) or len(reactive[bus_id]) != len(times):
                raise ValueError("Each bus needs one P and Q value per timestamp")
            for p_kw, q_kvar in zip(values, reactive[bus_id]):
                _check_number(p_kw, "Profile P", nonnegative=True)
                _check_number(q_kvar, "Profile Q")
                if p_kw == 0 and q_kvar != 0:
                    raise ValueError("Uncertainty Q/P scaling requires zero Q when P is zero")


@dataclass
class Scenario:
    scenario_id: str
    profiles: ProfileData
    probability: float | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class ScenarioSet:
    scenarios: list[Scenario]
    metadata: dict[str, object] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.scenarios:
            raise ValueError("ScenarioSet must not be empty")
        ids = set()
        reference = self.scenarios[0].profiles
        for scenario in self.scenarios:
            if not isinstance(scenario.scenario_id, str) or not scenario.scenario_id.strip():
                raise ValueError("Scenario IDs must be nonempty strings")
            if scenario.scenario_id in ids:
                raise ValueError("Scenario IDs must be unique")
            ids.add(scenario.scenario_id)
            _validate_profiles(scenario.profiles)
            if scenario.probability is not None:
                _check_number(scenario.probability, "Scenario probability", nonnegative=True)
                if scenario.probability > 1:
                    raise ValueError("Scenario probability cannot exceed one")
            if (list(scenario.profiles.timestamps) != list(reference.timestamps)
                    or set(scenario.profiles.load_p_kw) != set(reference.load_p_kw)
                    or set(scenario.profiles.pv_p_kw) != set(reference.pv_p_kw)):
                raise ValueError("Scenarios must share timestamps and bus keys")


@dataclass
class _SeriesModel:
    hourly_p: np.ndarray
    hourly_q_ratio: np.ndarray
    scale: float
    fitted: object
    capacity_kw: float | None
    fit_warnings: list[str]
    residual_pool: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    model_name: str = "ARIMA"
    fit_status: str = "converged"

    def restore(self, residuals, times):
        hours = np.array([pd.Timestamp(time).hour for time in times])
        baseline = self.hourly_p[hours]
        values = baseline + self.scale * residuals
        if not np.isfinite(values).all():
            raise ValueError("ARIMA produced non-finite power; check history and order")
        values = np.maximum(values, 0.0)
        if self.capacity_kw is not None:
            # Treat floating-point traces (e.g. sin(pi)) as numerical zero too.
            dark = baseline <= 1e-10 * max(self.capacity_kw, 1.0)
            values[dark] = 0.0
            values = np.minimum(values, self.capacity_kw)
        return values


def _series_parts(p_values, q_values, times):
    hours = np.array([pd.Timestamp(time).hour for time in times])
    active = np.asarray(p_values, dtype=float)
    reactive = np.asarray(q_values, dtype=float)
    hourly_p = np.zeros(24)
    hourly_q_ratio = np.zeros(24)
    for hour in range(24):
        mask = hours == hour
        if not mask.any():
            raise ValueError("Training history must cover all 24 hours of the day")
        hourly_p[hour] = active[mask].mean()
        if active[mask].sum() > 0:
            hourly_q_ratio[hour] = reactive[mask].sum() / active[mask].sum()
    if not np.isfinite(hourly_q_ratio).all():
        raise ValueError("Historical hourly Q/P ratios are not finite")
    scale = max(float(active.mean()), 1.0)
    residuals = (active - hourly_p[hours]) / scale
    return active, hourly_p, hourly_q_ratio, scale, residuals


def _bootstrap_series(p_values, q_values, times, capacity_kw, warning=""):
    active, hourly_p, hourly_q_ratio, scale, residuals = _series_parts(
        p_values, q_values, times,
    )
    warnings_list = [warning] if warning else []
    return _SeriesModel(
        hourly_p=hourly_p, hourly_q_ratio=hourly_q_ratio, scale=scale,
        fitted=None, capacity_kw=capacity_kw, fit_warnings=warnings_list,
        residual_pool=np.asarray(residuals, dtype=float),
        model_name="hourly_residual_bootstrap", fit_status="fallback",
    )


def _fit_series(p_values, q_values, times, order, capacity_kw):
    active, hourly_p, hourly_q_ratio, scale, residuals = _series_parts(
        p_values, q_values, times,
    )
    fitted = None
    fit_warnings = []
    if np.max(np.abs(residuals)) > 1e-10:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fitted = ARIMA(residuals, order=order, trend="n").fit(method_kwargs={"maxiter": 200})
        fit_warnings = sorted({str(item.message) for item in caught})
        if not fitted.mle_retvals.get("converged", False):
            raise ValueError("ARIMA fit did not converge; check data or change arima_order")
        if not np.isfinite(fitted.params).all():
            raise ValueError("ARIMA fitted non-finite parameters")
    model_name = "ARIMA" if fitted is not None else "deterministic_hourly_pattern"
    return _SeriesModel(
        hourly_p=hourly_p, hourly_q_ratio=hourly_q_ratio, scale=scale,
        fitted=fitted, capacity_kw=capacity_kw, fit_warnings=fit_warnings,
        residual_pool=np.asarray(residuals, dtype=float), model_name=model_name,
        fit_status="converged" if fitted is not None else "not_required",
    )


def _fit_with_mode(p_values, q_values, times, order, capacity_kw, mode):
    if mode == "bootstrap":
        return _bootstrap_series(p_values, q_values, times, capacity_kw)
    try:
        return _fit_series(p_values, q_values, times, order, capacity_kw)
    except ValueError as error:
        if mode == "arima":
            raise
        return _bootstrap_series(
            p_values, q_values, times, capacity_kw,
            f"ARIMA rejected: {error}; using hourly residual bootstrap",
        )


def _forecast_series(model, times):
    residuals = np.zeros(len(times))
    if model.fitted is not None:
        residuals = np.asarray(model.fitted.forecast(steps=len(times)), dtype=float)
    return model.restore(residuals, times)


def _forecast_errors(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    errors = actual - np.asarray(predicted, dtype=float)
    zero_tolerance = 1e-10 * max(float(np.max(np.abs(actual))), 1.0)
    mask = actual > zero_tolerance
    mape = None
    if mask.any():
        mape = float(np.mean(np.abs(errors[mask] / actual[mask])) * 100.0)
    return {"rmse_kw": sqrt(float(np.mean(errors ** 2))),
            "mape_percent": mape, "mape_sample_count": int(mask.sum())}


def _build_profiles(times, load_p, load_q, pv_p, pv_q):
    streams = []
    labels = [pd.Timestamp(time).isoformat() for time in times]
    for active, reactive in ((load_p, load_q), (pv_p, pv_q)):
        stream = StringIO()
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["timestamp", "bus_id", "p_kw", "q_kvar"])
        for bus_id in sorted(active):
            for index, timestamp in enumerate(labels):
                writer.writerow([timestamp, bus_id, active[bus_id][index], reactive[bus_id][index]])
        stream.seek(0)
        streams.append(stream)
    return ProfileData(streams[0], streams[1])  # Public loader, in memory and unchanged.


def generate_scenarios(history: ProfileData, config: UncertaintyConfig, *, progress=None) -> ScenarioSet:
    """Validate on a held-out tail, refit all history and draw conditional paths."""
    _validate_profiles(history)
    training_count = len(history.timestamps) - config.validation_hours
    required_training = max(48, 2 * sum(config.arima_order) + 10)
    if training_count < required_training:
        raise ValueError(f"Need at least {required_training} training hours plus validation_hours")
    if set(config.pv_capacity_kw) != set(history.pv_p_kw):
        raise ValueError("Supply one installed PV capacity for every PV profile bus")
    for bus_id, values in history.pv_p_kw.items():
        if max(values) > config.pv_capacity_kw[bus_id] + 1e-9:
            raise ValueError(f"Historical PV at bus {bus_id} exceeds its supplied capacity")
    future_times = list(pd.date_range(
        start=pd.Timestamp(history.timestamps[-1]) + pd.Timedelta(hours=1),
        periods=config.forecast_hours, freq="h",
    ))
    holdout_times = history.timestamps[training_count:]
    rng = np.random.default_rng(config.seed)
    paths = {"load": {}, "pv": {}}
    forecasts = {"load": {}, "pv": {}}
    ratios = {"load": {}, "pv": {}}
    validation = {"load": {}, "pv": {}}
    models = {"load": {}, "pv": {}}
    fit_total = 2 * (len(history.load_p_kw) + len(history.pv_p_kw))
    fit_completed = 0
    for kind, active, reactive in (("load", history.load_p_kw, history.load_q_kvar),
                                    ("pv", history.pv_p_kw, history.pv_q_kvar)):
        for bus_id in sorted(active):
            p_values, q_values = active[bus_id], reactive[bus_id]
            capacity = config.pv_capacity_kw[bus_id] if kind == "pv" else None
            if progress is not None:
                progress(ProgressEvent("ARIMA", fit_completed, fit_total,
                                       f"{kind} bus {bus_id}: fitting training history", True))
            try:
                training_model = _fit_with_mode(
                    p_values[:training_count], q_values[:training_count],
                    history.timestamps[:training_count], config.arima_order, capacity,
                    config.model_mode,
                )
            except ValueError as error:
                raise ValueError(f"ARIMA {kind} bus {bus_id}, training fit: {error}") from error
            fit_completed += 1
            prediction = _forecast_series(training_model, holdout_times)
            naive = [p_values[training_count - 24 + i % 24] for i in range(len(holdout_times))]
            arima_errors = _forecast_errors(p_values[training_count:], prediction)
            naive_errors = _forecast_errors(p_values[training_count:], naive)
            if (config.model_mode == "automatic" and training_model.model_name == "ARIMA"
                    and arima_errors["rmse_kw"] >= naive_errors["rmse_kw"]):
                training_model = _bootstrap_series(
                    p_values[:training_count], q_values[:training_count],
                    history.timestamps[:training_count], capacity,
                    "ARIMA validation RMSE did not improve on repeat-last-day; using hourly residual bootstrap",
                )
                prediction = _forecast_series(training_model, holdout_times)
                arima_errors = _forecast_errors(p_values[training_count:], prediction)
            validation[kind][bus_id] = {
                "arima": arima_errors,
                "repeat_last_day": naive_errors,
                "training_warnings": training_model.fit_warnings,
            }
            if progress is not None:
                progress(ProgressEvent("ARIMA", fit_completed, fit_total,
                                       f"{kind} bus {bus_id}: fitting full history", True))
            try:
                full_mode = "bootstrap" if training_model.model_name == "hourly_residual_bootstrap" else config.model_mode
                model = _fit_with_mode(
                    p_values, q_values, history.timestamps, config.arima_order,
                    capacity, full_mode,
                )
            except ValueError as error:
                raise ValueError(f"ARIMA {kind} bus {bus_id}, full-history fit: {error}") from error
            fit_completed += 1
            forecasts[kind][bus_id] = _forecast_series(model, future_times).tolist()
            ratios[kind][bus_id] = [float(model.hourly_q_ratio[time.hour]) for time in future_times]
            models[kind][bus_id] = {
                "model": model.model_name, "fit_status": model.fit_status,
                "order": config.arima_order,
                "warnings": sorted(set(training_model.fit_warnings + model.fit_warnings)),
            }
            residual_paths = np.zeros((config.forecast_hours, config.scenario_count))
            if model.fitted is not None:
                simulated = model.fitted.simulate(
                    nsimulations=config.forecast_hours, anchor="end",
                    repetitions=config.scenario_count, random_state=rng,
                )
                residual_paths = np.asarray(simulated).reshape(config.forecast_hours, config.scenario_count)
            elif model.model_name == "hourly_residual_bootstrap" and model.residual_pool.size:
                residual_paths = rng.choice(
                    model.residual_pool,
                    size=(config.forecast_hours, config.scenario_count),
                    replace=True,
                )
            paths[kind][bus_id] = [model.restore(residual_paths[:, i], future_times).tolist()
                                   for i in range(config.scenario_count)]
    if progress is not None:
        progress(ProgressEvent("ARIMA", fit_completed, fit_total, "All series fitted", True))
    scenarios = []
    for index in range(config.scenario_count):
        if progress is not None:
            progress(ProgressEvent("Scenarios", index, config.scenario_count, "Building scenario profiles"))
        active = {"load": {}, "pv": {}}
        reactive = {"load": {}, "pv": {}}
        for kind in ("load", "pv"):
            for bus_id, bus_paths in paths[kind].items():
                active[kind][bus_id] = bus_paths[index]
                reactive[kind][bus_id] = [p_kw * ratio for p_kw, ratio in
                                          zip(bus_paths[index], ratios[kind][bus_id])]
        profiles = _build_profiles(future_times, active["load"], reactive["load"],
                                    active["pv"], reactive["pv"])
        scenarios.append(Scenario(f"scenario_{index + 1:03d}", profiles, 1.0 / config.scenario_count))
    if progress is not None:
        progress(ProgressEvent("Scenarios", config.scenario_count, config.scenario_count,
                               "Scenario generation completed", True))
    return ScenarioSet(scenarios, {
        "method": "hourly means + ARIMA residual paths", "seed": config.seed,
        "history_hours": len(history.timestamps), "forecast_hours": config.forecast_hours,
        "scenario_count": config.scenario_count, "arima_order": config.arima_order,
        "pv_capacity_kw": dict(config.pv_capacity_kw),
        "validation_hours": config.validation_hours, "model_mode": config.model_mode,
        "validation": validation,
        "forecast_p_kw": forecasts, "models": models,
        "assumptions": ["Independent innovations between buses and between load/PV",
                        "Hourly historical Q/P ratios; fixed historical PV daylight hours",
                        "Clipped Gaussian paths; no parameter or seasonal uncertainty"],
    })


def scenario_features(profiles: ProfileData) -> dict[str, float]:
    """Calculate the four confirmed pre-optimization profile-stress features."""
    _validate_profiles(profiles)
    net = []
    for index in range(len(profiles.timestamps)):
        load = sum(values[index] for values in profiles.load_p_kw.values())
        pv = sum(values[index] for values in profiles.pv_p_kw.values())
        net.append(load - pv)
    return {
        "net_energy_kwh": sum(max(value, 0.0) for value in net) * profiles.dt_hours,
        "peak_net_kw": max(net),
        "surplus_energy_kwh": sum(max(-value, 0.0) for value in net) * profiles.dt_hours,
        "ramp_kw": max(abs(net[i] - net[i - 1]) for i in range(1, len(net))),
    }


def select_scenarios(scenario_set: ScenarioSet,
                     selection_config: SelectionConfig | None = None) -> ScenarioSet:
    """Retain distinct low/high stress and random cases; do not invent probabilities."""
    settings = selection_config if selection_config is not None else SelectionConfig()
    scenario_set.validate()
    count = settings.best_count + settings.worst_count + settings.random_count
    if count > len(scenario_set.scenarios):
        raise ValueError("Requested more selected scenarios than available")
    features = {item.scenario_id: scenario_features(item.profiles) for item in scenario_set.scenarios}
    weights = {"net_energy_kwh": 0.35, "peak_net_kw": 0.30,
               "surplus_energy_kwh": 0.20, "ramp_kw": 0.15}
    scores = {item.scenario_id: 0.0 for item in scenario_set.scenarios}
    for name, weight in weights.items():
        low = min(values[name] for values in features.values())
        high = max(values[name] for values in features.values())
        if high > low:
            for scenario_id, values in features.items():
                scores[scenario_id] += weight * (values[name] - low) / (high - low)
    ranked = sorted(scenario_set.scenarios, key=lambda item: (scores[item.scenario_id], item.scenario_id))
    best = ranked[:settings.best_count]
    worst = ranked[len(ranked) - settings.worst_count:] if settings.worst_count else []
    used = {item.scenario_id for item in best + worst}
    remaining = sorted((item for item in ranked if item.scenario_id not in used), key=lambda item: item.scenario_id)
    random_cases = Random(settings.seed).sample(remaining, settings.random_count)
    selected = []
    for group, cases in (("best", best), ("worst", worst), ("random", random_cases)):
        for scenario in cases:
            selected.append(replace(scenario, probability=None, metadata={
                **scenario.metadata, "selection_group": group,
                "stress_score": scores[scenario.scenario_id],
                "stress_features": features[scenario.scenario_id],
                "source_probability": scenario.probability,
            }))
    return ScenarioSet(selected, {
        **scenario_set.metadata, "selection_seed": settings.seed,
        "source_scenario_count": len(scenario_set.scenarios), "stress_scores": scores,
        "selection_counts": {"best": len(best), "worst": len(worst), "random": len(random_cases)},
        "weighting": "Equal-weight stress portfolio, not a probability-preserving reduction",
    })


def _aggregate_metrics(metrics):
    """Means for energy/durations, worst-case extrema; investment counted once."""
    result = replace(metrics[0], notes=["Equal-weight scenario means; extrema/peak are worst-case values."])
    mean_fields = (
        "duration_hours", "served_load_energy_kwh", "pv_generation_energy_kwh",
        "grid_import_energy_kwh", "grid_export_energy_kwh", "loss_energy_kwh",
        "voltage_violation_hours", "voltage_violation_bus_hours", "reserve_violation_hours",
        "bess_charge_energy_kwh", "bess_discharge_energy_kwh", "curtailment_energy_kwh",
        "load_shedding_energy_kwh", "requested_load_energy_kwh", "available_pv_energy_kwh",
    )
    for name in mean_fields:
        values = [getattr(item, name) for item in metrics]
        setattr(result, name, None if any(value is None for value in values) else sum(values) / len(values))
    result.peak_grid_import_kw = max(item.peak_grid_import_kw for item in metrics)
    result.voltage_min_pu = min(item.voltage_min_pu for item in metrics)
    result.voltage_max_pu = max(item.voltage_max_pu for item in metrics)
    for name, function in (("bess_soc_min", min), ("bess_soc_max", max)):
        values = [getattr(item, name) for item in metrics]
        setattr(result, name, None if any(value is None for value in values) else function(values))
    result.feasible = all(item.feasible for item in metrics)
    if any(item.bess_cost != result.bess_cost or item.currency != result.currency for item in metrics):
        raise ValueError("One candidate must have the same investment cost/currency in every case")
    for item in metrics:
        for note in item.notes:
            if note not in result.notes:
                result.notes.append(note)
    return result


@dataclass
class ScenarioCandidateEvaluation(CandidateEvaluation):
    scenario_evaluations: dict[str, CandidateEvaluation] = field(default_factory=dict)


@dataclass
class ScenarioEvaluator:
    """Adapt one-profile evaluation to an explicitly equal-weight stress set."""
    profile_evaluator: SimulationEvaluator
    progress: object = None

    def __call__(self, network, scenario_set: ScenarioSet,
                 candidate: BESSCandidate) -> ScenarioCandidateEvaluation:
        if not isinstance(scenario_set, ScenarioSet):
            raise TypeError("ScenarioEvaluator expects ScenarioSet")
        scenario_set.validate()
        evaluations = {}
        for index, scenario in enumerate(scenario_set.scenarios):
            if self.progress is not None:
                self.progress(ProgressEvent("Scenario", index, len(scenario_set.scenarios),
                                             f"evaluating {scenario.scenario_id}"))
            evaluation = self.profile_evaluator(network, scenario.profiles, candidate)
            if not isinstance(evaluation, CandidateEvaluation) or evaluation.candidate != candidate:
                raise ValueError("Profile evaluator must return the requested candidate")
            evaluations[scenario.scenario_id] = evaluation
            if self.progress is not None:
                self.progress(ProgressEvent("Scenario", index + 1, len(scenario_set.scenarios),
                                             f"completed {scenario.scenario_id}; feasible={evaluation.feasible}"))
            if not evaluation.feasible or (evaluation.metrics is not None and not evaluation.metrics.feasible):
                return ScenarioCandidateEvaluation(
                    candidate, float("inf"), False,
                    message=f"Rejected in {scenario.scenario_id}: {evaluation.message}",
                    scenario_evaluations=evaluations,
                )
            _check_number(evaluation.objective, "Scenario objective", nonnegative=True)
        metrics = [item.metrics for item in evaluations.values()]
        aggregate = _aggregate_metrics(metrics) if all(item is not None for item in metrics) else None
        return ScenarioCandidateEvaluation(
            candidate, sum(item.objective for item in evaluations.values()) / len(evaluations), True,
            metrics=aggregate, message=f"Feasible in all {len(evaluations)} equally weighted stress cases.",
            scenario_evaluations=evaluations,
        )
