# EE499 Team 16 — C1 radial power-flow solver benchmark

**Project:** https://github.com/Islahi/EE499-Team16.git  
**Status:** Benchmark framework prepared; **no full benchmark has been executed in the preparation environment**. All engineering rankings and measured performance are created on your own Windows computer.

## What is bundled

- `C1_Simple_Test/` — unmodified historical C1 Python solver, 22 network workbooks, published-paper reference tables, original results and plots.
- `benchmark_core.py` — normalized balanced three-phase network assumptions, canonical network inputs, deterministic scenarios, numerical residual, solver adapters.
- `run_benchmark.py` — availability, case/solver selection, nominal/reference comparisons, warm/cold measurements, resuming, manifest.
- `reporting.py` — measured-result CSV, PNG charts, offline dashboard, PDFs and optional Excel workbook.
- `config.json` — solver tolerance, timing repetition and qualification settings.
- `tests/` — small deterministic checks, separate from official benchmark measurements.
- `historical_reference/` — user-supplied supplemental C1 7z archive and radial-system review PDF; archive files are references, not fabricated run outputs.

## Start on Windows PowerShell

Extract the ZIP into a normal writable folder such as `C:\EE499\C1_Benchmark`, then open PowerShell in that folder. The following numbered launchers may be double-clicked. Run `00_START_HERE.bat` first to show a menu and archive older unnumbered launcher files safely.

```powershell
.\00_START_HERE.bat
# Or run individual scripts:
.\01_SETUP.bat
.\02_SETUP_OPTIONAL.bat
.\03_INSTALL_MATLAB_ENGINE.bat
.\04_VERIFY_MATLAB.bat
.\05_CHECK_SOLVERS.bat
.\06_RUN_QUICK_TEST.bat
.\09_RUN_FULL_BENCHMARK.bat
.\11_GENERATE_REPORTS.bat
.\12_OPEN_DASHBOARD.bat
```

This launcher update defaults to **shared Python 3.14**, with **no virtual environment**. MATLAB R2026b officially supports Python 3.14, and the C1 benchmark can use the same interpreter as the forecasting program. To select a different installed interpreter temporarily, set `$env:EE499_PYTHON_VERSION = "3.13"` before running the launchers. Run setup again for that interpreter; packages are installed per Python version. For an eight-solver performance comparison, use the same interpreter throughout. Install MATLAB Engine R2026b package `matlabengine==26.2.5` in Python 3.14, using `03_INSTALL_MATLAB_ENGINE.bat`.

Compatibility references: https://www.mathworks.com/support/requirements/python-compatibility.html and https://pypi.org/project/matlabengine/.

Equivalent commands after setup:

```powershell
py -3.14 .\run_benchmark.py check
py -3.14 .\run_benchmark.py quick
py -3.14 .\run_benchmark.py accuracy
py -3.14 .\run_benchmark.py speed
py -3.14 .\run_benchmark.py full
py -3.14 .\run_benchmark.py full --case T04 --solver fbs_python,scipy_nr,pandapower_nr
py -3.14 .\run_benchmark.py failed
py -3.14 .\run_benchmark.py reports
py -3.14 -m pytest tests -q
```

**Numbered-launcher update:** `00_START_HERE.bat` provides a menu of all 13 tasks. On first use, it moves only legacy unnumbered `.bat` launchers to `_old_launchers_before_numbering/`. The original project code, `PYTHON_CONFIG.bat`, outputs, and MATLAB setup are untouched.

**No-venv update:** Run `01_SETUP.bat` and `02_SETUP_OPTIONAL.bat` once for the shared Python 3.14 user site. An older `.venv` is not used by the updated launchers; delete it only after verifying global/shared dependencies and ensuring no other project relies on it. MATLAB Engine is a separately installed package for this interpreter.

**MATLAB test from PowerShell** (after installing MATPOWER):

```powershell
py -3.14 -m pip show matlabengine
py -3.14 -c "import matlab.engine; eng=matlab.engine.start_matlab(); print(eng.version()); print('runpf:',eng.exist('runpf','file')); eng.quit()"
.\04_VERIFY_MATLAB.bat
.\05_CHECK_SOLVERS.bat
```

`--force` reruns the matching cache. `--case` matches filenames; `--solver` can be comma-separated. `--config other.json` supports custom settings. Input/workbook paths with spaces are handled by the launchers. Workload and requested solver availability must be checked before a long run.

### Supported numerical adapters

| Entry | Method and implementation | Dependency | Status |
|---|---|---|---|
| `fbs_python` | Original C1 current-summation backward/forward sweep | NumPy | Bundled, required baseline |
| `fbs_numpy` | Same FBS algorithm, array backend | NumPy | Bundled |
| `fbs_numba` | Same FBS algorithm, compiled CPU backend | Numba | Optional |
| `scipy_nr` | Independent damped Newton–Raphson AC power mismatch with exact rectangular Jacobian (real/imag voltage unknowns) | SciPy | Included |
| `pandapower_bfsw` | pandapower backward/forward sweep | pandapower | Optional |
| `pandapower_nr` | pandapower Newton–Raphson | pandapower | Optional |
| `opendss` | OpenDSSDirect.py OpenDSS balanced three-phase model | OpenDSSDirect.py | Optional, inspect conversion validation |
| `matpower_matlab` | MATLAB Engine + installed MATPOWER `runpf`, NR | MATLAB, MATLAB Engine, MATPOWER | Optional |

**Important:** The SciPy adapter implements damped rectangular-coordinate AC Newton–Raphson with an explicitly assembled analytical power Jacobian and SciPy dense linear solves. It is independent from the project FBS implementation.

