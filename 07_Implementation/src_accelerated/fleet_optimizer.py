"""Network-guided two-stage GWO with exact chronological finalist evaluation."""
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from itertools import cycle
from math import inf, isfinite
from multiprocessing import get_context
from random import Random
from time import perf_counter, process_time

from .bess import BESSFleet, FleetUnit
from .fbs import prepare_fbs
from .metrics import capital_recovery_factor, evaluate_results, validate_annual_inputs, with_terminal_policy
from .network_screening import BaselineCache, branch_severity, rank_locations, select_windows
from .optimizer import BESSCandidate, move_catalog_wolves
from .progress import ProgressEvent
from .simulation import simulate_timeseries


@dataclass(frozen=True, order=True)
class FleetCandidate:
    units: tuple[BESSCandidate, ...]

    def __post_init__(self):
        units = tuple(sorted(self.units))
        if len(units) > 3 or len({unit.bus_id for unit in units}) != len(units):
            raise ValueError("Fleet candidates require up to three distinct installation buses")
        object.__setattr__(self, "units", units)

    @property
    def power_rating_kw(self):
        return sum(unit.power_rating_kw for unit in self.units)

    @property
    def energy_capacity_kwh(self):
        return sum(unit.energy_capacity_kwh for unit in self.units)

    @property
    def bus_id(self):
        return ", ".join(str(unit.bus_id) for unit in self.units)

    def build(self, parameters):
        return BESSFleet(tuple(FleetUnit(f"B{unit.bus_id}", parameters.build_config(unit)) for unit in self.units))


@dataclass(frozen=True)
class FleetSearchConfig:
    counts: tuple[int, ...] = (1, 2, 3)
    capacity_mode: str = "equal"
    objective: str = "reliability"
    total_kw: float = 1250.
    total_kwh: float = 6250.
    annual_cost_budget: float | None = None
    capital_budget: float | None = None
    screened: bool = True
    top_k: int = 10
    exploration: int = 2
    trial_kw: float = 100.
    window_days: int = 7
    window_count: int = 4
    finalists: int = 5
    distinct_sections: bool = False
    require_annual: bool = True
    include_previous_winner: bool = True

    def __post_init__(self):
        counts = tuple(sorted(set(self.counts)))
        if any(type(count) is not int or not 1 <= count <= 3 for count in counts) or not counts:
            raise ValueError("Choose fleet counts from one through three")
        object.__setattr__(self, "counts", counts)
        if self.capacity_mode not in ("equal", "flexible") or self.objective not in ("reliability", "economics"):
            raise ValueError("Unknown fleet capacity mode or objective")
        for key in ("total_kw", "total_kwh", "trial_kw"):
            if not isfinite(getattr(self, key)) or getattr(self, key) <= 0:
                raise ValueError(f"{key} must be finite and positive")
        for key in ("annual_cost_budget", "capital_budget"):
            value = getattr(self, key)
            if value is not None and (not isfinite(value) or value < 0):
                raise ValueError(f"{key} must be finite and nonnegative")
        for key in ("top_k", "exploration", "window_days", "window_count", "finalists"):
            if type(getattr(self, key)) is not int or getattr(self, key) < (0 if key == "exploration" else 1):
                raise ValueError(f"Invalid fleet search setting {key}")


@dataclass
class FleetEvaluation:
    candidate: FleetCandidate
    feasible: bool
    stage: str
    hours: int
    shedding_kwh: float | None
    curtailment_kwh: float | None
    cost: float | None
    capex: float | None
    details: dict = field(default_factory=dict)


@dataclass
class FleetExperiment:
    baseline: object
    evaluation: FleetEvaluation
    screened: list[FleetEvaluation]
    verified: list[FleetEvaluation]
    winners: dict
    metadata: dict


def _catalog_scale(value):
    return int(round(value * 1_000_000))


