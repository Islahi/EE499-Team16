# `results.py` — save and inspect program outputs

This module formats existing results and saves CSV files. It does not calculate
new metrics, run power flow, advance battery SOC or repeat optimization. The
saved HTML dashboard reads these canonical exports and the archived inputs.

## Open and use the dashboard

Completed simulation and optimization runs generate a self-contained
`dashboard.html` asynchronously and open it in the default browser. The
**Dashboard** menu opens the latest report in the app, opens an archived run,
regenerates HTML, or exports a portable ZIP. The **Base Case** still represents
one static workbook operating point.

- **Summary** opens first and includes study coverage, available KPIs, matched
  No-BESS and With-BESS bars, and a responsive chart grid. Use **Focus** to expand a
  chart and **Engineering** to see its series editor and a sample of the data.
  Topic tabs offer related presets. **Detailed views** retains the existing
  charts, heatmaps, raw control ledger and saved-report comparison.
- **Edit** changes the series, axis, line or bar style, color, scenario and
  time/element linking. Search **Add series** for measurements. To build a
  composite, add requested load, shedding and grid import. Use bars for
  shedding and lines for the other two. A separate axis is needed for an
  unrelated unit. Stacking is available for compatible additive bars, such
  as served and shed load in the same scenario at the same entity.
- **Sync** controls time and feeder selection independently. The global
  period supports 24 hours, 7 days, 14 days, a calendar month or year, full
  history and a custom range. **Show chart controls** reveals the grouped
  study, time, resolution and layout settings. The controls can be hidden
  without changing their values. Drag across a chart to zoom and use
  **Zoom / export** to pan or reset. Use the arrow keys on a chart to move
  across samples and Enter to inspect the selected reading.
- **Network** switches between the exact selected-hour Snapshot and **Overall
  Health (full study)**. Select a bus or line to inspect either view. A time-series point opens
  **Point details** with the exact timestamp, archived quantities and control
  evidence for that hour. A daily or monthly point shows its recorded interval.
  Use **Inspect recorded hour** to open an individual timestamp. Source
  evidence is available through the filtered **Exact CSV** and **Exact JSON**.
- Use **More → Pin to My Dashboard** to combine charts from different topics.
  Reorder with **Move earlier / later** or drag pinned cards. Change size in
  **Edit**. The layout is stored per report when the viewer allows local
  storage. **Layouts** exports/imports a versioned JSON layout or a reusable
  template. The embedded Qt viewer uses a private profile. Export a layout to
  keep it after the window closes. External reference reports must be reopened
  after a reload.
- **Compare Runs** opens other local HTML reports without changing them. In
  **Edit**, choose the reference scenario or report and **Overlay**,
  **Side by side**, or **Difference**. Difference is candidate minus reference
  and compares recorded matching timestamps. Different clocks, sample
  durations and currencies are flagged. Partial overlaps show matched counts.

### Metric and display conventions

| Measure | Interpretation |
| --- | --- |
| Original requested P / Q | Imported active demand in kW and reactive demand in kvar at the recorded hour. Workbook base curves are shown separately where recorded. |
| Served and shed demand | Served demand after correction and the reduction allocated to load shedding. The corresponding interval energy is in kWh. |
| PV nameplate, available and delivered | Installed rating, hourly available active power, and actual injection after curtailment. Irradiance is shown only when its source was archived. |
| Voltage and branch loading | Voltage magnitude in pu, voltage angle in degrees, current/rating in A, line power in kW or kvar, and loading as a percent of recorded rating. |
| BESS state and power | SOC percentages and fractions are labeled separately. BESS P, Q and S use kW, kvar and kVA. |
| Cost and energy | Annual cost components use the recorded currency per year. Partial runs carry hourly costs only where recorded. Use **Integrate power to energy** to multiply recorded kW/kvar by the saved sample duration before totaling. |
| Correction evidence | Before, after BESS and final values are distinct observations. A missing record, a resolved constraint and a non-unique cause are reported separately. |

### Time resolution

**Period** selects the dates. **Resolution** groups records within those dates.
The global and per-chart resolution options are Auto, Hourly, Daily, Weekly,
Monthly and Yearly. Auto uses recorded samples up to 336 points, daily buckets
up to 9,000 points, and then monthly buckets. Hourly displays the recorded
steps at their saved spacing. Weekly buckets start on Monday. Calendar buckets
follow the dates in the recorded study clock. Missing or offset-ambiguous
timestamps are kept in their recorded form, and coverage is reported.

| Quantity | Bucket behavior |
| --- | --- |
| kW, kvar, W/m² | Time-weighted mean when durations are available. A sample mean is labeled if duration is unavailable. Minimum and maximum are available. Select integrated energy for kW or kvar to get kWh or kvarh. |
| kWh, kvarh, recorded interval cost | Sum the recorded interval values. A sum or integral with an internal missing sample stays unavailable. Annual cost metadata is only shown as a genuine annual comparison. |
| SOC and other state or ratio | Mean, minimum, maximum or final recorded value. |
| Voltage magnitude and angle | Feeder minima use the bucket minimum and maxima the bucket maximum. Default bus voltage buckets show minimum/mean/maximum, with violation counts in the detail drawer. Angles use circular means. |
| Constraint flags | Count the affected recorded samples. Feeder health also reports valid hours and affected hours when durations are recorded. |

