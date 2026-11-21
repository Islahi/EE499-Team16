# BESS Planning Tool

Start with the [user guide](BESS_Planning_Tool_User_Guide.md) for the Windows launcher,
GoiEner folder import, solar input formats, technical simulations, annual optimization,
and saved study migration.

The desktop application in `src_accelerated` uses Numba CPU FBS. Sector-sum demand
forecasts use CalendarRidge, XGBoost, and LightGBM. The common PV forecast uses
XGBoost trained on historical modeled power. Use the repository's existing Windows
Python 3.14 installation with the pinned dependencies in `requirements-accelerated.txt`.

An imported study selects its first 24 hours while retaining the full history for
later selections and forecast training. Annual economic optimization requires a
complete calendar year and explicit import and export tariffs. The annual objective
is reported in USD/year and includes ownership, net grid purchases, curtailment,
unserved energy, and any priced terminal energy difference.

The equal-SOC policy bounds each dispatch request so that the remaining hours can
restore the starting SOC at the configured battery charge and discharge limits.
Network and reserve constraints still apply to every hourly step. The terminal
check marks a candidate infeasible if this schedule fails to close. The alternate
priced policy accounts for the energy difference in the annual objective and
requires an explicit positive replacement price. The dispatch policy evaluates
each candidate using rules for local PV and demand rather than optimizing the
entire annual operating schedule.

Run the regression suite from `07_Implementation` in PowerShell:

```powershell
python -m pip install -r requirements-test.txt
$env:QT_QPA_PLATFORM = 'offscreen'
python -m pytest tests -q -ra
```

The suite uses the repository's `Validation` directory for archived C1 and C2
fixtures. Set `EE499_VALIDATION_ROOT` to the extracted Validation directory if
it is stored separately. Missing fixtures are reported as explicit skips.
