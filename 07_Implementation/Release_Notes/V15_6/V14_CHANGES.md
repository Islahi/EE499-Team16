# V14 — Hard energy-to-power duration limits for battery planning

**Source:** The user-uploaded `BESS_Planning_Karve_Multi_v13_Coordinated_OPF(1).zip` (22 November 2026). V13 remains unchanged; V14 is a separate local release. The project reference is https://github.com/Islahi/EE499-Team16.git. This package has **not** been committed or pushed to GitHub.

## New constraint

For every installed battery, defined using **nameplate** ratings (not the remaining SOC energy):

\[
T_{\min} \leq \frac{E_{\rm rated}\;({\rm kWh})}{P_{\rm rated}\;({\rm kW})} \leq T_{\max}
\]

Default **2–12 hours**, editable under **Settings → Optimization → Advanced search → Battery sizing bounds**. The minimum is deliberately **2**, not the previously discussed **1**, because a 1-hour minimum would incorrectly permit the user's 5,000 kW / 5,250 kWh example (1.05 h). Duration is a **configurable planning assumption**, not an IEEE universal battery minimum and not a guarantee of sustained full-power output under the configured SOC reserve.

The initial comparison grid is: power **250–2,500 kW** in **50 kW** steps; energy **250–15,000 kWh** in **50 kWh** steps. Grid limits and duration limits are separate; neither overrides the other. Other grids and duration bands can be selected for sensitivity studies.

| Example | Nominal duration | Allowed at 2–12 h? |
|---|---:|---|
| 5,000 kW / 5,250 kWh | 1.05 h | No |
| 3,000 kW / 250 kWh | 0.083 h | No |
| 250 kW / 250 kWh | 1 h | No |
| 250 kW / 500 kWh | 2 h | Yes |
| 1,000 kW / 8,000 kWh | 8 h | Yes |
| 250 kW / 50,000 kWh | 200 h | No |

The default grid contains **46 power choices**, **296 energy choices** and **13,616 raw P/E pairs** per bus; **8,796 satisfy the duration bounds** (35.4% fewer combinations). This is a reduction in *admissible search space*, **not a measured 35.4% solver-speed increase**. Exact candidates simulated by a stochastic optimizer depend on GWO trajectory, caching and early stopping.

## Implementation coverage

- `OptimizationBounds` owns minimum/maximum durations, validates the grid has at least one compatible P/E pair, uses sorted-catalog binary searches to find compatible energies per power, reports feasible pair counts, and rejects an invalid candidate before the expensive FBS/OPF evaluation.
- **GWO**: every random initial candidate, extreme seed, wolf's rounded position, fallback reseed and initial user-supplied candidate is constrained. Invalid P/E coordinates are projected to the nearest admissible catalog indices. Cache and existing multiworker `ProcessPoolExecutor` remain enabled.
- **Sequential multi-BESS**: deterministic low/mid/high lateral probes are constrained, finalist candidates are validated before independent annual evaluation, post-selection energy-reduction trials can select **only permitted energies for the fixed battery power**, and selected installation receives a final guard. Each unit individually satisfies the duration range; there is no invalid fleet configuration silently accepted from a valid per-unit search.
- **Other optimizer entrypoints**: exhaustive search enumerates only compatible pairs, and legacy GA crossover/mutation repairs invalid offspring before their simulation. UI still selects GWO as the approved workflow.
- **Settings**: new `spin_opt_duration_min_hours` and `spin_opt_duration_max_hours` fields (2/12 h by default); defaults are applied when an older saved study does not have these fields. The GUI validates there is at least one feasible catalog pair before starting optimization. Manually entered single batteries must satisfy the same duration window. The six sizing-grid fields now start with the agreed IEEE 33-bus comparison values rather than zero/required placeholders.
- **Reporting**: serialized metadata stores duration bounds and valid pair counts; HTML results show a duration summary and individual battery durations; `fleet_units.csv`, `annual_finalist_checks.csv`, `screening_candidate_audit.csv` and candidate evaluation CSV append a duration-hours column; text summaries show selected nameplate duration. Historical file field order is otherwise retained.
- **Unchanged V13 features**: selectable 72-hour P lookahead and coordinated P/Q OPF, nonlinear Numba FBS validation, inverter capability assumptions, voltage/current/grid limits, bus-specific progressive shedding, chronological SOC, annual economics, HTML dashboard, parallel screening and parallel annual verification.

## Test evidence and limitations

`RUN_TESTS.bat` is still the Windows entrypoint. The Linux development environment completed **97 / 97 automated `unittest` tests**: the original 85 test cases plus 12 V14 tests. The two original V12 historical refinement checks now explicitly request their old 2–100 h study window so they can continue checking the former 100 h test battery without weakening V14's 2–12 h default. New tests verify invalid tuples are never dispatched to the evaluator, boundary inclusivity, empty-grid rejection, GWO wolf projection, GA, exhaustive search, deterministic probes, refinement, serialization/default UI fields, and **2-worker Windows-style `spawn` GWO**.

No **full 8,760-hour OPF/GWO optimization** has been run using V14, so no new economic optimum, final battery location, annual energy savings, or runtime speedup is claimed. GUI rendering and Windows dependency installation have not been checked in this Linux environment, because PySide6 is unavailable here. The Qt Designer `.ui` XML structure was parsed successfully.

**Caution on cross-version comparison:** The historical V12/V13 fixed fleet had 250 kW/250 kWh (1 h) units and 1,750 kW/33,250 kWh (19 h) at Bus 8; both violate V14's default band. The historical comparison can still be reproduced in V13. It is **not** a V14-feasible installation. To isolate control improvements or planning effects, compare reoptimized V12, V13 and V14 using matched P/E bounds, time series, PV capacities, economics, reliability constraints, seed/iteration budget and enabled controls. V14 does not invalidate historical runs; it restricts new configurations.

### Run on Windows

1. Unzip V14 into a new directory separate from V13 and run `RUN_APP.bat`.
2. Import the IEEE 33-bus network and 2021 hourly profiles from the existing study folder (the uploaded V13 ZIP contains code, not this full external dataset).
3. Open **Settings → Optimization**, enable **Advanced search**, and review the **Battery sizing bounds**, including minimum and maximum duration. The default comparison grid is prefilled.
4. Select **Coordinated P/Q OPF (V13 experimental)** under Battery control if testing the coordinated controller, retain the intended parallel worker counts, and run the staged GWO.
5. Review `summary.md`, `fleet_units.csv` and the saved HTML dashboard. Inspect actual full-year annual finalists before interpreting savings.

If you intentionally want one-hour battery designs for a controlled sensitivity experiment, set the **minimum** duration lower in Settings; the V14 implementation enforces the *configured* value, not a hard-coded industry claim.
