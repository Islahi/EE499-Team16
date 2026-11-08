# Integrated Upgrade Change Log

- Replaced dimensionality-inconsistent raw weighted sum with annualized monetary minimization.
- Added configurable capital recovery/O&M/tariffs/VoLL/curtailment and terminal energy balancing.
- Added discrete GA alongside existing GWO, shared evaluator and no-BESS comparison.
- Added simplified grid-aware rule dispatch and ampacity and optional terminal-SOC checks.
- Removed scenario generator UI/module; added modal ARIMA/SARIMA/SARIMAX forecasting, using Nixtla StatsForecast AutoARIMA.
- Removed the active Study Period requirement; imported CSV defines hourly interval.
- Kept Designer-generated main layout and existing report/chart components where practical.
- Added regression tests and a Windows source launcher.

This is a modified source package, not a replacement compiled `.exe`.

- 2026-11-05: Corrected the forecasting backend to `statsforecast.models.AutoARIMA`; changed default GUI model, requirements, validation label and tests.

- Scope revision: removed net-load-target dispatch and transformer-kVA constraint (GUI and active backend); retained grid-aware dispatch, import/export limits and SOC/ampacity checks. No GA crossover changes.

- GA refinement: whole-chromosome crossover decision and single-point, single-child recombination (supersedes original per-gene crossover), unchanged mutation and UI.
