# V15.3 Quick Start (Windows)

1. Extract the complete ZIP to a new folder. Run `RUN_APP.bat` from that folder (do not overwrite an active older version).
2. Import the **same** `network.xlsx`, `load_profile.csv`, and `pv_profile.csv` as the preceding IEEE 33-bus tests. Ensure they cover the selected interval.
3. In Settings choose **Sindi strict: daily P/Q MILP + PF bound + SOC restoration** (first option under fleet dispatch). Confirm minimum PF **0.95**, efficiency **95% charge and discharge**, horizon **24 hours**, and your desired SOC limits. For the paper-reference costs use **$200/kWh energy** and **$175/kVA converter**. Confirm tariff and penalty assumptions independently.
4. For a quick check, choose a **24- or 48-hour interval**, enable a manual BESS with 2–12 h duration, and click **Simulate**. Examine `sindi_daily_audit.csv` in the exported run: `soc_restored` and `pf_compliant` should both be true; network feasibility must also be true.
5. Before **Optimize**, select the full calendar year, permitted bus locations, candidate power/energy grids and number of batteries. The joint SESS GA and parallel representative-day screening are retained. The strict scheduling mode can substantially increase runtime and may accept **no BESS** if strict feasibility or economics reject all designs.
6. Numerical run completion is saved into the session first. The dashboard then builds in a separate worker; inspect the Results tab or the run's `summary.md`, `metrics.csv`, `fleet_units.csv` and audit while HTML is being prepared.
7. If dashboard HTML fails, drag the exported run folder onto `REGENERATE_SAVED_DASHBOARD.bat`. If an **older** session contains exported runs not listed in `session.json`, call:

   ```bat
   python RECOVER_ARCHIVED_RUN.py "C:\path\to\Results\Sessions\<your-session>"
   ```

   This backs up `session.json` before adding missing completed runs. It does not alter numerical outputs.

## Key differences from the previous SESS results

The previous 3-BESS fleet at Buses 18,30,33 cannot be assumed feasible or economically optimal when **Q at P=0 is forbidden** and **every day must close its SOC**. A new full-year optimization is required; the historic 91.15% cost saving is *not* a V15.3 result.

## Debugging

Run `RUN_TESTS.bat` for automated tests. If Windows GUI completion still fails, preserve `session.json`, `session.log`, `summary.md`, `sindi_daily_audit.csv`, and the final run log so the handoff can be examined without rerunning GA.
