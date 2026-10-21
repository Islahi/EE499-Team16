# Accelerated Program Script Reference

This reference describes the current files in `src_accelerated/`, their role,
their principal inputs/outputs, and the equations used where applicable.

## Entry points and UI

| Script | Responsibility |
|---|---|
| `app.pyw` | Windows double-click launcher. Adds `07_Implementation` to `sys.path`, opens the Qt UI, and shows a dialog if startup fails without a console. |
| `ui.py` | Main PySide6 application: Load Data, Settings, Scenarios, job threads, progress/log updates, static base case, simulation, optimization, network graphics, and result selection. |
| `ui_workflow.py` | UI-independent orchestration. Validates/imports source data, builds a prepared study, runs base case/simulation/optimization, and saves retained results. |
| `assets/*.ui` | Qt Designer forms loaded at runtime by `ui.py`; they define widgets/layout, not numerical calculations. |
| `network_icons.py` | Produces palette-aware vector icons for Fit, Zoom In, and Zoom Out controls. |
| `progress.py` | Defines structured stage/progress events and duration formatting used by UI workers and numerical loops. |

## Static network and import

| Script | Responsibility |
|---|---|
| `network_model.py` | Defines `Bus`, `Line`, `Load`, `PVUnit`, `NetworkModel`, and radial order. Validates one slack bus, valid references, connectivity, and radial topology. |
| `network_loader.py` | Reads supported project/IEEE-33 Excel workbooks and turns sheets into `NetworkModel` objects. Rejects unsupported PJM/generator or meshed-transmission workbooks. |
| `network_cases.py` | Creates prepared 3-bus/5-bus guide cases for validation and demos. |
| `main.py` | Console demonstration of the Guide 5-Bus static FBS case. `base_operating_point()` builds fixed base-load/PV inputs. |

## Electrical power-flow model

| Script | Responsibility |
|---|---|
| `fbs.py` | Primary balanced radial Forward/Backward Sweep solver. Returns bus voltage, branch current, sending-end power, losses, slack power, convergence status, and optional iteration history. |
| `accelerated_fbs.py` | Array implementation of the same FBS calculation using Python/NumPy/Numba and experimental CuPy. Normal UI exposes only CPU choices. |

For each bus, the solver forms net complex power:

```text
P_net = P_load − P_PV − P_BESS
Q_net = Q_load − Q_PV − Q_BESS
S_net = P_net + j Q_net
```

It uses constant-power current injection in per unit:

```text
I_bus = conjugate(S_net / V_bus)
I_line = I_child + Σ I_downstream
V_child = V_parent − Z_line I_line
S_send = V_parent conjugate(I_line) S_base
Loss_line = |I_line|² Z_line S_base
```

The solver converges when the maximum complex voltage change is no more than
`voltage_tolerance_pu`; it fails if values become non-finite, voltage becomes
near zero, or maximum sweeps are exhausted.

## Profile, PV, and BESS preparation

| Script | Responsibility |
|---|---|
| `data_loader.py` | Reads validated long-format load/PV CSVs into `ProfileData` and returns an hourly `ProfileSlice`. Requires matching timestamps and bus coverage. |
| `pv_model.py` | Reads prepared/Open-Meteo/NASA irradiance CSVs and creates hourly PV power by installed PV bus. |
| `load_generator.py` | Creates reproducible synthetic hourly load profiles from network base loads and configurable hourly/weekly multipliers plus random variation. |
| `bess.py` | Defines BESS configuration/state and clips requested battery power against kW, SOC, capacity, efficiency, and timestep limits. |
| `dispatch.py` | Implements the simple net-load-target request: discharge above target and charge below target. It requests power; `bess.py` and `simulation.py` enforce physical limits. |

The implemented PV model is piecewise, with irradiance `G`, critical threshold
`G_c`, standard irradiance `G_std`, and rated AC power `P_rated`:

```text
P_PV = P_rated (G/G_std)(G/G_c),   G < G_c
P_PV = P_rated (G/G_std),          G_c ≤ G < G_std
P_PV = P_rated,                    G ≥ G_std
```

The model uses a GHI proxy and zero reactive PV power; it does not model panel
temperature, tilt, inverter losses, or a plane-of-array conversion.

BESS sign convention is positive discharge and negative charge. For timestep
duration `Δt`, the energy update is:

```text
Discharge: E_after = E_before − P_actual Δt / η_discharge
Charge:    E_after = E_before − P_actual Δt η_charge
SOC = E / E_capacity
```

The second charge equation works because `P_actual` is negative while charging.
The code clips power so SOC remains between configured minimum and maximum.

## Simulation, feasibility, and metrics

| Script | Responsibility |
|---|---|
| `simulation.py` | Runs one FBS calculation per hourly profile row; applies optional BESS, reserve, voltage/import/export checks, PV curtailment, load shedding, and stores each step. |
| `metrics.py` | Converts retained simulation steps into energy, voltage, feasibility, reserve, curtailment, shedding, grid, and simple BESS-cost metrics. |
| `results.py` | Formats human-readable summaries and exports retained simulation/optimization outputs to CSV/text. |

Energy quantities are integrated as:

```text
E = Σ(P_t Δt)
```

When necessary, the control layer searches for the smallest proportional PV
curtailment or load shedding fraction that clears the relevant violation:

```text
P_new = (1 − r) P_original
Q_new = (1 − r) Q_original
```

where `r` is found by bounded bisection. This preserves the original power
factor while reducing active and reactive power together.

## Optimization

| Script | Responsibility |
|---|---|
| `optimizer.py` | Defines BESS candidates and catalogs, evaluates each candidate with simulation, calculates the raw weighted objective, and performs GWO with optional CPU worker processes and evaluation caching. |

Candidate decision variables are:

```text
x = (BESS bus ID, power rating kW, energy capacity kWh)
```

The implemented raw weighted-sum objective is:

```text
J = 0.50 × BESS_cost
  + 0.25 × curtailed_PV_energy
  + 0.25 × load_shedding_energy
```

An infeasible candidate receives `J = infinity`. This is deliberately **not
normalized**, following the project decision; therefore units/scales strongly
affect the search. GWO operates on catalog-index positions, rounds them back to
allowed bus/power/energy values, and retains feasible leaders. It is heuristic,
not a global-optimum proof.

## Uncertainty and scenario persistence

| Script | Responsibility |
|---|---|
| `uncertainty.py` | Builds load and PV-power scenarios using hourly baseline patterns plus ARIMA residual paths, with residual-bootstrap fallback; ranks/selects stress scenarios and evaluates candidates across them. |
| `scenario_store.py` | Saves each generated scenario as an individual CSV plus manifest, ranking, and validation files; reloads selected scenarios. |
| `study_session.py` | Creates reproducible session folders, snapshots accepted source inputs, tracks active scenarios, records saved runs, and writes the session log/manifest. |

For each power series, the scenario model uses a mean by hour of day plus a
scaled residual:

```text
P_t = hourly_mean(hour(t)) + scale × residual_t
```

Residual paths are generated by ARIMA when fitting/holdout validation succeeds;
otherwise hourly residual bootstrap is used. Outputs are clipped to nonnegative
values and, for PV, to installed kW rating. Reactive power is reconstructed from
the historical hourly `Q/P` ratio.

Scenario stress features are net import energy, peak net load, surplus energy,
and maximum ramp. The current score is:

```text
score = 0.35 N(net energy)
      + 0.30 N(peak net load)
      + 0.20 N(surplus energy)
      + 0.15 N(ramp)
```

`N()` is min-max normalization across generated scenarios. Selected scenarios
are an equal-weight stress portfolio; their original probabilities are not
preserved.

## Network drawing

| Script | Responsibility |
|---|---|
| `network_layout.py` | Calculates an automatically arranged radial layout, branch sides, busbar extents, equipment ports, and orthogonal line routes. |
| `network_diagram.py` | Draws the selectable single-line diagram, bus/load/PV/BESS/grid symbols, optional property/result annotations, rotation, line hit corridor, and wheel zoom. |

## Package support

| Script | Responsibility |
|---|---|
| `__init__.py` | Marks `src_accelerated` as an importable Python package. |

## Documentation files

| File | Purpose |
|---|---|
| `README.md` | Overall accelerated-program guide and static FBS background. |
| `README_ui.md` | Desktop UI input, behavior, and test guide. |
| `README_simulation.md`, `README_metrics.md`, `README_optimizer.md`, `README_uncertainty.md` | Deeper references for their corresponding numerical modules. |
| `README_network_loader.md`, `README_pv_model.md`, `README_load_generator.md`, `README_results.md` | Data schemas, conversion, generation, and export references. |
