"""Coordinated day-ahead battery scheduling using linear-programming MPC.

Supports both:
  - V11/V12 active-power-only (P) receding-horizon LP (coupled_pq=False)
  - Dr. Sindi SESS coupled P/Q receding-horizon LP (coupled_pq=True), which
    co-optimizes BESS P/Q, PV Q, load shedding, and voltage regulation using
    both R-path and X-path radial sensitivities and inscribed inverter polygons.

Every actual hourly command is limited by step_bess, checked with nonlinear
Numba FBS, and subjected to unchanged corrective load-shedding safeguards.
"""
from dataclasses import dataclass
from math import cos, pi, sin
from time import perf_counter

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

from .data_loader import profile_at
from .simulation import _operating_point


@dataclass(frozen=True)
class PredictiveSettings:
    horizon_hours: int = 72
    replan_interval_hours: int = 24
    monitored_buses: int = 12
    # The former 24-hour V11 controller remains selectable for A/B verification.
    shedding_aware: bool = True
    shedding_penalty_per_kwh: float = 12.0
    reserve_penalty_per_kwh: float = 0.06
    # Explicit engineering study weights, NOT claimed literature constants.
    voltage_shortfall_penalty_per_pu_hour: float = 120_000.0
    voltage_excess_penalty_per_pu_hour: float = 60_000.0
    import_excess_penalty_per_kwh: float = 12.0
    export_excess_penalty_per_kwh: float = 0.10
    cycling_cost_per_kwh: float = 0.025
    terminal_energy_value_per_kwh: float = 0.12
    grid_purchase_tariff_per_kwh: float = 0.10
    # Dr. Sindi SESS coupled P/Q look-ahead options (enabled in 'opf' mode)
    coupled_pq: bool = False
    bess_kva_multiplier: float = 1.00
    pv_kva_multiplier: float = 1.00
    reactive_cost_per_kvarh: float = 0.002
    inverter_polygon_sides: int = 8


