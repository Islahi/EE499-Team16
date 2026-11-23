"""EE499 approved, non-editable study assumptions.

An interface control being hidden must not become an untracked input.  Use this
module to normalize new study settings and to record their provenance.
Old result exports must never be rewritten by this module.
"""
from __future__ import annotations

from math import isfinite
from os import cpu_count
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .saved_schema import canonical_dispatch_mode

VERSION = "EE499-coordinated-PQ-OPF-sequential-BESS-v14.1"
CURRENCY = "USD"
PV_CRITICAL_IRRADIANCE_W_M2 = 120.0
PV_STANDARD_IRRADIANCE_W_M2 = 1000.0
SYNTHETIC_SEED = 42
SHED_EDGES = (0.50, 0.80)
SHED_WEIGHTS = (1.0, 3.0, 10.0)
DISPATCH_MODE = 1  # Legacy single-BESS UI compatibility. Multi-BESS uses an hourly feeder-aware rule.
FORECAST_METHOD = "sector_sum"
SEARCH_PRESET = "standard"

# UI IDs are retained as stable internal serialization keys for older study files.
FIXED_WIDGET_SETTINGS = {
    "dispatch_mode": DISPATCH_MODE,
    "edit_currency": CURRENCY,
    "group_economic_inputs": True,
    "shedding_policy": "progressive",
    "spin_shed_edge_1": SHED_EDGES[0] * 100,
    "spin_shed_edge_2": SHED_EDGES[1] * 100,
    "spin_shed_weight_1": SHED_WEIGHTS[0],
    "spin_shed_weight_2": SHED_WEIGHTS[1],
    "spin_shed_weight_3": SHED_WEIGHTS[2],
}

# Not shown to the ordinary user; both the internal decision and its origin are
# retained in run/session metadata and the Methodology explanation.
METHOD_LABELS = (
    "Up to three sequential BESS units; all bus voltages solved jointly with Numba FBS",
    "V14 nominal battery duration E/P is constrained to 2–12 hours by default; editable under advanced optimization settings",
    "V13 selectable first-order FBS-linearized coordinated P/Q OPF after 72h P scheduling; nonlinear FBS verified; not exact nonlinear AC OPF; inverter kVA multipliers are explicit assumptions",
    "No terminal SOC equality: final energy is reported, and a purchase-price replacement adjustment is included for inventory deficits",
    "Soft 72h end-of-horizon energy-reserve penalty; not a hard operational SOC requirement",
    "Progressive shedding: 50%/80% tiers, weights 1x/3x/10x",
    "Straight-line BESS annual cost = installation CAPEX / lifetime + yearly O&M",
    "Annual total = energy purchases - export credit + shedding and PV-curtailment penalties + terminal inventory deficit replacement + BESS annual cost",
    "Balance the combined voltage/shedding shortlist across electrical laterals; verify annual technical improvements; when shedding decreases, report pre-control voltage deficit as a diagnostic rather than an annual acceptance veto (verified final network constraints remain mandatory)",
    "Historical PV irradiance conversion: 120/1000 W/m2",
    "Sector winner forecast with common PV XGBoost, method sector_sum",
)


def auto_workers(cpu_total=None):
    """Conservative worker count; benchmark per machine before raising this cap."""
    logical = max(1, int(cpu_total if cpu_total is not None else (cpu_count() or 1)))
    return min(4, max(1, logical - 1))


