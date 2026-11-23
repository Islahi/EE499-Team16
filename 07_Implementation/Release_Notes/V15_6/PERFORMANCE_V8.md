# EE499 BESS Planning v8 — Performance, Convergence and Verification

**Source of code:** The v7 ZIP provided in this conversation. The online project repository, https://github.com/Islahi/EE499-Team16.git, was **not used** as a source and was not modified. v7 and the ongoing second-configuration run are left intact.

## What changed

1. **GWO convergence stopping** (`optimizer.py`): Default minimum 8 iterations, 6 consecutive generations without an improvement exceeding 0.1% in the *best feasible* screening objective, maximum user-configured iteration limit. If no feasible objective exists, GWO continues up to its configured limit. Each run records `stop_reason` (`converged_no_meaningful_improvement` or `maximum_iterations`), actual iterations and tolerance. This is a heuristic convergence test, **not proof of global optimality**. The GUI's existing GWO maximum iterations remains active.
2. **Representative-window evaluation caching** (`sequential_multi.py`): GWO's own per-candidate cache remains enabled. Explicit sizing probes now share the exact same stage-scoped evaluation cache. Cache results are reusable only for the **same installed fleet, same selected time windows, same network, same input profiles and unchanged economic/dispatch parameters**. A newly installed BESS changes the physical problem, invalidating the preceding stage's results.
3. **Annual baseline reuse** (`single_bess_search.py` existing content-hash cache, now connected to multi-BESS via `sequential_multi.py`): The No-BESS annual run is calculated at most once per matching dataset/configuration in a running application process; network, input profiles, clock, simulation and economic settings are part of the cache fingerprint. Restarting the app clears this in-memory cache.
4. **Accepted annual result reuse** (`sequential_multi.py`): The first full-year verified result for the selected BESS is retained with dispatch data and reused for the **next placement's annual feeder/bus assessment**, instead of running the same full-year fleet simulation a second time. Each newly accepted installation *still* causes a new full-year network assessment through its finalist evaluation, with coupled network physics and updated SOC trajectories.
5. **Adaptive annual finalist verification** (`sequential_multi.py`): Verify **up to three lateral-diverse finalists initially**. If none meets the annual technical acceptance requirements, verify additional candidates up to the existing user-set maximum (default 6). If one of the first three is acceptable, the rest are not verified. This prioritizes speed; the selected finalist is *not guaranteed* to be the cheapest among unverified configurations. The same user-entered technical acceptance rules remain active.
6. **Conservative early rejection**: A placement stage stops before GWO if **all laterals have zero baseline shedding and zero pre-shedding voltage deficit** (when both improvement thresholds are positive). A finalist at a lateral with both zero metrics is skipped because it cannot satisfy the positive local-improvement requirements. Screening simulations already short-circuit if a representative period is infeasible. We do **not** discard candidates based on unrepresentative sample-year financial costs or unsupported global lower bounds.
7. **FBS Numba memory cleanup** (`fbs.py`): Reuses the voltage scratch array inside compiled FBS iterations and avoids allocating a full per-iteration history when no history was requested. **The power-flow equations, tolerance, convergence logic, sensitivity calculation and nonlinear corrective controller remain unchanged.** Benchmarked electrical outputs matched v7 on four IEEE-style 33-bus operating points, but stand-alone runtime measurements were mixed, so **no FBS speedup is claimed**.
8. **Audit trail**: `sequential_stages.csv` gains columns for GWO iterations, stop reason, unique evaluations, screen-cache hits, checked annual finalists, annual finalist budget and accepted-result reuse. The HTML dashboard shows why each GWO stage stopped. Optimization metadata includes annual simulation count and cached baseline flag.

## What remains unchanged

- Numba FBS remains the sole power-flow backend, with unchanged electrical constraints and network representation.
- Bus-specific corrective shedding and curtailment, active-power voltage-sensitive fleet dispatch, and individual battery SOC evolution.
- The v7 per-lateral **10% shedding OR 10% voltage-deficit** experimental improvement threshold with 1% deterioration tolerance, configurable in Settings.
- Optional 'exclude previously installed laterals', OFF by default.
- The original user-specified battery power/energy catalogs, 2-week critical-period selection, tariffs, and eligibility lists.
- All annual comparisons continue to use the original **chronological** profiles.

## Recommended comparison against v7

1. Keep your ongoing v7 second-configuration run untouched; finish it in the v7 folder.
2. Extract this v8 ZIP to a **separate folder**. Do **not** mix the versions' Python packages.
3. Run `CHECK_WINDOWS_GUI.bat`, `RUN_TESTS.bat` and then `RUN_APP.bat`.
4. For a meaningful performance comparison, use the same network, 2021 profiles, seed, population, voltage limits, cost parameters and power/energy catalogs. Set lateral exclusion consistently with the v7 comparison run.
5. Compare actual wall-clock runtime, GWO stopping reason, `annual_fleet_simulations`, selected buses, kW/kWh, annual cost, shedding, pre-correction voltage deficit and verified annual technical acceptance.
6. If v8 converges early but delivers worse placement results, increase the GWO maximum iterations or adjust convergence tolerance/patience **in `OptimizerConfig`**; these controls are deliberately code defaults rather than additional GUI fields. For research-grade results, repeat runs with several seeds and/or a less aggressive convergence criterion.

## Validation completed in this environment

- **43 automated unit/regression tests pass**, including targeted tests for convergence, infeasible-case nonconvergence, stage-scoped cache behavior, accepted annual result reuse, No-BESS baseline invalidation and FBS recording equivalence.
- Four 33-bus operating points matched v7 voltage magnitudes (to 12 decimal places), slack kW (to 9 decimal places), losses (to 9 decimal places), convergence state and FBS iteration count.
- Code compiled and the settings XML and dashboard JavaScript passed their parsers.

**Not completed:** a full 8,760-hour v7-versus-v8 benchmark on the user's Windows hardware, direct Windows PySide6 GUI interaction, and optimization against the user's original full annual demand/PV data. Runtime benefits depend on how early GWO converges and whether the first three finalists satisfy the annual checks. The Numba kernel refactor alone did not show a consistent speedup in short synthetic benchmarks.
