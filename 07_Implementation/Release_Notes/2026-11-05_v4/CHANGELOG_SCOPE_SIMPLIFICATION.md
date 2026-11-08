# Scope simplification — 2026-11-05

## Requested changes

- Removed the `Net-load target` option and `Net-load target` input from the Battery/Dispatch settings. The Grid-aware rule remains the default; Idle remains as a diagnostic option.
- Removed the `NetLoadTargetPolicy` class and optional `target_kw` field of `GridAwareDispatchPolicy`. The calculation `load − PV` remains essential to the Grid-aware rule.
- Removed the optional transformer-kVA limit field and its constraint check from `SimulationConfig`. Existing import/export active-power caps, voltage, battery SOC/reserve and branch ampacity feasibility checks remain.
- Preserved the economic metrics, annualized objective, GA/GWO selection, StatsForecast AutoARIMA forecasting and CSV-driven time axis.

## GA offspring history

At the scope-simplification stage, the GA used one child per mating with per-gene crossover. The **subsequent chromosome-crossover revision supersedes that detail**: it still produces one child, but now uses one crossover decision for the whole chromosome and a single-point cut. A paired-offspring design was not added.

## Important battery-operation limitation

`GridAwareDispatchPolicy` is a self-consumption operating heuristic, not a full economic optimizer: it reacts to the current network-wide load and PV only. It does not optimize against a future time-varying tariff or forecast. SOC may decline over time if PV surplus is absent; terminal SOC is therefore worth checking.

## Test status

Numerical tests and Qt Designer XML parsing verified in the build environment. PySide6 was unavailable for GUI interaction; StatsForecast real-library integration is likewise skipped when unavailable. Rebuild/launch the GUI with dependencies installed on Windows for the final integration check.
