from dataclasses import dataclass
from math import isfinite


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


@dataclass(frozen=True)
class FleetUnit:
    unit_id: str
    config: BESSConfig
    terminal_soc: float | None = None
    reactive_kvar: float = 0.0
    reserve_weight: float | None = None

    def __post_init__(self):
        battery = self.config
        if not isinstance(self.unit_id, str) or not self.unit_id.strip() or type(battery.bus_id) is not int:
            raise ValueError("A fleet unit requires a nonempty ID and an integer installation bus")
        for value in (battery.energy_capacity_kwh, battery.power_rating_kw, battery.max_charge_kw, battery.max_discharge_kw):
            if not isfinite(value) or value <= 0:
                raise ValueError("Fleet unit capacity and ratings must be positive and finite")
        if not 0 <= battery.soc_min < battery.soc_max <= 1 or not battery.soc_min <= battery.soc_initial <= battery.soc_max:
            raise ValueError("Fleet unit initial SOC must be inside its validated SOC bounds")
        if not 0 < battery.eta_charge <= 1 or not 0 < battery.eta_discharge <= 1:
            raise ValueError("Fleet unit efficiencies must be between zero and one")
        if self.terminal_soc is not None and not battery.soc_min <= self.terminal_soc <= battery.soc_max:
            raise ValueError("Fleet unit terminal SOC lies outside its SOC bounds")
        if not isfinite(self.reactive_kvar) or abs(self.reactive_kvar) >= battery.power_rating_kw:
            raise ValueError("Fleet unit reactive setpoint must fit the inverter rating")
        if self.reserve_weight is not None and (not isfinite(self.reserve_weight) or self.reserve_weight < 0):
            raise ValueError("A fleet reserve weight must be finite and nonnegative")

    @property
    def target_soc(self):
        return self.config.soc_initial if self.terminal_soc is None else self.terminal_soc


@dataclass(frozen=True)
class BESSFleet:
    units: tuple[FleetUnit, ...] = ()

    def __post_init__(self):
        units = tuple(sorted(self.units, key=lambda unit: unit.config.bus_id))
        if len(units) > 3 or len({unit.unit_id for unit in units}) != len(units):
            raise ValueError("A fleet supports at most three distinct unit IDs")
        if len({unit.config.bus_id for unit in units}) != len(units):
            raise ValueError("Fleet units must use distinct installation buses")
        object.__setattr__(self, "units", units)


@dataclass
class FleetUnitStep:
    unit_id: str
    bus_id: int
    requested_kw: float
    battery: "BESSStepResult"
    reactive_kvar: float
    reserve_kw: float
    reserve_energy_kwh: float
    dispatchable_kw: float
    dispatchable_kwh: float
    terminal_target_soc: float

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


def step_bess(config: BESSConfig, 
              state: BESSState, 
              requested_power_kw: float, 
              dt_hours: float):
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
