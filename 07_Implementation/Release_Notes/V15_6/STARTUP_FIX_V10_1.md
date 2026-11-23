# V10.1 startup hotfix

## Problem
The V10 application failed at startup with:
`Missing Designer object 'spin_min_lateral_voltage_pct' in LoadDataDialog`.

## Cause and fix
The legacy voltage-percentage spinner is defined in `src_accelerated/assets/settings_dialog.ui`, not in `load_data_dialog.ui`. A misplaced V10 visibility call tried to access it from `LoadDataDialog.apply_approved_visibility()`.

The incorrect reference has been removed from `LoadDataDialog`. The correct settings-side handling remains in `SettingsDialog.apply_approved_visibility()`, where the legacy spinner is disabled. V10's actual voltage compliance logic is unchanged.

## Regression protection
`tests/test_v10_startup_ui_ownership.py` verifies Designer widget ownership across the three dialogs and checks the legacy spinner is only referenced in `SettingsDialog`. The existing Windows runtime check `CHECK_WINDOWS_GUI.bat` should still be run on the user's PC to validate Qt/PySide6, forecast-library imports and the actual `MainWindow()` constructor.

## How to update
Extract this complete package into a **new folder**, or replace only `src_accelerated/ui.py` in an existing untouched V10 folder. Do not overwrite a running V9 program or result folder.

Run `RUN_TESTS.bat`, then `CHECK_WINDOWS_GUI.bat`, then `RUN_APP.bat`.
