# Understanding `metrics.py`

[metrics.py](metrics.py) summarizes the results returned by
[simulation.py](simulation.py). It is part of the actual program and can later
be called by the optimizer, result exporter and UI.

## Start here: commands from the repository root

If PowerShell shows `PS C:\Users\ISLAHI\Documents\EE499-Team16>`, run:

```powershell
python .\07_Implementation\examples\run_simulation.py
python -m unittest discover -s .\07_Implementation\tests -p test_metrics.py -v
```

The example should print baseline/BESS summaries. Test discovery should report
16 metrics tests, not zero. The example uses synthetic inputs and runs without
cost coefficients. Cost stays unavailable until prices are supplied; curtailment
and shedding are now calculated automatically from simulation action records.

The shorter commands `python examples/run_simulation.py` and
`python -m unittest discover -s tests -p test_metrics.py -v` require first moving
into `07_Implementation`:

```powershell
cd .\07_Implementation
python examples/run_simulation.py
python -m unittest discover -s tests -p test_metrics.py -v
```

Choose one command sequence to match your current folder. Do not repeat the
directory-change command when already inside `07_Implementation`.

`can't open file ...\EE499-Team16\examples\run_simulation.py` means Python
looked for the relative path in the wrong folder. `Ran 0 tests` / `NO TESTS RAN`
means discovery did not find the intended tests; it is not a passing test run.

## What happens

```text
Completed simulation + economic settings + battery configuration
                              |
                        evaluate_results()
                              |
                       PerformanceMetrics
```

The function integrates each recorded power over the time interval:

```text
energy_kwh = sum(power_kw * dt_hours)
```

It reads the existing results without rerunning power flow, changing battery
SOC or selecting operating actions. Empty, incomplete and non-converged runs
raise `ValueError`. A converged run with voltage/reserve violations can be
summarized, but its returned `feasible` flag stays false.

## Main inputs

```python
metrics = evaluate_results(
    simulation_result=result,
    economic_config=EconomicConfig(),
    bess_config=bess_config,
)
```

Use the same `BESSConfig` supplied to the simulation. Nominal power and energy
capacity are not stored in the simulation result, so they must be supplied for
a BESS run. Omit `bess_config` for a no-BESS baseline.

`EconomicConfig()` leaves coefficients unset. Once the team finds suitable
values, supply `cost_per_kwh` and `cost_per_kw` in one currency. The default
currency label is SAR; the module does not perform currency conversion.

## Which variables to fill or change

### Values you can supply now

| Variable | Where to supply it | What to put there |
|---|---|---|
| `cost_per_kwh` | `EconomicConfig`, or example flag `--cost-per-kwh` | Sourced nonnegative battery energy cost in currency/kWh. Leave unset until the team finds a value. |
| `cost_per_kw` | `EconomicConfig`, or example flag `--cost-per-kw` | Sourced nonnegative power/inverter cost in currency/kW. Leave unset until available. |
| `currency` | `EconomicConfig`, or example flag `--currency` | Currency shared by both coefficients; default `SAR`. Changing the label does not convert prices. |
| `hours` | Example flag `--hours` | Synthetic demonstration duration. Default 24; 2160 represents January–March 2026. Actual runs use the number of input timestamps. |
| `bess_config` | Supply the same object to simulation and evaluation | The battery bus, energy capacity, power rating, SOC bounds/initial SOC and directional efficiencies used in that run. |
| `voltage_min_pu`, `voltage_max_pu` | `SimulationConfig` before running simulation | Voltage bounds; current defaults are 0.95 and 1.05 pu. |
| `reserve_fraction` | `SimulationConfig` before simulation | Fraction of peak demand reserved; default 0.10. Use 0.0 to disable it for a trial. |
| `reserve_duration_hours` | `SimulationConfig` before simulation | Reserve duration; default one hour. This does not change the simulation time step. |
| `allow_pv_curtailment` | `SimulationConfig` before simulation | Default True: reduce PV if upper voltage or export limits are exceeded. |
| `allow_load_shedding` | `SimulationConfig` before simulation | Default True: reduce demand if lower voltage or import limits are exceeded. |
| `grid_import_limit_kw` | `SimulationConfig` or `--grid-import-limit-kw` | Optional upstream supply cap in kW; None means unlimited. |
| `grid_export_limit_kw` | `SimulationConfig` or `--grid-export-limit-kw` | Optional export cap in kW; use 0 to forbid export, None for unlimited. |
| `pv_rating_kw` | Example flag `--pv-rating-kw` | Override the demonstration's bus-4 PV rating to explore surplus generation. |

Example from the repository root, using illustrative cost coefficients:

