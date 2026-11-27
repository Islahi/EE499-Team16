"""Readable summaries and CSV exports; no simulation or optimization equations."""
import csv
from dataclasses import asdict, fields
from math import isclose
from pathlib import Path
from collections.abc import Mapping
import json

from .electrical_details import BUS_FIELDS, BRANCH_FIELDS, battery_ratings, bus_readings, branch_readings, line_ends
from .metrics import (PerformanceMetrics, load_service, percentage_reduction, service_verified,
                      summarize_service)
from .optimizer import OptimizationResult
from .simulation import TimeSeriesSimulationResult


Result = TimeSeriesSimulationResult | PerformanceMetrics | OptimizationResult

COMPARISON_FIELDS = (
    "requested_load_energy_kwh", "served_load_energy_kwh", "available_pv_energy_kwh",
    "pv_generation_energy_kwh", "grid_import_energy_kwh", "grid_export_energy_kwh",
    "load_shedding_energy_kwh", "curtailment_energy_kwh", "loss_energy_kwh",
    "annual_grid_purchases", "annual_export_credit", "annual_grid_cost",
    "annual_shedding_cost", "annual_curtailment_cost", "annual_operating_cost",
    "annual_bess_capital_cost", "annual_bess_om_cost", "annualized_bess_cost",
    "annual_total_cost", "bess_cost",
    "voltage_min_pu", "voltage_max_pu", "voltage_violation_hours",
    "fully_disconnected_bus_hours", "hours_with_full_disconnection",
)



def _result_metrics(result, supplied):
    if not isinstance(result, (TimeSeriesSimulationResult, PerformanceMetrics, OptimizationResult)):
        raise TypeError("Use a simulation result, PerformanceMetrics or OptimizationResult")
    if supplied is not None and not isinstance(supplied, PerformanceMetrics):
        raise TypeError("metrics must be PerformanceMetrics")
    if isinstance(result, TimeSeriesSimulationResult):
        if supplied is not None:
            if not result.completed or not result.converged or any(not step.power_flow.converged for step in result.steps):
                raise ValueError("Do not attach performance metrics to an incomplete/non-converged run")
            if not isclose(supplied.duration_hours, len(result.steps) * result.dt_hours):
                raise ValueError("Metrics duration does not match the simulation")
            if supplied.feasible and not (result.feasible and all(step.feasible for step in result.steps)):
                raise ValueError("Metrics feasibility does not match the simulation")
        return supplied
    if supplied is not None:
        raise ValueError("Only simulation results accept a separate metrics argument")
    if isinstance(result, OptimizationResult):
        if result.success and result.best_candidate is None and not result.metadata.get("no_bess_selected"):
            raise ValueError("Successful optimization must have a battery or a declared no-BESS selection")
        if not result.success and (result.best_candidate is not None or result.metrics is not None):
            raise ValueError("Failed optimization cannot claim a selected candidate or its metrics")
        if result.success and result.metrics is not None and not result.metrics.feasible:
            raise ValueError("Successful optimization cannot claim infeasible best metrics")
        return result.metrics
    return result


def _context_items(context):
    if context is None:
        return []
    if not isinstance(context, Mapping):
        raise TypeError("context must be a mapping of text labels to text values")
    return sorted((str(key), value if isinstance(value,str) else json.dumps(value,default=str)) for key,value in context.items())


def _display(value):
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return f"{value:.8g}"
    if isinstance(value, list):
        return " | ".join(str(item) for item in value) if value else "none"
    return str(value)


def _unit(name, metrics):
    if name.startswith("annual_") or name == "annualized_bess_cost":
        return metrics.currency + "/year"
    if name == "bess_cost":
        return metrics.currency
    for suffix, unit in (("_bus_hours", "bus-hours"), ("_hours", "h"),
                         ("_kvarh", "kvarh"), ("_kwh", "kWh"), ("_kw", "kW"), ("_pu", "pu")):
        if name.endswith(suffix):
            return unit
    if name in ("bess_soc_min", "bess_soc_max", "final_soc_deviation"):
        return "fraction"
    return ""


