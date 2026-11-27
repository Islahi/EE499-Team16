"""Dr. Sindi SESS coupled P/Q distribution OPF with damped SLP and FBS verification.

Replaces the V13 2-step undamped LP in 'opf' mode while preserving all physical
and economic contracts:
  - Preserves exact optimization target: BESS + Load Shedding + PV Curtailment
    + Grid Import/Export cost.
  - Accepts coupled (P_ref, Q_ref) from DayAheadFleetPlanner (24h/72h P/Q LP).
  - Uses damped Sequential Linearized AC Power Flow (up to 4 iterations with
    step-halving trust-region recovery if a linear step fails FBS convergence).
  - Adds secondary voltage-deviation flattening min sum |V_i - 1.0| (Eq. 17)
    strictly subordinate to shedding/curtailment penalties so free inverter Q
    actively pulls bus voltages closer to 1.00 p.u. inside [0.95, 1.05].
  - Every executed operating point is verified by the actual nonlinear Numba FBS.
"""
from dataclasses import dataclass, replace
from math import cos, isfinite, pi, sin, sqrt
from time import perf_counter
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix

from .app_log import record_opf_pv_boundary
from .daily_milp_dispatch import q_per_kw_at_min_pf
from .bess import step_bess
from .constraint_dispatch import check_flow
from .network_control import Correction, NetworkCorrector


# HiGHS' default primal feasibility tolerance. Apply it only when decoding
# the active PV curtailment variable, in kW, before handing the point to FBS.
PV_CURTAILMENT_TOLERANCE_KW = 1e-7


@dataclass
class JointOPFSettings:
    bess_kva_multiplier: float = 1.00
    pv_kva_multiplier: float = 1.00
    allow_pv_reactive_at_night: bool = False
    reactive_cost_per_kvarh: float = 0.002
    battery_plan_deviation_cost_per_kwh: float = 0.18
    # Dr. Sindi Eq. (17) active voltage-flattening weight ($/pu-h), strictly
    # subordinate to shedding ($12/kWh) and curtailment ($0.07/kWh).
    voltage_deviation_weight_per_pu_hour: float = 0.05
    # 16-sided INSCRIBED inverter capability polygon. Conservative vs circle.
    inverter_polygon_sides: int = 16
    voltage_guard_pu: float = 1.0e-4
    linearization_iterations: int = 4


