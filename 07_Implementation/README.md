# Term 2 Implementation

[V15.6](Release_Notes/V15_6/V15_6_CLEANUP_QUICKSTART.md) is the current BESS
Planning Tool. Its source and desktop assets are in `src/`. The app supports
radial-network workbooks, hourly load and PV data, Numba Forward/Backward
Sweep, battery planning and dispatch, and saved HTML results dashboards.

## Run on Windows

From `07_Implementation`, using Python 3.14:

```bat
py -3.14 -m pip install -r requirements-accelerated.txt
start_windows.bat
```

The Information button shows effective settings, equations, and model
assumptions. For setup, simulation, optimization, and saved reports, use the
[V15.6 quick start](Release_Notes/V15_6/V15_6_CLEANUP_QUICKSTART.md).
New runs use `src/Results/`. Saved run folders can also be opened from the
desktop. See the [V15.6 release notes](Release_Notes/V15_6/V15_6_CHANGES.md)
for the session export fix and recovery instructions.

## Verify and maintain

```bat
py -3.14 -m pip install -r requirements-test.txt
test_windows.bat -q
CHECK_WINDOWS_GUI.bat --no-pause
```

- Application code and technical notes are under [src](src/docs/README.md).
- Saved-run recovery and dashboard regeneration utilities are beside the launcher.
- Historical validation kits are under [Validation](Validation/). Standalone
  data-preparation and plotting tools are under [Tools](Tools/).
- [Earlier releases](Release_Notes/) document the evolution of the solver and UI.

The previous desktop tests and the raw weighted-sum and synthetic uncertainty
examples can be reproduced from the preceding Git revision. The active test
suite targets V15.6 and keeps the compatible reference network, PV, and search
checks.