def format_summary(result: Result, *, metrics: PerformanceMetrics | None = None,
                   context: Mapping[str, str] | None = None) -> str:
    """Format existing values only; the caller supplies the study's provenance."""
    performance = _result_metrics(result, metrics)
    details = _context_items(context)
    lines = ["# Results summary", ""]
    if isinstance(result, TimeSeriesSimulationResult):
        lines.extend([
            "Type: hourly simulation", f"Completed: {result.completed}",
            f"Converged: {result.converged}", f"Feasible: {result.feasible}",
            f"Recorded steps: {len(result.steps)}", f"Time step: {result.dt_hours:g} h",
            f"Message: {result.message}",
        ])
        if result.steps:
            lines.extend([f"First timestamp: {result.steps[0].timestamp}",
                          f"Last timestamp: {result.steps[-1].timestamp}"])
        if not result.completed or not result.converged:
            lines.append("WARNING: incomplete/non-converged run; failed rows are diagnostic, not accepted operation.")
    elif isinstance(result, OptimizationResult):
        lines.extend(["Type: optimization", f"Success: {result.success}",
                      f"Message: {result.message}", f"Iterations: {result.iterations}",
                      f"Evaluator calls retained: {len(result.evaluations)}",
                      f"Best annual economic objective: {_display(result.best_objective)}"])
        if result.metadata.get("fleet"):
            lines.append(f"Sequentially installed batteries: {len(result.metadata['fleet'])}")
            for index, battery in enumerate(result.metadata['fleet'], 1):
                lines.append(f"BESS {index}: bus {battery['bus_id']}, "
                             f"{battery['power_rating_kw']:g} kW / {battery['energy_capacity_kwh']:g} kWh "
                             f"({battery['energy_capacity_kwh']/battery['power_rating_kw']:.3g} h)")
        elif result.best_candidate is not None:
            candidate = result.best_candidate
            lines.extend([f"Selected bus: {candidate.bus_id}",
                          f"Battery power: {candidate.power_rating_kw:g} kW",
                          f"Battery energy: {candidate.energy_capacity_kwh:g} kWh",
                          f"Battery duration (nameplate E/P): {candidate.energy_capacity_kwh/candidate.power_rating_kw:.3g} h"])
        else:
            lines.append("No battery installed (see placement-stage technical decisions; this is not necessarily the cheapest economic selection)." if result.metadata.get("no_bess_selected")
                         else "No feasible battery selected.")
        for key, value in sorted(result.metadata.items()):
            if key == "academic_ga_diagnostics":
                continue  # Persisted as a structured sidecar.
            lines.append(f"Optimizer {key}: {_display(value)}")
        lines.append("Annual economic score uses common monetary units; inspect the tariff assumptions.")
        lines.append("The selected alternative is the best among evaluated candidates and the no-BESS baseline, not a global-optimum guarantee.")
    else:
        lines.extend(["Type: performance metrics only", f"Feasible: {result.feasible}",
                      "Completion/convergence details were not supplied with this metrics-only export."])
    if performance is not None:
        lines.extend(["", "## Performance", ""])
        for item in fields(performance):
            value = _display(getattr(performance, item.name))
            lines.append(f"{item.name}: {value} {_unit(item.name, performance)}".rstrip())
    else:
        lines.extend(["", "Performance metrics: unavailable (not supplied or not retained)."])
    if details:
        lines.extend(["", "## Supplied study context", ""])
        for key, value in details:
            lines.append(f"{key}: {value}")
    lines.extend(["", "Feasible does not mean all demand was served; inspect shedding and curtailment.",
                  "Blank CSV values mean unavailable/not applicable, not zero.",
                  "No simulation or optimization was rerun during export.", ""])
    # List items remain separate lines in a rendered Markdown preview too.
    formatted = []
    for line in lines:
        formatted.append(f"- {line}" if line and not line.startswith("#") else line)
    return "\n".join(formatted)


def _csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, list):
        value = " | ".join(str(item) for item in value)
    # Text supplied through messages/labels must not become Excel formulas.
    if isinstance(value, str) and (value.lstrip().startswith(("=", "+", "-", "@"))
                                   or value.startswith(("\t", "\r", "\n"))):
        return "'" + value
    return value


def _write_csv(path, header, rows):
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        for row in rows:
            writer.writerow([_csv_cell(value) for value in row])


SYSTEM_FIELDS = ("requested_load_kw", "requested_load_kvar", "served_load_kvar", "available_pv_kw",
                 "grid_import_kw", "grid_export_kw", "loss_q_kvar", "minimum_voltage_bus", "maximum_voltage_bus",
                 "served_load_kwh", "pv_generation_kwh", "shed_kwh", "curtailed_kwh", "loss_kwh",
                 "grid_purchase_cost", "grid_export_credit", "shedding_cost", "curtailment_cost",
                 "requested_load_kwh", "available_pv_kwh", "grid_import_kwh", "grid_export_kwh",
                 "bess_charge_kw", "bess_discharge_kw", "bess_charge_kwh", "bess_discharge_kwh")


CONSTRAINT_FIELDS = ("voltage_violation_bus_count", "voltage_violation_max_pu", "uncontrolled_voltage_min_pu",
                     "uncontrolled_voltage_max_pu", "overloaded_line_count",
                     "grid_import_violation_kw", "grid_export_violation_kw")


