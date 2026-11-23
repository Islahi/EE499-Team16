"""V15.3: static-BESS adaptation of Ahmed, Sindi, Azzouz & Awad (IEEE TEC 2022).

Paper equations adapted: (34)-(44) PF-bound Q, mutually exclusive charging
and discharging, cumulative SOC and daily energy equality. Unlike the paper's
full nonlinear, monthly, mobile-network GRG model, this is a 24-hour MILP with
first-order radial voltage sensitivities and hourly nonlinear FBS verification.
It does NOT implement transportation, FCS/PV siting, emissions, or full AC MINLP.

The forecast supplied by a saved study is *perfect foresight*. It is not a
validated operational prediction. Expose this clearly in result metadata.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import acos, tan
from time import perf_counter

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from .data_loader import profile_at
from .simulation import _operating_point


def q_per_kw_at_min_pf(min_pf: float) -> float:
    if not 0.0 < min_pf <= 1.0:
        raise ValueError('Minimum power factor must lie in (0, 1]')
    return tan(acos(min_pf))


def inverter_kva(power_kw: float, minimum_pf: float, multiplier: float = 1.0) -> float:
    """Equipment S rating for a P-rated converter able to reach PF_min."""
    return power_kw * max(multiplier, 1.0 / minimum_pf)


def terminal_reachable_power_bounds(config, state, target_kwh: float, hours_after: int):
    """Feasible AC injection [low,high] for THIS hour, ensuring next-state
    can physically reach day-end energy using remaining nameplate power.
    Negative is charge; positive is discharge. These bounds are NECESSARY but
    not sufficient for voltage/network feasibility on subsequent hours.
    """
    if hours_after < 0:
        raise ValueError('Negative remaining hours')
    energy = state.energy_kwh
    c_rate = min(config.power_rating_kw, config.max_charge_kw)
    d_rate = min(config.power_rating_kw, config.max_discharge_kw)
    emin = config.soc_min * config.energy_capacity_kwh
    emax = config.soc_max * config.energy_capacity_kwh
    next_min = max(emin, target_kwh - hours_after * c_rate * config.eta_charge)
    next_max = min(emax, target_kwh + hours_after * d_rate / config.eta_discharge)
    if next_min > next_max + 1e-7:
        raise ValueError('Day-end energy target outside physical SOC range')

    def p_for_next_energy(next_energy):
        # Inverting the BESS energy update (AC bus injection sign convention).
        return ((energy - next_energy) * config.eta_discharge if energy >= next_energy
                else (energy - next_energy) / config.eta_charge)

    low = max(p_for_next_energy(next_max), -c_rate)
    high = min(p_for_next_energy(next_min), d_rate)
    if low > high + 1e-6:
        raise ValueError('Day-end SOC cannot be restored at current hour')
    return low, high


@dataclass(frozen=True)
class DailyMILPSettings:
    horizon_hours: int = 24
    min_power_factor: float = 0.95  # published journal version; older table has 0.80
    monitored_buses: int = 12
    cycling_cost_usd_per_kwh: float = 0.025
    reactive_cost_usd_per_kvarh: float = 0.002
    voltage_shortfall_cost_per_pu_hour: float = 120000.
    voltage_excess_cost_per_pu_hour: float = 60000.
    milp_time_limit_s: float = 3.0

    @classmethod
    def from_simulation(cls, simulation):
        return cls(min_power_factor=simulation.minimum_discharge_pf, horizon_hours=simulation.dispatch_horizon_hours)


class DailyMILPPlanner:
    """Joint day-ahead C/D/Q MILP; schedule re-established each calendar day.

    Uses 1-h input profiles, sparse MILP matrices, actual start-of-day SOC,
    binary exclusivity, daily Eend=Estart, and a paper-inspired Q<=tan(PF)*D.
    Hourly OPF remains responsible for all-bus nonlinear network feasibility.
    """

    def __init__(self, network, profiles, sim_settings, configs, solve_fbs, *, params=None):
        self.network, self.profiles, self.settings = network, profiles, sim_settings
        self.configs = tuple(sorted(configs, key=lambda c: c.bus_id))
        self.solve_fbs = solve_fbs
        self.params = params or DailyMILPSettings.from_simulation(sim_settings)
        q_per_kw_at_min_pf(self.params.min_power_factor)
        self.parameters = self.params  # compatible DispatchEvent horizon field
        self.p_schedule, self.q_schedule = {}, {}
        self.day_target_kwh = {}
        self.daily_plans = self.milp_failures = self.milp_seconds = 0
        self.forecast_fbs_calls = 0
        self.last_reason = 'not planned'
        self.forecast_source = 'input hourly profiles (offline perfect foresight)'
        self._sens_p, self._sens_q = self._path_sensitivities(network)

    @staticmethod
    def _path_sensitivities(network):
        order = network.radial_order()
        branch = {l.line_id: l for l in network.lines}
        paths = {order.slack_bus_id: {}}
        remaining = set(order.parent_bus_by_bus)
        while remaining:
            ready = [b for b in remaining if order.parent_bus_by_bus[b] in paths]
            if not ready:
                raise ValueError('Non-radial or disconnected network')
            for bus in ready:
                parent = order.parent_bus_by_bus[bus]
                path = dict(paths[parent]); path[order.parent_line_by_bus[bus]] = branch[order.parent_line_by_bus[bus]]
                paths[bus] = path; remaining.remove(bus)
        kv = next(b.base_kv for b in network.buses if b.bus_id == order.slack_bus_id)
        factor = 1.0 / (1000.0 * kv * kv)
        def make(attr):
            return {source:{target: sum(getattr(paths[source][line],attr) for line in paths[source] if line in paths[target])*factor
                         for target in paths} for source in paths if source != order.slack_bus_id}
        return make('r_ohm'), make('x_ohm')

    def request(self, index, states, raw_flow):
        if index % 24 == 0:
            self.day_target_kwh = {c.bus_id: states[c.bus_id].energy_kwh for c in self.configs}
            try:
                self._plan(index, states)
            except Exception as exc:
                self.milp_failures += 1
                self.last_reason = f'no feasible schedule ({type(exc).__name__}: {exc}); idle fallback'
                self.p_schedule = {t: {c.bus_id: 0. for c in self.configs}
                                   for t in range(index, min(index+24, len(self.profiles.timestamps)))}
                self.q_schedule = {t: {c.bus_id: 0. for c in self.configs}
                                   for t in range(index, min(index+24, len(self.profiles.timestamps)))}
        return (dict(self.p_schedule.get(index, {})), f'Daily MILP: {self.last_reason}')

    def _plan(self, index, states):
        start = perf_counter()
        end = min(index+self.params.horizon_hours,len(self.profiles.timestamps))
        h = end-index; m = len(self.configs)
        if not h or not m:
            raise ValueError('Empty day or battery fleet')
        flows = []
        for t in range(index,end):
            flow = self.solve_fbs(_operating_point(self.network,profile_at(self.profiles,t)))
            self.forecast_fbs_calls += 1
            if not flow.converged:
                raise ValueError('Unconverged forecast network')
            flows.append(flow)
        scored = {}
        for flow in flows:
            for bus,v in flow.voltage_mag_pu.items():
                scored[bus] = scored.get(bus,0.) + max(0.,self.settings.voltage_min_pu-v) + max(0.,v-self.settings.voltage_max_pu)
        monitored = sorted(sorted(scored,key=lambda b:(-scored[b],b))[:self.params.monitored_buses])
        k = len(monitored)
        n = h*m
        # One binary Z is sufficient: C <= Cmax*Z, D <= Dmax*(1-Z).
        # Replaces two binary flags + exclusivity row without relaxing physics.
        # Blocks: charge, discharge, Q, Z, voltage-under/over, import/export slack
        C,D,Q,Z = (i*n for i in range(4))
        U=4*n; O=U+h*k; GI=O+h*k; GE=GI+h
        N=GE+h
        obj = np.zeros(N)
        lb=np.zeros(N); ub=np.full(N,np.inf)
        integral=np.zeros(N,dtype=int)
        pf_ratio=q_per_kw_at_min_pf(self.params.min_power_factor)
        tariff=self.settings.predictive_grid_tariff_per_kwh
        for t in range(h):
            for b,conf in enumerate(self.configs):
                ix=t*m+b
                cr=min(conf.power_rating_kw, conf.max_charge_kw)
                dr=min(conf.power_rating_kw, conf.max_discharge_kw)
                ub[C+ix]=cr; ub[D+ix]=dr; ub[Q+ix]=dr*pf_ratio
                ub[Z+ix]=1.
                integral[Z+ix]=1
                # Supply from PV export is assumed inexpensive only in screening.
                charge_tariff=0. if flows[t].slack_p_kw < -1e-6 else tariff
                obj[C+ix]=charge_tariff+self.params.cycling_cost_usd_per_kwh
                obj[D+ix]=self.params.cycling_cost_usd_per_kwh-tariff
                obj[Q+ix]=self.params.reactive_cost_usd_per_kvarh
            for j,bus in enumerate(monitored):
                obj[U+t*k+j]=self.params.voltage_shortfall_cost_per_pu_hour
                obj[O+t*k+j]=self.params.voltage_excess_cost_per_pu_hour
            obj[GI+t]=self.settings.shedding_penalty_per_kwh
            obj[GE+t]=self.settings.curtailment_penalty_per_kwh
        # Assemble sparse linear constraints with variable row bounds.
        rr=[]; cc=[]; vv=[]; lows=[]; highs=[]
        def add(coeff, lo=-np.inf, hi=np.inf):
            r=len(lows)
            for col,val in coeff.items():
                if abs(val)>1e-14:
                    rr.append(r); cc.append(col); vv.append(float(val))
            lows.append(float(lo)); highs.append(float(hi))
        for b,conf in enumerate(self.configs):
            e0=states[conf.bus_id].energy_kwh
            cumulative={}
            for t in range(h):
                ix=t*m+b
                add({C+ix:1., Z+ix:-min(conf.power_rating_kw,conf.max_charge_kw)},hi=0.)
                add({D+ix:1., Z+ix:min(conf.power_rating_kw,conf.max_discharge_kw)},
                    hi=min(conf.power_rating_kw,conf.max_discharge_kw))
                add({Q+ix:1., D+ix:-pf_ratio},hi=0.)
                cumulative[C+ix]=conf.eta_charge
                cumulative[D+ix]=-1./conf.eta_discharge
                add(cumulative, lo=conf.soc_min*conf.energy_capacity_kwh-e0,
                    hi=conf.soc_max*conf.energy_capacity_kwh-e0)
                # Eq. (41): strict restoration at each 24h boundary.
                # For 48/72h planning, also close intermediate days, not only
                # the end of the entire horizon.
                if (t+1) % 24 == 0 or t == h-1:
                    add(cumulative,lo=0.,hi=0.)
        for t,flow in enumerate(flows):
            for j,observed in enumerate(monitored):
                delta={}
                for b,conf in enumerate(self.configs):
                    ix=t*m+b
                    sp=self._sens_p[conf.bus_id].get(observed,0.)
                    sq=self._sens_q[conf.bus_id].get(observed,0.)
                    delta[C+ix]=-sp; delta[D+ix]=sp; delta[Q+ix]=sq
                v=flow.voltage_mag_pu[observed]
                add({**{ix:-val for ix,val in delta.items()},U+t*k:-1.},hi=v-self.settings.voltage_min_pu)
                add({**delta,O+t*k:-1.},hi=self.settings.voltage_max_pu-v)
            if self.settings.grid_import_limit_kw is not None:
                row={GI+t:-1.}
                for b in range(m):
                    ix=t*m+b; row[C+ix]=1.; row[D+ix]=-1.
                add(row,hi=self.settings.grid_import_limit_kw-flow.slack_p_kw)
            if self.settings.grid_export_limit_kw is not None:
                row={GE+t:-1.}
                for b in range(m):
                    ix=t*m+b; row[C+ix]=-1.; row[D+ix]=1.
                add(row,hi=self.settings.grid_export_limit_kw+flow.slack_p_kw)
        A=coo_matrix((vv,(rr,cc)),shape=(len(lows),N)).tocsr()
        solution=milp(c=obj, integrality=integral, bounds=Bounds(lb,ub),
                      constraints=LinearConstraint(A,np.asarray(lows),np.asarray(highs)),
                      options={'time_limit':self.params.milp_time_limit_s,'mip_rel_gap':0.03})
        self.milp_seconds += perf_counter()-start
        if solution.x is None or not np.all(np.isfinite(solution.x)):
            raise ValueError('MILP did not produce a feasible schedule: '+str(solution.message))
        # Check the returned vector even for a time-limited feasible incumbent.
        if np.max(np.abs(solution.x[integral == 1] - np.rint(solution.x[integral == 1]))) > 1e-5:
            raise ValueError('MILP integer decision tolerance exceeded')
        if np.max(A@solution.x-np.asarray(highs)) > 1e-4 or np.max(np.asarray(lows)-A@solution.x)>1e-4:
            raise ValueError('MILP incumbent violates its linear constraints')
        power={}; reactive={}
        for t in range(h):
            power[index+t]={};reactive[index+t]={}
            for b,conf in enumerate(self.configs):
                ix=t*m+b
                charge=max(0.,float(solution.x[C+ix])); discharge=max(0.,float(solution.x[D+ix]))
                if min(charge,discharge)>1e-5:
                    raise ValueError('MILP simultaneous charge/discharge')
                power[index+t][conf.bus_id]=discharge-charge
                reactive[index+t][conf.bus_id]=max(0.,float(solution.x[Q+ix]))
        self.p_schedule=power;self.q_schedule=reactive
        self.daily_plans += 1
        self.last_reason=f'feasible {h}h P/Q day ({len(monitored)} buses, status {solution.status})'

    def summary(self):
        return {'daily_milp_days_planned':self.daily_plans,
                'daily_milp_failures':self.milp_failures,
                'daily_milp_seconds':self.milp_seconds,
                'daily_milp_forecast_fbs_calls':self.forecast_fbs_calls,
                'minimum_discharge_pf':self.params.min_power_factor,
                'daily_soc_policy':'day start energy = day end energy; actual hourly equality independently audited',
                'dispatch_lookahead':f'{self.params.horizon_hours}h MILP with perfect input-profile foresight; daily replan and 24h SOC closure',
                'daily_milp_formulation':'static BESS MILP voltage linearization; not the paper full AC nonlinear GRG'}
