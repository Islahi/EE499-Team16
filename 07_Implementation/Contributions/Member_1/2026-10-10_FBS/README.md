# Member 1 - FBS submission and task review

Received and reviewed on 10 Oct 2026. The user identifies the contributor as **Member 1**; no personal name is inferred from the schedule's Owner field.

## Contents

- `Original/`: all six uploaded files, unchanged, with original filenames and SHA-256 checksums.
- `Runnable/`: copies of the two modules with import-compatible filenames (`network_model.py`, `fbs.py`) and a portable driver. The only driver changes import `Path`, replace `/home/claude/w/` with this contribution's `Reproduced_Results/` directory, and create that directory. No electrical calculation was changed.
- `Reproduced_Results/`: independently rerun hourly CSV and four charts.

These files are a separate development contribution. They do not replace `07_Implementation/src/`, change the team's module contracts, or select a new final network.

## Task assessment

Scheduling authority checked: [live Task Register](https://docs.google.com/spreadsheets/d/1HE7RNvaZ-VkVMlozWfkfPbe23hywnEdOzuaI1CfAEcY/edit), `Task Register!A1:O25`, on 10 Oct 2026. Technical acceptance also uses `02_Reports/Working/Planning/TERM2_DETAILED_TASK_GUIDE.md` and `TERM2_SOFTWARE_DESIGN_SPEC.md`. The older repository CSV is not used as the current status source.

| Task | Assessment from this submission | Evidence and remaining work |
|---|---|---|
| 12 - Build the 5-bus NetworkModel | Supporting implementation; already Done in live register | Five-bus radial feeder, loads, PV and topology checks are supplied. This is the 12.66 kV / 1 MVA guide case, not the prepared 11 kV / 10 MVA feeder. Its per-unit objects differ from the current public contract; retain the existing production module. |
| 13 - One-step FBS | Supporting implementation; already Done in live register | Correct backward/forward sweeps, voltages, currents, sending powers, losses and convergence flag. However, `run_fbs(network, tol_pu, max_iter)` and `FBSResult` do not implement the current `NetworkModel + OperatingPoint + FBSConfig -> PowerFlowResult` contract. The existing repository implementation already supplies that contract. |
| 14 - Verify FBS | Complete for the small-case implementation check | Report contains a three-bus manual comparison, five-bus balance, voltage approximation, loss bookkeeping and tolerance trials. Three-bus outputs and five-bus results were reproduced in this review. This is not formal Chapter 5 validation. |
| 15 - Show basic network results | Complete for the development case | Report tables/plots and solver summary show bus voltages, branch current/power, losses and source power. Driver regenerates four plots. Production engineering-unit outputs remain available in the existing `src` solver. |
| 16 - Profile import | Not supplied by Member 1; already Done by Islahi in live register | No `data_loader.py`, CSV input parsing or `ProfileData` integration is present. `hourly_results.csv` is an output, not a profile-import implementation. Do not credit this task to this submission or reset the existing completion. |
| 17 - Hourly simulation loop | Partial: development loop demonstrated | 24 hard-coded load/PV multiplier pairs call the unchanged submitted solver. Still needs the prepared timestamped `ProfileData`, existing FBS interface and public `simulation.py` orchestration. |
| 18 - Verify V1 implementation | Partial | All illustrative hours converge and balance, and the uploaded CSV is reproducible. Prepared-profile integration, input/error handling, failure propagation and BESS integration readiness are not demonstrated. |
| 19 - Chapter 4 V1 implementation | Complete as a standalone subsection draft | The five-page report covers setup, equations, implementation, trials/problems, verification, hourly results and limitations. It still needs integration into the main report and alignment with the production interfaces. Its title does not establish completion of every task numbered 12-19. |

The live register at review time marks 14/15 In Progress, 17 TBA, and 18/19 Not Started. The table above is an evidence-based assessment, not a write to the live schedule. No completion percentages or ownership changes have been invented.

## Reproduced checks

- Five-bus full-load/full-PV: 5 sweeps, lowest voltage 0.96342032 pu, losses 13.963418 kW, source power 733.963393 kW.
- The voltage complex values and active losses match the current repository solver on `build_guide_5_bus_case()` exactly for the same input and tolerance. This cross-check checks implementation consistency; the independent nodal reference already in `Validation/` remains the stronger independent method.
- Three-bus case from the report: 4 sweeps, bus 2 voltage 0.989843 pu, bus 3 voltage 0.985780 pu, active loss 3.714508 kW (rounds to 3.715 kW).
- All 24 generated CSV rows and fields match the uploaded CSV. Maximum absolute power-balance mismatch: 0.000328904 kW.
- Daily source energy: 16,537.7 kWh; line-loss energy: 305.3 kWh, using the declared one-hour intervals.
- Lowest voltage occurs at hour 18: 0.94668823 pu. Hours 18 and 19 fall below 0.95 pu. Convergence does not imply voltage feasibility.
- Tolerance trials reproduce 3/5/7/9 sweeps for 1e-3/1e-6/1e-9/1e-12 pu.
- Existing repository test suite: all 12 unittest cases pass. The existing BESS test file prints a smoke result at import; it adds no discovered unittest cases to this count.

## Important issues before integration

1. **Different interfaces and units:** submitted objects use mutable per-unit equipment values. Production objects separate static network data from operating-point kW/kvar and use ohms/A at public boundaries. Copying these modules into `src/` would break callers and tests. Production results also include diagnostics and required fields absent from this submitted result object.
2. **Network distinction:** the report discusses rejecting the looped PJM case. That is a reasonable reason not to use PJM for radial FBS, but PJM is a complementary transmission reference in this repository. It did not replace the prepared radial 11 kV feeder. Keep these three cases distinct when incorporating the text into Chapter 4.
3. **Driver portability:** the original fixed output directory can cause `FileNotFoundError` on another computer. The runnable copy fixes only this path; it retains all other limitations.
4. **Failure handling:** the loop does not reject `converged=False` before writing results. The submitted solver silently sets current to zero for an exactly zero voltage, and `max_iter=0` raises `KeyError(2)` rather than a clear configuration error.
5. **Validation gaps:** `validate_radial()` accepts multiple slack flags, an unknown load bus and a zero power base in targeted checks. It does not implement the existing production model's full physical/input validation.
6. **Source calculation:** `check_power_balance()` takes only the first branch's sending power. It works for this feeder's one outgoing slack branch and no slack load, but is not general for multiple slack branches or local slack demand.
7. **Illustrative inputs:** the 24 multiplier pairs are development fixtures. Do not present them as measured load/PV data or as verification of the prepared-profile import.

No major design decision or production engineering correction was made during this organizational import. Member 1's originals are preserved for comparison and discussion.

## Run

From the repository root:

```bash
python -m pip install -r 07_Implementation/Contributions/Member_1/2026-10-10_FBS/Runnable/requirements.txt
python 07_Implementation/Contributions/Member_1/2026-10-10_FBS/Runnable/run_simulation.py
```

The runnable driver writes CSV/charts only within this contribution's `Reproduced_Results/` directory.
