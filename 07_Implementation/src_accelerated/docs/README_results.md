# `results.py` — save and inspect program outputs

This module formats existing results and saves CSV files. It does not calculate
new metrics, run power flow, advance battery SOC or repeat optimization. Graphs
and the user interface are intentionally outside this first implementation.

## Run from the repository root

Open PowerShell in `EE499-Team16`. For a synthetic simulation export:

```powershell
python .\07_Implementation\examples\run_simulation.py --cost-per-kwh 2 --cost-per-kw 3 --pv-rating-kw 1200 --grid-import-limit-kw 400 --grid-export-limit-kw 0 --output-dir .\07_Implementation\Results\simulation_run_01
```

This creates `baseline` and `with_bess` subfolders. The cost coefficients,
PV rating and supply/export caps above are **demonstration inputs**, not verified
project values. The same profiles and network settings are used for both runs.
No output files are created if you omit `--output-dir`.

For deterministic GWO and an optional exhaustive reference:

```powershell
python .\07_Implementation\examples\run_optimization.py --cost-per-kwh 2 --cost-per-kw 3 --compare-exhaustive --output-dir .\07_Implementation\Results\optimization_run_01
```

This creates `baseline`, `gwo`, and `exhaustive` subfolders. The baseline has
hourly traces; the optimizers retain candidate metrics and convergence history,
not full hourly traces for every candidate.

For scenario-based GWO:

```powershell
python .\07_Implementation\examples\run_uncertainty.py --optimize --cost-per-kwh 2 --cost-per-kw 3 --output-dir .\07_Implementation\Results\scenario_run_01
```

This adds per-scenario evaluation rows. The uncertainty example requires
`--optimize` with `--output-dir`: it exports evaluated results, not all generated
historical/future profile files. It does not yet calculate a scenario no-BESS
comparison. Its mean is an **equal-weight stress-set mean**, not an unbiased
expected real-world cost; the supplied aggregation context and metric notes
retain that distinction.

Run the results tests or the complete suite:

```powershell
python -m unittest discover -s .\07_Implementation\tests -p test_results.py -v
python -m unittest discover -s .\07_Implementation\tests -v
```

Always use a **new output folder name**. Existing directories, even empty ones,
are refused. To repeat the commands, change `run_01` to `run_02`. Existing files
are never deleted or overwritten. Relative output paths are resolved from your
terminal's current directory, so the commands above assume the repository root.

## Files produced

| File | When present | Contents |
|---|---|---|
| `summary.md` | Every successful export | Readable status, existing metrics, optimizer choice/settings and supplied study context |
| `metrics.csv` | Metrics supplied/retained | One row per metric with value and unit, including feasibility and notes |
| `hourly.csv` | Simulation | One row per recorded step: convergence, feasibility, final/trial inputs, grid power, voltage range, BESS state, curtailment, shedding and reserve |
| `buses.csv` | Simulation | One row per bus/hour: P/Q inputs, voltage, controls and violation flag |
| `branches.csv` | Simulation | One row per branch/hour: current, sending P/Q and losses; no thermal constraint is added |
| `evaluations.csv` | Optimization | One row per retained evaluator call: candidate, score, feasibility, available metric components and message |
| `convergence.csv` | Optimization | Best-so-far raw WSM, with axis distinguishing GWO generations from exhaustive candidates |
| `scenario_evaluations.csv` | Scenario evaluations retained | Individual case IDs, candidate scores, metrics and failure messages |
| `comparison.csv` | Baseline metrics explicitly provided | Baseline/candidate values, reduction percentages and both feasibility flags |

Steps, evaluations and convergence use **zero-based indices**. Bus/line IDs
remain the network IDs. Rows have deterministic ordering; the numeric values
are not rounded in CSV. Summaries use compact formatting for readability.
Hourly/bus/branch exports stream rows without constructing a large table first.

CSV is UTF-8 with BOM for Excel, with commas as separators. If Excel does not
split columns automatically, use Data → From Text/CSV and select comma/UTF-8.
Messages containing commas, quotes or newlines are quoted by the CSV writer.
Formula-like text cells are prefixed with an apostrophe for spreadsheet safety;
actual numeric values, including negative charging/export power, are unchanged.

