# EE499 Academic Engineering Dashboard release record

24 November 2026 · Windows x64 · EE499-Team16

The active source is `07_Implementation/src`. This release uses the existing working tree on `main`, which was ahead of `origin/main` at inspection. The baseline was copied from the working tree because it contained updates beyond commit `fdcbfaaf9`. All existing edits and archives were retained. No commit or push was made.

## Acceptance matrix

Open the named section, then use **Engineering view** for the applicable presets. The existing chart editor remains available through **Show chart controls → Layout → Add chart**. The report distinguishes retained data, observed coverage and quantities that are unavailable.

| Decision | Placement, evidence and checks | Remaining limits |
|---|---|---|
| Q1 Bus voltage and angle | Network opens with a numerically ordered bus snapshot. Selected-hour and worst-hour criteria, common-hour scenario overlays, time-weighted bus statistics and recorded phase angles use indexed voltage rows. Static fixture checked bus order 1, 2, 10 and exact exported values. | Statistics give the maximum timestamp and retained hours per bus. Angle statistics over a period are available through the existing circular aggregation editor. |
| Q2 Voltage through time | Network envelope, critical buses, independent scenario overlays, retained pre-control voltages, violation hours and elapsed-duration curves. Uses archived system extrema, bus IDs, bus rows and configured limits. Tested on the paired simulation. | Detailed hours use a strict archived-bound check. The controller’s tolerance-based outcomes remain in the saved decision and health records. Duration curves use system minima/maxima. |
| Q3 Feeder and electrical inspection | Reuses the schematic, selected-element inspector and Overall Health. Added single-line equipment labels, electrical overlays, expandable bus/branch snapshot tables and actual slack-to-bus paths. The path test follows 1 → 10 → 2 while the voltage plot follows 1, 2, 10. | The existing Overall Health view covers the full archived study. Path-specific span and snapshot tables are available in their presets. |
| Q4 Demand and seasons | Inputs & Forecasting has chronological category demand and calendar energy, typical weekday/weekend profiles, monthly peaks, requested/served durations and weighted consumption statistics. Reuses archived assignment and custom category/bus/system series selectors. Tested duration weighting, zero and missing data on fixtures. | Typical-day grouping uses the recorded civil calendar and offers month filtering. Tariff proxy is labelled as an estimate. |
| Q5 Forecasting | Inputs & Forecasting uses retained actual/forecast matches, chronological errors, scope metrics, daily peak/energy errors, scatter and residual distributions. Compare Studies offers historical/forecast planning records. Tested score calculations with zero-denominator cases and historical-only unavailability. | Selected-window MASE and horizon/interval diagnostics require training scales, issuance or bounds that the new view does not reconstruct. Saved full-holdout scores are shown where present. |
| Q6 PV | System Operation provides available versus utilized power, curtailment, monthly utilization, installation-bus tables and linked irradiance/operating traces. Uses archived PV buses and excludes the preset when PV is absent. | Reason attribution depends on the saved control ledger. No renewable-origin allocation to BESS charging. |
| Q7 AC/Q balance | System Operation has separate signed active/reactive balances, integrated energy-flow Sankey, original residuals, import/export energy and peaks. The paired fixture rendered the energy flow offline. | Reported residuals may include numerical discrepancy. Where no separate balance tolerance is recorded, the table reports residual magnitudes without a pass/fail threshold. |
| Q8 Losses | Network has separate active/reactive series, monthly integrated quantities, branch snapshot/period selection, normalized ratios and branch/system reconciliation. BESS has inventory-adjusted conversion loss. Tested branch reading and exports without new power-flow calls. | Branch fault and loss coverage vary by archive. Unrated loading remains unavailable. |
| Q9 Service and shedding | System Operation opens with requested/served/shed and matched ENS. Spatial severity and service tables report nested thresholds, full disconnection and contiguous observed events. Reuses recorded corrective action inspection. | Interrupted or missing data split observed events. No customer-level reliability indices were derived. |
| Q10 BESS dispatch and SOC | BESS opens with signed gross dispatch and capacity-weighted SOC when rated capacities are retained. Presets cover per-unit Q, P–Q operation, daily closure, intraday range and strict observed limits. Two-unit manual fixture exercised. | Strict audit reports roundoff excursions. The saved restoration audit supplies tolerance-based results. Scheduled-versus-executed records are available only where captured. |
| Q11 Utilization | BESS has rated/peak dispatch, nameplate/usable/observed energy, duration, equivalent cycles and operation tables. Compare Studies and Optimization expose recorded study/candidate sizing points. | Near-rating threshold is explicitly 90%. No unrun sizing points, degradation or lifetime were calculated. |
| Q12 Economics | Verified annual ledger and signed benefit waterfall, monthly operating ledger, per-unit CAPEX, CRF assumptions and fixed-dispatch accounting sensitivity. Short runs open on recorded period costs. | Import sensitivity needs a verified zero inventory tariff exposure. Break-even, payback and trial reoptimization are outside the delivered accounting view. |
| Q13 GA | Optimization shows verified fleet, saved annual checks, convergence, settings, recorded membership, time/cache accounting, screen cost/ENS trade-offs and representative days. Fixed-seed regression checked the actual parallel evaluator. | Archives predating the sidecar lack generation membership. Optional detail records parents, post-crossover tuples and actual repaired offspring. Per-day cost components and individual repair steps were not archived. |
| Q14 Case studies | Compare Studies accepts saved HTML or the stored dashboard entry of a portable ZIP. Arbitrary reference/candidate, engineering metrics, deltas, A–D case classification, normalized ratios, sensitivity rows and compatibility evidence use saved records. Existing chart comparisons retain overlay, side-by-side and difference. | A–D is a classification of imported evidence. Separate controlled/uncontrolled and matched realized forecast studies are required to make the corresponding causal comparisons. |
| Q15 Reporting | Numerical Summary lands first. Engineering views render on demand. Preserved pinning/layouts, independent chart controls and offline viewer. Publication export supports SVG, 300/600 dpi PNG, vector PDF, full-precision CSV, XLSX and LaTeX. Active-view academic ZIP includes selected outputs, index and manifest. | SVG preserves Unicode throughout. The vector PDF uses standard Helvetica and transliterates some symbols. Academic ZIP uses the active view’s available figures/tables. The separate portable report carries canonical CSV/JSON. |