```powershell
python .\07_Implementation\examples\run_simulation.py --hours 24 --cost-per-kwh 2 --cost-per-kw 3 --currency SAR
```

Replace `2` and `3` with sourced coefficients when available. These numbers
only demonstrate the interface. If a quoted all-in cost already includes the
power equipment, do not add the same equipment cost again as a separate term.
Use consistent units and currency for both terms.

The example's battery values are in its `main()` function, in the `BESSConfig`
construction. Its 600 kW demonstration target is in `dispatch_bess()`. These
are example settings; the real simulation accepts whichever configuration and
dispatch function the caller supplies. Voltage/reserve settings can be passed
by replacing the example's `settings = SimulationConfig()` construction.

For actual data, supply your network and a `ProfileData` loaded from matching
load/PV CSV files instead of `make_demo_profiles()`. See
[the simulation test guide](../Validation/Simulation_Test_Guide.md) for CSV
requirements. There are currently no example CLI options for battery size,
voltage, reserve, or actual CSV paths; those use the Python configuration/API.

### Curtailment and shedding: now calculated automatically

You do not need to fill these by hand for new simulation runs. The simulator
records reductions after applying proportional PV/load controls and rerunning
FBS. Metrics reads them automatically:

| Variable | Meaning | What to supply |
|---|---|---|
| `curtailment_kw` | Available PV power intentionally not used | A list of total curtailed kW at each timestamp, summed across PV buses. |
| `shedding_kw` | Requested demand intentionally left unserved | A list of total shed kW at each timestamp, summed across load buses. |

Each list needs exactly `len(result.steps)` finite, nonnegative numbers in the
same timestamp order as the evaluated run. Supply power in kW, not energy in
kWh. The evaluator multiplies each value by the time interval itself.

For one hour, the intended accounting is:

```text
curtailment_kw = available_PV_kw - used_PV_kw
shedding_kw = requested_load_kw - served_load_kw
```

The final values sent to FBS represent `used_PV_kw` and `served_load_kw`.
Simulation records original minus final P, both per bus and as hourly totals.
Metrics integrates those totals. Explicit arrays remain available for legacy
results that have no records, but cannot contradict existing simulated records.

Omit both optional arguments, or pass `None` to use automatic records:

```python
from src.metrics import EconomicConfig, evaluate_results

# result and bess_config come from your completed BESS simulation.
metrics = evaluate_results(
    simulation_result=result,
    economic_config=EconomicConfig(),
    bess_config=bess_config,
    curtailment_kw=None,
    shedding_kw=None,
)
```

No action produces recorded zero; missing legacy records remain unavailable.
Do not invent arrays or change metric outputs to force an improvement.

To exercise both actions from the repository root:

```powershell
python .\07_Implementation\examples\run_simulation.py --pv-rating-kw 1200 --grid-import-limit-kw 400 --grid-export-limit-kw 0
```

These are demonstration settings: 1,200 kW PV, a 400 kW import cap and no export.
They are not established ratings of the actual project network. Voltage limits
remain 0.95–1.05 pu. Default import/export caps are unlimited. Both baseline
and BESS runs print calculated curtailed/shed energy and percentage reductions.
The simple controller can pause charging/discharging that worsens a limit.
Electrical feasibility can be True while demand was shed: inspect shedding
energy separately. The controller is not an optimal dispatch policy.

### Outputs to read, not fill manually

`bess_cost`, `loss_energy_kwh`, `grid_import_energy_kwh`, `grid_export_energy_kwh`,
`curtailment_energy_kwh`, `load_shedding_energy_kwh`, voltage summaries and SOC
summaries are calculated outputs. Read them from `metrics`; changing an output
does not change the simulation or its inputs. No changes inside `metrics.py`
are required to supply the inputs described above.

## Cost calculation

```text
BESS cost = cost_per_kwh * energy_capacity_kwh
          + cost_per_kw * power_rating_kw
```

This is the agreed simple investment-cost model. There are no operating costs,
electricity tariffs, interest, annualization, replacement or degradation costs.
The no-BESS investment cost is zero. For a BESS, either missing coefficient
produces `bess_cost=None` and an explanatory note. Explicit zero coefficients
are allowed and are distinct from missing values.

Illustrative arithmetic only: a 500 kWh / 100 kW battery with coefficients
2 SAR/kWh and 3 SAR/kW costs `500*2 + 100*3 = 1,300 SAR`. These are test numbers,
not recommended or sourced battery prices. Changing prices requires new
`EconomicConfig` inputs, not edits to the calculation.

## Returned fields

