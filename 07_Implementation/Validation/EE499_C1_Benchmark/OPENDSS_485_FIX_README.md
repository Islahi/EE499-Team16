# EE499 C1 — OpenDSS warning #485 hotfix

Repository reference: https://github.com/Islahi/EE499-Team16.git

This is a **one-file patch** for the separate C1 benchmark, not a change to the GitHub repository or project power-flow implementation.

## Reason for the fix

The 15-bus quick test executed the other seven solvers successfully, but OpenDSSDirect reported `(#485) Warning Max Control Iterations Exceeded`. The adapter explicitly set `maxcontroliter=1` and then used `Solution.Solve()`, which may enter the OpenDSS control loop.

The benchmark model contains lines, a slack source and constant-PQ loads, **no automatic voltage regulation or other control devices**. Running the power-flow calculation without device control actions is intentional and does not exclude Newton, fixed-point, or other electrical solution iterations.

## Changes

File: `benchmark_core.py`

- Remove `Set maxcontroliter=1` (the artificial control-loop limit).
- Keep `Set controlmode=off`.
- Replace `dss.Solution.Solve()` with the documented `dss.Solution.SolveNoControl()`.
- Retain `MaxIterations` and `Convergence` settings for power-flow solver iterations.

The 15-bus network, all other solver adapters, timing mechanism, and report code are unchanged.

## Install on Windows

1. **Close the running benchmark/menu** first.
2. Back up your existing `EE499_C1_Benchmark\benchmark_core.py` if you made local edits.
3. Extract this ZIP into the parent folder `...\07_Implementation\Validation\` and overwrite only `EE499_C1_Benchmark\benchmark_core.py`.
4. Start `00_START_HERE.bat` and choose **6** (15-bus quick test). The previous compatibility patch's numbered quick-test launcher uses `--force` and recalculates cached failures.
5. Confirm `opendss success`, then inspect its convergence and physical mismatch status in the generated results. Solver execution success does **not** by itself guarantee electrical accuracy.

If the warning remains, run in PowerShell from `EE499_C1_Benchmark`:

```powershell
py -3.14 run_benchmark.py quick --solver opendss --force
```

Preserve the full new error text, library version (`py -3.14 -m pip show opendssdirect`) and `results/failures.csv`. Do not increase the power-flow tolerance or disable convergence checks just to make a solver appear to pass.

## Documentation

- EPRI — `SolveNoControl`: https://opendss.epri.com/SolveNoControl.html
- OpenDSSDirect.py API — `Solution.SolveNoControl()`: https://dss-extensions.org/OpenDSSDirect.py/opendssdirect.html

## Verification limits

Patch source matches the earlier OpenDSS/Matplotlib hotfix release (`EE499_C1_QuickTest_API_Fix_Python314.zip`). The patched Python source passed AST compilation and call-site checks in the packaging environment. The actual OpenDSS engine was not available here, so the electrical solution must be tested on your Windows installation. This patch does not modify GitHub.
