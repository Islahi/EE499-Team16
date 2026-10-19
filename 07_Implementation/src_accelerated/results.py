"""Readable summaries and CSV exports; no simulation or optimization equations."""
import csv
from dataclasses import fields
from math import isclose
from pathlib import Path
from collections.abc import Mapping

from .metrics import PerformanceMetrics, percentage_reduction
from .optimizer import OptimizationResult
from .simulation import TimeSeriesSimulationResult


Result = TimeSeriesSimulationResult | PerformanceMetrics | OptimizationResult

COMPARISON_FIELDS = (
    "bess_cost", "curtailment_energy_kwh", "load_shedding_energy_kwh",
    "loss_energy_kwh", "grid_import_energy_kwh", "grid_export_energy_kwh",
    "peak_grid_import_kw", "voltage_violation_hours", "reserve_violation_hours",
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
            if supplied.feasible != (result.feasible and all(step.feasible for step in result.steps)):
                raise ValueError("Metrics feasibility does not match the simulation")
        return supplied
    if supplied is not None:
        raise ValueError("Only simulation results accept a separate metrics argument")
    if isinstance(result, OptimizationResult):
        if result.success and result.best_candidate is None:
            raise ValueError("Successful optimization must have a best candidate")
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
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in context.items()):
        raise TypeError("Context keys/values must be strings; describe settings explicitly")
    return sorted(context.items())


def _display(value):
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return f"{value:.8g}"
    if isinstance(value, list):
        return " | ".join(str(item) for item in value) if value else "none"
    return str(value)


def _unit(name, metrics):
    if name == "bess_cost":
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
                      f"Best raw WSM: {_display(result.best_objective)}"])
        if result.best_candidate is not None:
            candidate = result.best_candidate
            lines.extend([f"Selected bus: {candidate.bus_id}",
                          f"Battery power: {candidate.power_rating_kw:g} kW",
                          f"Battery energy: {candidate.energy_capacity_kwh:g} kWh"])
        else:
            lines.append("No feasible battery selected.")
        for key, value in sorted(result.metadata.items()):
            lines.append(f"Optimizer {key}: {_display(value)}")
        lines.append("Raw WSM mixes cost and energy units; this is not a normalized economic cost.")
        lines.append("The chosen battery is best among evaluated candidates, not a global-optimum guarantee.")
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
        ]


def _bus_rows(result):
    for index, step in enumerate(result.steps):
        point, flow = step.operating_point, step.power_flow
        for bus_id in sorted(point.p_load_kw):
            yield [index, str(step.timestamp), bus_id, flow.converged, step.feasible,
                   not flow.converged, flow.voltage_mag_pu.get(bus_id), flow.voltage_angle_deg.get(bus_id),
                   point.p_load_kw[bus_id], point.q_load_kvar[bus_id],
                   point.p_pv_kw[bus_id], point.q_pv_kvar[bus_id],
                   point.p_bess_kw[bus_id], point.q_bess_kvar[bus_id],
                   step.curtailment_by_bus_kw.get(bus_id) if step.curtailment_by_bus_kw is not None else None,
                   step.shedding_by_bus_kw.get(bus_id) if step.shedding_by_bus_kw is not None else None,
                   bus_id in step.voltage_violations if flow.converged else None]


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
    "raw_wsm", "message", "metrics_available", "metrics_feasible", "bess_cost", "currency",
    "curtailment_energy_kwh", "load_shedding_energy_kwh", "loss_energy_kwh",
    "voltage_min_pu", "voltage_max_pu", "reserve_violation_hours", "notes",
]


def _evaluation_row(index, evaluation):
    candidate, metrics = evaluation.candidate, evaluation.metrics
    row = [index, candidate.bus_id, candidate.power_rating_kw, candidate.energy_capacity_kwh,
           evaluation.feasible, evaluation.objective, evaluation.message, metrics is not None]
    for name in ("feasible", "bess_cost", "currency", "curtailment_energy_kwh",
                 "load_shedding_energy_kwh", "loss_energy_kwh", "voltage_min_pu",
                 "voltage_max_pu", "reserve_violation_hours", "notes"):
        row.append(getattr(metrics, name) if metrics is not None else None)
    return row


def _scenario_rows(result):
    for index, evaluation in enumerate(result.evaluations):
        # ScenarioCandidateEvaluation extends the ordinary evaluation contract.
        for scenario_id, case in sorted(getattr(evaluation, "scenario_evaluations", {}).items()):
            yield [scenario_id] + _evaluation_row(index, case)


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


def export_results(result: Result, output_path: str | Path, *,
                   metrics: PerformanceMetrics | None = None,
                   baseline_metrics: PerformanceMetrics | None = None,
                   context: Mapping[str, str] | None = None) -> dict[str, Path]:
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

    def write_table(filename, header, rows):
        path = output / filename
        _write_csv(path, header, rows)
        written[filename] = path

    if performance is not None:
        write_table("metrics.csv", ["metric", "value", "unit"],
                    ([item.name, getattr(performance, item.name), _unit(item.name, performance)]
                     for item in fields(performance)))
    if isinstance(result, TimeSeriesSimulationResult):
        write_table("hourly.csv", [
            "step_index", "timestamp", "dt_hours", "converged", "feasible", "diagnostic_only",
            "fbs_iterations", "fbs_message", "load_input_kw", "pv_input_kw", "slack_p_kw", "slack_q_kvar",
            "loss_p_kw", "voltage_min_pu", "voltage_max_pu", "bess_request_kw", "bess_trial_power_kw",
            "bess_soc_before", "bess_accepted_soc", "bess_accepted_energy_kwh", "bess_limited",
            "bess_limit_reason", "curtailment_kw", "shedding_kw", "reserve_power_kw",
            "reserve_power_shortfall_kw", "reserve_energy_shortfall_kwh", "voltage_violation_bus_ids", "messages",
        ], _hourly_rows(result))
        write_table("buses.csv", [
            "step_index", "timestamp", "bus_id", "converged", "step_feasible", "diagnostic_only",
            "voltage_pu", "voltage_angle_deg", "load_input_kw", "load_input_kvar", "pv_input_kw",
            "pv_input_kvar", "bess_input_kw", "bess_input_kvar", "curtailment_kw", "shedding_kw", "voltage_violation",
        ], _bus_rows(result))
        write_table("branches.csv", [
            "step_index", "timestamp", "line_id", "converged", "step_feasible", "diagnostic_only",
            "current_a", "sending_p_kw", "sending_q_kvar", "loss_p_kw", "loss_q_kvar",
        ], _branch_rows(result))
    if isinstance(result, OptimizationResult):
        write_table("evaluations.csv", EVALUATION_HEADER,
                    (_evaluation_row(index, item) for index, item in enumerate(result.evaluations)))
        write_table("convergence.csv", ["index", "axis", "best_so_far_raw_wsm"],
                    ([index, result.metadata.get("history_axis", "unspecified"), value]
                     for index, value in enumerate(result.convergence_history)))
        if any(getattr(item, "scenario_evaluations", {}) for item in result.evaluations):
            write_table("scenario_evaluations.csv", ["scenario_id"] + EVALUATION_HEADER, _scenario_rows(result))
            summary += "\nOnly retained/evaluated cases are exported; rejected candidates may stop at the first failed case.\n"
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