Partial calendar buckets show the actual retained timestamps. The original
hourly readings remain available in the canonical CSV exports.

### Overall feeder health

Overall Health uses the full archived interval for each scenario, regardless
of the visible chart period. The report includes valid and attempted
coverage, bus voltage extrema and limits, hour counts, available
shedding/curtailment subtotals, and branch currents, ratings and recorded
energy losses. Uncontrolled and archived before-correction evidence have
separate selectors when present. Branch colors always refer to final current
and a recorded rating.

Color indicates **no recorded violations** for complete valid coverage,
**some violations** below 5% of checked coverage, or **frequent violations**
at 5% or more. Missing assessments and unrated lines are gray. An orange
dashed bus outline identifies recorded uncontrolled stress on a bus that
meets the final limits. Dates, denominators, and unavailable metrics are
shown in the inspector. Regenerate older self-contained HTML from its saved
run folder to use this view when the necessary electrical rows were archived.

Dashboard measurements show up to three decimal places. `≈0` and `≈−0`
identify small nonzero readings. The point and chart exports, comparisons,
feasibility checks and saved numerical sources use the recorded precision.
Daily/monthly summation and energy integration leave gaps when part of an
observed bucket is missing. The bucket lists its retained interval. A partial
bucket represents that retained interval.

### Offline formulas and exports

**Information → Equations** in the desktop app and **Model & Assumptions** in
the offline report share versioned equation records. Matplotlib MathText
typesets the supported LaTeX expressions with its bundled STIX fonts and embeds
the resulting PNGs. Qt displays those images in its existing text widget.
MathText and STIX use their respective distributed licenses in the Matplotlib
package. If rendering is unavailable, the reference shows readable equation
text. Unrecognized archived formulas retain their original wording with an
archive label.

**Information → Parameters** shows the source identity, relevant recorded
properties, and hash previews. **View full provenance** opens a read-only
Qt window with exact paths and hashes. The browser report offers the same
data under **Source files & integrity**. Long readings such as eligible-bus
lists or candidate details stay available behind their compact table previews.

Use **Export → PNG / Exact CSV** on a chart, **Save offline HTML copy** in the
desktop menu, and **Print / PDF** for the current view. PDF uses the browser
or Qt print pipeline. To include the exported
layout, PNGs or PDF with the original numerical data, use **Export portable ZIP
with layout or charts** in the desktop menu and select the pre-exported files.
There are no external script, font or stylesheet requests.

From `07_Implementation`, regenerate or package a copied saved run:

```powershell
py -3.14 -m src.dashboard "<saved run folder>"
py -3.14 -m src.dashboard "<saved run folder>" --zip "<portable.zip>" --include "<layout.json>" "<chart.png>"
```

### Smoke tests

Open a 24-hour 33-bus dashboard offline and check the first **Summary** page.
Switch Grid, Focus, Engineering and back. In Network select Bus 6 and verify
the linked angle chart and exact values in the drawer. Inspect a shedding spike
and compare the action and constraint records with `control_decisions.jsonl`.
Create a line/bar composite with grid import, unlink its date window, and
verify that the global period only changes linked plots. Pin three charts with
different sizes, export the layout, reopen the report and import it. Compare
the 1.00 and 1.05 pu reports over their first 24 common hours, and switch all
three comparison modes. Export a chart and compare CSV values to the original
unrounded readings. Check Print/PDF and the ZIP's original data and optional
exports. In the desktop Information dialog, switch between current and
archived equations and check that the recorded formula context follows.

### Five-step walkthrough

1. Open the saved dashboard and read **Summary**. Compare the two bars for
   each available metric and check the preserved coverage dates.
2. Choose **Show chart controls**. Set a seven-day period and switch between
   Hourly, Daily and Weekly. Use **Edit** to override just one chart.
3. Open **Network** and switch from **Snapshot** to **Overall Health**. Select
   a bus or line to see the entire study's coverage and electrical evidence.
4. Pin a chart to **My Dashboard** and export the layout and the exact CSV.
   Reopen the report and try the layout import where browser storage is unavailable.
5. Open **Information → Parameters** on desktop or **Model & Assumptions** in
   the HTML. Confirm the PV source is compact, then open the full provenance
   to inspect or copy its original values.

```powershell
.\test_windows.bat -q --disable-warnings
node --test tests/test_dashboard_blocks.cjs tests/test_dashboard_workspace.cjs
py -3.14 tests/dashboard_webengine_smoke.py "<24-hour dashboard.html>" --pdf "<test.pdf>"
```

The WebEngine smoke test runs the small report in memory with nonlocal
requests blocked. Run it in a regular Windows desktop session if WebEngine
cannot initialize in a managed test environment.

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
