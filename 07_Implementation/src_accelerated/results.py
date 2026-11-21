"""Readable summaries and CSV exports; no simulation or optimization equations."""
import csv
from dataclasses import asdict, fields
from math import isclose
from pathlib import Path
from collections.abc import Mapping
import json

from .metrics import (PerformanceMetrics, load_service, percentage_reduction, service_verified,
                      summarize_service)
from .optimizer import OptimizationResult
from .simulation import TimeSeriesSimulationResult


Result = TimeSeriesSimulationResult | PerformanceMetrics | OptimizationResult

COMPARISON_FIELDS = (
    "annual_capital_recovery", "annual_fixed_om", "annual_grid_purchases", "annual_export_credit",
    "bess_cost", "annual_total_cost", "annualized_bess_cost", "annual_grid_cost",
    "annual_curtailment_cost", "annual_shedding_cost", "curtailment_energy_kwh", "load_shedding_energy_kwh",
    "loss_energy_kwh", "grid_import_energy_kwh", "grid_export_energy_kwh",
    "peak_grid_import_kw", "voltage_violation_hours", "reserve_violation_hours",
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
    if name.startswith("annual_") and name not in ("annualization_basis",):
        return metrics.currency + "/year"
    if name in ("bess_cost", "annual_total_cost", "annualized_bess_cost",
                "annual_grid_cost", "annual_curtailment_cost", "annual_shedding_cost",
                "annual_terminal_energy_cost"):
        return metrics.currency
    for suffix, unit in (("_bus_hours", "bus-hours"), ("_hours", "h"),
                         ("_kwh", "kWh"), ("_kw", "kW"), ("_pu", "pu")):
        if name.endswith(suffix):
            return unit
    if name in ("bess_soc_min", "bess_soc_max"):
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
        if result.best_candidate is not None:
            candidate = result.best_candidate
            lines.extend([f"Selected bus: {candidate.bus_id}",
                          f"Battery power: {candidate.power_rating_kw:g} kW",
                          f"Battery energy: {candidate.energy_capacity_kwh:g} kWh"])
        else:
            lines.append("No battery installed (economic no-BESS selection)." if result.metadata.get("no_bess_selected")
                         else "No feasible battery selected.")
        for key, value in sorted(result.metadata.items()):
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


def _hourly_rows(result):
    for index, step in enumerate(result.steps):
        flow, point, battery = step.power_flow, step.operating_point, step.bess_step
        correction = step.dispatch.correction if step.dispatch else None
        verified = service_verified(step)
        affected = sum(value > 1e-6 for value in (step.shedding_by_bus_kw or {}).values()) if verified else None
        balance_p = (flow.slack_p_kw + sum(point.p_pv_kw.values()) + sum(point.p_bess_kw.values())
                     - sum(point.p_load_kw.values()) - flow.total_loss_p_kw) if flow.converged else None
        balance_q = (flow.slack_q_kvar + sum(point.q_pv_kvar.values()) + sum(point.q_bess_kvar.values())
                     - sum(point.q_load_kvar.values()) - flow.total_loss_q_kvar) if flow.converged else None
        yield [
            index, str(step.timestamp), result.dt_hours, flow.converged, step.feasible,
            not flow.converged, flow.iterations, flow.message,
            sum(point.p_load_kw.values()), sum(point.p_pv_kw.values()),
            flow.slack_p_kw, flow.slack_q_kvar, flow.total_loss_p_kw,
            min(flow.voltage_mag_pu.values(), default=None), max(flow.voltage_mag_pu.values(), default=None),
            step.bess_request_kw, battery.actual_power_kw if battery is not None else None,
            battery.soc_before if battery is not None else None,
            step.bess_state.soc if step.bess_state is not None else None,
            step.bess_state.energy_kwh if step.bess_state is not None else None,
            battery.limited if battery is not None else None,
            battery.limit_reason if battery is not None else None,
            step.curtailment_kw, step.shedding_kw, step.reserve_power_kw,
            step.reserve_power_shortfall_kw, step.reserve_energy_shortfall_kwh,
            sorted(step.voltage_violations), step.messages,
            balance_p, balance_q, (correction or {}).get("status"),
            affected, (correction or {}).get("policy_score"), (correction or {}).get("objective_usd"),
        ]


def _bus_rows(result):
    for index, step in enumerate(result.steps):
        point, flow = step.operating_point, step.power_flow
        requested = step.requested_point
        verified = service_verified(step)
        for bus_id in sorted(point.p_load_kw):
            requested_p = requested.p_load_kw[bus_id] if requested else None
            requested_q = requested.q_load_kvar[bus_id] if requested else None
            served = flow.converged
            fraction, disconnected = load_service(requested_p, point.p_load_kw[bus_id] if verified else None)
            yield [index, str(step.timestamp), bus_id, flow.converged, step.feasible,
                   not flow.converged, flow.voltage_mag_pu.get(bus_id), flow.voltage_angle_deg.get(bus_id),
                   point.p_load_kw[bus_id], point.q_load_kvar[bus_id],
                   point.p_pv_kw[bus_id], point.q_pv_kvar[bus_id],
                   point.p_bess_kw[bus_id], point.q_bess_kvar[bus_id],
                   step.curtailment_by_bus_kw.get(bus_id) if step.curtailment_by_bus_kw is not None else None,
                   step.shedding_by_bus_kw.get(bus_id) if step.shedding_by_bus_kw is not None else None,
                   bus_id in step.voltage_violations if served else None,
                   requested_p, requested_q,
                   requested_q - point.q_load_kvar[bus_id] if served and requested else None,
                   point.p_load_kw[bus_id] / requested_p if served and requested_p else None,
                   requested.p_pv_kw[bus_id] if requested else None,
                   (step.pre_control_voltage_pu or {}).get(bus_id),
                   (1. - fraction) * 100. if fraction is not None else None, disconnected]


def _branch_rows(result):
    for index, step in enumerate(result.steps):
        flow = step.power_flow
        for line_id in sorted(flow.branch_current_a):
            yield [index, str(step.timestamp), line_id, flow.converged, step.feasible,
                   not flow.converged, flow.branch_current_a[line_id],
                   flow.branch_p_kw.get(line_id), flow.branch_q_kvar.get(line_id),
                   flow.line_loss_p_kw.get(line_id), flow.line_loss_q_kvar.get(line_id)]


EVALUATION_HEADER = [
    "evaluation_index", "bus_id", "power_rating_kw", "energy_capacity_kwh", "feasible",
    "annual_cost", "message", "metrics_available", "metrics_feasible", "bess_cost", "currency",
    "annual_total_cost", "annualized_bess_cost", "annual_grid_cost",
    "annual_curtailment_cost", "annual_shedding_cost", "curtailment_energy_kwh",
    "load_shedding_energy_kwh", "loss_energy_kwh", "voltage_min_pu", "voltage_max_pu",
    "reserve_violation_hours", "notes",
]


def _evaluation_row(index, evaluation):
    candidate, metrics = evaluation.candidate, evaluation.metrics
    row = [index, candidate.bus_id, candidate.power_rating_kw, candidate.energy_capacity_kwh,
           evaluation.feasible, evaluation.objective, evaluation.message, metrics is not None]
    for name in ("feasible", "bess_cost", "currency", "annual_total_cost", "annualized_bess_cost",
    "annual_grid_cost", "annual_curtailment_cost", "annual_shedding_cost", "curtailment_energy_kwh",
                 "load_shedding_energy_kwh", "loss_energy_kwh", "voltage_min_pu",
                 "voltage_max_pu", "reserve_violation_hours", "notes"):
        row.append(getattr(metrics, name) if metrics is not None else None)
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
        row = asdict(event)
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
                   baseline_series: TimeSeriesSimulationResult | None = None) -> dict[str, Path]:
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
        write_table("hourly.csv", [
            "step_index", "timestamp", "dt_hours", "converged", "feasible", "diagnostic_only",
            "fbs_iterations", "fbs_message", "load_input_kw", "pv_input_kw", "slack_p_kw", "slack_q_kvar",
            "loss_p_kw", "voltage_min_pu", "voltage_max_pu", "bess_request_kw", "bess_trial_power_kw",
            "bess_soc_before", "bess_accepted_soc", "bess_accepted_energy_kwh", "bess_limited",
            "bess_limit_reason", "curtailment_kw", "shedding_kw", "reserve_power_kw",
            "reserve_power_shortfall_kw", "reserve_energy_shortfall_kwh", "voltage_violation_bus_ids", "messages",
            "power_balance_residual_kw", "reactive_balance_residual_kvar", "correction_status",
            "affected_load_buses", "controller_policy_score", "physical_correction_cost_usd_per_hour",
        ], _hourly_rows(result))
        write_table("buses.csv", [
            "step_index", "timestamp", "bus_id", "converged", "step_feasible", "diagnostic_only",
            "voltage_pu", "voltage_angle_deg", "load_input_kw", "load_input_kvar", "pv_input_kw",
            "pv_input_kvar", "bess_input_kw", "bess_input_kvar", "curtailment_kw", "shedding_kw", "voltage_violation",
            "requested_load_kw", "requested_load_kvar", "shedding_kvar", "remaining_load_fraction",
            "available_pv_kw", "pre_control_voltage_pu",
            "shed_load_percent", "fully_disconnected",
        ], _bus_rows(result))
        quality, service_buses = summarize_service(result)
        if quality:
            write_table("service_by_bus.csv", ["bus_id", "requested_energy_kwh", "served_energy_kwh",
                        "shed_energy_kwh", "served_energy_percent", "share_of_shed_energy_percent",
                        "fully_disconnected_hours", "longest_disconnection_hours"], service_buses)
        write_table("branches.csv", [
            "step_index", "timestamp", "line_id", "converged", "step_feasible", "diagnostic_only",
            "current_a", "sending_p_kw", "sending_q_kvar", "loss_p_kw", "loss_q_kvar",
        ], _branch_rows(result))
    if isinstance(result, OptimizationResult):
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
