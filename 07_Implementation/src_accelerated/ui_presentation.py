"""Compact UI-only summaries. Does not alter simulation or saved report exports."""


def _number(value, unit=""):
    if value is None:
        return "Not available"
    try:
        return f"{value:,.2f}{(' ' + unit) if unit else ''}"
    except (ValueError, TypeError):
        return str(value)


def compact_summary(report):
    """Show essential results first; the original detailed summary remains available."""
    if report is None:
        return "No results yet. Load data and run a simulation or optimization."
    result = report.result
    metrics = getattr(report, "metrics", None)
    context = getattr(report, "context", {})
    # Base-case FBS returns a power-flow object and has a compact native summary.
    if not hasattr(result, "steps") and not hasattr(result, "best_objective"):
        return report.summary(detailed=False)
    lines = ["RESULTS", ""]
    if hasattr(result, "best_objective"):
        lines.append("Optimization" + ("  ·  Complete" if result.success else "  ·  Not successful"))
        candidate = result.best_candidate
        if candidate is not None:
            lines.extend([
                f"Selected bus          B{candidate.bus_id}",
                f"Battery power         {_number(candidate.power_rating_kw, 'kW')}",
                f"Battery capacity      {_number(candidate.energy_capacity_kwh, 'kWh')}",
            ])
        elif getattr(result, "metadata", {}).get("no_bess_selected"):
            lines.append("Best option            No BESS")
        else:
            lines.append("Best option            No feasible battery selected")
        if getattr(result, "best_objective", None) is not None:
            currency = getattr(metrics, "currency", "") if metrics else ""
            lines.append(f"Annual objective       {_number(result.best_objective, currency + '/year' if currency else '')}")
        algorithm = context.get("Optimization settings", "")
        if algorithm:
            # Do not attempt to parse the internal dict; show user-facing algorithm name when available.
            if "'optimizer_algorithm': 'GA'" in algorithm or '"optimizer_algorithm": "GA"' in algorithm:
                lines.append("Algorithm              GA")
            elif "'optimizer_algorithm': 'GWO'" in algorithm or '"optimizer_algorithm": "GWO"' in algorithm:
                lines.append("Algorithm              GWO")
    else:
        lines.extend([
            "Hourly simulation",
            "Status                 " + ("Completed" if result.completed else "Incomplete"),
            "Power flow             " + ("Converged" if result.converged else "Not converged"),
            f"Simulation hours       {_number(len(result.steps) * result.dt_hours, 'h')}",
        ])
    if metrics is not None:
        lines.extend([
            "", "PERFORMANCE", "",
            "Feasibility            " + ("Feasible" if metrics.feasible else "Infeasible"),
        ])
        if metrics.annual_total_cost is not None:
            lines.append("Annual total cost      " + _number(metrics.annual_total_cost, metrics.currency + "/year"))
        if metrics.annual_grid_cost is not None:
            lines.append("Annual grid cost       " + _number(metrics.annual_grid_cost, metrics.currency + "/year"))
        if metrics.grid_import_energy_kwh is not None:
            lines.append("Grid import            " + _number(metrics.grid_import_energy_kwh, "kWh"))
        if metrics.loss_energy_kwh is not None:
            lines.append("Network losses         " + _number(metrics.loss_energy_kwh, "kWh"))
        if metrics.load_shedding_energy_kwh is not None:
            lines.append("Load shedding          " + _number(metrics.load_shedding_energy_kwh, "kWh"))
        if metrics.curtailment_energy_kwh is not None:
            lines.append("PV curtailment         " + _number(metrics.curtailment_energy_kwh, "kWh"))
    elif hasattr(result, "best_objective"):
        lines.extend(["", "No feasible performance metrics were retained."])
    if context.get("Network"):
        lines.extend(["", "Network: " + context["Network"]])
    if context.get("Run duration"):
        lines.append("Elapsed: " + context["Run duration"])
    lines.extend(["", "Select 'Show full details' for all metrics, assumptions and warnings."])
    return "\n".join(lines)
