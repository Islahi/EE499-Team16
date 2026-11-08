# Designer-unified UI v3

- Main action buttons and network Fit/Zoom/Rotate now share **one row**, outside the Network/Results tabs so both remain available.
- The toolbar, all icons, button sizes, shortcuts, labels, tooltips, window margins, and styles are defined in `src_accelerated/assets/main_window.ui` (and `assets/icons`).
- The old hidden sidebar (`frame_action`), empty menubar, unused log-header placeholder, runtime `QToolBar` and runtime widget reparenting have been removed.
- Network-page checkboxes and buttons occupy a single compact row; selected-bus details remain optional.
- Forecasting input layout now also lives in `forecast_dialog.ui`; the Python class only fills data, starts forecasting and handles save/error actions.
- Permanent settings controls previously constructed in Python (GA, economics, dispatch, terminal SOC, compute, eligible-bus actions) are now declared in `settings_dialog.ui` and visible in Qt Designer.
- Stale tab-order references to removed scenario widgets have been deleted from `settings_dialog.ui`.
- Python still handles button signals, live selection-dependent visibility, calculations and logging; it no longer constructs the toolbar or permanent settings widgets.
- `QUiLoader.setWorkingDirectory` resolves relative SVG icon paths embedded in .ui files.
- Existing electrical, optimization and forecasting implementations unchanged.

**Testing:** structural XML, icon references and Python compilation checked. PySide6 is unavailable in this environment, so visually confirm layout and SVGs in Qt Designer / Windows runtime before replacing your last working version.