class FleetCatalog:
    def __init__(self, bounds, buses, count, search, sections):
        self.buses = tuple(buses)
        self.count = count
        self.sizes = [len(buses), len(bounds.power_ratings_kw), len(bounds.energy_capacities_kwh)] * count
        self.power = tuple(bounds.power_ratings_kw)
        self.energy = tuple(bounds.energy_capacities_kwh)
        self.limits = (_catalog_scale(search.total_kw), _catalog_scale(search.total_kwh))
        self.exact = search.capacity_mode == "equal"
        self.sections = sections if search.distinct_sections else None
        if len(self.buses) < count or self.sections is not None and len({sections[bus] for bus in self.buses}) < count:
            raise ValueError(f"The eligible sites cannot host {count} fleet units with the selected placement constraint")
        self._power_lookup = self._lookup(self.power)
        self._energy_lookup = self._lookup(self.energy)
        if not all(lookup(count, limit) for lookup, limit in zip((self._power_lookup, self._energy_lookup), self.limits)):
            raise ValueError(f"The configured size grids cannot satisfy the power/energy totals for {count} units")

    def _lookup(self, values):
        scaled = tuple(map(_catalog_scale, values))
        exact = self.exact

        @lru_cache(maxsize=None)
        def possible(left, remaining):
            if remaining < left * scaled[0] or exact and remaining > left * scaled[-1]:
                return False
            if not left:
                return remaining == 0 if exact else remaining >= 0
            if not exact:
                return remaining >= left * scaled[0]
            return any(possible(left - 1, remaining - value) for value in scaled)

        return possible

    def _allocate(self, coordinates, values, limit, lookup):
        selected = []
        for offset, coordinate in enumerate(coordinates):
            order = sorted(range(len(values)), key=lambda i: (abs(i + 1 - coordinate), i))
            index = next(i for i in order if lookup(self.count - offset - 1, limit - _catalog_scale(values[i])))
            selected.append(values[index])
            limit -= _catalog_scale(values[index])
        return selected

    def decode(self, position):
        buses = []
        used_sections = set()
        for coordinate in position[::3]:
            ranked = sorted(enumerate(self.buses, 1), key=lambda item: (abs(item[0] - coordinate), item[0]))
            bus = next(bus for _, bus in ranked if bus not in buses and
                       (self.sections is None or self.sections[bus] not in used_sections))
            buses.append(bus)
            if self.sections is not None:
                used_sections.add(self.sections[bus])
        power = self._allocate(position[1::3], self.power, self.limits[0], self._power_lookup)
        energy = self._allocate(position[2::3], self.energy, self.limits[1], self._energy_lookup)
        return FleetCandidate(tuple(BESSCandidate(*item) for item in zip(buses, power, energy)))

    def encode(self, candidate):
        return [index for unit in candidate.units for index in
            (self.buses.index(unit.bus_id) + 1, self.power.index(unit.power_rating_kw) + 1,
             self.energy.index(unit.energy_capacity_kwh) + 1)]


def rank(evaluation, objective, settings):
    bad = (not evaluation.feasible or evaluation.cost is None or evaluation.shedding_kwh is None or
           objective == "reliability" and (
               settings.annual_cost_budget is not None and evaluation.cost > settings.annual_cost_budget or
               settings.capital_budget is not None and (evaluation.capex is None or evaluation.capex > settings.capital_budget)))
    if bad:
        return inf, inf, evaluation.candidate
    if objective == "reliability":
        return evaluation.shedding_kwh, evaluation.cost, evaluation.candidate
    return evaluation.cost, evaluation.shedding_kwh, evaluation.candidate


def _peak_memory():
    try:
        import resource
    except ImportError:
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (key, ctypes.c_size_t) for key in ("peak", "working", "paged_peak", "paged", "nonpaged_peak",
                                                   "nonpaged", "pagefile", "pagefile_peak")]

        values = Counters()
        values.cb = ctypes.sizeof(values)
        ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        query = ctypes.windll.psapi.GetProcessMemoryInfo
        query.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
        return values.peak if query(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(values), values.cb) else None
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