VeraGrid/GridCal and GPU are **not implemented**; adding these requires adapter validation. MATLAB Engine must be installed into the selected Python version and `MATPOWER` added to MATLAB search path. For R2026b, first run `03_INSTALL_MATLAB_ENGINE.bat`, which installs pinned `matlabengine==26.2.5` for Python 3.14. Download MATPOWER from https://matpower.org/download/, unzip it to a folder of your choice, open MATLAB, navigate to the directory containing `install_matpower.m`, and run `install_matpower`. Then run `04_VERIFY_MATLAB.bat`. The MATLAB engine is reused across warm solves. The benchmark keeps MATLAB optional. The availability check in `05_CHECK_SOLVERS.bat` tests only whether MATLAB Engine imports; `04_VERIFY_MATLAB.bat` verifies that `runpf` actually resolves.

### Electrical comparability

All solver adapters use constant-P/Q per bus, one slack node, balanced positive-sequence total three-phase kW/kvar, single voltage base, a fixed radial topology, series R/X, **no line shunt capacitance**, and no tap changers. Voltage reference is phase-aligned for comparisons. Bus and line IDs are retained. OpenDSS uses three symmetric phases with identical positive- and zero-sequence R/X and zero capacitance; this is intended to match the positive-sequence equivalent but must be checked against the input audit and residual values. A different electrical model must be flagged, **not interpreted as a numerical solver error**.

The nominal baseline uses the historical `run_c1.py` protocol: 60 Hz, 100 iterations, 1e-8 pu complex-voltage tolerance, static P and Q, no PV or battery. Historical C1 results are included solely for regression reference and flags; the prepared package does not count them as benchmark scores. The publication uses a printed `Sbase=100` and has known data discrepancies. T18 is split into two independently rooted feeder files; neither is by itself the two-substation aggregate printed in the review. The package does not force numerical agreement against mismatched paper inputs.

### Scenario coverage

At least 24 reproducible operating points per case: nominal repeat, light/heavy demand, daytime/high solar, battery charge/discharge, reverse power, severe loading, then a deterministic time-varying profile. The BESS sign convention is **positive discharge**. Scenarios are generated under `results/operating_points/` for inspection. All adapters receive the identical bus injections (if they can represent them). Network topology and parameter conversion remain outside warm timed loops.

Warm timing includes updating nodal injections, the solver, and voltage/result extraction, but excludes report generation, file writes, and validation residual checks. Recorded first-call cold timing includes adapter setup and first solve, but **does not include Python process startup or initial library imports**; those require an additional process-level benchmark before interpreting as full cold-start cost. For very fast kernels use more repeats in `config.json`, and compare only timings measured on a single Windows computer. Present speedups only for converged, electrically equivalent and accuracy-qualified runs. Python/BLAS thread count is set in launchers and the manifest records versions. When feasible validate warm-start experiments separately; this default protocol uses flat starts and does not claim equal initialization overhead.

### Results after **you** run

`results/` is created locally and populated with:

- `manifest.json` — source checksum, network checksums, settings, OS/Python/library versions.
- `solver_availability.csv`, `input_audits/*.json`, `operating_points/*.csv`.
- `solver_summary.csv`, `bus_voltages.csv`, `published_comparison.csv`, `published_bus_voltages.csv`.
- `cross_solver_accuracy.csv`, `scenario_results.csv`, `timing_summary.csv`, `raw_timings/*.csv`, `failures.csv`, `solver_rankings.csv`.
- `C1_Results.xlsx` **if** the optional `artifact_tool` package is installed (all equivalent tables are always available as CSV).
- `figures/*.png` — one chart per PNG.
- `dashboard.html` — entirely local HTML, no CDN.
- `C1_Technical_Report.pdf` and `C1_Complete_Rankings.pdf` — created **only after** local run results exist.

Warning: generating reports with zero data produces empty templates, not analysis; run a benchmark first.

### Resume, failure and reproducibility

The cache under `results/raw/` uses a hash of configuration, input workbook, solver and execution mode. An interrupted run can be repeated with the same command. `failed` rechecks failed/missing entries rather than redoing successes when the matching cache exists; records also remain in `failures.csv`. Running accuracy and full modes separately produces distinct records, intentionally not merged. Passing a new configuration or modified workbook invalidates the cache. **Do not combine separate machine timings** or change source files without recording a new source revision.

### Engineering review of limitations

- Published-reference numerical values are not always based on matching input data. The 69-bus and additional IEEE 33-bus cases have pre-existing review flags; retain them.
- Initial qualification checks are strict (1e-6 pu voltage and 1e-3 kW/kvar nodal mismatch). Tighter solver tolerances may be needed; no fixed ranking can be assumed to emerge.
- Published tables contain rounded bus voltages; use their printed precision rather than demanding agreement to machine precision.
- SciPy uses its own analytical rectangular AC Jacobian and damped Newton steps. Verify convergence of stressed or very large cases rather than treating an iteration count as proof of accuracy.
- 22 workbooks include duplicated/near-duplicated topology cases. Rank individual network cases rather than counting duplicates as independent corroboration.
- OpenDSS `TotalPower` and per-bus phase extraction should be checked on the 5-bus case before trusting rankings.
- Optional solver installation and MATPOWER configuration cannot be verified from this environment; missing implementations are separately labeled.

### References

- Project: https://github.com/Islahi/EE499-Team16.git
- Published radial review: Y. Latreche et al., *Comprehensive Review of Radial Distribution Test Systems*, supplied PDF.
- pandapower AC power flow: https://pandapower.readthedocs.io/en/latest/powerflow/ac.html
- OpenDSSDirect.py: https://dss-extensions.org/OpenDSSDirect.py/notebooks/GettingStarted.html
- MATPOWER `runpf`: https://matpower.app/manual/matpower/ttrunpf.html

This ZIP makes **no changes to GitHub**.