def _hourly_rows(result, economics=None):
    prices = economics or {}
    def cost(energy, key):
        price = prices.get(key)
        return energy * price if energy is not None and price is not None else None

    for index, step in enumerate(result.steps):
        flow, point, battery = step.power_flow, step.operating_point, step.bess_step
        raw_failed = not flow.converged and result.dispatch_timing.get("control_mode") == "uncontrolled"
        final = step.dispatch.final if step.dispatch and flow.converged else None
        raw_voltage = step.uncontrolled_voltage_pu or {}
        violations = final.violations if final else {}
        correction = step.dispatch.correction if step.dispatch else None
        verified = service_verified(step)
        affected = sum(value > 1e-6 for value in (step.shedding_by_bus_kw or {}).values()) if verified else None
        balance_p = (flow.slack_p_kw + sum(point.p_pv_kw.values()) + sum(point.p_bess_kw.values())
                     - sum(point.p_load_kw.values()) - flow.total_loss_p_kw) if flow.converged else None
        balance_q = (flow.slack_q_kvar + sum(point.q_pv_kvar.values()) + sum(point.q_bess_kvar.values())
                     - sum(point.q_load_kvar.values()) - flow.total_loss_q_kvar) if flow.converged else None
        requested = step.requested_point
        imports = max(0., flow.slack_p_kw) if flow.converged else None
        exports = max(0., -flow.slack_p_kw) if flow.converged else None
        dt = result.dt_hours
        charge = sum(max(-p, 0.) for p in point.p_bess_kw.values())
        discharge = sum(max(p, 0.) for p in point.p_bess_kw.values())
        shed = step.shedding_kw * dt if step.shedding_kw is not None else None
        curtailed = step.curtailment_kw * dt if step.curtailment_kw is not None else None
        yield [
            index, str(step.timestamp), result.dt_hours, flow.converged, step.feasible,
            not flow.converged, flow.iterations, flow.message,
            sum(point.p_load_kw.values()) if not raw_failed else None,
            sum(point.p_pv_kw.values()) if not raw_failed else None,
            flow.slack_p_kw if not raw_failed else None, flow.slack_q_kvar if not raw_failed else None,
            flow.total_loss_p_kw if not raw_failed else None,
            min(flow.voltage_mag_pu.values(), default=None) if not raw_failed else None,
            max(flow.voltage_mag_pu.values(), default=None) if not raw_failed else None,
            step.bess_request_kw, battery.actual_power_kw if battery is not None else None,
            battery.soc_before if battery is not None else None,
            step.bess_state.soc if step.bess_state is not None else None,
            step.bess_state.energy_kwh if step.bess_state is not None else None,
            battery.limited if battery is not None else None,
            battery.limit_reason if battery is not None else None,
            step.curtailment_kw, step.shedding_kw,
            sorted(step.voltage_violations), step.messages,
            balance_p, balance_q, (correction or {}).get("status"),
            affected, (correction or {}).get("policy_score"), (correction or {}).get("objective_usd"),
            sum(point.q_bess_kvar.values()), sum(point.q_pv_kvar.values()),
            sum(requested.p_load_kw.values()) if requested else None,
            sum(requested.q_load_kvar.values()) if requested else None,
            sum(point.q_load_kvar.values()) if flow.converged else None,
            sum(requested.p_pv_kw.values()) if requested else None,
            imports, exports, flow.total_loss_q_kvar if flow.converged else None,
            min(flow.voltage_mag_pu, key=flow.voltage_mag_pu.get) if flow.converged else None,
            max(flow.voltage_mag_pu, key=flow.voltage_mag_pu.get) if flow.converged else None,
            sum(point.p_load_kw.values()) * dt if flow.converged else None,
            sum(point.p_pv_kw.values()) * dt if flow.converged else None, shed, curtailed,
            flow.total_loss_p_kw * dt if flow.converged else None,
            cost(imports * dt if imports is not None else None, "grid_import_tariff_per_kwh"),
            cost(exports * dt if exports is not None else None, "grid_export_tariff_per_kwh"),
            cost(shed, "shedding_penalty_per_kwh"), cost(curtailed, "curtailment_penalty_per_kwh"),
            sum(requested.p_load_kw.values()) * dt if requested else None,
            sum(requested.p_pv_kw.values()) * dt if requested else None,
            imports * dt if imports is not None else None, exports * dt if exports is not None else None,
            *(value if flow.converged else None for value in (charge, discharge, charge*dt, discharge*dt)),
            len(step.voltage_violations) if flow.converged else None,
            max((value for key, value in violations.items() if key.startswith(("undervoltage:", "overvoltage:"))),
                default=0.) if final else None,
            min(raw_voltage.values(), default=None), max(raw_voltage.values(), default=None),
            sum(key.startswith("ampacity:") for key in violations) if final else None,
            violations.get("import", 0.) if final else None, violations.get("export", 0.) if final else None,
        ]


