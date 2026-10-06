"""Task 10 skeleton. Battery equations belong to Tasks 20–23."""
from dataclasses import dataclass


@dataclass(frozen=True)
class BESSConfig:
    bus_id: int
    energy_capacity_kwh: float
    power_rating_kw: float
    soc_min: float
    soc_max: float
    soc_initial: float
    eta_charge: float
    eta_discharge: float
    max_charge_kw: float | None = None
    max_discharge_kw: float | None = None


@dataclass(frozen=True)
class BESSState:
    energy_kwh: float
    soc: float


@dataclass(frozen=True)
class BESSStepResult:
    actual_power_kw: float
    energy_before_kwh: float
    energy_after_kwh: float
    soc_before: float
    soc_after: float
    limited: bool
    limit_reason: str


def step_bess(config: BESSConfig, state: BESSState, requested_power_kw: float,
              dt_hours: float) -> BESSStepResult:
    raise NotImplementedError("Tasks 20–23: implement documented BESS limits and energy update")