class JointOPFController:
    """One instance per simulation/worker; no shared global state or threading."""
    def __init__(self, network, settings, solve_fbs, corrector=None, *, params=None):
        self.network = network
        self.settings = settings
        self.solve_fbs = solve_fbs
        self.corrector = corrector or NetworkCorrector(network, settings, solve_fbs)
        self.daily_milp_dispatch = settings.fleet_dispatch_mode == 'daily_milp_dispatch'
        self.pf_tangent = q_per_kw_at_min_pf(settings.minimum_discharge_pf) if self.daily_milp_dispatch else None
        self.params = params or JointOPFSettings(
            bess_kva_multiplier=settings.effective_bess_inverter_kva_per_kw,
            pv_kva_multiplier=settings.opf_pv_kva_multiplier,
        )
        self.pv_units = {unit.bus_id: unit for unit in network.pv_units}
        self.opf_hours = self.opf_lp_calls = self.opf_lp_failures = 0
        self.opf_fbs_trials = self.opf_fallbacks = 0
        self.opf_damped_recoveries = 0
        self.opf_lp_seconds = 0.
        self.opf_q_bess_kvarh = self.opf_q_pv_kvarh = 0.
        self.opf_adjusted_bess_kwh = 0.

    def summary(self):
        return {
            'opf_hours': self.opf_hours,
            'opf_lp_calls': self.opf_lp_calls,
            'opf_lp_failures': self.opf_lp_failures,
            'opf_lp_seconds': round(self.opf_lp_seconds, 4),
            'opf_fbs_trials': self.opf_fbs_trials,
            'opf_corrective_fallbacks': self.opf_fallbacks,
            'opf_damped_recoveries': self.opf_damped_recoveries,
            'opf_bess_reactive_abs_kvarh': self.opf_q_bess_kvarh,
            'opf_pv_reactive_abs_kvarh': self.opf_q_pv_kvarh,
            'opf_bess_plan_adjustment_abs_kwh': self.opf_adjusted_bess_kwh,
            'opf_formulation': ('Daily P/Q MILP active-power lock + discharge-linked PF + verified FBS' if self.daily_milp_dispatch else 'Coordinated P/Q OPF + damped SLP + FBS verification'),
            'opf_bess_inverter_kva_multiplier': self.params.bess_kva_multiplier,
            'opf_pv_inverter_kva_multiplier': self.params.pv_kva_multiplier,
        }

    @staticmethod
    def _blend_point(anchor, candidate, alpha, configs):
        """Convex interpolation along P/Q/load/PV step for trust-region damping."""
        p_bess = {b: anchor.p_bess_kw[b] + alpha * (candidate.p_bess_kw[b] - anchor.p_bess_kw[b])
                  for b in anchor.p_bess_kw}
        q_bess = {b: anchor.q_bess_kvar[b] + alpha * (candidate.q_bess_kvar[b] - anchor.q_bess_kvar[b])
                  for b in anchor.q_bess_kvar}
        p_pv = {b: anchor.p_pv_kw[b] + alpha * (candidate.p_pv_kw[b] - anchor.p_pv_kw[b])
                for b in anchor.p_pv_kw}
        q_pv = {b: anchor.q_pv_kvar[b] + alpha * (candidate.q_pv_kvar[b] - anchor.q_pv_kvar[b])
                for b in anchor.q_pv_kvar}
        p_load = {b: anchor.p_load_kw[b] + alpha * (candidate.p_load_kw[b] - anchor.p_load_kw[b])
                  for b in anchor.p_load_kw}
        q_load = {b: anchor.q_load_kvar[b] + alpha * (candidate.q_load_kvar[b] - anchor.q_load_kvar[b])
                  for b in anchor.q_load_kvar}
        return replace(anchor, p_bess_kw=p_bess, q_bess_kvar=q_bess,
                       p_pv_kw=p_pv, q_pv_kvar=q_pv, p_load_kw=p_load, q_load_kvar=q_load)

    def dispatch(self, raw_point, raw_flow, configs, states, requests, q_requests=None,
                 *, timestamp=None, representative_day=None):
        """Return (final point, flow, actual step results, correction, audit).

        The caller must commit returned BESS states only after FBS converges.
        On LP failure, retain conservative physical controls, never accept an
        unverified operating point and never silently report OPF success.
        """
        self.opf_hours += 1
        configs = tuple(configs)
        requested = {c.bus_id: step_bess(c, states[c.bus_id],
                                          requests.get(c.bus_id, 0.), 1.)
                     for c in configs}
        p_ref = {bus: step.actual_power_kw for bus, step in requested.items()}
        # Clamp coupled Q reference strictly inside inverter apparent-power circle
        q_ref = {}
        for c in configs:
            q_req = float((q_requests or {}).get(c.bus_id, 0.))
            s_max = self.params.bess_kva_multiplier * c.power_rating_kw
            q_lim = sqrt(max(0., s_max * s_max - p_ref[c.bus_id] ** 2))
            if self.daily_milp_dispatch:
                # The mobile-BESS paper binds positive Q injection to active discharge.
                q_lim = min(q_lim, max(0.0, p_ref[c.bus_id]) * self.pf_tangent)
                q_ref[c.bus_id] = min(q_lim, max(0.0, q_req))
            else:
                q_ref[c.bus_id] = max(-q_lim, min(q_lim, q_req))

        if any(abs(power) > 1e-12 for power in p_ref.values()) or any(abs(q) > 1e-12 for q in q_ref.values()):
            start = replace(raw_point,
                            p_bess_kw={**raw_point.p_bess_kw, **p_ref},
                            q_bess_kvar={**raw_point.q_bess_kvar, **q_ref})
            initial_flow = self.solve_fbs(start)
            self.opf_fbs_trials += 1
        else:
            start, initial_flow = raw_point, raw_flow
        self.last_reference_point = start
        self.last_reference_flow = initial_flow
        raw_check = check_flow(raw_flow, self.network, self.settings)
        initial_check = check_flow(initial_flow, self.network, self.settings)
        if initial_flow.converged and not initial_check.violations and (not raw_check.violations):
            return self._complete(start, initial_flow, configs, states, p_ref,
                                  Correction(), 'no_opf_needed')

        anchor, flow = start, initial_flow
        failure = None
        for attempt in range(self.params.linearization_iterations):
            if not flow.converged:
                failure = 'no converged sensitivity anchor'
                break
            try:
                candidate = self._optimize(anchor, flow, configs, states, p_ref,
                                           timestamp=timestamp, representative_day=representative_day)
            except Exception as exc:
                self.opf_lp_failures += 1
                failure = f'{type(exc).__name__}: {exc}'
                break
            candidate_flow = self.solve_fbs(candidate)
            self.opf_fbs_trials += 1
            check = check_flow(candidate_flow, self.network, self.settings)
            if check.converged and not check.violations:
                return self._complete(candidate, candidate_flow, configs, states, p_ref,
                                      Correction(status='verified'), f'opf_verified_{attempt+1}')
            if not candidate_flow.converged:
                # Damped trust-region recovery: halve step before giving up
                recovered = False
                for alpha in (0.5, 0.25):
                    damped = self._blend_point(anchor, candidate, alpha, configs)
                    damped_flow = self.solve_fbs(damped)
                    self.opf_fbs_trials += 1
                    if damped_flow.converged:
                        damped_check = check_flow(damped_flow, self.network, self.settings)
                        self.opf_damped_recoveries += 1
                        if not damped_check.violations:
                            return self._complete(damped, damped_flow, configs, states, p_ref,
                                                  Correction(status='verified'), f'opf_damped_{attempt+1}')
                        anchor, flow = damped, damped_flow
                        recovered = True
                        break
                if not recovered:
                    failure = 'linear OPF proposal failed FBS'
                    break
            else:
                anchor, flow = candidate, candidate_flow

        self.opf_fallbacks += 1
        if flow.converged:
            checked = check_flow(flow, self.network, self.settings)
            point, checked_flow, correction = self.corrector.correct(anchor, flow, checked)
            if checked_flow.converged and not check_flow(checked_flow, self.network, self.settings).violations:
                return self._complete(point, checked_flow, configs, states, p_ref,
                                      correction, 'opf_corrective_fallback')
        fallback_point, fallback_flow = start, initial_flow
        fallback_correction = Correction(status='not_needed')
        if not initial_flow.converged or initial_check.violations:
            fallback_point, fallback_flow, fallback_correction = self.corrector.correct(
                start, initial_flow, initial_check)
        return self._complete(fallback_point, fallback_flow, configs, states, p_ref,
                              fallback_correction, 'opf_failed_fallback: '+str(failure))

    def _complete(self, point, flow, configs, states, p_ref, correction, status):
        result = {c.bus_id: step_bess(c, states[c.bus_id], point.p_bess_kw[c.bus_id], 1.)
                  for c in configs}
        for c in configs:
            if abs(result[c.bus_id].actual_power_kw - point.p_bess_kw[c.bus_id]) > 1e-5:
                raise AssertionError('OPF result exceeds physical BESS power/SOC bounds')
        if self.daily_milp_dispatch:
            for c in configs:
                p = point.p_bess_kw[c.bus_id]
                q = point.q_bess_kvar.get(c.bus_id, 0.0)
                if abs(p - p_ref[c.bus_id]) > 1e-5:
                    raise AssertionError('Hourly OPF modified the day-ahead active power schedule')
                if q < -1e-6 or q > max(0., p) * self.pf_tangent + 1e-5:
                    raise AssertionError('Hourly dispatch violated the minimum discharge power factor')
        if flow.converged:
            self.opf_q_bess_kvarh += sum(abs(point.q_bess_kvar.get(c.bus_id, 0.)) for c in configs)
            self.opf_q_pv_kvarh += sum(abs(point.q_pv_kvar.get(bus, 0.)) for bus in self.pv_units)
            self.opf_adjusted_bess_kwh += sum(abs(point.p_bess_kw[c.bus_id] - p_ref[c.bus_id])
                                              for c in configs)
        return point, flow, result, correction, {'status': status}

    def _optimize(self, point, flow, configs, states, p_ref, *, timestamp=None, representative_day=None):
        """Costed simultaneous P/Q, shedding, curtailment, and voltage-deviation LP."""
        controls = []
        c, bounds, directions = [], [], []

        def variable(kind, bus, p_effect, q_effect, lo, hi, cost):
            idx = len(controls)
            controls.append((kind, bus))
            c.append(float(cost))
            bounds.append((float(lo), float(hi)))
            directions.append((2, bus, p_effect, q_effect, 0.))
            return idx

        bess_p, bess_q = {}, {}
        for battery in configs:
            bus = battery.bus_id
            state = states[bus]
            low = step_bess(battery, state, -battery.power_rating_kw, 1.).actual_power_kw
            high = step_bess(battery, state, battery.power_rating_kw, 1.).actual_power_kw
            base = point.p_bess_kw.get(bus, 0.)
            up = variable('bess_p_plus', bus, 1., 0., 0., 0. if self.daily_milp_dispatch else max(0., high-base),
                          self.params.battery_plan_deviation_cost_per_kwh)
            down = variable('bess_p_minus', bus, -1., 0., 0., 0. if self.daily_milp_dispatch else max(0., base-low),
                            self.params.battery_plan_deviation_cost_per_kwh)
            bess_p[bus] = (up, down)
            qcap = self.params.bess_kva_multiplier * battery.power_rating_kw
            base_q = point.q_bess_kvar.get(bus, 0.)
            if self.daily_milp_dispatch:
                qcap = min(qcap, max(0., base) * self.pf_tangent)
            qplus = variable('bess_q_plus', bus, 0., 1., 0., max(0., qcap - base_q),
                             self.params.reactive_cost_per_kvarh)
            qminus = variable('bess_q_minus', bus, 0., -1., 0., max(0., base_q) if self.daily_milp_dispatch else max(0., qcap + base_q),
                              self.params.reactive_cost_per_kvarh)
            bess_q[bus] = (qplus, qminus)

        pv_curt, pv_q = {}, {}
        for bus, pv in sorted(self.pv_units.items()):
            produced = max(0., point.p_pv_kw.get(bus, 0.))
            rated = max(produced, pv.p_rated_kw)
            s = self.params.pv_kva_multiplier * rated
            if self.settings.allow_pv_curtailment and produced > 1e-10:
                pv_curt[bus] = variable('pv_curtail', bus, -1., 0., 0., produced,
                                        self.settings.curtailment_penalty_per_kwh)
            if produced > 1e-10 or self.params.allow_pv_reactive_at_night:
                qcap = s
                if pv.q_capability_kvar is not None:
                    qcap = min(qcap, pv.q_capability_kvar)
                base_q = point.q_pv_kvar.get(bus, 0.)
                pos = variable('pv_q_plus', bus, 0., 1., 0., max(0., qcap-base_q),
                                self.params.reactive_cost_per_kvarh)
                neg = variable('pv_q_minus', bus, 0., -1., 0., max(0., qcap+base_q),
                                self.params.reactive_cost_per_kvarh)
                pv_q[bus] = (pos, neg)

        shed = {}
        if self.settings.allow_load_shedding:
            for bus, load in sorted(point.p_load_kw.items()):
                if bus == self.corrector.slack or load <= 1e-10:
                    continue
                ratio = point.q_load_kvar.get(bus, 0.) / load
                if self.settings.shedding_policy == 'progressive':
                    intervals = (0., *self.settings.shedding_tier_edges, 1.)
                    weights = self.settings.shedding_tier_weights
                else:
                    intervals, weights = (0., 1.), (1.,)
                shed[bus] = [variable('shed', bus, 1., ratio,
                            0., load * (intervals[k+1] - intervals[k]),
                            self.settings.shedding_penalty_per_kwh * weights[k])
                            for k in range(len(weights))]
        if not controls:
            raise ValueError('No controllable resources at this operating point')

        n_ctrl = len(controls)
        dv, dp, di = self.corrector.sensitivities(flow, point, directions)
        if not np.isfinite(dv).all() or not np.isfinite(dp).all():
            raise ValueError('Non-finite voltage or power sensitivities')

        # Add auxiliary voltage-deviation variables t_i >= |V_i - 1.0| (Dr. Sindi Eq. 17)
        v_weight = float(self.params.voltage_deviation_weight_per_pu_hour)
        n_buses = len(self.corrector.buses)
        use_vdev = v_weight > 0.0
        n = n_ctrl + (n_buses if use_vdev else 0)
        if use_vdev:
            cost = np.concatenate([np.array(c, dtype=float), np.full(n_buses, v_weight, dtype=float)])
            lohi = bounds + [(0.0, None)] * n_buses
        else:
            cost = np.array(c, dtype=float)
            lohi = bounds.copy()

        rows, rhs = [], []

        def add(row, bound):
            rows.append(np.asarray(row, dtype=float))
            rhs.append(float(bound))

        guard = self.params.voltage_guard_pu
        for row_index, bus in enumerate(self.corrector.buses):
            v = flow.voltage_mag_pu[bus]
            # Hard 0.95–1.05 p.u. bounds (Eq. 30)
            row_lo = np.zeros(n)
            row_lo[:n_ctrl] = -dv[row_index]
            add(row_lo, v - self.settings.voltage_min_pu - guard)

            row_hi = np.zeros(n)
            row_hi[:n_ctrl] = dv[row_index]
            add(row_hi, self.settings.voltage_max_pu - guard - v)

            # Epigraph bounds for t_i >= |V_i + dv_i x - 1.0| (Eq. 17)
            if use_vdev:
                t_col = n_ctrl + row_index
                ep1 = np.zeros(n)
                ep1[:n_ctrl] = dv[row_index]
                ep1[t_col] = -1.0
                add(ep1, 1.0 - v)

                ep2 = np.zeros(n)
                ep2[:n_ctrl] = -dv[row_index]
                ep2[t_col] = -1.0
                add(ep2, v - 1.0)

        if self.settings.grid_import_limit_kw is not None:
            row = np.zeros(n)
            row[:n_ctrl] = dp
            add(row, self.settings.grid_import_limit_kw - flow.slack_p_kw - 1e-4)
        if self.settings.grid_export_limit_kw is not None:
            row = np.zeros(n)
            row[:n_ctrl] = -dp
            add(row, self.settings.grid_export_limit_kw + flow.slack_p_kw - 1e-4)
        for i, (_, ampacity) in enumerate(self.corrector.lines):
            row = np.zeros(n)
            row[:n_ctrl] = di[i]
            add(row, ampacity - flow.branch_current_a[self.corrector.lines[i][0]] - 1e-4)

        def add_inverter_polygon(p_base, q_base, p_cols, q_cols, s):
            sides = self.params.inverter_polygon_sides
            for k in range(sides):
                theta = 2. * pi * (k + .5) / sides
                ct, st = cos(theta), sin(theta)
                row = np.zeros(n)
                for idx, sign in p_cols:
                    row[idx] += sign * ct
                for idx, sign in q_cols:
                    row[idx] += sign * st
                add(row, s * cos(pi/sides) - p_base*ct - q_base*st)

        for battery in configs:
            bus = battery.bus_id
            ppos, pneg = bess_p[bus]
            qpos, qneg = bess_q[bus]
            add_inverter_polygon(point.p_bess_kw[bus], point.q_bess_kvar.get(bus, 0.),
                                 ((ppos, 1.),(pneg,-1.)), ((qpos,1.),(qneg,-1.)),
                                 self.params.bess_kva_multiplier * battery.power_rating_kw)
        for bus, pv in sorted(self.pv_units.items()):
            produced = max(0., point.p_pv_kw.get(bus, 0.))
            if bus not in pv_q and bus not in pv_curt:
                continue
            pcols = ((pv_curt[bus], -1.),) if bus in pv_curt else ()
            qcols = ((pv_q[bus][0], 1.), (pv_q[bus][1], -1.)) if bus in pv_q else ()
            s = self.params.pv_kva_multiplier * max(produced, pv.p_rated_kw)
            add_inverter_polygon(produced, point.q_pv_kvar.get(bus,0.), pcols, qcols, s)

        a = np.vstack(rows)
        b = np.array(rhs)
        lower = np.array([l if l is not None else -1e9 for l, _ in lohi])
        upper = np.array([h if h is not None else 1e9 for _, h in lohi])
        maximum = np.sum(np.where(a >= 0., a * upper, a * lower), axis=1)
        mask = maximum >= b - 1e-8
        if mask.any():
            a, b = a[mask], b[mask]
        else:
            a, b = None, None
        started = perf_counter()
        self.opf_lp_calls += 1
        solution = linprog(cost, A_ub=csr_matrix(a) if a is not None else None,
                           b_ub=b, bounds=lohi, method='highs',
                           options={'presolve': True})
        self.opf_lp_seconds += perf_counter()-started
        if not solution.success or solution.x is None:
            raise ValueError('HiGHS OPF: '+solution.message)
        x = solution.x
        p_pv = point.p_pv_kw.copy()
        for bus, idx in pv_curt.items():
            available = p_pv[bus]
            proposed = float(x[idx])
            remaining = available - proposed
            if not 0. <= proposed <= available:
                valid_within_tolerance = (isfinite(proposed)
                                          and proposed >= -PV_CURTAILMENT_TOLERANCE_KW
                                          and remaining >= -PV_CURTAILMENT_TOLERANCE_KW)
                record_opf_pv_boundary({
                    "action": "clamped" if valid_within_tolerance else "fallback",
                    "fleet": [{"bus": c.bus_id, "power_kw": c.power_rating_kw,
                               "energy_kwh": c.energy_capacity_kwh} for c in configs],
                    "representative_day": representative_day,
                    "timestamp": str(timestamp) if timestamp is not None else None,
                    "bus": bus,
                    "available_pv_kw": float(available),
                    "proposed_curtailment_kw": proposed if isfinite(proposed) else str(proposed),
                    "resulting_pv_kw": float(remaining) if isfinite(remaining) else str(remaining),
                    "tolerance_kw": PV_CURTAILMENT_TOLERANCE_KW,
                })
                if not valid_within_tolerance:
                    raise ValueError(f'HiGHS OPF PV curtailment outside bounds at bus {bus}: '
                                     f'{proposed!r} kW for {available!r} kW available')
                remaining = 0. if proposed > available else available
            p_pv[bus] = remaining
        if not np.isfinite(x).all():
            raise ValueError('HiGHS OPF: '+solution.message)
        p_bess=point.p_bess_kw.copy(); q_bess=point.q_bess_kvar.copy()
        q_pv=point.q_pv_kvar.copy()
        p_load=point.p_load_kw.copy(); q_load=point.q_load_kvar.copy()
        for battery in configs:
            bus=battery.bus_id
            up,dn=bess_p[bus]; pos,neg=bess_q[bus]
            p_bess[bus] += x[up]-x[dn]
            q_bess[bus] += x[pos]-x[neg]
        for bus,(pos,neg) in pv_q.items():
            q_pv[bus] += x[pos]-x[neg]
        for bus,parts in shed.items():
            removal = float(sum(x[part] for part in parts))
            before=p_load[bus]
            p_load[bus] = max(0.,before-removal)
            q_load[bus] *= p_load[bus]/before
        for battery in configs:
            bus = battery.bus_id
            s=self.params.bess_kva_multiplier*battery.power_rating_kw
            if p_bess[bus]**2 + q_bess[bus]**2 > s*s+1e-5:
                raise AssertionError('BESS inverter kVA boundary exceeded')
        for bus,pv in self.pv_units.items():
            s=self.params.pv_kva_multiplier*max(pv.p_rated_kw,point.p_pv_kw.get(bus,0.))
            if p_pv.get(bus,0.)**2+q_pv.get(bus,0.)**2>s*s+1e-5:
                raise AssertionError('PV inverter kVA boundary exceeded')
        return replace(point, p_bess_kw=p_bess,q_bess_kvar=q_bess,
                       p_pv_kw=p_pv,q_pv_kvar=q_pv,p_load_kw=p_load,q_load_kvar=q_load)
