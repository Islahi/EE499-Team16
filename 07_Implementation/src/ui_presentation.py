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
    metrics = getattr(report, "metrics", None) or getattr(result,"metrics",None)
    context = getattr(report, "context", {})
    # Base-case FBS returns a power-flow object and has a compact native summary.
    if not hasattr(result, "steps") and not hasattr(result, "best_objective"):
        return report.summary(detailed=False)
    lines = ["RESULTS", ""]
    if hasattr(result, "best_objective"):
        lines.append("Optimization" + ("  ·  Complete" if result.success else "  ·  Not successful"))
        candidate = result.best_candidate
        fleet = getattr(result, "metadata", {}).get("fleet") or []
        if fleet:
            lines.append(f"BESS installed         {len(fleet)} units")
            for index, unit in enumerate(fleet, 1):
                lines.append(f"  Unit {index}: Bus {unit['bus_id']} · {_number(unit['power_rating_kw'], 'kW')} / {_number(unit['energy_capacity_kwh'], 'kWh')}")
        elif candidate is not None:
            lines.extend([
                f"Selected bus          B{candidate.bus_id}",
                f"Battery power         {_number(candidate.power_rating_kw, 'kW')}",
                f"Battery capacity      {_number(candidate.energy_capacity_kwh, 'kWh')}",
            ])
        elif getattr(result, "metadata", {}).get("no_bess_selected"):
            lines.append("Best option            No BESS")
            if getattr(result, "message", None):
                lines.append(result.message)
        else:
            lines.append("Best option            No feasible battery selected")
        if getattr(result, "best_objective", None) is not None:
            currency = getattr(metrics, "currency", "") if metrics else ""
            lines.append(f"Annual objective       {_number(result.best_objective, currency + '/year' if currency else '')}")
        algorithm = context.get("Optimizer algorithm")
        if algorithm:
            lines.append(f"Algorithm              {algorithm}")
    else:
        lines.extend([
            "Manual BESS simulation" if context.get("Manual BESS") else "No-BESS simulation",
            "Status                 " + ("Completed" if result.completed else "Incomplete"),
            "Power flow             " + ("Converged" if result.converged else "Not converged"),
            f"Simulation hours       {_number(len(result.steps) * result.dt_hours, 'h')}",
        ])
    if metrics is not None:
        lines.extend([
            "", "PERFORMANCE", "",
            "Feasibility            " + ("Feasible" if metrics.feasible else "Infeasible"),
        ])
        for name,label in (("bess_cost","Initial BESS investment (USD)"),
                           ("annual_bess_capital_cost","Annual BESS capital recovery"),
                           ("annual_bess_om_cost","Annual BESS operation and maintenance"),
                           ("annualized_bess_cost","Annual BESS ownership"),
                           ("annual_operating_cost","Annual grid and penalties"),
                           ("annual_grid_purchases","Annual grid purchases"),("annual_export_credit","Annual export credit"),
                           ("annual_curtailment_cost","Annual curtailment"),("annual_shedding_cost","Annual shedding")):
            value = getattr(metrics,name,None)
            if value is not None: lines.append(label+"    "+_number(value,metrics.currency if name=="bess_cost" else metrics.currency+"/year"))
        delta = getattr(result,"metadata",{}).get("delta_annual_cost")
        if delta is not None: lines.append("Annual delta vs no BESS    "+_number(delta,metrics.currency+"/year"))
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
        outage_hours = getattr(metrics, "hours_with_full_disconnection", None)
        if outage_hours is not None:
            lines.append("Hours with a fully disconnected load bus: " + _number(outage_hours, "h"))
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
