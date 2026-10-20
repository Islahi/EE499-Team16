# Understanding `simulation.py`

This README explains [simulation.py](simulation.py), the module that connects
the project's profile loader, battery model and power-flow solver. It is part
of the actual program. Future UI and optimizer code will call its functions.

## 1. Where it fits

```text
Load/PV CSV files
       |
   data_loader.py -> ProfileData containing all hourly values
       |
   simulation.py
       |-- takes one hour of load/PV values
       |-- asks the supplied dispatch policy for requested battery power
       |-- calls bess.py to calculate feasible battery power and energy
       |-- calls fbs.py to calculate voltages, currents and losses
       |-- curtails PV or sheds load when configured network limits require it
       |-- checks voltage and reserve requirements
       |-- saves the result and carries battery state into the next hour
       |
   TimeSeriesSimulationResult
       |
   Future metrics / optimizer / results / UI
```

The network supplies the buses, lines and equipment definitions. The profiles
supply the actual demand and PV output at each timestamp. The battery
configuration supplies its connection bus, power, capacity, SOC and efficiency.

The module does not contain a command-line entry point. Import its functions
from another script. For a runnable demonstration, use
[examples/run_simulation.py](../examples/run_simulation.py).

## 2. Objects and functions in the file

| Name | What it does |
|---|---|
| `SimulationConfig` | Groups voltage limits, reserve settings, FBS configuration and failure behavior. |
| `SimulationStepResult` | Stores inputs, calculations and feasibility for one hour. |
| `TimeSeriesSimulationResult` | Stores all hourly results and the overall status. |
| `DispatchPolicy` | Describes a function receiving an hour index, profile slice and battery state, then returning requested battery power in kW. |
| `_check_number()` | Rejects non-numeric, infinite or NaN inputs where it is called. |
| `_complete_profile()` | Checks bus references and required data, then adds zeros for buses without profile entries that are allowed to be omitted. |
| `_run_bess()` | Holds reserve power/energy, then calls the existing `step_bess()` calculation. |
| `_network_violations()` | Checks upper/lower voltage and optional import/export caps. |
| `_scale_operating_power()` | Creates a trial with proportionally reduced PV or demand, scaling Q with P. |
| `_reduce_until_allowed()` | Uses bounded bisection and FBS calls to find a reduction that clears the selected limit. |
| `simulate_step()` | Runs one hour through the battery and power-flow calculations. |
| `simulate_timeseries()` | Runs all supplied hourly timestamps and carries SOC between them. |

The three `@dataclass` classes are containers with named fields. Python creates
their constructors automatically. A leading underscore marks a helper intended
for use inside this module. Other modules should call the two `simulate_*`
functions instead of the helpers.

`copy()` creates separate battery configuration/state objects so this module
can apply reserve restrictions and pass state to a policy without changing the
caller's originals. `field(default_factory=FBSConfig)` creates a separate
default FBS configuration for each `SimulationConfig`.

## 3. What happens in one hour

`simulate_step()` receives the network, one `ProfileSlice`, FBS settings and,
optionally, a battery configuration, current battery state and power request.

1. Validate the network and assemble complete bus-indexed load/PV dictionaries.
   Every configured load/PV bus needs its required profile values. Unknown
   bus IDs and invalid numbers raise errors.
2. Initialize battery P/Q injections to zero at every bus.
3. If a battery is supplied, calculate reserve and limit its discharge request.
   Call `step_bess()` for its actual power, new energy and new SOC.
4. Insert actual battery active power at its connection bus. Battery reactive
   power remains zero in the current model.
5. Call `run_fbs()` with the assembled `OperatingPoint`.
6. If FBS converges, pause a battery action that worsens the triggering network
   limit. Apply proportional PV curtailment for excessive voltage/export, then
   proportional load shedding for insufficient voltage/excessive import. Rerun
   FBS for control trials and retain a converged final point. Accept battery
   energy only once, using the final action. A converged hour can remain
   infeasible if the controller cannot clear every network/reserve violation.
7. If FBS fails, retain the previous accepted battery state and return the
   attempted calculations as diagnostics.

The sign convention is:

| Power | Meaning |
|---|---|
| Positive load P/Q | Consumption |
| Positive PV P | Generation |
| Positive BESS P | Discharge into the feeder |
| Negative BESS P | Charge from the feeder |
| Positive slack P | Power supplied by the upstream grid |

Power uses kW/kvar, stored energy uses kWh, and SOC is a fraction: `0.5` means
50%. Voltage uses per unit: `1.0 pu` is the nominal base voltage, so `0.95 pu`
means 95% of nominal voltage.

## 4. What happens over many hours

`simulate_timeseries()` receives `NetworkModel`, `ProfileData`,
`SimulationConfig`, and optional `BESSConfig` and `dispatch_policy` inputs.

It checks that profiles are nonempty, hourly, consecutive and the same length
for each bus series. It calculates peak total demand across the supplied
horizon and initializes battery energy from:

```text
initial_energy_kwh = energy_capacity_kwh * soc_initial
```

For each timestamp it obtains a `ProfileSlice`, requests battery power from
the policy, calls `simulate_step()`, saves the result and carries the accepted
battery state forward. Every new time-series call starts from `soc_initial`.
It does not resume automatically from an earlier run.

With no policy, the requested battery power is zero. A policy has this shape:

```python
def dispatch_policy(index, profile, state):
    return 50.0  # Example request: discharge 50 kW for this hour.
```

The policy decides what is requested. Battery and reserve limits determine
what is actually delivered. The policy above is only a usage example, not an
approved operating strategy or optimization method.

The number of hours comes from the input timestamps. Three months is the
initial project horizon; it is not a fixed limit inside this module.

## 5. How reserve is handled

In a run with a BESS, the default reserve is 10% of peak total demand, held for
one hour. A no-BESS baseline has no battery reserve check.

```text
reserve_kw = reserve_fraction * peak_load_kw
reserve_energy_kwh = reserve_kw * reserve_duration_hours / eta_discharge
required_energy_kwh = soc_min * energy_capacity_kwh + reserve_energy_kwh
```

Ordinary discharge retains both spare discharge power and the required stored
energy. The module uses a copy of `BESSConfig` with a higher effective minimum
SOC, then lets the existing battery function apply its normal limits.

Example: with 1,000 kW peak demand, the default reserve is 100 kW. A 200 kW
battery therefore has at most 100 kW available for ordinary discharge. If its
energy capacity is 1,000 kWh, physical minimum SOC is 10%, and discharge
efficiency is 95%, the reserve energy floor is approximately 205.26 kWh, or
20.53% SOC. These are illustrative input values, not fixed battery parameters.

Reserve shortfalls make an hour infeasible. Charging is still allowed when
initial energy is below the reserve floor. Both the starting and ending energy
are checked; charging by the end of an hour does not erase a shortage at its
start. A battery whose rating or usable capacity cannot cover reserve remains
infeasible even if its FBS calculation converges.

For the time-series function, `peak_load_kw` is the maximum sum of bus demand
over the entire supplied horizon. For a standalone `simulate_step()` call,
pass `peak_load_kw` explicitly to use the same reserve basis. If omitted, that
single hour's total demand is used.

## 6. Settings that can already change

These defaults are used only when the caller does not override them:

| `SimulationConfig` field | Default | Purpose |
|---|---|---|
| `fbs_config` | A new `FBSConfig()` | Controls FBS iterations, tolerance and other solver settings. |
| `voltage_min_pu` | `0.95` | Minimum permitted voltage. |
| `voltage_max_pu` | `1.05` | Maximum permitted voltage. |
| `reserve_fraction` | `0.10` | Fraction of peak demand held as battery reserve; `0.0` disables reserve. |
| `reserve_duration_hours` | `1.0` | Duration for which reserve energy must be available. |
| `stop_on_power_flow_failure` | `True` | Stops the hourly loop after a non-converged FBS result. |
| `allow_pv_curtailment` | `True` | Reduce PV to address upper-voltage/export-limit violations. |
| `allow_load_shedding` | `True` | Reduce demand to address lower-voltage/import-limit violations. |
| `grid_import_limit_kw` | `None` | Optional upstream import cap; None means unlimited. |
| `grid_export_limit_kw` | `None` | Optional export cap; 0 forbids export, None means unlimited. |
| `control_max_iterations` | `30` | Maximum bisection iterations per curtailment/shedding search. |
| `control_tolerance_kw` | `1e-6` | Numerical tolerance for import/export-cap comparisons. |

For example:

```python
from src.fbs import FBSConfig
from src.simulation import SimulationConfig

settings = SimulationConfig(
    fbs_config=FBSConfig(max_iterations=100, voltage_tolerance_pu=1e-6),
    voltage_min_pu=0.95,
    voltage_max_pu=1.05,
    reserve_fraction=0.0,
    reserve_duration_hours=1.0,
    stop_on_power_flow_failure=True,
)
```

Battery bus, energy capacity, power rating, SOC bounds, initial SOC and
efficiencies are supplied through `BESSConfig`. Load and PV values come from
`ProfileData`. No fixed study network or battery size is embedded here.

## 7. Values that need future work to become changeable

| Current assumption | Where it appears | Future work |
|---|---|---|
| One-hour simulation step | `_run_bess()` passes `dt_hours=1.0`; the loop checks `1.0` hours and `3600` seconds and returns `dt_hours=1.0`. | Pass the actual interval consistently through simulation and battery calls, update the loader, and test another interval such as 15 minutes. |
| Active-power-only battery | `simulate_step()` supplies zero `q_bess_kvar` at every bus. | Extend the battery/dispatch interfaces with reactive power and suitable inverter limits. |
| Small numerical tolerance `1e-9` | Clipping, peak-load and reserve-shortfall comparisons. | If needed, expose named tolerances with clear units rather than changing individual comparisons. |
| Initial energy from `soc_initial` | `simulate_timeseries()` initializes state for each run. | Add an explicit initial-state input if continuing an earlier run is needed. |
| Reserve based on horizon peak demand | The pre-loop demand calculation and `_run_bess()`. | Add a documented reserve policy if a different definition is later selected. |