def normalize_settings(values, *, cpu_total=None):
    """Migrate values from the current UI or an older saved setup.

    Explicit tariff acknowledgement is *not* inferred here: an uninitialized
    zero price must never silently become an approved economic assumption.
    """
    result = {key: value for key, value in values.items() if key not in (
        "spin_discount_rate", "spin_fixed_cost",
        "spin_terminal_energy_price", "terminal_policy",
        "group_terminal_soc", "spin_terminal_soc_percent",
        "group_reserve", "spin_reserve_percent", "spin_reserve_hours",
        "spin_screen_sites", "spin_screen_exploratory", "spin_screen_finalists")}
    result.update(FIXED_WIDGET_SETTINGS)
    # V10.2: Auto remains the safe default for old saved configurations.
    # Manual counts are preserved (rather than silently reset each run).
    logical = max(1, int(cpu_total if cpu_total is not None else (cpu_count() or 1)))
    auto = bool(result.get("chk_auto_cpu_workers", True))
    result["chk_auto_cpu_workers"] = auto
    if auto:
        result["spin_cpu_workers"] = auto_workers(logical)
        result["spin_annual_workers"] = min(2, logical)
    else:
        def valid_worker_count(key, maximum, default):
            value = result.get(key, default)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{key} must be an integer worker count")
            if not 1 <= value <= maximum:
                raise ValueError(f"{key} must be between 1 and {maximum} on this machine")
            return value
        result["spin_cpu_workers"] = valid_worker_count("spin_cpu_workers", min(8, logical), auto_workers(logical))
        result["spin_annual_workers"] = valid_worker_count("spin_annual_workers", min(2, logical), min(2, logical))
    for key, default in (("spin_opf_bess_kva_multiplier", 1.00),
                         ("spin_opf_pv_kva_multiplier", 1.00),
                         ("spin_opt_duration_min_hours", 2.0),
                         ("spin_opt_duration_max_hours", 12.0)):
        result.setdefault(key, default)
    result["fleet_dispatch_mode"] = canonical_dispatch_mode(str(result.get("fleet_dispatch_mode", "predictive")))
    if result["fleet_dispatch_mode"] not in ("opf", "daily_milp_dispatch", "predictive", "predictive_24h", "legacy"):
        result["fleet_dispatch_mode"] = "predictive"
    result["search_mode"] = SEARCH_PRESET
    # Sequential GWO is the only active optimization workflow.
    result.pop("screen_sites", None)
    result.pop("screen_exploratory", None)
    result.pop("screen_finalists", None)
    result["optimizer_algorithm"] = "GWO"
    result["fixed_methodology_version"] = VERSION
    return result


def methodology_record(dispatch_mode=None):
    record = {
        "version": VERSION,
        "origin": "EE499 sequential multi-BESS planning",
        "battery_dispatch": "Daily MILP selectable 24/48/72h daily MILP with discharge-linked PF-constrained Q, binary charge/discharge exclusivity, hard daily SOC closure and verified nonlinear FBS; legacy v13 experimental selectable hourly FBS-linearized coordinated OPF (battery P/Q, PV Q, shedding, curtailment), 72h battery scheduling and nonlinear FBS verification; original v12 72-hour, v11 24-hour and legacy selectable; future profile is offline perfect foresight",
        "terminal_soc_closure": "disabled; legacy V12/V13 only. Strict-mode closure is enforced and audited separately.",
        "daily_soc_closure": "Each executed day must return to its starting SOC within the stated energy tolerance; otherwise simulation is infeasible.",
        "shedding_policy": "progressive",
        "shedding_tier_edges": SHED_EDGES,
        "shedding_tier_weights": SHED_WEIGHTS,
        "currency": CURRENCY,
        "pv_critical_w_m2": PV_CRITICAL_IRRADIANCE_W_M2,
        "pv_standard_w_m2": PV_STANDARD_IRRADIANCE_W_M2,
        "forecast_method": FORECAST_METHOD,
        "multi_bess_gwo_preset": SEARCH_PRESET,
        "sequential_limit": "Up to three installed; accept annual technical improvement on targeted electrical lateral; cost breaks ties among acceptable candidates",
        "candidate_screening": "annual weakest-bus ranking, 72-hour severity windows with candidate-specific year-chronological estimated SOC, diverse shortlisted annual FBS finalists and post-selection annual energy-size refinements",
        "economic_objective": "grid net cost + shedding penalty + curtailment penalty + terminal inventory deficit replacement cost + annual BESS capital + annual BESS O&M",
        "bess_capex": "Strict-mode battery energy USD/kWh + inverter nameplate USD/kVA (with PF-based kVA minimum). Legacy modes USD/kW + USD/kWh.",
        "bess_duration": "V14: enforced nameplate E/P duration 2–12 h by default, user configurable; optimize only feasible P/E catalog pairs",
        "bess_annualization": "Strict mode: inflation-adjusted real CRF from 5% interest, 1% inflation, 10-year life + 2% annual O&M. Legacy: straight-line.",
    }
    if dispatch_mode == "daily_milp_dispatch":
        record.pop("multi_bess_gwo_preset")
        record.pop("sequential_limit")
        record.update(
            version="EE499-daily-MILP-joint-fleet-GA",
            origin="EE499 daily MILP dispatch battery scheduling and Joint GA planning",
            battery_dispatch="Binary MILP with discharge-linked reactive power and daily SOC restoration, verified with nonlinear Numba FBS.",
            terminal_soc_closure="Daily SOC restoration within the configured energy tolerance.",
            candidate_screening="All eligible buses, probability-weighted representative days, independent stress days and chronological annual verification.",
            bess_annualization="Real CRF using the stated interest, inflation and lifetime, plus annual O&M as a fraction of CAPEX.",
            bess_capex="Battery energy USD/kWh and inverter nameplate USD/kVA, including the minimum kVA required by the discharge PF.",
        )
    return record


