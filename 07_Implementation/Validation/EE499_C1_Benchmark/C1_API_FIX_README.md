# EE499 C1 15-Bus Quick Test — OpenDSS and Matplotlib compatibility hotfix

**Repository reference:** https://github.com/Islahi/EE499-Team16.git  
**Target:** C1 Windows benchmark package, using the numbered launchers (Python 3.14 / MATLAB R2026b, no virtual environment).  
**Scope:** Three-file patch. No GitHub commits or production solver modifications.

## Installation

Extract this ZIP into the **`07_Implementation\Validation`** directory, preserving the included `EE499_C1_Benchmark` folder. If Windows asks, choose **Replace the files in the destination**.

The files replaced inside `EE499_C1_Benchmark` are:

- `benchmark_core.py`
- `reporting.py`
- `06_RUN_QUICK_TEST.bat`

**Optional safety:** make a copy of the original three files before overwriting. All saved benchmark outputs are left alone by the patch.

## Changes

1. In `dss_solve`, replace the nonexistent OpenDSSDirect.py `Solution.Tolerance(...)` call with its supported `Solution.Convergence(...)` call. The configured numerical tolerance is unchanged.
2. In `plot_results`, remove Matplotlib's unsupported `boxplot(..., labels=...)` argument; apply the same names with `xticks(...)` instead. This works with older and newer Matplotlib versions.
3. In `06_RUN_QUICK_TEST.bat`, add `--force` so the quick test retries OpenDSS and does not reuse the previously cached failure. This reruns all eight solvers in the 15-bus quick test.

## Run

From PowerShell in `EE499_C1_Benchmark`:

```powershell
.\06_RUN_QUICK_TEST.bat
```

Or run `00_START_HERE.bat` and select **6**.

The end of the run should say `Completed, results: ...` without the previous OpenDSS API error or the Matplotlib boxplot exception. Check the solver result lines; **an API error being fixed does not by itself prove numerical accuracy**. Inspect the generated `results/solver_summary.csv`, `results/failures.csv`, `results/accuracy_ranking.csv` and reports.

For report regeneration without rerunning power-flow solvers:

```powershell
.\11_GENERATE_REPORTS.bat
```

Do not run `10_RUN_FAILED.bat` solely to retry the earlier quick test; its different cache namespace and full-run semantics are not equivalent. The updated **option 6** is the intended path.

## Verification limits

- Python syntax and a small offline compatibility check were performed before packaging.
- Running all eight solvers still requires your local Windows/MATLAB installation.
- The ZIP contains **no** fabricated benchmark results and does not modify the upstream GitHub repository.