The one-hour simulation interval and one-hour reserve duration are different
concepts. Reserve duration is configurable already; simulation interval is not.

The future UI can expose existing configuration fields as input controls and
pass them into this module. Changing these settings does not require rewriting
the hourly loop. This README records the remaining changes for later; it does
not change the current Python implementation.

## 8. Understanding the output

`TimeSeriesSimulationResult` contains:

| Field | Meaning |
|---|---|
| `steps` | One `SimulationStepResult` for every attempted hour. |
| `dt_hours` | Current simulation interval: `1.0`. |
| `completed` | Every supplied timestamp was processed. |
| `converged` | Every attempted FBS call converged. |
| `feasible` | Every attempted hour converged and passed voltage/reserve checks. |
| `final_bess_state` | Last accepted battery energy/SOC, or `None` without a BESS. |
| `message` | Overall completion or failure message. |

`completed=True` alone does not establish that a run is usable. For example,
all hours can be processed with voltage violations, giving `converged=True`
and `feasible=False`. If continuation after FBS failure is enabled, a completed
run can also have `converged=False`.

Each item in `steps` contains:

| Field | Meaning |
|---|---|
| `timestamp` | Time of the attempted hour. |
| `operating_point` | Complete bus-indexed load, PV and actual battery injections sent to FBS. |
| `power_flow` | The solver's voltages, currents, powers, losses and convergence details. |
| `bess_request_kw` | Original requested battery power before clipping. |
| `bess_step` | Attempted battery power/energy/SOC calculation, or `None`. |
| `bess_state` | Accepted battery state after this hour, or `None`. |
| `voltage_violations` | Bus IDs mapped to their out-of-bounds voltage values. |
| `reserve_power_kw` | Required reserve power. |
| `reserve_power_shortfall_kw` | Missing reserve power capability. |
| `reserve_energy_shortfall_kwh` | Missing stored energy for reserve. |
| `feasible` | Whether this hour passed all implemented checks. |
| `messages` | Reasons for power-flow failure or voltage/reserve violations. |
| `curtailment_kw`, `shedding_kw` | Actual total P removed during this hour; None for failed hours. |
| `curtailment_by_bus_kw`, `shedding_by_bus_kw` | Actual removed P at each bus, preserving original minus final input. |

On FBS failure, `bess_step` describes a tentative update, while `bess_state`
retains the previous accepted state. Use `bess_state` for accepted SOC history.
Remaining voltage/grid-cap/reserve violations do not stop the loop; they are
recorded and make the run infeasible. By default only FBS non-convergence stops
the loop. Electrical feasibility does not guarantee that original demand was
fully served: shedding is a separate metric.

### Curtailment and shedding controls

Profile load/PV values are treated as original demand/available generation.
The controller modifies separate operating-point dictionaries and records the
removed power. It scales P/Q together across the affected buses, with no
critical-load priorities. Metrics reads the records automatically.

The controller searches from no removal to full removal using repeated FBS
calls, accepting a reduction that clears the triggering limit. If full removal
cannot clear it, the previous point is retained and residual infeasibility is
reported. It processes high-voltage/export problems before low-voltage/import
problems. Interacting problems can remain infeasible; this is a simple control
rule, not an optimal dispatcher. Initial non-convergence is still a solver
failure, not an invented amount of load shedding.

To simulate a supply/export restriction:

```python
settings = SimulationConfig(
    grid_import_limit_kw=400.0,
    grid_export_limit_kw=0.0,
)
```

Caps are optional study settings, not conductor thermal ratings. Default None
allows unlimited import/export. Voltage controls still apply. Disable an action
with `allow_pv_curtailment=False` or `allow_load_shedding=False`; any uncorrected
limit violation remains infeasible.

From the repository root, this demonstration exercises both actions:

```powershell
python .\07_Implementation\examples\run_simulation.py --pv-rating-kw 1200 --grid-import-limit-kw 400 --grid-export-limit-kw 0
```

## 9. Trying it and checking the results

From `07_Implementation`, run:

```powershell
python examples/run_simulation.py
python examples/run_simulation.py --hours 2160
python -m unittest discover -s tests -p test_simulation.py -v
```

The example uses synthetic data; `tests/test_simulation.py` contains automated
checks. Both call the actual simulation module. See the
[simulation test guide](../Validation/Simulation_Test_Guide.md) for CSV usage,
test coverage and the checks to make with actual project data.

The current module does not choose the best battery, calculate economic
fitness, export files or enforce terminal SOC. Those belong to later program
work. Thermal constraints are excluded from the agreed initial scope.