def summarize(candidate, runs, economics, settings, stage, verified_annual, cpu_seconds=0.):
    fleet = bool(candidate.units)
    converged = all(series.completed and series.converged for series, _ in runs)
    steps = [step for series, _ in runs for step in series.steps]
    timing = {key: sum(series.dispatch_timing.get(key, 0) for series, _ in runs)
              for key in ("fbs_calls", "correction_fbs_trials", "correction_seconds", "correction_unresolved_hours")}
    timing.update(cpu_seconds=cpu_seconds, worker_peak_rss_bytes=_peak_memory())
    if not converged:
        return FleetEvaluation(candidate, False, stage, len(steps), None, None, None, None,
                               {**timing, "message": "Incomplete or nonconverged FBS"})
    scores = [metrics for _, metrics in runs]
    dt = runs[0][0].dt_hours
    shed = sum(item.load_shedding_energy_kwh for item in scores)
    curtailed = sum(item.curtailment_energy_kwh for item in scores)
    capex = scores[0].bess_cost
    factor = capital_recovery_factor(economics.discount_rate, economics.lifetime_years) + economics.annual_om_fraction
    ownership = capex * factor
    grid = sum(item.grid_import_energy_kwh for item in scores)
    exported = sum(item.grid_export_energy_kwh for item in scores)
    if verified_annual:
        cost = scores[0].annual_total_cost
        objective_kind = "verified annual USD/year"
    else:
        weight = economics.annual_hours / (len(steps) * dt) if stage == "A" else 1.0
        terminal = 0.
        if fleet and economics.terminal_policy == "priced_energy":
            for series, _ in runs:
                for unit in series.fleet_configuration.units:
                    config = unit.config
                    difference = config.soc_initial * config.energy_capacity_kwh - series.final_fleet_states[unit.unit_id].energy_kwh
                    terminal += (max(0., difference) * economics.terminal_energy_price_per_kwh / config.eta_charge -
                                 max(0., -difference) * config.eta_discharge * economics.grid_export_tariff_per_kwh)
        cost = ownership * (1.0 if stage == "A" else len(steps) * dt / economics.annual_hours) + weight * (
            grid * economics.grid_import_tariff_per_kwh - exported * economics.grid_export_tariff_per_kwh +
            shed * economics.shedding_penalty_per_kwh + curtailed * economics.curtailment_penalty_per_kwh + terminal)
        objective_kind = "screening estimate USD/year" if stage == "A" else "reduced-horizon USD"
    bus_shed = {bus: sum(step.shedding_by_bus_kw[bus] * dt for step in steps) for bus in steps[0].operating_point.p_load_kw}
    disconnected = {bus: sum(step.operating_point.p_load_kw[bus] <= 1e-8 and step.shedding_by_bus_kw[bus] > 1e-8
                            for step in steps) * dt for bus in bus_shed}
    requested = {bus: sum(step.operating_point.p_load_kw[bus] * dt for step in steps) + bus_shed[bus] for bus in bus_shed}
    fractions = [bus_shed[bus] / value for bus, value in requested.items() if value > 0]
    details = {**timing, "cost_basis": objective_kind, "annualized_ownership_usd": ownership,
               "grid_import_kwh": grid, "losses_kwh": sum(item.loss_energy_kwh for item in scores),
               "voltage_violation_hours": sum(item.voltage_violation_hours for item in scores),
               "export_violation_hours": (sum(-step.power_flow.slack_p_kw > settings.grid_export_limit_kw + settings.control_tolerance_kw
                                          for step in steps) * dt if settings.grid_export_limit_kw is not None else None),
               "ampacity_violation_hours": sum(any(message.startswith("Line ampacity exceeded") for message in step.messages)
                                               for step in steps) * dt if settings.enforce_line_ampacity else None,
               "reserve_violation_hours": sum(item.reserve_violation_hours for item in scores),
               "fully_disconnected_hours_by_bus": disconnected, "shed_kwh_by_bus": bus_shed,
               "max_bus_shedding_fraction": max(fractions, default=None),
               "bus_shedding_fraction_spread": max(fractions) - min(fractions) if fractions else None,
               "terminal_soc": {key: state.soc for key, state in runs[-1][0].final_fleet_states.items()} if fleet else {},
               "message": "; ".join(dict.fromkeys(series.message for series, _ in runs))}
    return FleetEvaluation(candidate, all(item.feasible for item in scores), stage, len(steps), shed, curtailed, cost, capex, details)


@dataclass
class _Context:
    network: object
    full: object
    windows: tuple
    simulation: object
    economics: object
    policy: object
    parameters: object
    peak_kw: float
    annual: bool
    _solver: object = field(default=None, init=False, repr=False)

    def evaluate(self, job):
        candidate, stage = job
        battery = candidate.build(self.parameters)
        started = process_time()
        if self._solver is None:
            self._solver = prepare_fbs(self.network, self.simulation.fbs_config)
        runs = []
        for profiles in self.windows if stage == "A" else (self.full,):
            series = simulate_timeseries(self.network, profiles, self.simulation, battery, self.policy,
                                         capture_dispatch=False, reserve_peak_kw=self.peak_kw, _prepared_fbs=self._solver)
            metrics = evaluate_results(series, self.economics, battery) if series.completed and series.converged else None
            runs.append((series, metrics))
        return summarize(candidate, runs, self.economics, self.simulation, stage, self.annual and stage == "B", process_time() - started)


_WORKER = None


def _initialize(context):
    global _WORKER
    _WORKER = context


def _worker_evaluate(job):
    return _WORKER.evaluate(job)


