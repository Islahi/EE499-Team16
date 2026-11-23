# V14.1 — Annual-acceptance and offline dashboard fixes (experimental)

Project reference: https://github.com/Islahi/EE499-Team16.git

This is a **new local derivative of V14**, not an edit of either original V13/V14 ZIP, and is **not committed to GitHub**. It has not yet been tested in a full new 8,760-hour optimization or with the Windows/PySide6 GUI. Run from a **separate directory**.

## Investigation of the uploaded results (22 November 2026)

- **V13 session** `20261122_201821...zip`: two BESS accepted; dashboard `dashboard.html` was written at 21:22:18 and its manifest at 21:22:24.
- **V14 session** `20261122_212324...zip`: 6/6 finalists completed 8,760-hour annual checks, were reported network-feasible, but **none was technically accepted**. The generator wrote `dashboard.html` at 21:48:38 and its manifest at 21:48:40 (screenshot/log was at 21:48:33). SHA-256 file hashes match both reports' manifests. Therefore the **saved HTML completed**, although the screenshot by itself cannot establish whether the Qt UI eventually displayed its final completed status.
- Four V14 finalists (bus 14 at 2500/5000 and 1550/5550, bus 29 at 2500/5000, bus 6 at 2500/15000) were rejected on **pre-control voltage** worsening after they had already passed annual network feasibility and shedding non-deterioration checks. Bus 18 at 100/200 caused shedding deterioration on a different lateral; bus 25 at 2500/15000 had no measured marginal local benefit.
- The current settings in this V14 run were **100–2500 kW** and **100–15000 kWh**, not the advertised *initial defaults* 250–2500 kW and 250–15000 kWh. This is a user-configured search range recorded in the run, not evidence of an optimizer duration-constraint bypass.

## Fix 1 — Annual acceptance logic

In `src_accelerated/feeder_aware.py`:

- A **measurable annual reduction in target-lateral load shedding** can now pass the incremental technical criterion despite increased **pre-control** voltage deficit. Pre-control deficit is retained and reported in `pre_control_voltage_deterioration_pu_hours`; it does not prove a violation of the final controlled voltage bounds.
- Maintain **per-lateral and network-wide shedding non-deterioration**, within the preexisting 1% tolerance logic.
- Preserve mandatory **8,760-hour/8,784-hour completeness, nonlinear FBS convergence and final physical feasibility**, plus the positive verified annual cost-saving gate in the caller. This change does not relax final 0.95–1.05 pu limits.
- For candidates whose *only* benefit is a pre-control voltage improvement, retain the existing pre-control voltage non-deterioration checks. Never allow a voltage gain caused by **more load shedding**.
- This is a **methodological change**, not a purely numerical bug fix. Re-run both old and new acceptance policies as separate scenarios for auditable comparisons. A battery is not guaranteed to be accepted until V14.1 actually reruns the optimization; however, four stored V14 finalist trajectories failed the specific gate now changed.

## Fix 2 — Fast offline dashboard

The simplified three-tab JavaScript dashboard uses **hourly charts, fleet SOC, the saved optimizer metadata, and bus voltages at the worst hour**. It never accessed the huge `event_blocks`, `network_blocks`, full `bus_blocks` or `branch_blocks` that V14 was parsing and embedding.

`src_accelerated/dashboard.py` now reads only the required data, gets **one worst-hour bus-voltage snapshot** by streaming the bus CSV, compresses hourly and fleet traces, and omits unused event/branch/bus histories from the **HTML only**. All original `buses.csv`, `branches.csv`, `dispatch_events.jsonl`, `hourly.csv`, per-bus service data, and numerical results remain **unchanged canonical files** in the saved run; the integrity manifest still hashes them. `dashboard.js` reads the compact worst-hour snapshot.

Measured with the saved archives on the Linux test machine (not a controlled Windows timing comparison):

| Source archive | Original HTML | Rebuilt HTML | Reduction | Rebuild wall time |
|---|---:|---:|---:|---:|
| V13 two-BESS | 88.04 MB | 4.64 MB | 94.7% | 4.7 s |
| V14 No-BESS | 44.29 MB | 2.42 MB | 94.5% | 3.7 s |

Both regenerated reports include their **8,760-hour time series and all 33 worst-hour bus voltages**, all stored scenarios, and passed SHA-256 HTML integrity checks. The GUI's `stage()` now says **Dashboard ready: saved HTML report** after successful HTML generation.

A new `REGENERATE_SAVED_DASHBOARD.bat` can regenerate previous V13/V14 `run_001` directories *without recomputing the optimization*. It does not change the optimized numerical results. A saved HTML may be opened directly in Chrome/Edge; use a browser with `DecompressionStream` support.

## Validation and limitations

- **102 / 102** `unittest` tests passed on Linux (97 retained + 5 new V14.1 checks), including earlier multiprocessing smoke tests.
- New checks cover acceptance of shedding reductions despite pre-control voltage worsening, rejection of damage to other laterals, continued voltage-only guard, rejection of gains bought by extra shedding, and dropping unused report history without losing worst-hour voltage data.
- **No full-year optimization was run with changed acceptance logic.** Thus no new BESS P/E/location, cost, voltage, shedding or runtime result is claimed.
- **Windows/PySide6 GUI lifecycle was not executed** in this environment. The presence of completed HTML and manifest in the uploaded archives proves the report files were written, not that the UI necessarily closed its worker thread correctly.
- A smaller dashboard does **not** correct the separate issue of BESS inverter-reactive capability possibly dominating storage selection. Consider separate P/Q contribution and inverter-cost sensitivity in a follow-up experiment.