def _bus_rows(result, network=None, bounds=None, context=None):
    context = context or {}
    batteries = battery_ratings(context)
    prices = context.get("Economic inputs", {})
    buses = {b.bus_id: b for b in network.buses} if network else {}
    ratings = {bus: sum(p.p_rated_kw for p in units) for bus, units in network.pv_by_bus().items()} if network else {}
    for index, step in enumerate(result.steps):
        point, flow = step.operating_point, step.power_flow
        raw_failed = not flow.converged and result.dispatch_timing.get("control_mode") == "uncontrolled"
        requested = step.requested_point
        verified = service_verified(step)
        for bus_id in sorted(point.p_load_kw):
            requested_p = requested.p_load_kw[bus_id] if requested else None
            requested_q = requested.q_load_kvar[bus_id] if requested else None
            served = flow.converged
            fraction, disconnected = load_service(requested_p, point.p_load_kw[bus_id] if verified else None)
            shed = (step.shedding_by_bus_kw or {}).get(bus_id)
            curtailed = (step.curtailment_by_bus_kw or {}).get(bus_id)
            dt = result.dt_hours
            price_shed, price_curtail = prices.get("shedding_penalty_per_kwh"), prices.get("curtailment_penalty_per_kwh")
            yield [index, str(step.timestamp), bus_id, flow.converged, step.feasible,
                   not flow.converged, flow.voltage_mag_pu.get(bus_id) if not raw_failed else None,
                   flow.voltage_angle_deg.get(bus_id) if not raw_failed else None,
                   *(values[bus_id] if not raw_failed else None
                     for values in (point.p_load_kw, point.q_load_kvar, point.p_pv_kw, point.q_pv_kvar)),
                   point.p_bess_kw[bus_id], point.q_bess_kvar[bus_id],
                   step.curtailment_by_bus_kw.get(bus_id) if step.curtailment_by_bus_kw is not None else None,
                   step.shedding_by_bus_kw.get(bus_id) if step.shedding_by_bus_kw is not None else None,
                   bus_id in step.voltage_violations if served else None,
                   requested_p, requested_q,
                   requested_q - point.q_load_kvar[bus_id] if served and requested else None,
                   fraction,
                   requested.p_pv_kw[bus_id] if requested else None,
                   (step.pre_control_voltage_pu or {}).get(bus_id),
                   (1. - fraction) * 100. if fraction is not None else None, disconnected,
                   *(bus_readings(step, buses[bus_id], ratings[bus_id], bounds, batteries.get(bus_id)).values()
                     if bus_id in buses else [None] * len(BUS_FIELDS)),
                   requested.q_pv_kvar[bus_id] if requested else None,
                   requested_p*dt if requested_p is not None else None,
                   point.p_load_kw[bus_id]*dt if served else None,
                   shed*dt if shed is not None else None, curtailed*dt if curtailed is not None else None,
                   shed*dt*price_shed if shed is not None and price_shed is not None else None,
                   curtailed*dt*price_curtail if curtailed is not None and price_curtail is not None else None]


def _branch_rows(result, network=None):
    lines = {line.line_id: line for line in network.lines} if network else {}
    ends = line_ends(network) if network else {}
    for index, step in enumerate(result.steps):
        flow = step.power_flow
        raw_failed = not flow.converged and result.dispatch_timing.get("control_mode") == "uncontrolled"
        for line_id in sorted(lines if raw_failed else flow.branch_current_a):
            yield [index, str(step.timestamp), line_id, flow.converged, step.feasible,
                   not flow.converged,
                   *(values.get(line_id) if not raw_failed else None for values in
                     (flow.branch_current_a, flow.branch_p_kw, flow.branch_q_kvar, flow.line_loss_p_kw, flow.line_loss_q_kvar)),
                   *(branch_readings(flow, lines[line_id], ends[line_id]).values()
                     if line_id in lines else [None] * len(BRANCH_FIELDS))]


EVALUATION_HEADER = [
    "evaluation_index", "bus_id", "power_rating_kw", "energy_capacity_kwh", "feasible",
    "annual_cost", "message", "metrics_available", "metrics_feasible", "bess_cost", "currency",
    "annual_total_cost", "annual_grid_cost", "annual_operating_cost",
    "annual_bess_capital_cost", "annual_bess_om_cost", "annualized_bess_cost",
    "annual_curtailment_cost", "annual_shedding_cost", "curtailment_energy_kwh",
    "load_shedding_energy_kwh", "loss_energy_kwh", "voltage_min_pu", "voltage_max_pu",
    "notes", "duration_hours",
]


def _evaluation_row(index, evaluation):
    candidate, metrics = evaluation.candidate, evaluation.metrics
    row = [index, candidate.bus_id, candidate.power_rating_kw, candidate.energy_capacity_kwh,
           evaluation.feasible, evaluation.objective, evaluation.message, metrics is not None]
    for name in ("feasible", "bess_cost", "currency", "annual_total_cost",
    "annual_grid_cost", "annual_operating_cost", "annual_bess_capital_cost",
    "annual_bess_om_cost", "annualized_bess_cost", "annual_curtailment_cost",
    "annual_shedding_cost", "curtailment_energy_kwh",
                 "load_shedding_energy_kwh", "loss_energy_kwh", "voltage_min_pu",
                 "voltage_max_pu", "notes"):
        row.append(getattr(metrics, name) if metrics is not None else None)
    row.append(candidate.energy_capacity_kwh / candidate.power_rating_kw)
    return row