def _stage_gwo(catalog, config, settings, objective, stage, evaluations, evaluate, progress):
    rng = Random(config.seed)

    def random_position():
        return [rng.uniform(1, size) for size in catalog.sizes]

    positions = [random_position() for _ in range(config.population_size)]
    positions[0], positions[1] = [1.] * len(catalog.sizes), list(map(float, catalog.sizes))
    accumulated = {}
    history = []
    for generation in range(config.max_iterations):
        candidates = [catalog.decode(position) for position in positions]
        pending = list(dict.fromkeys(candidate for candidate in candidates if candidate not in evaluations))
        for result in evaluate((candidate, stage) for candidate in pending):
            evaluations[result.candidate] = result
        accumulated.update((candidate, evaluations[candidate]) for candidate in candidates)
        ordered = sorted(accumulated.values(), key=lambda item: rank(item, objective, settings))
        leader_score = rank(ordered[0], objective, settings)[0]
        history.append(leader_score if isfinite(leader_score) else None)
        if progress is not None:
            progress(ProgressEvent("Fleet GWO", generation + 1, config.max_iterations,
                f"Stage {stage} · {catalog.count} units · {objective} · {len(accumulated)} evaluated fleets", True))
        if not isfinite(leader_score):
            positions = [random_position() for _ in positions]
            continue
        leaders = [catalog.encode(item.candidate) for item in ordered[:3] if isfinite(rank(item, objective, settings)[0])]
        leaders = [item for _, item in zip(range(3), cycle(leaders))]
        scale = 2. * (1. - generation / max(1, config.max_iterations - 1))
        positions = move_catalog_wolves(positions, leaders, catalog.sizes, scale, rng)
    return ordered, history


def _diverse(ordered, limit):
    signatures = set()
    selected = []
    for evaluation in ordered:
        site = tuple(unit.bus_id for unit in evaluation.candidate.units)
        if site not in signatures:
            selected.append(evaluation.candidate)
            signatures.add(site)
            if len(selected) >= limit:
                break
    if len(selected) < limit:
        selected.extend([item.candidate for item in ordered if item.candidate not in selected][:limit - len(selected)])
    return selected


def _previous_winner(bounds, search, eligible):
    candidate = FleetCandidate((BESSCandidate(14, 1250., 6250.),))
    if not search.include_previous_winner or 1 not in search.counts or 14 not in eligible:
        return None
    if search.capacity_mode == "equal" and (candidate.power_rating_kw != search.total_kw or candidate.energy_capacity_kwh != search.total_kwh):
        return None
    if (candidate.power_rating_kw not in bounds.power_ratings_kw or candidate.energy_capacity_kwh not in bounds.energy_capacities_kwh
            or candidate.power_rating_kw > search.total_kw or candidate.energy_capacity_kwh > search.total_kwh):
        return None
    return candidate