class DayAheadFleetPlanner:
    """Solve a linearized horizon for the whole fleet, recomputing daily.

    The LP does not claim that constraints are satisfied: it is a *proposal*
    which the caller must verify by FBS before committing battery SOC.
    """

    def __init__(self, network, profiles, settings, configs, voltage_support, solve,
                 parameters=None):
        self.network, self.profiles, self.settings = network, profiles, settings
        self.configs = tuple(sorted(configs, key=lambda c: c.bus_id))
        self.support = voltage_support
        self.solve = solve
        self.parameters = parameters or PredictiveSettings()
        self.pv_units = {unit.bus_id: unit for unit in network.pv_units}
        self.schedule = {}
        self.q_schedule = {}
        self.last_reason = 'not planned'
        self.lp_calls = self.lp_failures = self.forecast_fbs_calls = 0
        self.lp_seconds = self.forecast_fbs_seconds = 0.0
        self.forecast_cache_hits = 0
        self._forecast_cache = {}
        self.plan_requests_kwh = 0.0
        self.plan_days = 0
        self.fallback_until = -1
        self.fallback_reason = None

    def request(self, index, states, raw_flow):
        """Get scheduled per-unit kW; replans using ACTUAL beginning-of-day SOC."""
        if index % self.parameters.replan_interval_hours == 0:
            try:
                self._plan(index, states)
                self.fallback_until = -1
                self.fallback_reason = None
            except Exception as exc:  # preserve safe legacy control for the full day
                self.lp_failures += 1
                self.fallback_until = index + self.parameters.replan_interval_hours
                self.fallback_reason = f'LP unavailable: {type(exc).__name__}: {exc}'
                self.schedule = {}
                self.q_schedule = {}
        if index < self.fallback_until:
            commands, legacy_reason = self.support.dispatch(raw_flow, self.configs, states,
                                                            self.settings)
            return commands, f'{self.fallback_reason}; legacy fallback: {legacy_reason}'
        prefix = 'coupled P/Q LP' if self.parameters.coupled_pq else 'day-ahead LP'
        return dict(self.schedule.get(index, {c.bus_id: 0.0 for c in self.configs})), \
            f'{prefix}: {self.last_reason}'

    def planned_q(self, index):
        """Return planned BESS reactive power dict (kvar) for hour index if coupled_pq is active."""
        return dict(self.q_schedule.get(index, {c.bus_id: 0.0 for c in self.configs}))

    def _plan(self, index, states):
        begin = perf_counter()
        n = len(self.profiles.timestamps)
        end = min(n, index + self.parameters.horizon_hours)
        horizon = end - index
        if horizon <= 0:
            raise ValueError('Empty predictive horizon')
        buses = tuple(c.bus_id for c in self.configs)
        count = len(buses)
        flows = []
        loads = []
        forecast_seconds = 0.0
        for old in tuple(self._forecast_cache):
            if old < index:
                del self._forecast_cache[old]
        for t in range(index, end):
            cached = self._forecast_cache.get(t)
            if cached is None:
                point = _operating_point(self.network, profile_at(self.profiles, t))
                start = perf_counter()
                flow = self.solve(point)
                forecast_seconds += perf_counter() - start
                self.forecast_fbs_calls += 1
                if not flow.converged:
                    raise ValueError('No converged base forecast FBS')
                self._forecast_cache[t] = (point, flow)
            else:
                self.forecast_cache_hits += 1
                point, flow = cached
            flows.append(flow)
            loads.append(point)
        self.forecast_fbs_seconds += forecast_seconds
        s = self.support.sensitivity
        sx = getattr(self.support, 'x_sensitivity', {})
        voltage_min, voltage_max = self.settings.voltage_min_pu, self.settings.voltage_max_pu
        scored = {}
        for flow in flows:
            for bus, voltage in flow.voltage_mag_pu.items():
                if bus not in s.get(buses[0], {}) and bus not in buses:
                    continue
                under = max(0., voltage_min - voltage)
                over = max(0., voltage - voltage_max)
                scored[bus] = scored.get(bus, 0.) + under * (1. + 10. * under) + over
        monitored = sorted(sorted(scored, key=lambda bus: (-scored[bus], bus))[:self.parameters.monitored_buses])
        if not monitored:
            monitored = list(buses)

        coupled_pq = bool(self.parameters.coupled_pq)
        pv_buses = tuple(sorted(self.pv_units)) if coupled_pq else ()
        pv_count = len(pv_buses)

        # Variable layout:
        # [cc (xdim), dd (xdim), ss (qdim), uu (qdim), oo (qdim), ii (H), ee (H), rr (count),
        #  (optional if coupled_pq): qb_pos (xdim), qb_neg (xdim), qpv_pos (H*pv), qpv_neg (H*pv)]
        xdim = horizon * count
        qdim = horizon * len(monitored)
        cc, dd = 0, xdim
        ss = 2 * xdim
        uu, oo = ss + qdim, ss + 2 * qdim
        ii, ee = ss + 3 * qdim, ss + 3 * qdim + horizon
        rr = ee + horizon
        size = rr + count
        if coupled_pq:
            qb_pos = size
            qb_neg = qb_pos + xdim
            qpv_pos = qb_neg + xdim
            qpv_neg = qpv_pos + horizon * pv_count
            size = qpv_neg + horizon * pv_count

        objective = np.zeros(size)
        bounds = [(0., None)] * size
        for t in range(horizon):
            for b, config in enumerate(self.configs):
                idx = t * count + b
                headroom_charge = max(0., min(config.power_rating_kw, config.max_charge_kw))
                headroom_discharge = max(0., min(config.power_rating_kw, config.max_discharge_kw))
                free_pv = max(0., -flows[t].slack_p_kw)
                discounted_price = (0.0 if free_pv > 1e-8 else
                                    self.parameters.grid_purchase_tariff_per_kwh)
                terminal = self.parameters.terminal_energy_value_per_kwh
                objective[cc + idx] = (discounted_price + self.parameters.cycling_cost_per_kwh
                                        - terminal * config.eta_charge)
                objective[dd + idx] = (self.parameters.cycling_cost_per_kwh
                                        + terminal / config.eta_discharge)
                bounds[cc + idx] = (0., headroom_charge)
                bounds[dd + idx] = (0., headroom_discharge)
                if coupled_pq:
                    qcap = self.parameters.bess_kva_multiplier * config.power_rating_kw
                    bounds[qb_pos + idx] = (0., qcap)
                    bounds[qb_neg + idx] = (0., qcap)
                    objective[qb_pos + idx] = self.parameters.reactive_cost_per_kvarh
                    objective[qb_neg + idx] = self.parameters.reactive_cost_per_kvarh
            if coupled_pq:
                for p_i, pv_bus in enumerate(pv_buses):
                    pv = self.pv_units[pv_bus]
                    produced = max(0., loads[t].p_pv_kw.get(pv_bus, 0.))
                    p_idx = t * pv_count + p_i
                    if produced > 1e-10:
                        s_pv = self.parameters.pv_kva_multiplier * max(produced, pv.p_rated_kw)
                        q_avail = float(np.sqrt(max(0., s_pv * s_pv - produced * produced)))
                        if pv.q_capability_kvar is not None:
                            q_avail = min(q_avail, pv.q_capability_kvar)
                    else:
                        q_avail = 0.0
                    bounds[qpv_pos + p_idx] = (0., q_avail)
                    bounds[qpv_neg + p_idx] = (0., q_avail)
                    objective[qpv_pos + p_idx] = self.parameters.reactive_cost_per_kvarh
                    objective[qpv_neg + p_idx] = self.parameters.reactive_cost_per_kvarh
            for k, bus in enumerate(monitored):
                load_kw = max(0., loads[t].p_load_kw.get(bus, 0.))
                bounds[ss + t * len(monitored) + k] = (
                    0., load_kw if self.parameters.shedding_aware and self.settings.allow_load_shedding else 0.)
                objective[ss + t * len(monitored) + k] = self.parameters.shedding_penalty_per_kwh

                v = flows[t].voltage_mag_pu[bus]
                weighting = 1. + 15. * max(0., voltage_min - v)
                objective[uu + t * len(monitored) + k] = (
                    self.parameters.voltage_shortfall_penalty_per_pu_hour * weighting)
                objective[oo + t * len(monitored) + k] = self.parameters.voltage_excess_penalty_per_pu_hour
            objective[ii + t] = self.parameters.import_excess_penalty_per_kwh
            objective[ee + t] = self.parameters.export_excess_penalty_per_kwh
        for b, config in enumerate(self.configs):
            bounds[rr + b] = (0., None)
            objective[rr + b] = self.parameters.reserve_penalty_per_kwh if self.parameters.shedding_aware else 0.
        rows, cols, coeffs, caps = [], [], [], []

        def add(row_coeffs, bound):
            row_id = len(caps)
            for col, value in row_coeffs.items():
                if abs(value) > 1e-14:
                    rows.append(row_id)
                    cols.append(col)
                    coeffs.append(float(value))
            caps.append(float(bound))

        for b, config in enumerate(self.configs):
            initial = states[config.bus_id].energy_kwh
            for t in range(horizon):
                energy_row = {}
                for k in range(t + 1):
                    idx = k * count + b
                    energy_row[cc + idx] = config.eta_charge
                    energy_row[dd + idx] = -1. / config.eta_discharge
                add({key: -value for key, value in energy_row.items()},
                    initial - config.soc_min * config.energy_capacity_kwh)
                add(energy_row, config.soc_max * config.energy_capacity_kwh - initial)
            terminal = {rr + b: -1.}
            for t in range(horizon):
                idx = t * count + b
                terminal[cc + idx] = -config.eta_charge
                terminal[dd + idx] = 1. / config.eta_discharge
            target = config.soc_initial * config.energy_capacity_kwh
            add(terminal, initial - target)

        for t in range(horizon):
            for k, bus in enumerate(monitored):
                v = flows[t].voltage_mag_pu[bus]
                gain = {b: s[c.bus_id].get(bus, 0.) for b, c in enumerate(self.configs)}
                low_row = {uu + t * len(monitored) + k: -1.}
                high_row = {oo + t * len(monitored) + k: -1.}
                for b in range(count):
                    idx = t * count + b
                    low_row[cc + idx] = gain[b]
                    low_row[dd + idx] = -gain[b]
                    high_row[cc + idx] = -gain[b]
                    high_row[dd + idx] = gain[b]
                    if coupled_pq:
                        q_gain = sx.get(self.configs[b].bus_id, {}).get(bus, 0.)
                        if abs(q_gain) > 1e-14:
                            low_row[qb_pos + idx] = -q_gain
                            low_row[qb_neg + idx] = q_gain
                            high_row[qb_pos + idx] = q_gain
                            high_row[qb_neg + idx] = -q_gain
                if coupled_pq:
                    for p_i, pv_bus in enumerate(pv_buses):
                        q_gain = sx.get(pv_bus, {}).get(bus, 0.)
                        if abs(q_gain) > 1e-14:
                            p_idx = t * pv_count + p_i
                            low_row[qpv_pos + p_idx] = -q_gain
                            low_row[qpv_neg + p_idx] = q_gain
                            high_row[qpv_pos + p_idx] = q_gain
                            high_row[qpv_neg + p_idx] = -q_gain
                for other_idx, shed_bus in enumerate(monitored):
                    source = s.get(shed_bus, {})
                    sensitivity = source.get(bus, 0.)
                    # Account for PF-consistent reactive load shedding in coupled P/Q mode
                    if coupled_pq:
                        load_p = loads[t].p_load_kw.get(shed_bus, 0.)
                        load_q = loads[t].q_load_kvar.get(shed_bus, 0.)
                        if load_p > 1e-10 and load_q > 0.:
                            sensitivity += sx.get(shed_bus, {}).get(bus, 0.) * (load_q / load_p)
                    low_row[ss + t * len(monitored) + other_idx] = -sensitivity
                    high_row[ss + t * len(monitored) + other_idx] = sensitivity
                add(low_row, v - voltage_min)
                add(high_row, voltage_max - v)
            if self.settings.grid_import_limit_kw is not None:
                row = {ii + t: -1.}
                for b in range(count):
                    idx = t * count + b
                    row[cc + idx] = 1.
                    row[dd + idx] = -1.
                for k in range(len(monitored)):
                    row[ss + t * len(monitored) + k] = -1.
                add(row, self.settings.grid_import_limit_kw - flows[t].slack_p_kw)
            if self.settings.grid_export_limit_kw is not None:
                row = {ee + t: -1.}
                for b in range(count):
                    idx = t * count + b
                    row[cc + idx] = -1.
                    row[dd + idx] = 1.
                for k in range(len(monitored)):
                    row[ss + t * len(monitored) + k] = 1.
                add(row, self.settings.grid_export_limit_kw + flows[t].slack_p_kw)

        # Shared inverter power + inscribed capability polygon (Dr. Sindi Eq. 49)
        sides = max(4, int(self.parameters.inverter_polygon_sides))
        for t in range(horizon):
            for b, config in enumerate(self.configs):
                idx = t * count + b
                add({cc + idx: 1., dd + idx: 1.}, config.power_rating_kw)
                if coupled_pq:
                    s_max = self.parameters.bess_kva_multiplier * config.power_rating_kw
                    rhs_poly = s_max * cos(pi / sides)
                    for side in range(sides):
                        theta = 2. * pi * (side + 0.5) / sides
                        ct, st = cos(theta), sin(theta)
                        add(
                            {
                                dd + idx: ct,
                                cc + idx: -ct,
                                qb_pos + idx: st,
                                qb_neg + idx: -st,
                            },
                            rhs_poly,
                        )

        a = coo_matrix((coeffs, (rows, cols)), shape=(len(caps), size)).tocsr()
        solve_begin = perf_counter()
        self.lp_calls += 1
        result = linprog(objective, A_ub=a, b_ub=np.asarray(caps), bounds=bounds, method='highs')
        self.lp_seconds += perf_counter() - solve_begin
        if not result.success or result.x is None or not np.all(np.isfinite(result.x)):
            raise ValueError(f'HiGHS failed: {result.message}')
        self.plan_days += 1
        self.last_reason = f'optimal ({horizon}h, {len(monitored)} monitored buses)'
        self.predicted_shedding_kwh = getattr(self, 'predicted_shedding_kwh', 0.) + sum(
            max(0., float(result.x[ss + i])) for i in range(qdim))
        self.predicted_reserve_shortfall_kwh = getattr(self, 'predicted_reserve_shortfall_kwh', 0.) + sum(
            max(0., float(result.x[rr + i])) for i in range(count))
        self.predicted_simultaneous_kw = getattr(self, 'predicted_simultaneous_kw', 0.) + sum(
            min(max(0., float(result.x[cc + i])), max(0., float(result.x[dd + i]))) for i in range(xdim))
        scheduled = {}
        q_scheduled = {}
        for t in range(horizon):
            commands = {}
            q_commands = {}
            for b, config in enumerate(self.configs):
                idx = t * count + b
                charge = max(0., float(result.x[cc + idx]))
                discharge = max(0., float(result.x[dd + idx]))
                net_power = discharge - charge
                commands[config.bus_id] = net_power
                self.plan_requests_kwh += abs(net_power)
                if coupled_pq:
                    q_net = max(0., float(result.x[qb_pos + idx])) - max(0., float(result.x[qb_neg + idx]))
                    q_commands[config.bus_id] = q_net
                else:
                    q_commands[config.bus_id] = 0.0
            scheduled[index + t] = commands
            q_scheduled[index + t] = q_commands
        self.schedule = scheduled
        self.q_schedule = q_scheduled
        self.total_plan_seconds = getattr(self, 'total_plan_seconds', 0.) + perf_counter() - begin

    def summary(self):
        return {
            'predictive_lp_calls': self.lp_calls,
            'predictive_lp_failures': self.lp_failures,
            'predictive_last_fallback_reason': self.fallback_reason,
            'predictive_lp_seconds': self.lp_seconds,
            'predictive_forecast_fbs_calls': self.forecast_fbs_calls,
            'predictive_forecast_cache_hits': self.forecast_cache_hits,
            'predictive_forecast_fbs_seconds': self.forecast_fbs_seconds,
            'predictive_days_planned': self.plan_days,
            'predictive_planned_absolute_kwh_in_overlapping_horizons': self.plan_requests_kwh,
            'predictive_lookahead_source': 'future hourly load/PV in supplied profile (offline perfect foresight)',
            'predictive_horizon_hours': self.parameters.horizon_hours,
            'predictive_replan_interval_hours': self.parameters.replan_interval_hours,
            'predictive_coupled_pq': self.parameters.coupled_pq,
            'predictive_shedding_aware': self.parameters.shedding_aware,
            'predictive_estimated_shedding_kwh_in_overlapping_horizons': getattr(self, 'predicted_shedding_kwh', 0.),
            'predictive_predicted_reserve_shortfall_kwh_in_overlapping_horizons': (getattr(self, 'predicted_reserve_shortfall_kwh', 0.) if self.parameters.shedding_aware else None),
            'predictive_simultaneous_charge_discharge_kw_in_overlapping_horizons': getattr(self, 'predicted_simultaneous_kw', 0.),
            'predictive_overlap_note': ('Forecast horizons overlap; predictions are not annual energy totals' if self.parameters.horizon_hours > self.parameters.replan_interval_hours else '24h horizons do not overlap'),
        }