## Backend preservation

- `fleet_ga_optimizer.py` instantiates optional passive observations, records actual generation/cached ranks and, in detail mode, records parent and resulting child references. All IDs follow observed cache insertions. Worker calls, random draws, ordering, evaluations and stop conditions are unchanged.
- `sequential_multi.py` passes the observations as optional result metadata. `dashboard.py` writes a versioned `ga_diagnostics.json` sidecar and embeds it as a lazy block. `results.py` omits the raw trace from the prose summary.
- FBS Numba, MILP, forecasts, corrective controls, economic objective and numerical parameters were preserved. The new voltage mean, service rate, reactive loss integration and publication figures use saved results only.
- `EE499_GA_DIAGNOSTICS=off` disables observations. Normal mode is `summary`. Set `EE499_GA_DIAGNOSTICS=detail` before starting the tool to include recorded crossover/offspring transitions. This setting affects diagnostic retention only.

## Source regression and archived cases

- `python -m pytest -q --disable-warnings tests` in `07_Implementation` passed **261 tests and 75 subtests**. The previous tree also passed its application suite once the referenced network and weather fixtures were present in the snapshot. A recursive validation-tree collection attempt encountered existing duplicate benchmark module names.
- `node --test 07_Implementation/tests/*.cjs` passed **29 tests**. New cases check numerical bus order against true feeder path, interval weighting, forecast denominators, inventory-aware battery losses, vector output, and saved ZIP reading.
- Fixed-seed candidate ranking, objective, feasibility, generations/cache counts and stopping reason matched exactly for the previous tree, passive summary, capture off, and detail. Serial detail matched with the expected worker setting difference. Seventeen canonical result files matched byte-for-byte for static FBS, controlled/uncontrolled simulation and multi-unit manual dispatch.
- The short GA fixture evaluated 12 unique candidates in three generations. Single timed observations were 5.51 s previous, 4.19 s summary, 6.74 s capture off, 5.40 s detail, and 1.48 s serial detail. Those are mixed-load runs and do not isolate overhead. Summary/detail JSON was 6,151/7,008 bytes, including 13 detailed transitions. Peak memory was not measured.
- Real IEEE 33-bus and 15-bus annual archives each contained 8,760 hourly steps. They were regenerated from copied/hard-linked read-only canonical inputs. IEEE33 HTML was 174,694,953 → 174,959,221 bytes and took 156.7 s to regenerate. The 15-bus HTML was 29,779,120 → 44,590,852 bytes and took 42.0 s. The older 15-bus report used an earlier viewer/schema, so this file-size difference includes intervening dashboard features. Web rendering inflates selected report blocks on demand.

