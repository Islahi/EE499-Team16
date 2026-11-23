# V10.2 — Visible CPU Workers and Simplified Optimization Settings

## Interface changes

- **Optimization → Computation** now provides **Auto (recommended)** and editable worker counts in Manual mode.
- On 16 logical processors, Auto uses **4 GWO workers + 2 annual-verification workers**.
- Manual GWO workers support **1–8** processes (limited by available logical CPUs).
- Manual annual finalist workers support **1–2** processes to avoid excessive memory pressure.
- The existing 10% **voltage improvement** input is removed from the visible form: voltage regulation is checked against absolute pu limits; the old input is retained only for saved-file compatibility.
- The 10% **cumulative shedding target** is informational, not an acceptance gate, so its obsolete input is also removed from the visible form. Its default stays recorded in the methodology.
- The optimization-page explanatory text is corrected to match V10. In Auto mode, inactive number boxes are hidden; uncheck Auto to reveal them. The Computation section stays visible without Advanced mode.
- GWO population, iteration limit, random seed, real annual deterioration tolerance, finalist budget, battery bounds, and eligible buses remain available; no study data or existing results are changed.

## Performance guidance for a 16-logical-CPU / 16-GB-RAM PC

Start in **Auto** (4 GWO, 2 annual), then benchmark **Manual 6 GWO / 2 annual**. Test 8 GWO only if RAM use and disk paging are comfortable. Performance is not guaranteed to scale linearly; candidate jobs are independent, but each full-year case has SOC-dependent chronological hours.

## Safety and compatibility

- Legacy saved configurations without the Auto toggle default to Auto.
- Manual worker settings are saved and restored, and passed into the sequential optimizer; never overwritten by the approved-methodology normalizer.
- Annual verification remains limited to 2 workers with full chronological SOC validation.
- This is a V10.1 UI/computation configuration fix; no numerical solver, LP or BESS dispatch changes.
- Run `RUN_TESTS.bat` before `RUN_APP.bat` after extracting to a **new** Windows folder.
- The live GitHub repository was not accessed or modified.
