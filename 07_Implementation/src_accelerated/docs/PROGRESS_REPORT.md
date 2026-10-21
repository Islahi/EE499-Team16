# Accelerated Program Progress Report

**Program:** BESS Planning Tool — accelerated implementation  
**Authoritative program folder:** `07_Implementation/src_accelerated/`  
**Report date:** 21 October 2026  
**Scope:** implemented work only. Planned work is explicitly identified as such.

## Current purpose

The program models a balanced radial distribution feeder, prepares hourly load
and PV profiles, performs Forward/Backward Sweep (FBS) power flow, simulates a
BESS across an hourly profile, generates uncertainty scenarios, and searches
for a BESS location/power/energy combination using Grey Wolf Optimizer (GWO).
It also provides a PySide6 desktop interface with session-based saving.

## Chronological implementation record

| Date | Commit | Completed work |
|---|---|---|
| 19 Oct 2026 | `8c6ef58` | Built the accelerated implementation: radial network model/import, FBS solver, CPU array/Numba/GPU experimental backends, BESS timestep model, hourly simulation, metrics, results export, GWO optimization, uncertainty generation, and the first Qt desktop UI. |
| 20 Oct 2026 | `018d0c3` | Added reusable scenario workflow: a Scenarios window, ARIMA/residual-bootstrap generation, scenario selection, import/save/use behavior, and reproducible study sessions. |
| 20 Oct 2026 | `10024f2` | Refined sessions and operation: all generated scenarios save as individual CSV files; normal UI offers CPU backends only; Settings shows workers and selectable candidate buses; static base-case FBS was introduced. |
| 20 Oct 2026 | `82890a4` | Organized the accelerated program: moved READMEs into `docs/` and added `app.pyw` for Windows double-click launch. |
| 20 Oct 2026 | `f047976` | Improved result presentation: static base-case values can be rendered in the network result layer; bus/line labels identify `B#`/`L#`; redundant base-voltage annotation and the visible scenario Validation tab were removed; session output moved under `src_accelerated/Results/`. |

## Delivered workflow

1. **Launch** — run `app.pyw` or `examples/run_accelerated_ui.py`.
2. **Load Data** — choose an Excel radial network, then prepare/import load and
   PV data. A session is created only after the dialog is accepted with **OK**.
3. **Session snapshot** — the accepted network and profile inputs are copied to
   `src_accelerated/Results/Sessions/<timestamp>_<network>/inputs/`.
4. **Static base case** — run one FBS snapshot using original base load and
   installed PV ratings, with BESS inactive at 0 kW. This is for comparison
   with a conventional static power-flow tool.
5. **Time-series simulation** — run FBS once per profile timestamp, optionally
   with BESS dispatch, reserve, PV curtailment, load shedding, and grid limits.
6. **Scenarios** — optionally fit/load scenarios, save every generated
   scenario as a separate CSV, then activate a selected stress portfolio.
7. **Optimization** — search selected BESS buses and power/energy catalogs
   using GWO. Each candidate is assessed using simulation and metrics.
8. **Review/export** — text summaries, selected network results, convergence,
   evaluation history, and CSV outputs remain inside the session folder.

## Important implemented design decisions

- **Base case versus simulation:** the base case is one static FBS snapshot;
  simulation is repeated FBS over time-series data. A BESS is optional in both.
  The current base case keeps it inactive because SOC alone cannot determine a
  static BESS power injection.
- **PV uncertainty:** scenarios forecast PV **power**, not irradiance. The
  irradiance-to-PV conversion happens before scenario generation.
- **Scenario validation:** the user-facing validation tab was removed for a
  simpler UI, but `validation.csv` is retained with each saved scenario set.
- **GPU:** GPU code remains experimental but is intentionally not selectable in
  the normal UI because measured small/serial FBS workloads did not benefit.
- **Thermal constraints:** not implemented in the initial scope. Voltage,
  reserve, import/export, curtailment, and shedding constraints are supported.

## Current limitations and work still needed

| Area | Current limitation | Consequence |
|---|---|---|
| Network model | Balanced single-phase-equivalent radial model; no transformers, shunts, or unbalanced phases | Not a full commercial distribution-system study tool. |
| Base case | BESS fixed at 0 kW | A static BESS comparison needs a future explicit fixed kW setpoint. |
| Optimization | GWO is heuristic and expensive for 33 buses × many hours × scenarios | It can remain inside one iteration for several minutes; progress logs show the last completed candidate. |
| Economics | User must provide cost coefficients | Results are not supplier quotations or financial advice. |
| PV model | Uses GHI proxy, shared irradiance, unity PF, no temperature/tilt/inverter model | PV values are planning estimates. |
| Scenarios | Independent innovations by bus; no seasonal or parameter uncertainty | Scenario results are stress tests, not calibrated probabilistic forecasts. |
| Tests | Existing checks cover much of FBS/simulation, but full desktop and long 33-bus optimization runs have not been exhaustively automated | Manual review is still required before a final academic claim. |

## Result-folder structure

```text
src_accelerated/Results/
  Sessions/<timestamp>_<network>/
    inputs/                 accepted network/load/PV snapshots
    scenarios/set_###/
      all_scenarios/S###_scenario_###.csv
      validation.csv
      scenario_ranking.csv
      manifest.json
    base_case/run_###/      bus voltages, line flows, summary
    simulation/run_###/     saved hourly simulation outputs
    optimization/run_###/   convergence and candidate evaluations
    session.json
    session.log
```

## Recommended next verification

1. Compare the Guide 5-Bus static base case against an external FBS/power-flow
   calculation using exactly the same base loads, PV power, impedance, and
   per-unit bases.
2. Use a short profile and small GWO catalog before a three-month/33-bus run.
3. Inspect `validation.csv`, `scenario_ranking.csv`, and individual scenario
   CSVs before treating the uncertainty portfolio as credible.
4. Record approved cost coefficients and any required battery supplier data.
