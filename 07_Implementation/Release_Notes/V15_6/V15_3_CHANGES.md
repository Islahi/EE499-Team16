# V15.3 — Sindi-style strict static BESS operation + robust dashboard completion

## Baseline

Built directly on the **uploaded SESS joint-GA backend**, not on the older sequential-GWO branch. Its discrete GA location representation, k-means representative-day screening, parallel evaluations, full-year finalist verification, and Numba FBS remain available.

## Strict operating model (`sindi_strict`)

A new *optional* mode is selectable in Settings. This is a **static-battery adaptation** of Ahmed, Sindi, Azzouz and Awad, *Optimal Sizing and Scheduling of Mobile Energy Storage Toward High Penetration Levels of Renewable Energy and Fast Charging Stations*, IEEE Transactions on Energy Conversion, DOI: 10.1109/TEC.2021.3116234. It is **not** an exact reproduction of the complete mobile-storage nonlinear formulation; see Limitations.

- Plans charging **C**, discharging **D** and positive reactive injection **Q** *jointly* using a 24-hour SciPy/HiGHS mixed-integer linear model (optional 48- or 72-hour look-ahead, replanned each day).
- Binary operating variables enforce **no simultaneous charge and discharge** in the planned schedule.
- Positive reactive output is constrained by **`0 ≤ Q ≤ P_dis × tan(acos(PF_min))`**, additionally constrained by inverter kVA; Q at zero discharge is zero. Default PF_min = 0.95 (configurable; a table in a different edition used 0.80).
- Battery energy follows actual per-step charge/discharge efficiencies (default 95% each), nameplate power and SOC bounds.
- Planned **end-of-day SOC = start-of-day SOC** for every day, including the intermediate days of a 48-/72-hour look-ahead.
- The **hourly coordinated corrective OPF cannot alter the planned BESS active P**. It can adjust permissible Q/PV support, PV curtailment and bus-specific load shedding; every final dispatch is checked by nonlinear Numba FBS. If actual daily SOC fails to close (default tolerance 0.05 kWh), the **result is infeasible**. If the daily MILP fails to produce a schedule, the program can use safe idle control but does **not** accept the result as a validated strict run.
- Files: `src_accelerated/sindi_strict.py`, `joint_opf.py`, `multi_bess.py`, `simulation.py`.

## Economic configuration

Strict GUI defaults use **$200/kWh** battery-energy capital cost and **$175/kVA** inverter/converter capital cost, default 95% charge and discharge efficiencies, 10-year equipment life, annual O&M 2% of investment, with real-discount capital recovery based on 5% nominal interest and 1% inflation. The kVA rating is at least `P_rated / PF_min` to price the inverter separately. Legacy independent-P/Q mode retains its original cost settings and straight-line capitalization for comparisons. These are model inputs, not market quotations.

The battery duration search still uses configurable 2–12 hours; a nominal 3-hour reference is relevant to the paper but **not forced on every candidate** unless the user sets min/max to 3.0. The GA retains joint bus/P/E optimization.

## Dashboard completion repair

Numerical result exports (CSV/JSON/metadata) are saved and the run is **registered in `session.json` inside the background worker** before HTML generation. The main GUI then reports the numerical run as finished and starts a separate dashboard worker. HTML errors are logged and do not erase completed numerical results.

A direct worker-thread `QThread.quit` signal prevents the specific main-thread queued `quit` problem seen in previous versions. Extra exception diagnostics and recovery are included. Dashboard regeneration excludes unused full-year trace blocks; original CSV/JSON stays intact. `REGENERATE_SAVED_DASHBOARD.bat` rebuilds HTML from saved results. `RECOVER_ARCHIVED_RUN.py` repairs old, fully exported runs missing from `session.json` (backs up the manifest first).

## New output

`sindi_daily_audit.csv` is exported for strict runs: bus, each day's starting/ending SOC, energy residual, closure status, discharge-linked PF compliance and violations. This audit uses **executed** hourly data, not just the day-ahead plan.

## Validation performed

- **116 passed pytest tests**, including old SESS tests and new strict-mode checks (21 additional subtests); 2 warnings.
- Tests cover 24-/48-/72-hour planning, full hourly Q and inverter limits, SOC boundaries, charging/discharging exclusivity, empty-fleet baseline, manual single BESS, synthetic daily restoration, forced SOC failure, forced MILP failure rejection, cost basis, GUI-neutral `run_study` and dashboard worker registration logic.
- User's saved IEEE 33-bus input: **48-hour** strict No-BESS, Bus-18 single BESS, and buses 18+30 two-BESS simulations ran. Single BESS and no-Battery cases were feasible; two-BESS case had network constraint violations and was **correctly rejected** despite SOC closure. This is expected: old results are not automatically feasible with strict control.
- Original uploaded SESS 8,760-hour archived outputs: rebuilt offline dashboard to **4,539,383 bytes (~4.54 MB)** in about **4 seconds**; manifest hash matched.
- Complete **48-hour** IEEE 33-bus export test: numerical export, `sindi_daily_audit.csv`, saved dashboard metadata, dashboard regeneration and manifest succeeded.

## Limitations / unverified

- A complete **8,760-hour, multi-BESS, Windows GUI optimization** has **not** been run here. Therefore **no new annual savings, selected battery fleet or Windows GUI-completion guarantee** is claimed.
- Exact paper replication would require its mobile BESS routing, fast-charging stations, PV/wind design, uncertainties and nonlinear GA/GRG formulation. This version follows the *relevant strict operating constraints* using linearized daily MILP + verified AC FBS, not the complete original formulation.
- Saved hourly profiles used for offline look-ahead are **perfect foresight**, not an independently validated forecast. Run on actual forecast profiles before any operational conclusions.
- Tight daily SOC restoration with strict discharge-linked Q can reject many candidates or significantly increase cost and computation. Feasible daily schedules are *not* a guarantee of network feasibility, and vice versa; both must pass.
- Qt UI is not executable in the Linux test container, so Windows handoff remains to be verified on the user's machine; if the GUI hangs again, the numerical session should still be registered and recoverable.

## Running

Read `V15_3_QUICKSTART.md`. The project reference remains https://github.com/Islahi/EE499-Team16.git. This package is local, not pushed to GitHub.
