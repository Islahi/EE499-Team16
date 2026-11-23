# BESS Planning Tool V16

V16 runs from the existing `07_Implementation/src`.

## Changes

| Phase | Changes and paths relative to `07_Implementation` |
| --- | --- |
| Excel and import | `src/distributed_dataset.py`, `src/data_loader.py`, `src/network_loader.py`, `src/ui_workflow.py`, `src/study_session.py`, and `src/docs/README_network_loader.md`. Validate bus and hour coverage, P/Q, clock, PV ratings and profile integrity. Archive the selected and distributor workbook hashes. Electrical edits compatible with the same profile folder receive a provenance note. A previously saved setup still verifies its input fingerprints. |
| Electrical inspection and control ledger | `src/ui.py`, `src/electrical_details.py`, `src/results.py`, `src/simulation.py`, `src/multi_bess.py`, and `src/control_audit.py`. Include solved angles, voltage in pu and kV, branch flows and ratings, requested and accepted P/Q, actions, and the time context. Show separately the uncontrolled voltage, the voltage before final correction, and the final voltage. The rich ledger is captured for retained results. |
| Offline reports | `src/dashboard.py`, `src/dashboard_series.py`, `src/forecast_accuracy.py`, and `src/assets/dashboard{,_gallery}.js` with `src/assets/dashboard.css`. Add time-indexed views of archived inputs, electrical outputs, demand/PV, BESS, costs, controls, forecast diagnostics where present, and saved-run comparison. Preserve canonical exports and include them in portable ZIPs. |
| GA and desktop workflow | Integrate the existing V16 work in `src/planning_policy.py`, `src/sequential_multi.py`, `src/assets/settings_dialog.ui`, `src/saved_schema.py`, `src/study_setup.py`, `src/dashboard_viewer.py`, and `src/model_information.py`. **GA stall generations** defaults to 6. Its upper bound is the configured maximum generations. Verification covers saved settings and the GA's stop reason. |
| Regression and documentation | `tests/test_v16_diagnostics.py`, `tests/test_dashboard_blocks.cjs`, `README.md`, and the root README and project journal. |

Base Case uses a static workbook snapshot. Simulate uses the selected hourly
interval and its absolute profiles. Trials continue to use Numba FBS and the
existing GA, screening and dispatch algorithms. Historical reports used for
regeneration were copied before testing.

## 33-bus workbook check

Both the 15- and 33-bus datasets passed import with all 43,921 hourly timestamps.
For the 33-bus check, the source workbook matched the distributor's original
SHA-256. A copy changed only `Bus Data!E2` from 1.00 to 1.05. Both runs used
the same distributed folder, 60 Hz and the declared UTC study clock. The table
uses the first hour, 2021-01-01 00:00 UTC, before controls unless noted.

| Quantity | 1.00 pu workbook | 1.05 pu workbook |
| --- | ---: | ---: |
| Solved slack voltage (pu) | 1.000000 | 1.050000 |
| Bus 33 voltage (pu) | 0.913469 | 0.968284 |
| Bus 33 angle (degrees) | −0.423061 | −0.380262 |
| Bus 33 angle after corrective control (degrees) | −0.308435 | −0.380262 |
| Feeder minimum voltage (pu) | 0.899228 | 0.954905 |
| Bus 2 requested demand (kW / kvar) | 144.116555 / 86.469933 | 144.116555 / 86.469933 |

In the 1.00 pu run the first ledger action accepted 144.116555 kW and 72.058277
kvar of shedding at bus 8. Bus 8 went from 0.936710 to 0.962853 pu against a
0.95 pu lower limit. The hour ended feasible after simultaneous corrective
actions. The ledger records `reason_not_unique` for that hour. The 1.05 pu run
also recorded corrective actions at other hours, including PV reactive support.

## Open and reproduce on Windows

From the project root in PowerShell, run:

```powershell
Set-Location .\07_Implementation
.\start_windows.bat
```

1. In **Import Data**, select the distributor's original `IEEE_33Bus_Network_Data.xlsx` workbook and the corresponding `IEEE_33Bus_Network_Data` distributed profile folder. Use 60 Hz and the dataset's PV installation option. Prepare the study.
2. Select the historical interval starting at 2021-01-01 00:00 and run a 24-hour **Simulate** with no battery. Click bus 33 or a line, then change the selected hour. Compare the angle shown in the inspector to `buses.csv` for that hour. **Plot bus** or **Plot line** opens the corresponding entity and timestamp.
3. Save a workbook copy and edit `Bus Data!E2` to 1.05. Select that copy with the same distributed folder and simulate the same interval as a new run. The import status should report the provenance difference and accept the inputs.
4. In either report, use **Study inputs → Load input → 2 → Active power (kW)** for the original bus 2 curve and its workbook base reference. Switch to reactive power to inspect kvar. In **Network**, choose **Bus → 33 → Voltage angle (°)**. In **Compare runs**, load the second report and choose a common field and time window.

The local validation examples in `Results/Diagnostics/V16_20261123` cover 24
hours at 1.00 pu and 168 hours at 1.05 pu. Their first 24 timestamps align.
The 24-hour portable ZIP includes the report and hashed source exports. To
regenerate a dashboard from a compatible saved folder, run
`py -3.14 -m src.dashboard "PATH_TO_SAVED_RUN"` from `07_Implementation`.

## Verification

| Check | Result |
| --- | --- |
| `test_windows.bat -q --disable-warnings` | 222 tests and 75 subtests passed. The dashboard-focused rerun after the final UI asset edit passed 17 tests. |
| `CHECK_WINDOWS_GUI.bat --no-pause` | Passed Python/Qt, Numba FBS, bus-specific shedding, forecasting runtime imports, and Qt WebEngine import. The Qt inspector smoke test selected bus and line, changed hour, and checked the linked report request. |
| `node --test tests/test_dashboard_blocks.cjs` | All 3 checks passed for byte offsets, exact CSV export values, and extrema-preserving plot reduction. |
| Real saved report data | The report's JavaScript matched 72 sampled readings to the source CSVs across 24-hour, 168-hour, 8,760-hour, and 43,921-hour reports. Checks covered negative angles, a block boundary, the last history hour, common comparison timestamps, and a ledger action. ZIP entries matched manifest hashes. |
| Physical results | Shared numerical columns in hourly, bus, branch and metric exports for all three simulation fixtures matched their pre-edit results with relative and absolute tolerances of `1e-9`. |
| GA | On a fixed-fitness plateau, stall settings of 1, 2, 3, 6 and 10 reached `FleetGAConfig` and stopped after 2, 3, 4, 7 and 11 generations, respectively. |
| Audit overhead | On a warm synthetic 2-bus, 168-hour run, median simulation times were 0.627 s with and without capture (three runs each). Peak Python-tracked allocation was 1.82 MiB with capture and 0.96 MiB without, with identical shedding. |
| Report generation | Copied 33-bus annual run with two 8,760-hour scenarios regenerated in 42.2 s, producing 83.0 MiB HTML with a 167 MiB peak process working set. The full 43,921-hour input-only archive took 25.4 s, producing 31.2 MiB HTML with a 188 MiB peak. |

## Verification limits

The managed browser refused local file navigation and the embedded Qt renderer
did not initialize in this environment. Offline data extraction and chart
functions were tested in Node. Visual rendering, chart PNG download, Print/PDF
and browser responsiveness remain unverified. The annual report uses saved
canonical results, with optimizer propagation and stopping behavior covered by
targeted tests. The 43,921-hour fixture exercises input history packaging.