## Windows build and launch

Extract the complete portable ZIP to a writable folder and double-click `BESS_Planning_Tool.exe`. Keep the accompanying `_internal` directory beside it. The existing application name and icon are preserved. The portable application is unsigned. A separate clean Windows machine was not available.

Build from the repository root with the existing packaging spec and Windows application dependencies. The earlier packaging virtual environment provides PyInstaller 6.22.3 but is missing the current forecasting dependencies, so it is appended to the validated application interpreter’s import path only for the build.

```powershell
$env:EE499_BUNDLER = (Resolve-Path .venv-exe/Lib/site-packages).Path
python -c "import os,sys; sys.path.append(os.environ['EE499_BUNDLER']); from PyInstaller.__main__ import run; run()" --noconfirm --clean --distpath dist/ee499-academic-windows-x64 --workpath dist/ee499-academic-work/pyinstaller 07_Implementation/Packaging/BESS_Planning_Tool.spec
```

The portable verification command is `BESS_Planning_Tool.exe --check-academic-release "<writable smoke output>"`. It runs the small real FBS, dispatched and two-worker GA fixture, then opens saved results in offline Qt WebEngine and verifies generated files. The controller and optimization methods are the same ones used by normal runs.

## Verified portable executable

- File name: `BESS_Planning_Tool.exe`. Native AMD64 Windows PE, 35,179,421 bytes.
- SHA-256: `7746c86b42d619df1df47dee0e0299982d99a47725b71a126f882e889f1381db`.
- Native smoke checks passed from a relocated installation path with spaces. The executable loaded a real Excel workbook and prepared input directory, ran static FBS, 24-hour controlled/uncontrolled studies, two-unit dispatch and the fixed-seed GA with two workers. All 17 canonical result hashes and all deterministic GA fields matched the previous source.
- The same executable opened the three results in Qt WebEngine and exported verified SVG, PNG, vector PDF, CSV, XLSX, LaTeX and the academic ZIP. No external requests were observed. The automated WebEngine checks used offscreen/software rendering in this Windows session.
- The archived IEEE 33-bus annual dashboard opened in 1.88 s in a single Qt file-load check. The preset sweep exercised feeder, losses, service, BESS, costs and comparison. A separate 336-hour slice of archived forecast/PV results rendered held-out accuracy and PV presets offline. Original archives were preserved.
- Package: `BESS_Planning_Tool_Academic_Dashboard_Windows_x64_Portable.zip`. Build environment: Windows, Python 3.14.7, PyInstaller 6.22.3. Key versions: PySide6 6.12.0, numba 0.68.1, llvmlite 0.50.0, numpy 2.5.2, scipy 1.18.1, pandas 2.3.3, scikit-learn 1.9.0, lightgbm 4.7.0, xgboost 3.4.1.

## Additional measurement and boundaries

Single-worker measurements in fresh Python processes recorded 1.242 s with capture off, 1.285 s with the default summary, and 1.148 s with detail. Whole-process peak working sets were 210,669,568, 210,554,880, and 210,870,272 bytes respectively. Those measurements include interpreter and library memory. They do not isolate diagnostic-only allocation or characterize full-year runtime.

The release does not include an independent clean-machine or 8,784-hour archive test. The leap-day fixture exercises calendar grouping. Scenario metrics, raw category assignments and historic clock context are restricted to the evidence saved in the archive. Comparative event drill-down uses existing chart and decision views. Several specialist options are partial: worst-hour pairs use a shared timestamp, feeder health is full-study, the voltage duration preset uses system rather than bus curves, and the publication batch is scoped to the active view.

The files fbs.py, daily_milp_dispatch.py, multi_bess.py, network_control.py, joint_opf.py, forecasting.py, forecast_models.py, metrics.py, optimizer.py and representative_days.py matched the pre-edit snapshot by SHA-256.

Portable ZIP integrity test passed. Size: 440749365 bytes. SHA-256: `8847cc9caff251a152e009bdf20cdef2f66834c8bb9e99274845fe325138b365`.
