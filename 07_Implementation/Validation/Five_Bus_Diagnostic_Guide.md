# Five-bus diagnostic test

This is a small **radial distribution development fixture**, copied from
`src/network_cases.py: build_guide_5_bus_case`. It is not the incompatible PJM
five-bus transmission workbook and is not presented as an IEEE-standard feeder.
Topology: 1 → 2 → 3 → 4, with a lateral 2 → 5. The workbook retains the existing
fixture's R/X, bus ratings, loads and PV installation. No PV mode removes the
PV installation for the first diagnostic only. Values are test inputs, not
supplier recommendations or a validated grid design.

## Desktop test

Restart the desktop after stopping your previous run, so it imports the updated
code. From the repository root in PowerShell:

```powershell
python .\07_Implementation\examples\run_ui.py
```

1. Load Data > Network: browse to
   `04_Research/Working_Data/Network_Data/Guide_5Bus_Radial_Test.xlsx`.
   Keep workbook format Auto and frequency 60 Hz; click Load Network.
2. PV / Irradiance: choose **No PV**. Load: use synthetic demand and seed 42.
3. Study Period: start 2024-01-01 and use the shortest calendar period appropriate
   for the loaded source data. The desktop has no separate 24-hour override.
4. Settings: disable reserve, grid import/export limits and uncertainty for this
   first comparison. Keep the default 0.95–1.05 pu voltage limits.
5. Battery: net-load-target policy, target **600 kW**; charge/discharge efficiency
   **95%**; minimum/initial/maximum SOC **10% / 50% / 90%**.
6. Optimization: allowed bus **4 only**; power min/max/step **50 / 100 / 50 kW**;
   energy min/max/step **100 / 200 / 100 kWh**; population **3**, iterations **2**,
   seed **42**. Enable economic inputs, cost per kWh **2**, cost per kW **3**.
   These prices are illustrative software-test values only.
7. Run Simulation first, then Run Optimization. Check completion, convergence,
   feasibility and shedding separately in Results; a completed run need not
   imply every timestep was feasible.

Expected GWO progress: completed iterations 0/2 → 1/2 → 2/2 (0%, 50%, 100%).
Candidate and hour counters provide detail within an iteration. The five-bus
test may finish too fast to see every intermediate update. Enable Show run log
to inspect timestamped boundaries. Results include Run duration and device-clock
start/finish; the live elapsed label freezes at the end. No Cancel Run is added.

Then change **only one factor at a time**: use a longer source period, then try the
33-bus workbook with the same small search. Test uncertainty separately
with sufficient training history (at least 72 hours) and a 24-hour forecast. An
ARIMA fitting failure is a separate issue, not GWO convergence. The error now
identifies the series/bus and training or full-history fit.

## Repeatable backend comparison

From the repository root:

```powershell
python .\07_Implementation\examples\run_five_bus_diagnostic.py --hours 24 --compare-ieee33
python -m unittest discover -s .\07_Implementation\tests -p test_progress.py -v
```

The diagnostic uses the real loader/simulation/GWO, four possible battery
combinations and an exhaustive-search reference. It prints JSON and counts
actual power-flow calls. `--output NEW_PATH.json` optionally saves a new file;
existing files are refused. The diagnostic does not change GUI settings.

Measured on this development device (24 hours, no PV, no uncertainty):

| Network | GWO duration | Unique candidate evaluations | Power-flow calls | Matches exhaustive objective |
|---|---:|---:|---:|---|
| Guide 5 buses | 0.025 s | 3 | 72 | Yes |
| IEEE 33 buses | 1.649 s | 3 | 2,025 | Yes |

Both selected bus 4, 50 kW / 100 kWh on this tiny illustrative catalog.
Recorded output: `Five_Bus_Diagnostic_Results.json`. Timings exclude workbook/profile
preparation and the separate exhaustive search. They depend on hardware and settings.
The higher 33-bus solve count includes repeated power flows for control searches.
This demonstrates a computational multiplier; it does **not** diagnose the original
one-hour run, establish GWO global optimality, or validate these battery sizes.
GWO stops after configured iterations; its percentage is not a convergence test.
