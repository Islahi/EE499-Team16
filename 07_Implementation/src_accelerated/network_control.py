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
    objective_usd: float | None = None  # Historical name for physical cost at a one-hour step.
    policy_score: float | None = None
    lp_calls: int = 0
    lp_seconds: float = 0.0
    sensitivity_calls: int = 0
    sensitivity_seconds: float = 0.0
    probe_trials: int = 0
    verified_linear_shortcuts: int = 0


def _single_binding_solution(jacobian, target, lower, upper, objective):
    """Solve a relaxed one-row LP only when its unique optimum satisfies every row."""
    deficit = jacobian @ lower - target
    row = deficit.argmax()
    if deficit[row] <= 0.:
        return lower
    improvement = -jacobian[row]
    eligible = np.flatnonzero((improvement > 1e-12) & (upper > lower))
    if not eligible.size:
        return None
    marginal = objective[eligible] / improvement[eligible]
    order = marginal.argsort(kind="stable")
    indices, marginal = eligible[order], marginal[order]
    widths = upper[indices] - lower[indices]
    cumulative = np.cumsum(improvement[indices] * widths)
    stop = cumulative.searchsorted(deficit[row])
    if stop >= len(indices):
        return None
    # Leave degenerate ties to HiGHS so the historical allocation stays repeatable.
    nearby = marginal[max(0, stop - 1):stop + 2]
    if np.any(np.diff(nearby) <= 1e-7 * marginal[stop]):
        return None
    answer = lower.copy()
    answer[indices[:stop]] = upper[indices[:stop]]
    used = cumulative[stop - 1] if stop else 0.
    answer[indices[stop]] += (deficit[row] - used) / improvement[indices[stop]]
    if np.max(jacobian @ answer - target) <= 1e-11:
        return answer
    return None


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
        self.identity = np.eye(len(self.buses))
        self.rated_downstream = self.downstream[self.rated_indices]
        self.evaluations = 0
        self.trials = 0
        self.seconds = 0.0
        self.unresolved = 0
        self.lp_calls = self.sensitivity_calls = self.probe_trials = 0
        self.verified_linear_shortcuts = 0
        self.lp_seconds = self.sensitivity_seconds = 0.0

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
        matrix = np.block([[self.identity - a.real, -a.imag], [-a.imag, self.identity + a.real]])
        with catch_warnings():
            simplefilter("error", LinAlgWarning)
            derivative = solve_linear(matrix, np.vstack((rhs.real, rhs.imag)))
        dv = derivative[:len(voltage)] + 1j * derivative[len(voltage):]
        di = rhs_current - np.conjugate(demand[:, None] * dv / voltage[:, None] ** 2)
        voltage_mag = (np.conjugate(voltage[:, None]) * dv).real / np.abs(voltage[:, None])
        pcc_kw = (flow.voltage_complex_pu[self.slack] * np.conjugate(di.sum(axis=0))).real * self.base_power + slack_kw
        if self.lines:
            rated_current = np.array([flow.branch_current_pu[line] for line, _ in self.lines])
            derivative_i = self.rated_downstream @ di
            magnitude = np.abs(rated_current[:, None])
            current_a = np.divide((np.conjugate(rated_current[:, None]) * derivative_i).real, magnitude,
                                  out=np.zeros_like(derivative_i.real), where=magnitude > 1e-12) * self.base_current
        else:
            current_a = np.empty((0, len(actions)))
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
        self.lp_calls += result.lp_calls
        self.lp_seconds += result.lp_seconds
        self.sensitivity_calls += result.sensitivity_calls
        self.sensitivity_seconds += result.sensitivity_seconds
        self.probe_trials += result.probe_trials
        self.verified_linear_shortcuts += result.verified_linear_shortcuts
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
        progressive = settings.shedding_policy == "progressive" and any(action[0] == 0 for action in actions)
        if progressive:
            counts = np.array([3 if action[0] == 0 else 1 for action in actions])
            physical_column = np.repeat(np.arange(len(actions)), counts)
            edges = (0., *settings.shedding_tier_edges, 1.)
            fractions = np.concatenate([np.diff(edges) if count == 3 else (1.,) for count in counts])
            starts = capacity[physical_column] * np.concatenate([
                edges[:-1] if count == 3 else (0.,) for count in counts])
            weights = np.concatenate([settings.shedding_tier_weights if count == 3 else (1.,) for count in counts])
            decision_capacity = capacity[physical_column] * fractions
            score_prices = prices[physical_column] * weights
            # With zero real VoLL, prefer shallower tiers among otherwise equivalent LP solutions.
            objective = score_prices + max(1., max(score_prices)) * 1e-9 * weights
        else:
            decision_capacity, score_prices = capacity, prices
            objective = prices + max(1., max(prices)) * 1e-9

        def aggregate(decisions):
            if not progressive:
                return decisions
            return np.minimum(capacity, np.bincount(physical_column, weights=decisions, minlength=len(actions)))

        def score(decisions):
            return float(score_prices @ decisions)

        def cheapest_allocation(amounts):
            if not progressive:
                return amounts
            return np.clip(amounts[physical_column] - starts, 0., decision_capacity)

        def optimize_linear(cost, **kwargs):
            start = perf_counter()
            solved = linprog(cost, method="highs", **kwargs)
            result.lp_calls += 1
            result.lp_seconds += perf_counter() - start
            return solved
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

        decisions = np.zeros(len(decision_capacity))
        amounts = np.zeros(len(actions))
        anchor_point = point
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
                    anchor_point = candidate
                    decisions = cheapest_allocation(amounts)
                    if not check_flow(anchor_flow, self.network, settings).violations:
                        best = (score(decisions), candidate, anchor_flow, amounts)
                    break
            else:
                result.status = "fbs_nonconvergence"
                return point, flow

        trust = 1.0
        for iteration in range(min(settings.control_max_iterations, 10)):
            result.iterations = iteration + 1
            residual = residuals(anchor_flow)
            try:
                started = perf_counter()
                result.sensitivity_calls += 1
                try:
                    dv, dp, di = self.sensitivities(anchor_flow, anchor_point, actions)
                finally:
                    result.sensitivity_seconds += perf_counter() - started
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
                    result.probe_trials += 1
                    _, perturbed = trial(probe)
                    if not perturbed.converged:
                        result.linear_status = "sensitivity_probe_failed"
                        break
                    jacobian[:, index] = (residuals(perturbed) - residual) / step
                if result.linear_status == "sensitivity_probe_failed":
                    break
            if progressive:
                jacobian = jacobian[:, physical_column]
            if len(residual):
                initial_violation = max(0., float(np.max(residual)))
                # Near the boundary, large swaps between buses with almost
                # equal marginal costs can erase a tiny predicted improvement.
                # A verified point gives us a safe incumbent for cost refinement.
                radius = trust
                if iteration and best is None and initial_violation < 1e-4:
                    radius *= max(.002, initial_violation * 25)
                lower = np.maximum(-decisions, -decision_capacity * radius)
                upper = np.minimum(decision_capacity - decisions, decision_capacity * radius)
                move = _single_binding_solution(jacobian, -residual, lower, upper, objective)
                if move is not None:
                    result.verified_linear_shortcuts += 1
                    result.linear_status = "optimal"
                else:
                    bounds = np.column_stack((lower, upper))
                    linear = optimize_linear(objective, A_ub=jacobian, b_ub=-residual, bounds=bounds,
                                             options={"primal_feasibility_tolerance": 1e-10})
                    result.linear_status = {0: "optimal", 1: "iteration_limit", 2: "linear_model_infeasible",
                                            3: "unbounded", 4: "numerical_failure"}.get(linear.status, "solver_failure")
                    if linear.status == 2 and best is None:
                        # Phase I minimizes the worst normalized violation when the
                        # current linearization cannot satisfy every bound.
                        linear = optimize_linear(np.r_[np.zeros(len(decisions)), 1.0],
                                                 A_ub=np.column_stack((jacobian, -np.ones(len(residual)))),
                                                 b_ub=-residual, bounds=np.vstack((bounds, (0., np.inf))))
                    if linear.success:
                        move = linear.x[:len(decisions)]
                if move is not None:
                    for fraction in (1., 0.5, 0.25, 0.125):
                        candidate_decisions = np.clip(decisions + fraction * move, 0., decision_capacity)
                        candidate_amounts = aggregate(candidate_decisions)
                        candidate_decisions = cheapest_allocation(candidate_amounts)
                        candidate, candidate_flow = trial(candidate_amounts)
                        if not candidate_flow.converged:
                            continue
                        verified = not check_flow(candidate_flow, self.network, settings).violations
                        cost = score(candidate_decisions)
                        previous_cost = best[0] if best else None
                        if verified and (best is None or cost < best[0]):
                            best = (cost, candidate, candidate_flow, candidate_amounts)
                        if verified or max(0., float(np.max(residuals(candidate_flow)))) < initial_violation - 1e-10:
                            amounts, anchor_point, anchor_flow = candidate_amounts, candidate, candidate_flow
                            decisions = candidate_decisions
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
            result.policy_score = best[0]
            result.objective_usd = float(prices @ best[3])
            result.status = "verified"
            return best[1], best[2]
        result.status = ("solver_failure" if result.linear_status in
                         {"sensitivity_probe_failed", "numerical_failure", "unbounded", "solver_failure"}
                         else "correction_unresolved")
        # Keep the original physical state and its residuals when no feasible
        # corrected point was found; diagnostic trials never become delivered load.
        return point, flow