def read_manifest_assumptions(manifest):
    """Resolve source time zone and site from explicit, consistent metadata.

    Never infer an IANA clock or geographic coordinates from the user's machine.
    Missing location is allowed for a *no-PV* study, but an automatic solar
    source requires a valid declared site in the study/solar metadata.
    """
    if not isinstance(manifest, dict):
        raise ValueError("Missing or unreadable study manifest.json")
    clocks = [str(manifest[k]).strip() for k in ("clock", "timezone", "time_zone")
              if manifest.get(k) is not None and str(manifest[k]).strip()]
    if len(set(clocks)) > 1:
        raise ValueError("Study manifest declares conflicting source clocks; correct its metadata")
    clock = clocks[0] if clocks else None
    if not clock:
        raise ValueError("Study manifest has no source clock; declare an actual IANA/UTC clock in the data metadata")
    if clock.upper() == "LST":
        raise ValueError("NASA local solar time is not a civil time zone; provide an explicit source-clock conversion")
    try:
        ZoneInfo(clock)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(f"Invalid source clock {clock!r}; use a real IANA time zone or UTC") from error
    reference = manifest.get("pv_reference") or {}
    site = manifest.get("site") or reference.get("site") or {}
    latitude = site.get("latitude", manifest.get("site_lat"))
    longitude = site.get("longitude", manifest.get("site_lon"))
    if (latitude is None) != (longitude is None):
        raise ValueError("Study metadata has only one site coordinate; declare both latitude and longitude")
    if latitude is not None:
        try:
            latitude, longitude = float(latitude), float(longitude)
        except (ValueError, TypeError) as error:
            raise ValueError("Study coordinates must be numeric degrees") from error
        if not (isfinite(latitude) and isfinite(longitude) and
                -90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("Study latitude/longitude are outside geographic bounds")
    capacity = reference.get("capacity_kw")
    if capacity is not None:
        try:
            capacity = float(capacity)
        except (TypeError, ValueError) as error:
            raise ValueError("PV reference capacity must be numeric") from error
        if not isfinite(capacity) or capacity <= 0:
            raise ValueError("PV reference capacity must be positive")
    return {"clock": clock, "latitude": latitude, "longitude": longitude,
            "reference_capacity_kw": capacity}


def resolve_solar_location(case, source):
    """Validate explicit site compatibility without conflating source and case."""
    def pair(meta):
        lat = meta.get("site_lat", meta.get("latitude"))
        lon = meta.get("site_lon", meta.get("longitude"))
        if lat is None and lon is None:
            return None
        if lat is None or lon is None:
            raise ValueError("Solar metadata needs both latitude and longitude")
        try:
            lat, lon = float(lat), float(lon)
        except (ValueError, TypeError) as error:
            raise ValueError("Solar coordinates must be numeric") from error
        if not (isfinite(lat) and isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Solar coordinates are out of range")
        return (lat, lon)
    case_pair = pair(case)
    source_pair = pair(source)
    if case_pair and source_pair and any(abs(a-b)>1e-5 for a,b in zip(case_pair, source_pair)):
        raise ValueError("Solar-file site conflicts with the prepared study site; use matching data or document a conversion")
    return source_pair or case_pair