| Field | Meaning |
|---|---|
| `duration_hours` | Number of steps multiplied by the result's time interval. |
| `served_load_energy_kwh` | Active demand actually included in the power-flow inputs. |
| `pv_generation_energy_kwh` | PV active generation actually included in those inputs. |
| `requested_load_energy_kwh` | Original demand: served energy plus shed energy, when records are available. |
| `available_pv_energy_kwh` | Original available PV: used generation plus curtailed energy, when records are available. |
| `grid_import_energy_kwh` | Positive slack power integrated over time. |
| `grid_export_energy_kwh` | Magnitude of negative slack power integrated over time. |
| `loss_energy_kwh` | Total active line-loss power integrated over time. |
| `peak_grid_import_kw` | Highest positive slack power; zero for export-only runs. |
| `voltage_min_pu`, `voltage_max_pu` | Minimum and maximum voltage across all buses/hours. |
| `voltage_violation_hours` | Duration with at least one violating bus. |
| `voltage_violation_bus_hours` | Sum of violating-bus counts multiplied by the interval. |
| `reserve_violation_hours` | Duration with insufficient reserve power or energy, counting each step once. |
| `bess_charge_energy_kwh` | Network-side energy absorbed by the battery. |
| `bess_discharge_energy_kwh` | Network-side energy delivered by the battery. |
| `bess_soc_min`, `bess_soc_max` | SOC extrema, including initial SOC; `None` without a BESS. |
| `bess_cost`, `currency` | Simple investment cost and currency label. |
| `curtailment_energy_kwh` | Integrated simulated curtailment, or external legacy records; None if no complete records exist. |
| `load_shedding_energy_kwh` | Integrated simulated shedding, or external legacy records; None if no complete records exist. |
| `feasible` | Preserves the simulation/step feasibility flags. |
| `notes` | Explanations of unavailable metrics and infeasibility. |

Charge/discharge energy uses actual, clipped battery power. It is not equal
to the stored-energy change because the battery model includes efficiency.
Example: one hour discharging 40 kW at 80% efficiency delivers 40 kWh but
removes 50 kWh from stored energy.

Voltage/reserve classification comes from the simulation's recorded checks.
This module does not replace the chosen voltage limits with another set.

## Curtailment and shedding availability

The simulator now records curtailment/shedding for every converged hour. New
runs produce numeric totals automatically; zero means no removal occurred.
Failed hours are diagnostic and the evaluator rejects non-converged runs.

For legacy simulations without records only, external records can be supplied
in matching timestamp order:

```python
metrics = evaluate_results(
    legacy_result,
    EconomicConfig(),
    curtailment_kw=[10.0, 20.0],
    shedding_kw=[2.0, 3.0],
)
```

For an unrecorded no-BESS, two-hour result with one-hour steps, those records give 30 kWh
curtailed and 5 kWh shed. The series must contain one finite, nonnegative value
per step. For a BESS result also supply its `bess_config`.

These must describe the same operating actions that produced the simulation
inputs. Net load is not shedding; export is not curtailment; a failed FBS call
is not evidence of a specific amount of unserved energy. No control actions
are inferred by metrics. Omitted arguments read the simulation's records;
only missing legacy records remain unavailable. Original demand is served
load energy plus shed energy.

## Comparing a baseline and a candidate

```python
from src.metrics import percentage_reduction

reduction = percentage_reduction(
    baseline_metrics.loss_energy_kwh,
    bess_metrics.loss_energy_kwh,
)
```

The formula is `100 * (baseline - candidate) / baseline`. A positive number
means a reduction and a negative number means an increase. Missing values or
a zero baseline with a nonzero candidate return `None`. Zero versus zero
returns `0.0`. Compare matching horizons and inputs; the helper does not check
their provenance. No WSM normalization, score or optimizer penalty is added.

## Running and testing

From `07_Implementation`:

```powershell
python -m unittest discover -s tests -p test_metrics.py -v
python examples/run_simulation.py
```

The demonstration prints calculated control metrics and leaves unknown cost
clearly labelled. To exercise cost arithmetic with the illustrative
coefficients above:

```powershell
python examples/run_simulation.py --cost-per-kwh 2 --cost-per-kw 3
```

The example uses a 1,000 kWh / 200 kW battery, so that command should report
2,600 SAR for its BESS investment cost. Real cost inputs remain for the team
to supply. The tests use hand-calculated energy totals and verify an independent
network energy balance, input preservation, violation counting, missing values,
and rejection of failed/incomplete runs.

Thermal constraints and emissions are outside this version. Reliability
indices requiring outage/customer records are not calculated from voltage
violations alone. Curtailment/shedding energies now feed the raw WSM in
[`optimizer.py`](README_optimizer.md); investment cost still needs the team's
coefficients for a real study.
