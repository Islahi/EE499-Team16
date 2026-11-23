# BESS Planning v9 — Cumulative Improvement and Audited Annual Verification

Project identifier: https://github.com/Islahi/EE499-Team16.git. **Source code for this release is the user's uploaded v8 ZIP**, not GitHub. Existing v6/v7/v8 folders remain untouched.

## What was fixed

1. **The 10% target is cumulative, not a single-installation barrier.** The Settings controls for shedding and voltage now describe the targets relative to the original full-year No-BESS baseline. A BESS may be accepted with a smaller improvement if its targeted lateral gains **at least 0.5% in shedding OR pre-correction voltage deficit**, the other local metric does not deteriorate by more than the configured tolerance, and no other lateral or network-wide total is harmed beyond allowed tolerances. The 0.5% floor is a *provisional experimental setting* and may be revised after reviewing results. The original 10% target remains reported even when unmet. An initial 6% gain does not block the second or third installation.
2. **Chronological annual verification is audited per finalist.** Every finalist used for acceptance is simulated across the exact original **8,760 or 8,784 hourly timestamps**, without skipping failed power-flow hours. Each report records expected hours, processed hours, coverage percentage, and verification status. A truncated, misaligned, non-converged, or infeasible run **cannot** be accepted, annualized from a shorter duration, or presented as fully verified. The initial No-BESS and each accepted BESS fleet still receive their own annual assessment; accepted annual finalist results are **reused without resimulation** for the next placement's ranking.
3. **Short-period GWO screening is explicitly separate.** GWO still uses the original one/two 168-hour representative windows, so it remains much faster than annualizing every wolf evaluation. The new `screening_candidate_audit.csv` says `representative_window_only`, records the number of screened hours, and shows which candidates passed complete annual checks. Screened scores are never claimed as measured annual economics.
4. **Power and energy diversity before annual validation.** The first three finalists now include a strong screened candidate, a candidate from another weak electrical lateral (where available), and a high-kW design when available. Medium-kW and smaller-energy alternatives fill additional verification slots. Deterministic probes cover both large power and compact energy, so a 250 kW/50,000 kWh result is no longer accepted without competition from at least some other power/energy combinations.
5. **Avoid excess energy sizing in the two-week screening.** Independent screening windows can otherwise give a large battery free initially stored energy each week. The screening cost now includes an explicit terminal inventory *recharge estimate* for each sampled window. This is an approximation; the final year still uses complete chronological battery SOC and the original annual economic accounting.
6. **Trade-off-aware annual finalist choice.** Among fully verified incremental candidates, prefer stronger year-wide technical improvement. When technical outcomes are within **1 percentage point** in the normalized combined remaining-shedding/voltage metric, prefer lower verified annual cost. Selected installations may add cost, which is recorded as such. This is an EE499 design heuristic, not a proof of global optimality or a published Karve formula.
7. **Preserve v8 performance work.** Retain Numba FBS, convergence-based GWO stopping, stage-scoped screening caches, reusable No-BESS baseline, adaptive 3-to-6 annual finalists, and reuse of an accepted annual evaluation for next-stage ranking. More power/energy probing can add screening work, so **a net runtime improvement over v8 is not claimed**.

## What the output files mean

| File | Meaning |
|---|---|
| `screening_candidate_audit.csv` | All distinct screened candidate ratings, short-period hours, screening score, and whether they had an annual check |
| `annual_finalist_checks.csv` | Full-year verification hours (`annual_processed_hours` / `annual_expected_hours`), validity, incremental gains, and cumulative target status |
| `sequential_stages.csv` | GWO stop reason, placements, screening hours, annual hours, costs and cumulative improvement |
| `lateral_improvement_by_stage.csv` | Before/after changes on every electrical lateral |
| `bus_ranking_by_stage.csv` | Ranking recomputed after **each accepted** BESS; no static baseline reused for a changed fleet |
| `fleet_hourly.csv`, `service_by_bus.csv`, `buses.csv` | Final *selected* full-year fleet operation when installed; diagnostic detail on dispatch, shedding and voltages |

**Important distinction:** GWO will still evaluate many candidate designs on *less than 8,000 hours* intentionally. Only the annual finalists receive an 8,760/8,784-hour simulation. A 336-hour screened candidate is not an annual result. Running all 8,760 hours for every GWO candidate would significantly increase runtime, defeating the requested performance constraint.

## Suggested first comparison

Use the same IEEE 33-bus input year and the **same GWO settings and economic assumptions** as the prior v8 run. Keep the previous 250–5,000 kW and 250–50,000 kWh catalog if you wish to isolate the algorithm effect. Keep *Exclude previously installed laterals* OFF initially, because hard exclusion can hide a legitimate additional BESS on a still-weak lateral.

Run `CHECK_WINDOWS_GUI.bat`, `RUN_TESTS.bat`, and `RUN_APP.bat`. Compare `annual_finalist_checks.csv`, `sequential_stages.csv`, the dashboard, and complete fleet hourly outputs against v8. Check especially whether BESS 1 is accepted even when under 10%, whether a second stage is attempted, and whether the selected power is still at the minimum of the catalog.

## Validation in this build environment

- **51 automated Python regression tests pass** (43 inherited + 8 new). New cases test sub-10% incremental acceptance, cumulative progress, deterioration protection, 4,000/8,760 incomplete-run rejection, timestamp mismatch, complete 8,760-hour coverage, and power-rating diversification.
- A synthetic **8,760-hour end-to-end** optimization was executed on a three-bus network. Three finalists were fully checked (8,760/8,760 steps each), a battery was accepted, and the next stage reused its annual result. CSV export includes accurate screened-versus-verified-hour counts.
- Python compile checks, Qt Designer UI XML parsing, and dashboard JavaScript syntax checks completed.

**Not completed:** Full annual IEEE 33-bus real-dataset optimization on the user's Windows hardware, measured v8/v9 runtime comparison on the same dataset, or interactive Windows GUI testing. This package is Python source for Windows, not a compiled standalone EXE.

## Limitations and research integrity

- The model is active-power-only BESS voltage support; it has no inverter reactive-power capability or Q-control.
- Cumulative targets are **reliability targets**, not proof of zero shedding. Remaining unserved energy and voltage deficits are reported after every accepted placement. An optimizer that exhausts its budget may stop short of zero shedding.
- Strict non-deterioration rules may still reject every candidate when gains in one lateral produce network losses elsewhere. This must be disclosed, not automatically overridden.
- The full-year verdict applies only to the fully verified finalists; no global optimality claim is made. GWO convergence is a heuristic stagnation criterion.
