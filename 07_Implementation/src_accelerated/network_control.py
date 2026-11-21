"""Bus-specific load shedding and PV curtailment for the radial FBS solver."""
from dataclasses import dataclass, replace
from math import sqrt
from time import perf_counter
from warnings import catch_warnings, simplefilter

import numpy as np
from scipy.linalg import LinAlgWarning, solve as solve_linear
from scipy.optimize import linprog

from .constraint_dispatch import check_flow


@dataclass
class Correction:
    status: str = "not_needed"
    iterations: int = 0
    fbs_trials: int = 0
    seconds: float = 0.0
    linear_status: str | None = None
    objective_usd: float | None = None


class NetworkCorrector:
    """Reuse the fixed feeder constraints across all hours of one simulation."""

    def __init__(self, network, settings, solve):
        self.network = network
        self.settings = settings
        self.solve = solve
        self.slack = network.slack_bus_id()
        self.buses = tuple(sorted(bus.bus_id for bus in network.buses if bus.bus_id != self.slack))
        self.lines = tuple((line.line_id, line.ampacity_a) for line in network.lines
                           if settings.enforce_line_ampacity and line.ampacity_a is not None)
        order = network.radial_order()
        line_by_id = {line.line_id: line for line in network.lines}
        line_index = {line_id: i for i, line_id in enumerate(order.forward_line_ids)}
        slack = next(bus for bus in network.buses if bus.bus_id == self.slack)
        self.base_power = network.base_power_kva
        self.base_current = self.base_power / (sqrt(3) * slack.base_kv)
        base_impedance = slack.base_kv ** 2 / (self.base_power / 1000)
        impedance = np.array([complex(line_by_id[line_id].r_ohm, line_by_id[line_id].x_ohm)
                              for line_id in line_index]) / base_impedance
        self.bus_index = {bus: index for index, bus in enumerate(self.buses)}
        self.downstream = np.zeros((len(line_index), len(self.buses)))
        for bus, index in self.bus_index.items():
            child = bus
            while child != self.slack:
                self.downstream[line_index[order.parent_line_by_bus[child]], index] = 1.
                child = order.parent_bus_by_bus[child]
        self.impedance = (self.downstream.T * impedance) @ self.downstream
        self.rated_indices = [line_index[line] for line, _ in self.lines]
        self.evaluations = 0
        self.trials = 0
        self.seconds = 0.0
        self.unresolved = 0

    def sensitivities(self, flow, point, actions):
        """Differentiate the converged current-summation FBS equations in kW."""
        voltage = np.array([flow.voltage_complex_pu[bus] for bus in self.buses])
        demand = np.array([complex(point.p_load_kw[bus] - point.p_pv_kw[bus] - point.p_bess_kw[bus],
                                   point.q_load_kvar[bus] - point.q_pv_kvar[bus] - point.q_bess_kvar[bus])
                           for bus in self.buses]) / self.base_power
        direction = np.zeros((len(self.buses), len(actions)), dtype=complex)
        slack_kw = np.zeros(len(actions))
        for i, (group, bus, p, q, _) in enumerate(actions):
            delta = complex(1., q / p) * (-1 if group == 0 else 1)
            if bus == self.slack:
                slack_kw[i] = delta.real
            else:
                direction[self.bus_index[bus], i] = delta / self.base_power

        # V = V_slack - Zbus conj(S / V). The derivative is of the form
        # dV - A conj(dV) = rhs, so solve one real block system for all actions.
        a = self.impedance * np.conjugate(demand / voltage ** 2)
        rhs_current = np.conjugate(direction / voltage[:, None])
        rhs = -self.impedance @ rhs_current
        identity = np.eye(len(voltage))
        matrix = np.block([[identity - a.real, -a.imag], [-a.imag, identity + a.real]])
        with catch_warnings():
            simplefilter("error", LinAlgWarning)
            derivative = solve_linear(matrix, np.vstack((rhs.real, rhs.imag)))
        dv = derivative[:len(voltage)] + 1j * derivative[len(voltage):]
        di = rhs_current - np.conjugate(demand[:, None] * dv / voltage[:, None] ** 2)
        voltage_mag = (np.conjugate(voltage[:, None]) * dv).real / np.abs(voltage[:, None])
        pcc_kw = (flow.voltage_complex_pu[self.slack] * np.conjugate(di.sum(axis=0))).real * self.base_power + slack_kw
        rated_current = np.array([flow.branch_current_pu[line] for line, _ in self.lines])
        derivative_i = self.downstream[self.rated_indices] @ di
        magnitude = np.abs(rated_current[:, None])
        current_a = np.divide((np.conjugate(rated_current[:, None]) * derivative_i).real, magnitude,
                              out=np.zeros_like(derivative_i.real), where=magnitude > 1e-12) * self.base_current
        return voltage_mag, pcc_kw, current_a

    def correct(self, point, flow, check):
        if check.converged and not check.violations:
            return point, flow, Correction()
        start = perf_counter()
        result = Correction()
        corrected, verified = self._correct(point, flow, check, result)
        result.seconds = perf_counter() - start
        self.evaluations += 1
        self.trials += result.fbs_trials
        self.seconds += result.seconds
        self.unresolved += result.status != "verified"
        return corrected, verified, result

    def _correct(self, point, flow, check, result):
        settings = self.settings
        # Slack voltage is fixed. A violation there cannot be corrected by P/Q changes.
        if any(f"{kind}:{self.slack}" in check.violations for kind in ("undervoltage", "overvoltage")):
            result.status = "physically_infeasible_slack_voltage"
            return point, flow

        # Q-only loads and Q-only generators remain fixed because these controls
        # move real power and preserve the original power factor at each bus.
        groups = ((settings.allow_load_shedding, point.p_load_kw, point.q_load_kvar,
                   self.buses, settings.shedding_penalty_per_kwh),
                  (settings.allow_pv_curtailment, point.p_pv_kw, point.q_pv_kvar,
                   tuple(sorted(point.p_pv_kw)), settings.curtailment_penalty_per_kwh))
        actions = [(group, bus, p[bus], q[bus], price)
                   for group, (allowed, p, q, buses, price) in enumerate(groups) if allowed
                   for bus in buses if p[bus] > 0.0]
        if not actions:
            result.status = "physically_infeasible_no_controls" if check.converged else "fbs_nonconvergence"
            return point, flow

        capacity = np.array([action[2] for action in actions])
        prices = np.array([action[4] for action in actions])
        # Break zero-price ties by using less corrective energy.
        objective = prices + max(1.0, max(prices)) * 1e-9
        scale_kw = max(1.0, sum(point.p_load_kw.values()), sum(point.p_pv_kw.values()))
        voltage_scale = max(0.01, settings.voltage_max_pu - settings.voltage_min_pu)
        voltage_guard = min(2e-7, (settings.voltage_max_pu - settings.voltage_min_pu) / 4)
        import_bound, export_bound = settings.grid_import_limit_kw, settings.grid_export_limit_kw
        # Allow for the last FBS iterate and LP roundoff at the PCC. Keep a
        # feasible interval when both grid limits together are effectively zero.
        grid_guard = max(1e-5, scale_kw * 1e-8)
        if import_bound is not None and export_bound is not None:
            grid_guard = min(grid_guard, (import_bound + export_bound) / 4)

        def operating_point(amounts):
            active = [point.p_load_kw.copy(), point.p_pv_kw.copy()]
            reactive = [point.q_load_kvar.copy(), point.q_pv_kvar.copy()]
            for amount, (group, bus, p, q, _) in zip(amounts, actions):
                remaining = p - float(amount)
                active[group][bus] = remaining
                reactive[group][bus] = q * (remaining / p)
            return replace(point, p_load_kw=active[0], q_load_kvar=reactive[0],
                           p_pv_kw=active[1], q_pv_kvar=reactive[1])

        def trial(amounts):
            result.fbs_trials += 1
            candidate = operating_point(amounts)
            return candidate, self.solve(candidate)

        def residuals(state):
            # Positive residuals violate the guarded LP limit. The final FBS
            # check uses the configured physical limits and tolerances.
            voltage = np.array([state.voltage_mag_pu[bus] for bus in self.buses])
            residual = list((settings.voltage_min_pu + voltage_guard - voltage) / voltage_scale)
            residual.extend((voltage - settings.voltage_max_pu + voltage_guard) / voltage_scale)
            if import_bound is not None:
                residual.append((state.slack_p_kw - import_bound + grid_guard) / scale_kw)
            if export_bound is not None:
                residual.append((-state.slack_p_kw - export_bound + grid_guard) / scale_kw)
            residual.extend((state.branch_current_a[line] - rating) / max(1., rating)
                            for line, rating in self.lines)
            return np.array(residual)

        amounts = np.zeros(len(actions))
        anchor_flow = flow
        best = None
        if not flow.converged:
            # Seek a solvable anchor without asserting an unsolved FBS state is
            # physically impossible. Every recovered anchor is checked below.
            for fraction in (0.25, 0.5, 0.75, 1.0):
                candidate_amounts = fraction * capacity
                candidate, anchor_flow = trial(candidate_amounts)
                if anchor_flow.converged:
                    amounts = candidate_amounts
                    if not check_flow(anchor_flow, self.network, settings).violations:
                        best = (float(prices @ amounts), candidate, anchor_flow)
                    break
            else:
                result.status = "fbs_nonconvergence"
                return point, flow

        trust = 1.0
        for iteration in range(min(settings.control_max_iterations, 10)):
            result.iterations = iteration + 1
            residual = residuals(anchor_flow)
            try:
                dv, dp, di = self.sensitivities(anchor_flow, operating_point(amounts), actions)
                rows = [-dv / voltage_scale, dv / voltage_scale]
                if import_bound is not None:
                    rows.append(dp / scale_kw)
                if export_bound is not None:
                    rows.append(-dp / scale_kw)
                rows.extend(di[i] / max(1., rating) for i, (_, rating) in enumerate(self.lines))
                jacobian = np.vstack(rows)
                if not np.isfinite(jacobian).all():
                    raise ValueError("Non-finite FBS sensitivities")
            except (np.linalg.LinAlgError, LinAlgWarning, ValueError):
                # Near a singular state, estimate locally from actual FBS probes.
                jacobian = np.zeros((len(residual), len(actions)))
                for index, limit in enumerate(capacity):
                    direction = 1 if limit - amounts[index] >= amounts[index] else -1
                    step = direction * min(max(0.01, limit * 0.001), limit / 2)
                    probe = amounts.copy()
                    probe[index] += step
                    _, perturbed = trial(probe)
                    if not perturbed.converged:
                        result.linear_status = "sensitivity_probe_failed"
                        break
                    jacobian[:, index] = (residuals(perturbed) - residual) / step
                if result.linear_status == "sensitivity_probe_failed":
                    break
            if len(residual):
                initial_violation = max(0., float(np.max(residual)))
                # Near the boundary, large swaps between buses with almost
                # equal marginal costs can erase a tiny predicted improvement.
                # A verified point gives us a safe incumbent for cost refinement.
                radius = trust
                if iteration and best is None and initial_violation < 1e-4:
                    radius *= max(.002, initial_violation * 25)
                lower = np.maximum(-amounts, -capacity * radius)
                upper = np.minimum(capacity - amounts, capacity * radius)
                bounds = list(zip(lower, upper))
                linear = linprog(objective, A_ub=jacobian, b_ub=-residual, bounds=bounds,
                                 method="highs", options={"primal_feasibility_tolerance": 1e-10})
                result.linear_status = {0: "optimal", 1: "iteration_limit", 2: "linear_model_infeasible",
                                        3: "unbounded", 4: "numerical_failure"}.get(linear.status, "solver_failure")
                if linear.status == 2 and best is None:
                    # Phase I minimizes the worst normalized violation when the
                    # current linearization cannot satisfy every bound.
                    linear = linprog(np.r_[np.zeros(len(actions)), 1.0],
                                     A_ub=np.column_stack((jacobian, -np.ones(len(residual)))),
                                     b_ub=-residual, bounds=[*bounds, (0, None)], method="highs")
                if linear.success:
                    move = linear.x[:len(actions)]
                    for fraction in (1., 0.5, 0.25, 0.125):
                        candidate_amounts = np.clip(amounts + fraction * move, 0., capacity)
                        candidate, candidate_flow = trial(candidate_amounts)
                        if not candidate_flow.converged:
                            continue
                        verified = not check_flow(candidate_flow, self.network, settings).violations
                        cost = float(prices @ candidate_amounts)
                        previous_cost = best[0] if best else None
                        if verified and (best is None or cost < best[0]):
                            best = (cost, candidate, candidate_flow)
                        if verified or max(0., float(np.max(residuals(candidate_flow)))) < initial_violation - 1e-10:
                            amounts, anchor_flow = candidate_amounts, candidate_flow
                            break
                    else:
                        trust *= 0.5
                        if trust >= 1 / 16 and best is None:
                            continue
                        break
                    if verified and previous_cost is not None and previous_cost - cost <= max(1e-5, cost * 1e-5):
                        break
                    continue
            break

        if best is not None:
            result.objective_usd = best[0]  # One-hour operating point.
            result.status = "verified"
            return best[1], best[2]
        result.status = ("solver_failure" if result.linear_status in
                         {"sensitivity_probe_failed", "numerical_failure", "unbounded", "solver_failure"}
                         else "correction_unresolved")
        # Keep the original physical state and its residuals when no feasible
        # corrected point was found; diagnostic trials never become delivered load.
        return point, flow
