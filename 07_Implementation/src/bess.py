class BESSConfig:
    def __init__(self, 
                 bus_id: int, 
                 energy_capacity_kwh: float, 
                 power_rating_kw: float,
                 soc_min: float, 
                 soc_max: float, 
                 soc_initial: float,
                 eta_charge: float, 
                 eta_discharge: float,
                 max_charge_kw: float | None = None, 
                 max_discharge_kw: float | None = None):
        self.bus_id = bus_id
        self.energy_capacity_kwh = energy_capacity_kwh
        self.power_rating_kw = power_rating_kw
        self.soc_min = soc_min
        self.soc_max = soc_max
        self.soc_initial = soc_initial
        self.eta_charge = eta_charge
        self.eta_discharge = eta_discharge
        self.max_charge_kw = max_charge_kw if max_charge_kw is not None else power_rating_kw
        self.max_discharge_kw = max_discharge_kw if max_discharge_kw is not None else power_rating_kw




class BESSState:
    def __init__(self, energy_kwh: float, soc: float):
        self.energy_kwh = energy_kwh
        self.soc = soc



class BESSStepResult:
    def __init__(self, 
                 actual_power_kw: float,
                 energy_before_kwh: float,
                 energy_after_kwh: float,
                 soc_before: float,
                 soc_after: float,
                 limited: bool,
                 limit_reason: str):

        self.actual_power_kw = actual_power_kw
        self.energy_before_kwh = energy_before_kwh
        self.energy_after_kwh = energy_after_kwh
        self.soc_before = soc_before
        self.soc_after = soc_after
        self.limited = limited
        self.limit_reason = limit_reason       


def step_bess(config: BESSConfig, state: BESSState, requested_power_kw: float, dt_hours: float):
    energy_before = state.energy_kwh
    soc_before = state.soc

    if dt_hours <= 0:
        raise ValueError("Time step must be positive.")
        
    if requested_power_kw > 0:
        energy_min = config.soc_min * config.energy_capacity_kwh
        power_soc_limit = max(
            0,
            (energy_before - energy_min) * config.eta_discharge / dt_hours
        )
        max_discharge = config.max_discharge_kw
        if max_discharge is None:
            max_discharge = config.power_rating_kw
        actual_power_kw = min(
            requested_power_kw,
            config.power_rating_kw,
            max_discharge,
            power_soc_limit
        )
        energy_after = energy_before - (
            actual_power_kw * dt_hours / config.eta_discharge
        )
    elif requested_power_kw < 0:

        energy_max = config.soc_max * config.energy_capacity_kwh

        power_soc_limit = max(
            0,
            (energy_max - energy_before) / (config.eta_charge * dt_hours)
        )

        max_charge = config.max_charge_kw

        if max_charge is None:
            max_charge = config.power_rating_kw

        actual_power_kw = min(
            abs(requested_power_kw),
            config.power_rating_kw,
            max_charge,
            power_soc_limit
        )

        energy_after = energy_before + (
            actual_power_kw * dt_hours * config.eta_charge
        )

        actual_power_kw = -actual_power_kw
    else:
        actual_power_kw = 0.0
        energy_after = energy_before
        
    soc_after = energy_after / config.energy_capacity_kwh

    limited = not abs(actual_power_kw - requested_power_kw) <= 1e-9

    if limited:
        limit_reason = "Power or SOC limit reached"
    else:
        limit_reason = "None"

    return BESSStepResult(
        actual_power_kw=actual_power_kw,
        energy_before_kwh=energy_before,
        energy_after_kwh=energy_after,
        soc_before=soc_before,
        soc_after=soc_after,
        limited=limited,
        limit_reason=limit_reason
    )