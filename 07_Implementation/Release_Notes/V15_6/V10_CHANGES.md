# BESS Planning v10 — Voltage Compliance, Annual-Aware Sampling and Parallel Speed

**Source:** Built from your uploaded `BESS_Planning_Karve_Multi_v9_Verified` folder/ZIP. V9 is unchanged; no GitHub file was read or modified. Project reference only: https://github.com/Islahi/EE499-Team16.git.

## Decisions made in V10

1. **Voltage compliance is absolute, not a 10% improvement requirement.** The configured FBS voltage limits (normally 0.95–1.05 pu) remain physical limits on the final operating point. The *pre-shedding* voltage deficit is used for screening and technical benefit. A tiny positive reduction is sufficient when it removes an undervoltage; there is no arbitrary 10% voltage barrier. Further voltage gains beyond compliance are not rewarded by the deficit metric. A voltage gain obtained by *increasing load shedding on the target lateral* is rejected.
2. **Shedding matters more.** Sequential annual bus screening uses **80% shedding rank / 20% voltage rank** before balancing electrical laterals (other legacy one-BESS screening remains 50/50). The GWO screening score is 94% technical and 6% estimated economic, with the technical portion now **80% normalized unserved energy + 20% normalized pre-shedding voltage deficit** (or 100% of the remaining nonzero metric). The annual finalist ranking uses the same 80/20 technical preference and annual cost breaks close ties. The **10% cumulative shedding target remains informational**, not a hard per-BESS rejection threshold. No technical improvement means no installation.
3. **The same 336-hour default screening budget spans the year.** Two 168-hour representative weeks have been replaced with **seven nonoverlapping 48-hour windows**: up to three critical windows from distinct annually stressed laterals plus one typical window in each quarterly season. All are selected from the **current complete annual installed-fleet baseline**, which is rerun/reassessed only after each accepted BESS. This increases calendar coverage without multiplying GWO hours. For a one-week budget, the total may be rounded down to whole 48-hour blocks. Short windows are screening estimates, *not* annual results. Independent windows restart battery SOC and use the existing terminal-inventory adjustment; this limitation remains.
4. **GWO candidate parallelism.** Previously `workers=1` was hard-coded in sequential stages. V10 honors the CPU-worker setting, capped at 4 for GWO. The nested progress callback is removed before Windows worker pickling. GWO still has seeded candidates, caching and convergence-based early stopping.
5. **Concurrent annual finalists.** Independent candidates are evaluated with up to **two worker processes**, preserving 8,760/8,784 consecutive hours and full SOC continuity *within each candidate*. First three finalists are evaluated, then additional candidates (up to the configured maximum) only if needed. Each accepted result is reused for the next annual feeder assessment. The two-worker cap limits RAM pressure; selecting CPU workers = 1 enables serial verification for debugging.
6. **LP corrective-control acceleration.** At each correction iteration, remove linear constraint rows that are mathematically satisfied for **every possible LP control change inside the current bounds**. Retain the same objective, progressive shedding weights, sensitivity model, nonlinear FBS verification and constraint limits. Record `lp_redundant_rows` in simulation timing. This is not removal of operational constraints, only elimination of redundant rows from an individual LP subproblem.
7. **Annual coverage checks preserved.** A candidate must have the exact original chronological timestamp series and converge with feasible operating constraints to be considered annually verified. Incomplete (e.g. 4,000/8,760 hours) and unverified short-period candidates cannot be accepted. `annual_finalist_checks.csv` now additionally exports pre-shedding voltage compliance and absolute reductions in shedding and voltage deficit. The dashboard and stage export record worker counts and window policy.

## Defaults for first V10 run

- Keep **the same network and inputs, prices, voltage limits, battery catalog and random seed** as your V9 test.
- Keep previous 250–5,000 kW and 250–50,000 kWh catalog only if you want a direct comparison; larger energy is not automatically more useful.
- Keep **up to 3 BESS** and **Exclude previously installed laterals OFF** for the main comparison.
- Set **CPU workers = 2** as the first conservative parallel run. Test 4 for screening only if RAM and CPU permit. Annual finalists remain capped at 2 concurrent processes.
- Keep up to **6 annual finalists**, GWO population/iteration settings unchanged for comparability. Convergence stopping still applies.
- Use two-week screening budget (automatically seven 48-hour windows); this is not exhaustive annual optimization.
- The GUI's former voltage-percentage control remains visible but disabled for saved-settings compatibility; **it has no role in V10 acceptance**. The physical `voltage_min_pu` and `voltage_max_pu` settings are authoritative.

## Testing and provenance

- **59 Python automated tests passed** (51 inherited and 8 new), including representative sampling across four quarters, physically small voltage corrections, no extra target shedding, independent process verification and callback stripping.
- **Synthetic complete 8,760-hour end-to-end optimization passed** with two-worker annual verification: three finalists were each verified 8,760/8,760 hours, and an installation was accepted. This is not your historical 33-bus run.
- **Spawn-mode multiprocessing smoke test passed** for both GWO and annual finalists (emulates Windows process creation).
- **120-hour synthetic stressed 15-bus comparison:** v9 and v10 voltages, shedding, losses, grid imports and feasibility matched exactly (at the recorded precision). V10 eliminated 8,580 provably redundant LP rows. On this one run, total elapsed time was about 1.93 s for v9 vs. 1.70 s for v10. This is neither a controlled repeated benchmark nor a prediction of Windows full-year speed.
- Python compilation, JS syntax and Qt Designer XML parse checks passed.
- **Not validated**: full real-year IEEE-33 optimization on your Windows PC, actual v9/v10 runtime speedup on that dataset, or interactive PySide6 GUI operation.

## How to run

1. Extract this ZIP into a **new folder**, without overwriting V9 while it runs.
2. Use `CHECK_WINDOWS_GUI.bat`, then `RUN_TESTS.bat`, then `RUN_APP.bat`. Uses the existing system Python (prefer 3.14), no virtual environment created.
3. To compare runs: use identical inputs/seed/catalog/settings; inspect `sequential_stages.csv`, `annual_finalist_checks.csv`, `screening_candidate_audit.csv`, `lateral_improvement_by_stage.csv`, `fleet_hourly.csv` and the dashboard.
4. Look at *annual processed/expected hours*, the selected batteries' actual kW output and SOC, the physical pre-shedding voltage deficits, and net unserved energy. A short screening score is not a final annual claim.

## Limitations and safeguards

- Improvement thresholds, costs and the 80/20 weighting are **study heuristics**, not universal engineering standards or the original Karve formula.
- The algorithm is sequential/greedy; it cannot prove globally optimal multi-BESS placement, and selecting a battery does not guarantee zero shedding over all scenarios.
- The physical model is still BESS active-power-only (no inverter Q support); BESS cannot guarantee voltage compliance before shedding in every hour.
- Multiple worker processes use more CPU/RAM. If Windows process startup or memory pressure outweighs benefits, use **CPU workers = 1** and compare outputs.
- Annual simulation of the current fleet is recomputed after each accepted placement, with the original No-BESS annual baseline cached and unchanged.