def run_fleet_experiment(network, profiles, simulation, economics, policy, parameters, bounds, optimizer,
                         settings=FleetSearchConfig(), *, clock=None, cache=None, progress=None):
    """Return actual full-horizon winners separately from screening estimates."""
    start = perf_counter()
    if simulation.legacy_proportional_validation:
        raise ValueError("Fleet optimization requires the joint corrective controller")
    bounds.validate_network(network)
    if any(getattr(economics, field) is None for field in (
            "cost_per_kw", "cost_per_kwh", "grid_import_tariff_per_kwh", "grid_export_tariff_per_kwh")):
        raise ValueError("Fleet planning requires explicit investment coefficients and import/export tariffs")
    if economics.annual_day_weights:
        raise ValueError("Fleet screening requires chronological profiles, not weighted representative days")
    try:
        validate_annual_inputs(profiles.timestamps, economics, profiles.dt_hours)
        annual = True
    except ValueError:
        if settings.require_annual:
            raise
        annual = False
    if not annual and (settings.annual_cost_budget is not None):
        raise ValueError("An annual operating-cost budget requires annual finalist verification")
    simulation = with_terminal_policy(simulation, economics) if annual else simulation
    peak = max(map(sum, zip(*profiles.load_p_kw.values())), default=0.)
    eligible = tuple(bus for bus in bounds.allowed_bus_ids if bus != network.slack_bus_id())
    if len(eligible) < max(settings.counts):
        raise ValueError("Choose enough eligible non-slack installation buses for the requested fleet counts")
    cache = cache if cache is not None else BaselineCache()
    baseline_started, baseline_cpu_started = perf_counter(), process_time()
    baseline = cache.run(network, profiles, simulation, economics, clock, progress)
    base = summarize(FleetCandidate(()), [(baseline, evaluate_results(baseline, economics))], economics,
                     simulation, "B", annual, process_time() - baseline_cpu_started)
    baseline_wall = perf_counter() - baseline_started
    screening_started = perf_counter()
    if settings.screened:
        buses, branches, severity, sections, probes = rank_locations(network, profiles, simulation, baseline, eligible,
            max(settings.top_k, max(settings.counts)), settings.exploration, settings.trial_kw)
        windows = select_windows(baseline, settings.window_days, settings.window_count)
    else:
        branches, severity, sections = branch_severity(network, baseline)
        buses, probes, windows = eligible, {}, []
    screening_wall = perf_counter() - screening_started
    context = _Context(network, profiles, tuple(profiles.slice(profiles.timestamps[first],
                       profiles.timestamps[end] if end < len(profiles.timestamps) else None)
                       for first, end, _ in windows), simulation, economics, policy, parameters, peak, annual)
    screened, verified, history, finalists = {}, {}, {}, []
    objectives = (settings.objective, "economics" if settings.objective == "reliability" else "reliability")
    stage_a_wall = stage_b_wall = 0.
    executor = (ProcessPoolExecutor(max_workers=min(optimizer.workers, optimizer.population_size),
        mp_context=get_context("spawn"), initializer=_initialize, initargs=(context,)) if optimizer.workers > 1 else None)
    try:
        def evaluate(jobs):
            return executor.map(_worker_evaluate, jobs) if executor else map(context.evaluate, jobs)

        start_a = perf_counter()
        for count in settings.counts:
            catalog = FleetCatalog(bounds, buses, count, settings, sections)
            for objective in objectives:
                stage = "A" if settings.screened else "B"
                values = screened if settings.screened else verified
                ordered, history[f"{count}:{objective}"] = _stage_gwo(catalog, optimizer, settings, objective,
                                                                       stage, values, evaluate, progress)
                if settings.screened:
                    feasible = [item for item in ordered if isfinite(rank(item, objective, settings)[0])]
                    if len(feasible) < settings.finalists:
                        feasible.extend(item for item in ordered if not isfinite(rank(item, objective, settings)[0]))
                    finalists.extend(_diverse(feasible, settings.finalists))
                    exploratory = [item.candidate for item in ordered if any(
                        severity[unit.bus_id]["selection"] == "exploration outside top K" for unit in item.candidate.units)]
                    finalists.extend(exploratory[:1])
        if settings.screened:
            stage_a_wall = perf_counter() - start_a
            start_b = perf_counter()
        else:
            start_b = start_a
        previous = _previous_winner(bounds, settings, eligible)
        if previous is not None:
            finalists.append(previous)
        pending = [candidate for candidate in dict.fromkeys(finalists) if candidate not in verified]
        for result in evaluate((candidate, "B") for candidate in pending):
            verified[result.candidate] = result
            if progress is not None:
                progress(ProgressEvent("Fleet verification", len(verified), len(pending),
                                        f"Verified buses {result.candidate.bus_id}", True))
        stage_b_wall = perf_counter() - start_b
    finally:
        if executor:
            executor.shutdown(cancel_futures=True)

    winners = {}
    for objective in objectives:
        options = {0: base if isfinite(rank(base, objective, settings)[0]) else None}
        for count in settings.counts:
            candidates = [item for item in verified.values() if len(item.candidate.units) == count and
                          isfinite(rank(item, objective, settings)[0])]
            options[count] = min(candidates, key=lambda item: rank(item, objective, settings), default=None)
        winners[objective] = options
    metadata = {"search": asdict(settings), "reserve_fraction": simulation.reserve_fraction, "reserve_reference_peak_kw": peak,
        "global_reserve_kw": simulation.reserve_fraction * peak, "clock": clock, "baseline_fingerprint": cache.fingerprint,
        "full_horizon_hours": len(profiles.timestamps), "annual_verified": annual, "candidate_sites": buses,
        "sections": branches, "bus_severity": severity, "placement_probe_timing": probes, "gwo_history": history,
        "windows": [{"start": str(profiles.timestamps[first]), "last_hour": str(profiles.timestamps[end - 1]),
                      "hours": end - first, "rule": rule, "SOC": "Reset to specified initial SOC", "clock": clock}
                    for first, end, rule in windows], "workers": optimizer.workers, "seed": optimizer.seed,
        "baseline_wall_seconds": baseline_wall, "location_screen_wall_seconds": screening_wall,
        "stage_a_wall_seconds": stage_a_wall, "stage_b_wall_seconds": stage_b_wall, "wall_seconds": perf_counter() - start,
        "stage_a_candidate_hours": sum(item.hours for item in screened.values()),
        "stage_b_candidate_hours": sum(item.hours for item in verified.values())}
    metadata["archive_reference"] = asdict(previous) if previous is not None else None
    return FleetExperiment(baseline, base, list(screened.values()), list(verified.values()), winners, metadata)
