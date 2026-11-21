"""Horizon-aware energy closure for the existing rule-based dispatch.

The reachable-energy envelope preserves enough remaining charging/discharging
time to return to the initial stored energy. Every request still goes through
the battery and electrical constraints; the terminal check reports failure if
those constraints prevent closure. This is a schedule, not a feasibility proof
or an electricity-price optimizer. Grid charging is included in metered imports.
"""


def terminal_request(request, state, battery, remaining_hours, reserve_kw=0., *,
                     charge_headroom_kwh=None, discharge_headroom_kwh=None):
    target = battery.energy_capacity_kwh * battery.soc_initial
    charge = min(battery.power_rating_kw, battery.max_charge_kw) * battery.eta_charge
    discharge = max(0., min(battery.power_rating_kw, battery.max_discharge_kw) - reserve_kw) / battery.eta_discharge
    future_charge = remaining_hours * charge if charge_headroom_kwh is None else charge_headroom_kwh
    future_discharge = remaining_hours * discharge if discharge_headroom_kwh is None else discharge_headroom_kwh
    low = max(battery.soc_min * battery.energy_capacity_kwh, target - future_charge)
    high = min(battery.soc_max * battery.energy_capacity_kwh, target + future_discharge)
    proposed = state.energy_kwh - (request / battery.eta_discharge if request >= 0 else request * battery.eta_charge)
    desired = min(high, max(low, proposed))
    delta = desired - state.energy_kwh
    return -delta / battery.eta_charge if delta >= 0 else -delta * battery.eta_discharge
