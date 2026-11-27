"""Control decisions on retained runs. Each hour's FBS evidence is stored once."""
from math import hypot


def constraint_evidence(network, config, checks, flows):
    """Keep measured readings for constraints violated at any of the three stages."""
    considered = ["undervoltage", "overvoltage"]
    considered.extend(name for name, limit in (("import", config.grid_import_limit_kw),
                                                ("export", config.grid_export_limit_kw)) if limit is not None)
    ratings = {line.line_id: line.ampacity_a for line in network.lines if line.ampacity_a is not None}
    if config.enforce_line_ampacity and ratings:
        considered.append("ampacity")
    keys = sorted(set().union(*(check.violations for check in checks if check)))
    records = []
    for key in keys:
        kind, _, entity = key.partition(":")
        if kind == "ampacity":
            limit, unit = ratings[entity], "A"
        elif kind.endswith("voltage"):
            limit = config.voltage_min_pu if kind == "undervoltage" else config.voltage_max_pu
            unit = "pu"
        else:
            limit = getattr(config, f"grid_{kind}_limit_kw")
            unit = "kW"
        readings = {}
        for stage, flow, check in zip(("before", "after_bess", "final"), flows, checks):
            value = None
            if flow.converged:
                if kind.endswith("voltage"):
                    value = flow.voltage_mag_pu[int(entity)]
                elif kind == "ampacity":
                    value = flow.branch_current_a[entity]
                else:
                    value = getattr(check, kind + "_kw")
            readings[stage] = dict(measured=value, excess=check.violations.get(key, 0.) if flow.converged else None)
        records.append(dict(constraint=key, type=kind, entity=entity or "grid", limit=limit, unit=unit, **readings))
    return dict(considered=considered, constraints=records)


def decisions(step):
    event = step.dispatch
    if not event:
        return []
    point = step.operating_point
    original = step.requested_point
    records = []
    solved = step.power_flow.converged

    def record(action, bus, requested, actual, unit, p=None, q=None):
        if not any(value is not None and abs(value) > 1e-9 for value in (requested, actual)):
            return
        status = ("unverified" if not solved or actual is None else "accepted" if requested is None or abs(requested - actual) < 1e-6
                  else "rejected" if abs(actual) < 1e-9 else "adjusted")
        if status == "adjusted" and requested * actual > 0 and abs(actual) < abs(requested):
            status = "clipped"
        records.append(dict(sequence=len(records) + 1, action=action, bus_id=bus,
                            requested=requested, accepted=actual if solved else None, unit=unit,
                            p_kw=p if solved else None, q_kvar=q if solved else None,
                            s_kva=hypot(p, q) if solved and p is not None and q is not None else None,
                            status=status))

    preqs = event.requested_p_by_bus or ({event.bus_id: event.request_kw} if event.bus_id is not None else {})
    for bus in sorted(point.p_bess_kw.keys() | preqs.keys()):
        p, q = point.p_bess_kw.get(bus, 0.), point.q_bess_kvar.get(bus, 0.)
        request = preqs.get(bus)
        if request and p * request < -1e-9:
            record("bess_charge" if request < 0 else "bess_discharge", bus, request, 0., "kW", 0., None)
            request = None
        record("bess_charge" if (p or request or 0.) < 0 else "bess_discharge",
               bus, request, p, "kW", p, q)
        record("bess_q", bus, event.requested_q_by_bus.get(bus), q, "kvar", p, q)
    for bus in sorted(point.p_load_kw):
        curtailed = (step.curtailment_by_bus_kw or {}).get(bus)
        q_change = point.q_pv_kvar[bus] - original.q_pv_kvar[bus] if original else None
        # A fixed-PF P correction also reduces Q. Count that change once with
        # curtailment unless the coordinated controller adjusted Q independently.
        coupled_q = (original.q_pv_kvar[bus] * curtailed / original.p_pv_kw[bus]
                     if original and curtailed and original.p_pv_kw[bus] else 0.)
        only_curtail = q_change is not None and abs(q_change + coupled_q) <= 1e-9
        if not only_curtail:
            record("pv_q", bus, None, q_change, "kvar", point.p_pv_kw[bus], point.q_pv_kvar[bus])
        record("load_shed", bus, None, (step.shedding_by_bus_kw or {}).get(bus), "kW",
               (step.shedding_by_bus_kw or {}).get(bus),
               original.q_load_kvar[bus] - point.q_load_kvar[bus] if original else None)
        record("pv_curtail", bus, None, curtailed, "kW", curtailed, coupled_q if only_curtail else None)
    return records


def ledger_hours(result, context):
    for index, step in enumerate(result.steps):
        event = step.dispatch
        if not event:
            continue
        actions = decisions(step)
        if not actions and step.feasible and event.policy != "uncontrolled-fbs":
            continue
        checks = {name: dict(violations=dict(check.violations), binding=check.binding, converged=check.converged)
                  for name, check in (("before", event.pre), ("after_bess", event.after_bess), ("final", event.final))
                  if check}
        triggers = sorted({key for check in checks.values() for key in check["violations"]})
        yield dict(schema_version=2, run_id=context.get("Run ID"), scenario=context.get("Alternative", "Simulation"),
                   timestamp=str(step.timestamp), step_index=index, dt_hours=result.dt_hours,
                   policy=event.policy, source=event.source, reason_codes=event.reason_codes, triggers=triggers,
                   messages=step.messages, sequence_basis="retained net actions within the hour",
                   attribution="reason_not_unique" if len(triggers) > 1 or len(actions) > 1 else
                               "observed_constraint" if triggers else "policy" if event.reason_codes else "unknown",
                   converged=step.power_flow.converged, feasible=step.feasible,
                   correction_status=(event.correction or {}).get("status"),
                   outcome="feasible" if step.feasible else "unresolved", stages=checks, **event.evidence,
                   actions=actions)

