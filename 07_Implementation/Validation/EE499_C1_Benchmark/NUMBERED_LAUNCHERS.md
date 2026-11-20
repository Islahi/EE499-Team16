# C1 benchmark — numbered Windows launchers

**Project:** https://github.com/Islahi/EE499-Team16.git

This update changes only the Windows `.bat` launchers and the benchmark documentation. The solver implementations, source data, cached benchmark results, and GitHub repository remain unchanged.

## Install over an existing benchmark

1. Extract this ZIP into the **parent directory** containing `EE499_C1_Benchmark` (for example, `...\07_Implementation\Validation`). Replace `README.md` when prompted.
2. Open the existing `EE499_C1_Benchmark` folder.
3. Double-click `00_START_HERE.bat` (or run `.\00_START_HERE.bat` in PowerShell).
4. The menu automatically moves the **old, unnumbered launcher `.bat` files only** into `_old_launchers_before_numbering/`. It does not delete results. The new `01_` through `13_` launchers remain in the main folder.
5. Select a numbered option in the menu, or execute a numbered `.bat` file directly.

The update uses shared **Python 3.14**, **MATLAB R2026b**, `matlabengine==26.2.5`, and **no project-specific virtual environment**. `PYTHON_CONFIG.bat` remains unnumbered because it is called internally by the launchers, not run by the user.

### Order for a new installation

| Step | Launcher | Purpose |
|---:|---|---|
| 01 | `01_SETUP.bat` | Install core Python libraries |
| 02 | `02_SETUP_OPTIONAL.bat` | Install optional solver libraries |
| 03 | `03_INSTALL_MATLAB_ENGINE.bat` | Install MATLAB Engine for R2026b |
| 04 | `04_VERIFY_MATLAB.bat` | Verify MATLAB and MATPOWER |
| 05 | `05_CHECK_SOLVERS.bat` | Check solver availability |
| 06 | `06_RUN_QUICK_TEST.bat` | Run 15-bus quick test |
| 07 | `07_RUN_ACCURACY.bat` | Run accuracy benchmark |
| 08 | `08_RUN_SPEED.bat` | Run speed benchmark |
| 09 | `09_RUN_FULL_BENCHMARK.bat` | Run full benchmark |
| 10 | `10_RUN_FAILED.bat` | Rerun failed / missing cases |
| 11 | `11_GENERATE_REPORTS.bat` | Regenerate reports from saved data |
| 12 | `12_OPEN_DASHBOARD.bat` | Open offline dashboard |
| 13 | `13_PROFILE_QUICK.bat` | Run profiling diagnostic (not timed benchmark) |

Recommended first-time sequence: **01 → 02 → 03 → install MATPOWER in MATLAB → 04 → 05 → 06 → 09 → 11 → 12**. If you already installed dependencies, skip those completed steps.

**MATLAB note:** `04_VERIFY_MATLAB.bat` checks the Engine connection and MATLAB `runpf`. `05_CHECK_SOLVERS.bat` checks import availability and is not proof that all algorithms are numerically correct.

**No need to use 07, 08 and 09 together** unless you want separate accuracy and speed studies. The full benchmark (09) handles both modes, subject to the supplied benchmark configuration.

Do not execute `.bat` files in `_old_launchers_before_numbering/` unless restoring a previous launcher revision.
