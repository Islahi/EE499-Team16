# Designer-to-Python wiring fix (v4)

## Symptom reproduced from the user's Windows logs

- Selecting **Numba compiled (CPU)** displayed `Unavailable: Unknown backend: None`.
- Selecting AutoARIMA produced `ValueError: Forecast method must be autoarima, arima, sarima or sarimax` before any model fit.
- GA vs GWO selection could also be misrouted because `currentData()` was `None`.

## Root cause

The `.ui` files included the intended semantic identifiers as per-item `userData`, but `QUiLoader` did not reliably assign those fields to Qt combo items. Visible text and selection index alone were not sufficient. The app used `currentData()` to configure computation and forecasting, so it received `None`.

## Changes

- Added `src_accelerated/ui_bindings.py` to read combo identifiers **directly from the `.ui` XML** and restore them with `setItemData` immediately after `QUiLoader.load`.
- The binding layer verifies each item label and count. Designer remains the single source of truth for layout, labels and these semantic keys; Python only wires runtime values and callbacks.
- Verified mappings include compute backends `python` / `numpy` / `numba`, optimizers `GWO` / `GA`, and forecast methods `autoarima` / `arima` / `sarima` / `sarimax`.
- Forecast dialog catches invalid configuration at the button-click boundary and displays the error in the dialog instead of an unhandled console traceback.
- On the **first** network attachment, select all eligible non-slack buses by default. Later user choices (including Clear) are not automatically overwritten for that network.
- Added unit tests for missing-data recovery, mappings, label drift, and an optional **real PySide6 QUiLoader smoke test**.

## Scope and validation

This revision does not modify the GA/GWO search algorithms, StatsForecast model, FBS solver, BESS dispatch, costs, or physical limits. The `.ui` layout was not changed.

The standard regression suite passes in the build environment. The real-PySide6 UI test skips when PySide6 is not installed; it will run on a Windows machine with the project requirements installed. The user should verify that Settings displays `Ready` for the selected available compute backend and that forecast creation starts successfully.