## How values and failures are represented

- Blank means **unavailable or not applicable**, never an assumed zero. A
  no-battery simulation has blank BESS state fields. Known zero controls remain
  numeric zero. Legacy controls without records remain blank.
- `inf` is preserved for rejected objectives/no feasible optimizer solution.
  It is not replaced by zero or disguised as a valid finite score.
- A completed simulation can still be infeasible. Feasibility also does not
  imply all demand was served: inspect shedding separately.
- A failed FBS row has `diagnostic_only=True`. Its power/voltage values are
  diagnostic iterates and its injections are attempted inputs, not verified
  operation. `bess_trial_power_kw` is the attempted BESS step; accepted SOC and
  energy are exported separately and do not advance on a failed step.
- For converged rows, `load_input_kw` is served load and `pv_input_kw` is used
  PV. Original demand/available-PV totals are retained in metrics when known.
- Metrics cannot be attached to an incomplete/non-converged run. Completed,
  converged but infeasible runs may retain their metrics, labelled infeasible.
- A rejected scenario candidate may stop at its first failed case. Only cases
  actually retained by the evaluator are exported; missing cases are not
  silently counted as successful or zero-cost.

`summary.md` is published last, using a temporary write then rename. If an I/O
error occurs, the exception is returned to the caller and partial files remain
for inspection. Without the final summary, do not treat the export as complete.
There is no automatic deletion or retry over an existing run directory.

## Inputs to fill or change

| Input | What you provide |
|---|---|
| `result` | The object returned by simulation/optimization, or a `PerformanceMetrics` object |
| `output_path` / `--output-dir` | A new directory for this run |
| `metrics` | Optional, for a simulation only: the metrics calculated from that same run and BESS configuration |
| `baseline_metrics` | Optional: no-BESS/reference metrics using the same study inputs and aggregation basis |
| `context` | Optional text-to-text mapping documenting case/data source, model/settings, dispatch, economics, seeds and assumptions |

You do **not** fill in curtailment, shedding, SOC or voltage in `results.py`.
These must already come from the simulation and metrics modules. Change the
study inputs there; exporting does not repair a wrong simulation or fill in
missing prices. See the simulation/metrics/optimizer/uncertainty READMEs.

Example in a driver that already imports the `src` package:

```python
from src.results import export_results, format_summary

# simulation_result, metrics and baseline_metrics were calculated earlier.
files = export_results(
    simulation_result,
    "Results/my_new_run",
    metrics=metrics,
    baseline_metrics=baseline_metrics,
    context={"study": "Describe the actual network/data and assumptions here"},
)
print(files["summary.md"])
print(format_summary(simulation_result, metrics=metrics))

# Optimization already retains its own metrics; do not pass metrics= again.
# files = export_results(optimization_result, "Results/my_new_optimization")
```

The export function returns a dictionary mapping filenames to absolute `Path`
objects, so a future interface can link to the files without guessing paths.
`format_summary()` returns text and performs no filesystem writes.

## Baseline comparison and remaining limits

Comparison uses the existing `percentage_reduction()` from `metrics.py`:
`100 * (baseline-candidate) / baseline`. Negative means the quantity increased;
that is not automatically undesirable for every metric (for example exports).
Zero versus zero gives zero percent; zero versus a nonzero candidate gives
blank because percentage reduction is undefined. Unknown inputs also stay blank.

Duration and currency must match. **These checks cannot prove comparability.**
The caller must use the same network, profiles/scenarios, control settings and
aggregation method. A single sunny-day result must not be compared with a
45-scenario mean just because the number of hours happens to match. Both
feasibility flags remain visible even if one case performs worse.

The optimizer deliberately retains metrics rather than every hourly trace.
If you need the selected battery's trace, explicitly simulate it again with
the same profile, initial SOC and policy/settings, then export that simulation.
For scenarios, label and export each replayed case separately. `results.py`
does not initiate these replays or invent an aggregate hourly SOC trajectory.

Plots, XLSX/PDF reports, full profile/model serialization and automatic capture
of every engineering input are not included. Drivers must supply honest study
context. Real-data and statistical validation remain separate from testing
that CSV values faithfully match the supplied program outputs.