def _comparison_rows(baseline, candidate):
    if not isinstance(baseline, PerformanceMetrics) or candidate is None:
        raise ValueError("Comparison needs baseline and candidate PerformanceMetrics")
    if not isclose(baseline.duration_hours, candidate.duration_hours):
        raise ValueError("Comparison durations must match")
    if baseline.currency != candidate.currency:
        raise ValueError("Comparison currencies must match")
    rows = []
    for name in COMPARISON_FIELDS:
        before, after = getattr(baseline, name), getattr(candidate, name)
        rows.append([name, _unit(name, candidate), before, after,
                     percentage_reduction(before, after), baseline.feasible, candidate.feasible])
    return rows


def _dispatch_rows(result, baseline, context):
    for index, step in enumerate(result.steps):
        event = step.dispatch
        if event is None:
            continue
        matched = baseline.steps[index] if baseline is not None else None
        row = {key: value for key, value in vars(event).items() if key != "evidence"}
        for key in ("pre", "after_bess", "final"):
            row[key] = asdict(row[key]) if row[key] else None
        row.update(step_index=index, timestamp=str(step.timestamp), run_id=context.get("Run ID"),
                   scenario=context.get("Alternative", "Simulation"),
                   source=event.source or context.get("Active input source"),
                   shedding_kw=step.shedding_kw, curtailment_kw=step.curtailment_kw,
                   soc_before=step.bess_step.soc_before if step.bess_step else None,
                   soc_after=step.bess_state.soc if step.bess_state and step.power_flow.converged else None,
                   energy_before_kwh=step.bess_step.energy_before_kwh if step.bess_step else None,
                   energy_after_kwh=step.bess_state.energy_kwh if step.bess_state and step.power_flow.converged else None,
                   messages=step.messages)
        for name in ("shedding", "curtailment"):
            actual = getattr(step, f"{name}_kw")
            counterfactual = getattr(matched, f"{name}_kw") if matched else None
            row[f"no_bess_{name}_kw"] = counterfactual
            row[f"avoided_{name}_kw"] = (counterfactual - actual
                                        if actual is not None and counterfactual is not None else None)
        yield row


