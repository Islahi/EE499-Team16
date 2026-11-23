"""Fast radial feeder voltage-aware P/Q sensitivity and legacy P dispatch.

Use linearized R-path and X-path sensitivities only to propose bounded injections.
Every proposed joint action is checked by the original nonlinear FBS solver.
"""
from .bess import step_bess


class VoltageSupport:
    def __init__(self, network):
        order = network.radial_order()
        lines = {line.line_id: line for line in network.lines}
        slack = order.slack_bus_id
        r_paths = {slack: {}}
        x_paths = {slack: {}}
        for bus in order.parent_bus_by_bus:
            parent = order.parent_bus_by_bus[bus]
            # radial_order uses parent-first traversal for the IEEE network.
            if parent not in r_paths:
                cursor, chain = parent, []
                while cursor not in r_paths:
                    chain.append(cursor)
                    cursor = order.parent_bus_by_bus[cursor]
                for entry in reversed(chain):
                    upper = order.parent_bus_by_bus[entry]
                    lid = order.parent_line_by_bus[entry]
                    r_paths[entry] = {**r_paths[upper], lid: lines[lid].r_ohm}
                    x_paths[entry] = {**x_paths[upper], lid: lines[lid].x_ohm}
            lid = order.parent_line_by_bus[bus]
            r_paths[bus] = {**r_paths[parent], lid: lines[lid].r_ohm}
            x_paths[bus] = {**x_paths[parent], lid: lines[lid].x_ohm}
        kv = next(bus.base_kv for bus in network.buses if bus.bus_id == slack)
        denom = 1000. * kv ** 2
        self.sensitivity = {
            candidate: {
                observed: (sum(resistance for line, resistance in r_paths[candidate].items()
                               if line in r_paths[observed]) / denom)
                for observed in r_paths
            }
            for candidate in r_paths if candidate != slack
        }
        self.x_sensitivity = {
            candidate: {
                observed: (sum(reactance for line, reactance in x_paths[candidate].items()
                               if line in x_paths[observed]) / denom)
                for observed in x_paths
            }
            for candidate in x_paths if candidate != slack
        }

    def dispatch(self, flow, configs, states, settings):
        """Return per-BESS requested kW, prioritizing marginal voltage relief.

        Charging remains conservative: restore to configured SOC MAX only at
        comfortable voltages with spare grid-import capacity. No mandatory
        year-end energy closure is imposed.
        """
        requests = {c.bus_id: 0.0 for c in configs}
        if not flow.converged:
            return requests, 'power-flow nonconvergence'
        volts = flow.voltage_mag_pu
        deficits = {bus: settings.voltage_min_pu - v for bus, v in volts.items()
                    if v < settings.voltage_min_pu - 1e-8}
        import_need = max(0., flow.slack_p_kw - settings.grid_import_limit_kw) if settings.grid_import_limit_kw is not None else 0.
        headrooms = {c.bus_id: max(0., step_bess(c, states[c.bus_id], c.power_rating_kw, 1.).actual_power_kw)
                     for c in configs}
        if deficits or import_need > 1e-7:
            # Gradual allocation permits another battery to take over when its
            # shared-path resistance gives a larger benefit to critical buses.
            remaining = headrooms.copy()
            increment = max(1., sum(headrooms.values()) / 28.)
            for _ in range(120):
                if (not any(d > 2e-5 for d in deficits.values()) and import_need <= 1e-5) or not any(v > 1e-7 for v in remaining.values()):
                    break
                possibilities = []
                for bus, headroom in remaining.items():
                    if headroom <= 1e-8:
                        continue
                    step = min(headroom, increment)
                    gain = sum(d*d - max(0., d - self.sensitivity[bus].get(target, 0.) * step)**2
                               for target, d in deficits.items())
                    # If any import relief is required, all discharge helps it.
                    score = gain / step + (1e-6 if import_need > 1e-5 else 0.)
                    possibilities.append((score, bus, step))
                if not possibilities:
                    break
                score, bus, step = max(possibilities, key=lambda row: (row[0], -row[1]))
                if score <= 1e-12 and import_need <= 1e-5:
                    break
                requests[bus] += step
                remaining[bus] -= step
                import_need = max(0., import_need - step)
                deficits = {target: max(0., d - self.sensitivity[bus].get(target, 0.) * step)
                            for target, d in deficits.items()}
            return requests, 'voltage/import sensitivity dispatch'
        if (settings.grid_export_limit_kw is not None and
                -flow.slack_p_kw > settings.grid_export_limit_kw):
            required = -flow.slack_p_kw - settings.grid_export_limit_kw
        elif max(volts.values()) > settings.voltage_max_pu:
            required = sum(c.power_rating_kw for c in configs)
        else:
            required = 0.
        # Restore toward SOC MAX, not initial SOC. Avoid charging near the
        # undervoltage threshold and reserve explicit grid-import headroom.
        safe_for_recharge = min(volts.values()) >= settings.voltage_min_pu + 0.015
        if not required and safe_for_recharge:
            required = sum(max(0., (c.energy_capacity_kwh * c.soc_max - states[c.bus_id].energy_kwh) / c.eta_charge)
                           for c in configs)
            if settings.grid_import_limit_kw is not None:
                required = min(required, max(0., settings.grid_import_limit_kw - max(0., flow.slack_p_kw)))
        if required > 1e-8 and (safe_for_recharge or max(volts.values()) > settings.voltage_max_pu):
            # Sequential allocation is deterministic; SOC headroom is enforced
            # through step_bess and the downstream nonlinear FBS safeguard.
            for c in sorted(configs, key=lambda c: (states[c.bus_id].soc, c.bus_id)):
                if required <= 1e-8:
                    break
                accepted = -step_bess(c, states[c.bus_id], -required, 1.).actual_power_kw
                requests[c.bus_id] = -accepted
                required -= accepted
            return requests, 'safe recharge / overvoltage absorb'
        return requests, 'no safe request'
