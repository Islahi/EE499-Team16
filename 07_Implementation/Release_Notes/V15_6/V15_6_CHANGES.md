# V15.6 — Session registration and JSON export stability

## Root cause (uploaded 2026-11-23 03:06 session)

The Joint GA completed its 20-generation search, the independent stress screen, and **one full chronological 8,760-hour verification** of its first finalist (BESS at buses 7 and 8). The annual result and numerical exports were saved. The optimizer then failed **after** `Numerical results and dashboard metadata saved` when the worker tried to append the run to `session.json`.

`src/study_session.py::_json_value()` handled dictionaries, lists, paths and datetimes, but not NumPy scalar types. In the GA's nested `Placement stages → full_year_candidates → economic_acceptable`, a NumPy boolean reached `json.dumps`, resulting in `TypeError: Object of type bool is not JSON serializable` on the user's Python 3.14/NumPy installation. The GUI then incorrectly logged the successful computation as failed because registration failed.

## Changes

1. Deep-convert `np.bool_`, NumPy integers, floats, and arrays into JSON-safe native values throughout nested metadata. Non-finite floats become JSON `null`, avoiding malformed metadata and failures with strict JSON encoders.
2. Serialize the complete session manifest **before** opening the target file, then atomically replace it from a temporary file. An export exception cannot truncate the existing `session.json`.
3. Update `RECOVER_ARCHIVED_RUN.py` to recognize a previously failed run marked with this **specific JSON serialization error**, only when fully exported result files prove a successful and feasible run. The existing failed entry is replaced in place (not duplicated), retaining the error as `recovered_from_error`. Existing unrelated failure records are never promoted.
4. Add five focused regression tests covering deep NumPy values, realistic run registration, atomic-save failure preservation, archived-run recovery and recovery rejection for actual physics failures. All old simulation, solver and optimizer functionality is unchanged.

## Uploaded run evidence

- Session: `20261123_030642_ieee_33bus_network_data`
- Full-year finalist 1/3: `[7, 8]` — passed, then early-stopped further annual checks.
- BESS 1: Bus 7, 1,200 kW / 10,700 kWh / 1,263.16 kVA.
- BESS 2: Bus 8, 250 kW / 2,850 kWh / 263.16 kVA.
- Cost: No BESS $39,504,196.19/year; BESS $26,489,470.83/year; savings $13,014,725.37/year (32.95%).
- Sindi daily audit: 730/730 battery-day entries have restored SOC and zero power-factor violations; full-year simulation reported 0 post-control voltage-violation hours.
- Recorded processing: about 14m13s through the run registration failure.

## Recovery of old results without optimization

1. Use this new V15.6 package's `RECOVER_ARCHIVED_RUN.py` with the **session root folder**, not `optimization/run_001`:

   `python RECOVER_ARCHIVED_RUN.py "C:\path\to\Results\Sessions\20261123_030642_ieee_33bus_network_data"`

2. The utility creates `session.json.before_recovery_YYYYMMDD_HHMMSS` and updates the archived session's run record to `recovered_complete`. It does not modify original CSVs, hourly traces, optimizer output, or economic results.
3. Generate the HTML separately if needed, without rerunning the optimizer:

   `REGENERATE_SAVED_DASHBOARD.bat "C:\path\to\Results\Sessions\20261123_030642_ieee_33bus_network_data\optimization\run_001"`

## Validation limits

- 132 automated tests passed, plus 21 parametrized subtests; tested against the uploaded archive's real `session.json` and saved run metadata in a separate local recovery copy.
- The prior 8,760-hour run has already completed on the user's PC; a **new V15.6 Windows GUI execution has not been independently run**.
- This is a targeted serialization and recovery patch; it does not alter GA search, Sindi operating policy, physical feasibility, costs, or dashboard rendering logic.
