import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.bess import BESSConfig, BESSState, step_bess
from math import sqrt


config = BESSConfig(
    bus_id=4,
    energy_capacity_kwh=500,
    power_rating_kw=100,
    soc_min=0.1,
    soc_max=0.9,
    soc_initial=0.5,
    eta_charge=sqrt(0.85),
    eta_discharge=sqrt(0.85)
)

state = BESSState(
    energy_kwh=250,
    soc=0.5
)

result = step_bess(
    config=config,
    state=state,
    requested_power_kw=0,
    dt_hours=1
)

print("Actual power:", result.actual_power_kw, "kW")
print("Energy before:", result.energy_before_kwh, "kWh")
print("Energy after:", result.energy_after_kwh, "kWh")
print("SOC before:", result.soc_before * 100, "%")
print("SOC after:", result.soc_after * 100, "%")
print("Limited:", result.limited)
print("Reason:", result.limit_reason)