def export_results(result: Result, output_path: str | Path, *,
                   metrics: PerformanceMetrics | None = None,
                   baseline_metrics: PerformanceMetrics | None = None,
                   context: Mapping[str, str] | None = None, input_snapshot=None,
                   baseline_series: TimeSeriesSimulationResult | None = None, network=None, voltage_bounds=None) -> dict[str, Path]:
    """Create a new export directory. Existing paths are never overwritten.

    Matching duration/currency is necessary, not sufficient, for a fair baseline
    comparison: the caller must use matching profiles and engineering settings.
    I/O failures propagate; summary.md is written last as the completion marker.
    """
    performance = _result_metrics(result, metrics)
    summary = format_summary(result, metrics=metrics, context=context)
    comparison = _comparison_rows(baseline_metrics, performance) if baseline_metrics is not None else None
    output = Path(output_path).resolve()
    output.mkdir(parents=True, exist_ok=False)
    written = {}
    if input_snapshot is not None:
        from .study_session import write_input_snapshot
        written.update(write_input_snapshot(output, **input_snapshot))

    def write_table(filename, header, rows):
        path = output / filename
        _write_csv(path, header, rows)
        written[filename] = path

    if performance is not None:
        write_table("metrics.csv", ["metric", "value", "unit"],
                    ([item.name, getattr(performance, item.name), _unit(item.name, performance)]
                     for item in fields(performance)))
    if isinstance(result, TimeSeriesSimulationResult):
        matched = (baseline_series if baseline_series is not None and
                   baseline_series.dt_hours == result.dt_hours and
                   [step.timestamp for step in baseline_series.steps] == [step.timestamp for step in result.steps]
                   else None)
        if any(step.dispatch is not None for step in result.steps):
            path = output / "dispatch_events.jsonl"
            with path.open("w", encoding="utf-8") as stream:
                for row in _dispatch_rows(result, matched, context or {}):
                    json.dump(row, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                    stream.write("\n")
            written[path.name] = path
            from .control_audit import ledger_hours
            ledger = output / "control_decisions.jsonl"
            with ledger.open("x", encoding="utf-8") as stream:
                for hour in ledger_hours(result, context or {}):
                    stream.write(json.dumps(hour, separators=(",", ":"), allow_nan=False) + "\n")
            written[ledger.name] = ledger
        if any(getattr(step, "fleet_steps", None) for step in result.steps):
            write_table("fleet_hourly.csv", ["step_index", "timestamp", "bus_id", "power_kw",
                        "soc_before", "soc_after", "energy_after_kwh", "limited", "limit_reason",
                        "reactive_power_kvar"],
                        ([index, str(step.timestamp), bus, unit.actual_power_kw,
                          unit.soc_before, unit.soc_after, unit.energy_after_kwh,
                          unit.limited, unit.limit_reason,
                          step.operating_point.q_bess_kvar.get(bus, 0.)]
                         for index, step in enumerate(result.steps)
                         for bus, unit in sorted((step.fleet_steps or {}).items())))
        if result.dispatch_timing.get('fleet_dispatch_mode') == 'daily_milp_dispatch':
            from math import acos, tan
            pf = float(result.dispatch_timing.get('minimum_discharge_pf',
                 (context or {}).get('Simulation settings', {}).get('minimum_discharge_pf', 0.95)
                 if isinstance((context or {}).get('Simulation settings', {}), dict) else 0.95))
            limit = tan(acos(pf))
            rows = []
            day_steps = result.steps
            for first in range(0, len(day_steps), 24):
                day = day_steps[first:first + 24]
                if not day or not day[0].fleet_steps:
                    continue
                for bus in sorted(day[0].fleet_steps):
                    start_soc = day[0].fleet_steps[bus].soc_before
                    end_soc = day[-1].fleet_steps[bus].soc_after
                    # Get energy capacity from first physically recorded state;
                    # every BESSState energy is available in the exported step.
                    first_unit = day[0].fleet_steps[bus]
                    capacity = (first_unit.energy_after_kwh / first_unit.soc_after
                                if first_unit.soc_after > 1e-9 else None)
                    diff_kwh = ((end_soc - start_soc) * capacity if capacity is not None else None)
                    q_invalid = 0
                    for step in day:
                        p_kw = step.operating_point.p_bess_kw.get(bus, 0.)
                        q_kvar = step.operating_point.q_bess_kvar.get(bus, 0.)
                        if q_kvar < -1e-6 or q_kvar > max(0., p_kw) * limit + 1e-5:
                            q_invalid += 1
                    tolerance = float(result.dispatch_timing.get('daily_soc_tolerance_kwh', 0.05))
                    rows.append([str(day[0].timestamp),str(day[-1].timestamp),bus,
                                 len(day),start_soc,end_soc,diff_kwh,
                                 diff_kwh is not None and abs(diff_kwh) <= tolerance,
                                 q_invalid, q_invalid == 0])
            write_table("battery_daily_audit.csv", ["first_timestamp", "last_timestamp", "bus_id",
                        "hours", "soc_start", "soc_end", "energy_difference_kwh",
                        "soc_restored", "pf_violation_hours", "pf_compliant"], rows)
        write_table("hourly.csv", [
            "step_index", "timestamp", "dt_hours", "converged", "feasible", "diagnostic_only",
            "fbs_iterations", "fbs_message", "load_input_kw", "pv_input_kw", "slack_p_kw", "slack_q_kvar",
            "loss_p_kw", "voltage_min_pu", "voltage_max_pu", "bess_request_kw", "bess_trial_power_kw",
            "bess_soc_before", "bess_accepted_soc", "bess_accepted_energy_kwh", "bess_limited",
            "bess_limit_reason", "curtailment_kw", "shedding_kw", "voltage_violation_bus_ids", "messages",
            "power_balance_residual_kw", "reactive_balance_residual_kvar", "correction_status",
            "affected_load_buses", "controller_policy_score", "physical_correction_cost_usd_per_hour",
            "bess_reactive_power_kvar", "pv_reactive_power_kvar", *SYSTEM_FIELDS, *CONSTRAINT_FIELDS,
        ], _hourly_rows(result, (context or {}).get("Economic inputs")))
        write_table("buses.csv", [
            "step_index", "timestamp", "bus_id", "converged", "step_feasible", "diagnostic_only",
            "voltage_pu", "voltage_angle_deg", "load_input_kw", "load_input_kvar", "pv_input_kw",
            "pv_input_kvar", "bess_input_kw", "bess_input_kvar", "curtailment_kw", "shedding_kw", "voltage_violation",
            "requested_load_kw", "requested_load_kvar", "shedding_kvar", "remaining_load_fraction",
            "available_pv_kw", "pre_control_voltage_pu",
            "shed_load_percent", "fully_disconnected", *BUS_FIELDS, "available_pv_kvar", "requested_load_kwh",
            "served_load_kwh", "shed_kwh", "curtailed_kwh", "shedding_cost", "curtailment_cost",
        ], _bus_rows(result, network, voltage_bounds, context))
        quality, service_buses = summarize_service(result)
        if quality:
            write_table("service_by_bus.csv", ["bus_id", "requested_energy_kwh", "served_energy_kwh",
                        "shed_energy_kwh", "served_energy_percent", "share_of_shed_energy_percent",
                        "fully_disconnected_hours", "longest_disconnection_hours"], service_buses)
        write_table("branches.csv", [
            "step_index", "timestamp", "line_id", "converged", "step_feasible", "diagnostic_only",
            "current_a", "sending_p_kw", "sending_q_kvar", "loss_p_kw", "loss_q_kvar", *BRANCH_FIELDS,
        ], _branch_rows(result, network))
    if isinstance(result, OptimizationResult):
        if result.metadata.get("fleet"):
            inverter_ratio = float(result.metadata.get('inverter_kva_per_kw', 1.0))
            write_table("fleet_units.csv", ["unit", "bus_id", "power_rating_kw", "energy_capacity_kwh", "duration_hours", "inverter_rating_kva"],
                        ([index, unit["bus_id"], unit["power_rating_kw"], unit["energy_capacity_kwh"],
                          unit["energy_capacity_kwh"]/unit["power_rating_kw"], unit["power_rating_kw"] * inverter_ratio]
                         for index, unit in enumerate(result.metadata["fleet"], 1)))
        if result.metadata.get("stages"):
            # Every placement is reranked on the annual run with the previously
            # accepted batteries. Export ALL eligible buses, not only finalists,
            # so the top-third cutoff and competing feeder areas can be audited.
            ranking_header = ["stage", "combined_rank", "bus_id", "voltage_rank",
                              "shedding_rank", "combined_score", "voltage_deficit_pu_hours",
                              "worst_pre_control_voltage_pu", "undervoltage_hours",
                              "shedding_kwh", "retained", "selected_for_installation", "electrical_lateral", "installed_lateral"]
            write_table("bus_ranking_by_stage.csv", ranking_header,
                        ([stage_row["index"], row["rank"], row["bus"],
                          row.get("voltage_rank"), row.get("shedding_rank"),
                          row.get("combined_score"), row.get("voltage_deficit_pu_hours"),
                          row.get("worst_pre_control_voltage_pu"), row.get("undervoltage_hours"),
                          row.get("local_baseline_shedding_kwh"), bool(row.get("retained")),
                          bool((stage_row.get("selected") or {}).get("bus_id") == row["bus"]),
                          row.get("lateral"), bool(row.get("installed_lateral"))]
                         for stage_row in result.metadata["stages"]
                         for row in stage_row.get("weakness_ranking", [])))
            write_table("sequential_stages.csv", ["stage", "status", "selected_bus", "candidate_count",
                         "cost_before", "cost_after", "annual_saving", "selected_lateral",
                         "shedding_improvement_percent", "voltage_improvement_percent",
                         "gwo_iterations", "gwo_stop_reason", "gwo_evaluations",
                         "representative_cache_hits", "annual_finalists_verified",
                         "annual_finalists_budget", "accepted_annual_result_reused",
                         "screening_hours_per_candidate", "annual_hours_required",
                         "cumulative_target_met", "cumulative_shedding_improvement_percent",
                         "cumulative_voltage_improvement_percent", "target_voltage_compliant_before_shedding",
                         "parallel_gwo_workers", "parallel_annual_workers", "screening_selection_policy"],
                        ([row["index"], row["status"], (row.get("selected") or {}).get("bus_id"),
                          row.get("candidate_count"), row.get("current_annual_cost"),
                          row.get("updated_annual_cost"), row.get("annual_saving_vs_previous"),
                          row.get("selected_lateral"),
                          (row.get("technical_check") or {}).get("shedding_improvement_percent"),
                          (row.get("technical_check") or {}).get("voltage_improvement_percent"),
                          row.get("screening_iterations"), row.get("gwo_stop_reason"),
                          row.get("gwo_evaluations"), row.get("screening_cache_hits"),
                          row.get("annual_finalists_verified"), row.get("annual_finalist_budget"),
                          row.get("accepted_result_reused"),
                          row.get("screening_hours_per_candidate"), row.get("annual_hours_required"),
                          row.get("cumulative_target_met"),
                          row.get("cumulative_shedding_improvement_percent"),
                          row.get("cumulative_voltage_improvement_percent"),
                          (row.get("technical_check") or {}).get("voltage_compliant_before_shedding"),
                          row.get("parallel_gwo_workers"), row.get("parallel_annual_workers"),
                          row.get("screening_selection_policy")]
                         for row in result.metadata["stages"]))
            write_table("annual_finalist_checks.csv", [
                "stage", "bus_id", "electrical_lateral", "power_kw", "energy_kwh", "annual_cost",
                "network_feasible", "technical_acceptable", "technical_reason",
                "lateral_shedding_improvement_percent", "lateral_voltage_improvement_percent",
                "screening_hours", "annual_processed_hours", "annual_expected_hours",
                "annual_coverage_percent", "verification_status", "cumulative_target_met",
                "cumulative_shedding_improvement_percent", "cumulative_voltage_improvement_percent",
                "voltage_compliant_before_shedding", "voltage_deficit_reduction_pu_hours",
                "shedding_reduction_kwh", "duration_hours"],
                ([stage_row['index'], row.get('bus'), row.get('lateral'), row.get('power_kw'),
                  row.get('energy_kwh'), row.get('annual_cost'), row.get('feasible'),
                  row.get('technical_acceptable'), row.get('technical_reason'),
                  row.get('shedding_improvement_percent'), row.get('voltage_improvement_percent'),
                  row.get('screening_hours'), row.get('annual_processed_hours'),
                  row.get('annual_expected_hours'), row.get('annual_coverage_percent'),
                  row.get('verification_status'), row.get('cumulative_target_met'),
                  row.get('cumulative_shedding_improvement_percent'),
                  row.get('cumulative_voltage_improvement_percent'),
                  row.get('voltage_compliant_before_shedding'),
                  row.get('voltage_deficit_reduction_pu_hours'),
                  row.get('shedding_reduction_kwh'),
                  row.get('energy_kwh')/row.get('power_kw') if row.get('power_kw') and row.get('energy_kwh') else None]
                 for stage_row in result.metadata['stages']
                 for row in stage_row.get('full_year_candidates', [])))
            write_table("screening_candidate_audit.csv", [
                "stage", "bus_id", "power_kw", "energy_kwh", "screening_score",
                "screening_feasible", "screening_hours", "evaluation_kind", "annual_verified", "duration_hours"],
                ([stage_row['index'], row.get('bus'), row.get('power_kw'),
                  row.get('energy_kwh'), row.get('screening_score'), row.get('screening_feasible'),
                  row.get('screening_hours'), row.get('evaluation_kind'),
                  row.get('annual_verified'),
                  row.get('energy_kwh')/row.get('power_kw') if row.get('power_kw') and row.get('energy_kwh') else None]
                 for stage_row in result.metadata['stages']
                 for row in stage_row.get('screening_candidates', [])))
            write_table("lateral_improvement_by_stage.csv", [
                "stage", "lateral", "buses", "installed_here", "shed_before_kwh", "shed_after_kwh",
                "shedding_improvement_percent", "voltage_deficit_before_pu_hours",
                "voltage_deficit_after_pu_hours", "voltage_improvement_percent"],
                ([stage_row['index'], label, ','.join(map(str, before['buses'])),
                  label == stage_row.get('selected_lateral'), before['shedding_kwh'],
                  after['shedding_kwh'],
                  (100*(before['shedding_kwh']-after['shedding_kwh'])/before['shedding_kwh']
                   if before['shedding_kwh'] > 1e-9 else None),
                  before['voltage_deficit_pu_hours'], after['voltage_deficit_pu_hours'],
                  (100*(before['voltage_deficit_pu_hours']-after['voltage_deficit_pu_hours'])/before['voltage_deficit_pu_hours']
                   if before['voltage_deficit_pu_hours'] > 1e-9 else None)]
                 for stage_row in result.metadata['stages']
                 for label, before in (stage_row.get('lateral_metrics_before') or {}).items()
                 for after in [(stage_row.get('lateral_metrics_after') or {}).get(label)]
                 if after is not None))
        write_table("evaluations.csv", EVALUATION_HEADER,
                    (_evaluation_row(index, item) for index, item in enumerate(result.evaluations)))
        write_table("convergence.csv", ["index", "axis", "best_annual_cost"],
                    ([index, result.metadata.get("history_axis", "unspecified"), value]
                     for index, value in enumerate(result.convergence_history)))
    if isinstance(result, OptimizationResult) and "no_bess_annual_cost" in result.metadata:
        baseline = result.metadata.get("no_bess_annual_cost")
        write_table("economic_comparison.csv", ["alternative", "annual_cost", "currency", "feasible", "selected"], [
            ["No BESS", baseline, performance.currency if performance else "", result.metadata.get("no_bess_feasible"),
             bool(result.metadata.get("no_bess_selected"))],
            ["Best feasible BESS", result.metadata.get("best_bess_annual_cost"),
             performance.currency if performance else "", bool(result.metadata.get("best_bess_feasible")),
             bool(result.success and result.best_candidate is not None)],
        ])
        if baseline is not None and result.success and result.metadata.get("no_bess_feasible"):
            summary += f"\nAnnual savings relative to no BESS: {baseline - result.best_objective:.6g} {performance.currency if performance else ''}/year\n"
    if comparison is not None:
        write_table("comparison.csv", ["metric", "unit", "baseline", "candidate", "reduction_percent",
                                       "baseline_feasible", "candidate_feasible"], comparison)
        summary += ("\nComparison reductions use (baseline-candidate)/baseline; negative means an increase.\n"
                    "A reduction is not automatically desirable for every quantity (e.g. grid exports).\n"
                    "Matching profiles/settings and aggregation basis must be confirmed by the caller.\n")
    summary += "\nExported tables: " + (", ".join(written) if written else "none") + "\n"
    path = output / "summary.md"
    temporary_path = output / "summary.md.tmp"
    with temporary_path.open("x", encoding="utf-8") as stream:
        stream.write(summary)
    temporary_path.rename(path)
    written["summary.md"] = path
    return written
