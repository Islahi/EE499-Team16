# V15.4 — Sindi horizon Settings dropdown fix

## Fixed

- Qt Designer declares `combo_sindi_horizon` values as XML `<number>24</number>`, `<number>48</number>`, and `<number>72</number>`. The earlier `ui_bindings.py` only parsed `<string>` values and silently skipped the numeric dropdown, leaving its Qt `currentData()` as `None`.
- `ui_bindings.py` now restores typed scalar `userData` (integer, floating point, boolean, string) instead of ignoring numeric entries. Existing string-based mode, search, and policy dropdowns are unchanged.
- The Settings dialog now validates the selected integer at capture, emits an actionable message for missing data, and restores saved values of 24/48/72 even when stored as numeric strings.
- New tests check the actual Qt Designer interface for all three choices and ensure `SimulationConfig` accepts each.

## Unchanged

- Sindi-style solver, Joint GA backend, Numba FBS, battery constraints, parallel evaluation, economics, and asynchronous dashboard logic.

## Test scope

Unit/regression tests run in the local environment. A Windows PySide6 GUI launch is still recommended to verify the native Qt appearance and Apply button.

Source project: https://github.com/Islahi/EE499-Team16.git
