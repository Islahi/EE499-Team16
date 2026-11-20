# Testing the hourly simulation

Run commands from `07_Implementation`. Install the existing `requirements.txt`
if pandas is unavailable. `bess.py` and `data_loader.py` are used unchanged.

## 1. Run the automated checks

```powershell
python -m unittest discover -s tests -p test_simulation.py -v
```

The 25 integration tests check:

- baseline agreement with a direct FBS call;
- charge/discharge signs, efficiency and SOC carryover;
- physical power/SOC clipping through the existing BESS function;
- reserve power headroom and energy retention, using the horizon's peak load;
- infeasibility when the BESS cannot provide reserve;
- under/overvoltage detection at 0.95/1.05 pu;
- stopping after FBS failure without advancing SOC;
- optional continuation with failures still flagged;
- profile bus completeness, series length and hourly alignment;
- isolated state copies and idle operation when no dispatch policy is supplied;
- a complete synthetic 2,160-hour January–March 2026 horizon.
- automatic voltage/import/export controls and per-bus action records;
- proportional P/Q reduction, energy balance and unchanged source profiles;
- battery charging/discharging reducing curtailed/shed energy;
- SOC updates only once when network limits pause a battery action;
- infeasibility for disabled controls or uncontrollable slack voltage.

Run the existing tests alongside these with:

```powershell
python -m unittest discover -s tests -v
```

## 2. Inspect a short example

```powershell
python examples/run_simulation.py
```

This compares no BESS with a fixed BESS on the guide's five-bus network using
synthetic daily load/PV curves. It prints convergence, feasibility, voltage
range, losses, SOC and the first six BESS requests/actual outputs.

Look for:

1. Both runs finish 24 hours and converge.
2. Negative actual BESS power charges the battery; positive power discharges it.
3. Requests are clipped at SOC, power or reserve limits when necessary.
4. SOC remains between the example's 10% and 90% physical bounds. The reserve
   energy floor may stop discharge above 10%.
5. Any voltage remaining out of range after controls is listed in
   `step.voltage_violations` and makes `result.feasible` false. Disable controls
   explicitly to inspect uncorrected voltage violations.

To exercise both curtailment and shedding from the repository root:

```powershell
python .\07_Implementation\examples\run_simulation.py --pv-rating-kw 1200 --grid-import-limit-kw 400 --grid-export-limit-kw 0
```

This uses demonstration ratings/caps only. Both runs should print nonzero
curtailed/shed energies. `feasible=True` describes electrical/reserve compliance,
not a guarantee that all original demand was served.

For a three-month synthetic smoke test:

```powershell
python examples/run_simulation.py --hours 2160
```

The example assumes a 1,000 kWh / 200 kW BESS and 95% efficiency in each
direction. These are demonstration parameters, not a decision about the
project's unresolved 85% efficiency interpretation. The example policy targets
600 kW net load. It does not optimize the battery or establish cost savings.

## 3. Use the module with actual files

```python
from pathlib import Path
from src.data_loader import ProfileData
from src.network_cases import build_guide_5_bus_case
from src.simulation import SimulationConfig, simulate_timeseries

network = build_guide_5_bus_case()
profiles = ProfileData(
    csv_load=Path("load_profile.csv"),
    csv_pv=Path("pv_profile.csv"),
)
result = simulate_timeseries(network, profiles, SimulationConfig())
print(result.message, result.completed, result.converged, result.feasible)
```

Use CSV files matching the selected network: every configured load bus needs
P/Q demand and every PV bus needs P/Q generation at every timestamp. The current
loader requires `timestamp,bus_id,p_kw,q_kvar` in both files. Do not mix inputs
for the prepared 11 kV feeder with the guide's 12.66 kV feeder accidentally.

To add a BESS, pass a `BESSConfig` and a named policy:

```python
def dispatch_policy(index, profile, state):
    return 50.0  # Request 50 kW discharge, clipped to available limits/reserve.

result = simulate_timeseries(
    network, profiles, SimulationConfig(), bess_config, dispatch_policy
)
```

No policy means zero requested BESS power. Disable reserve explicitly for a
physical-SOC-only trial with `SimulationConfig(reserve_fraction=0.0)`.

Each step exposes `operating_point`, `power_flow`, `bess_step`, `bess_state`,
`voltage_violations`, `reserve_power_shortfall_kw`,
`reserve_energy_shortfall_kwh`, `feasible`, `messages`, `curtailment_kw`,
`shedding_kw`, `curtailment_by_bus_kw` and `shedding_by_bus_kw`.

`completed` means every supplied timestamp was processed. `converged` means
all FBS calls converged. `feasible` also requires voltage/reserve compliance.
Failed-step `bess_step` values are tentative diagnostics; `bess_state` and
`final_bess_state` retain the last accepted state.

Real-data checks still needed: confirm load/PV magnitudes and timestamps,
observe SOC over the chosen three months, and compare selected hours against
manual/direct FBS runs. Automatic proportional curtailment/shedding is now
included. Terminal SOC, thermal constraints and optimization remain outside
this implementation.
