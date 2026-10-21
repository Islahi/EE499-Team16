# How the program was built — chronological explanation

This is **not a progress report or presentation draft**. It is a dated explanation of what changed in the software, why, which tools/libraries were used, and what each calculation does. Use it as source material when writing your own report. Dates below follow the [project journal](../../../PROJECT_JOURNAL.md) and Git history; they are not guessed from file modification times. The current runnable application is `07_Implementation/src_accelerated/`. Its modules are explained individually in [SCRIPT_REFERENCE.md](SCRIPT_REFERENCE.md).

The initial work was developed in `07_Implementation/src/`. On **19 October**, it was copied into `src_accelerated` and extended; the copy's first Git commit must **not** be read as the date on which all of its algorithms were first written. The two folders are now separate versions. `src_accelerated` is the current final working version for this discussion.

## 29-09-2026 — Hourly profile-reading library

**What was built:** `data_loader.py` reads load and PV CSV files in long form: `timestamp,bus_id,p_kw,q_kvar`. It checks duplicate `(timestamp,bus_id)` rows, matching load/PV time sets and consecutive hourly timestamps. `ProfileData` stores a list of values for each bus; `profile_at()` returns one hourly slice.

**Why:** FBS needs one operating point at a time, while the available demand/PV data are time series. This file supplies the bridge from CSV to timestamped dictionaries. It is **not** the whole simulation and does not decide battery operation.

**Tools/libraries:** Python `pathlib`/`datetime` and `pandas` for CSV tables and timestamps. Git milestone `79aaad8`. The original library was preserved while later modules were connected to it.

## 06-10-2026 — Network objects and one-step feeder calculation

**What was built:** `network_model.py` defines buses, lines, loads, PV units and a `NetworkModel`. It enforces one slack bus, valid references, connected topology and a radial tree. `network_cases.py` provides guide 3-bus/5-bus examples and a separate unloaded 11-kV five-bus chain. `fbs.py` implements one balanced Forward/Backward Sweep (FBS) power-flow solution; `main.py` prints a guide-case result. The current guide 5-bus case is **not** the meshed PJM 5-bus workbook.

**Why:** The battery and optimizer cannot be evaluated without knowing voltage, currents, grid power and losses for a specified feeder loading. Radial ordering gives each non-slack bus exactly one parent line so backward current accumulation and forward voltage updates are well-defined.

**Core calculation:** With three-phase base power and line-line base voltage,

$$Z_{\mathrm{base}}=\frac{V_{\mathrm{base}}^2}{S_{\mathrm{base}}},\qquad
I_{\mathrm{base}}=\frac{S_{\mathrm{base}}}{\sqrt{3}V_{\mathrm{base}}},\qquad
S_{i,\mathrm{net}}=(P_{L,i}-P_{PV,i}-P_{B,i})+j(Q_{L,i}-Q_{PV,i}-Q_{B,i}).$$

The solver starts at the slack voltage, computes bus demand current, sums currents from leaves toward the slack, then computes voltages from the slack toward the leaves:

$$I_i=\left(\frac{S_{i,\mathrm{net}}}{V_i}\right)^*,\qquad
I_{p\to i}=I_i+\sum_{k\in\mathrm{children}(i)}I_{i\to k},\qquad
V_i=V_p-Z_{p\to i}I_{p\to i}.$$

It repeats until $\max_i|V_i^{(n+1)}-V_i^{(n)}|\le\varepsilon$ or the iteration cap is reached. Branch complex loss is $S_{\mathrm{loss},\ell}=|I_\ell|^2Z_\ell$. **Convergence** means the equations settled numerically; it does not mean every bus is within the allowed voltage range.

**Tools/libraries:** Python `dataclasses`, `cmath`, `math`; initially the core solver required no heavy numerical package. Git milestones `60469a0` and `f840089`. The journal records 12 unit tests and a separate SciPy nonlinear nodal-equation verification on guide cases; that was implementation verification, not final field validation.

## 08-10-2026 — Battery state and physical power clipping

**What was built:** `bess.py` defines `BESSConfig`, `BESSState` and `step_bess()`. It accepts a *requested* signed kW, limits it by rated/charge/discharge kW and remaining usable energy, and returns actual kW plus updated energy/SOC. Positive BESS power means **discharge to the feeder**; negative means charging.

**Why:** A dispatch request cannot be assumed deliverable. Without these limits an optimizer could invent discharge after the battery reaches minimum SOC or charge above maximum SOC.

$$E_{t+1}=E_t-\frac{P_t\Delta t}{\eta_{\mathrm{dis}}}\quad(P_t>0),\qquad
E_{t+1}=E_t-P_t\Delta t\eta_{\mathrm{ch}}\quad(P_t<0),\qquad
SOC_{t+1}=\frac{E_{t+1}}{E_{\mathrm{rated}}}.$$

For discharge, the SOC-limited maximum is $\max(0,(E_t-SOC_{\min}E_{\mathrm{rated}})\eta_{\mathrm{dis}}/\Delta t)$; charging has the analogous upper-energy limit. This is a generic battery model, not a Li-ion or Li-polymer supplier model.

**Tools/libraries:** Plain Python. Git milestone `92c08f8`. This step did not yet choose *when* to charge or discharge.

## 15-10-2026 — First hourly simulation

**What was built:** `simulation.py` connected `ProfileData`, `step_bess()` and `run_fbs()`. It processes timestamps in order, constructs a complete bus operating point, applies an optional dispatch callback, advances SOC only after a converged power flow, and stores per-hour results. Configurable voltage bounds and an explicit reserve rule were added.

**Why:** One static FBS solve cannot describe an hour-by-hour PV/load pattern or battery energy carry-over. The simulation needed separate states for “all hours processed,” “power flow converged,” and “operating constraints feasible.” A failed electrical calculation must not silently advance accepted SOC.

The first-version reserve is based on the study's **peak requested hourly load**:

$$P_{\mathrm{reserve}}=r_{\mathrm{reserve}}P_{L,\mathrm{peak}},\qquad
E_{\mathrm{reserve}}=\frac{P_{\mathrm{reserve}}T_{\mathrm{reserve}}}{\eta_{\mathrm{dis}}}.$$

The default $r_{\mathrm{reserve}}=0.10$ and $T_{\mathrm{reserve}}=1\,\mathrm{h}$ are configurable planning choices. The nominal voltage feasibility rule defaults to $0.95\le|V_i|\le1.05\,\mathrm{pu}$; it is separate from FBS numerical tolerance. No line thermal constraint was added.

**Tools/libraries:** Python `dataclasses`, existing project modules and the standard library. The journal records integration tests and 24-hour/2,160-hour synthetic example runs. Those runs are not evidence from a measured feeder.

## 17-10-2026 — Metrics and simple cost model

**What was built:** `metrics.py` aggregates completed simulation steps into served load/PV energy, grid import/export, losses, voltage/reserve violation duration, battery charge/discharge throughput and SOC extrema. `EconomicConfig` holds only two cost coefficients. Missing cost input remains unavailable, not zero.

**Why:** The optimizer needs comparable quantities derived from **actual simulated operation**. Keeping metrics separate from the simulation prevents calculation of reports from changing electrical state.

For one-hour steps (the code still writes the general $\Delta t$),

$$E_X=\sum_t P_{X,t}\Delta t,\qquad
E_{\mathrm{import}}=\sum_t\max(P_{\mathrm{slack},t},0)\Delta t,\qquad
E_{\mathrm{export}}=\sum_t\max(-P_{\mathrm{slack},t},0)\Delta t.$$

The simplified BESS investment expression is

$$C_{\mathrm{BESS}}=c_EE_{\mathrm{rated}}+c_PP_{\mathrm{rated}},$$

where $c_E$ is cost per kWh and $c_P$ is cost per kW. The user/team must supply actual values; tariffs, degradation, replacement, discounting and O&M are not included.

**Tools/libraries:** Python `dataclasses`, existing simulation objects. The journal records hand-calculated metric tests.

## 17-10-2026 — Curtailment and shedding became real control actions

**What changed:** Instead of treating curtailed PV and shed load as numbers entered after simulation, `simulation.py` now applies proportional reductions to the operating point and re-runs FBS. Overvoltage/excess grid export can trigger PV curtailment; undervoltage/excess import can trigger shedding. If the requested BESS action worsens a limit, it can first be paused. `metrics.py` integrates the **recorded** actions.

**Why:** A weighted objective cannot legitimately penalize curtailment/shedding unless the electrical simulator actually used those reduced P/Q values. The change also makes a crucial distinction visible: a feeder may become voltage-feasible **because some requested demand was not served**.

For reduction fraction $r$, the control uses

$$P'=P(1-r),\qquad Q'=Q(1-r),\qquad
P_{\mathrm{curtailed/shed}}=P-P'.$$

A bounded bisection search tests FBS at trial $r$ values until it finds an allowable reduction. P and Q are reduced together to preserve power factor. This is a simple ordered proportional controller, **not** optimal load dispatch or priority-based shedding. If full reduction cannot clear the limit, the case stays infeasible.

**Tools/libraries:** Existing FBS/simulation/metrics modules; no new power-flow engine. The journal records regression tests for action accounting and disabled/uncontrollable controls.

## 17-10-2026 — BESS location/size search

**What was built:** `optimizer.py` searches the decision triple $(B,P,E)$: allowed installation bus, discrete power rating and discrete energy capacity. GWO evaluates each candidate by running the existing hourly simulator and metrics. It keeps feasible leaders, caches duplicate evaluations and offers a small-case exhaustive-search reference.

**Why:** The project is a design/planning tool; manual testing of every bus/size combination becomes tedious. A discrete catalog matches the later decision to enter min/max **and a configurable step** instead of claiming continuous or supplier-specific equipment sizes.

The first-version *raw, unnormalized* objective is

$$J(B,P,E)=0.50C_{\mathrm{BESS}}+0.25E_{\mathrm{PV,curtailed}}+0.25E_{\mathrm{load,shed}}.$$

Infeasible candidates receive $J=\infty$. GWO moves catalog-index coordinates toward the three best leaders using the standard coefficient idea $A=2ar_1-a$, $C=2r_2$, $D=|CX_{\mathrm{leader}}-X|$ and $X'=X_{\mathrm{leader}}-AD$; three estimates are averaged, bounded and rounded to actual catalog choices. The seeded search is **heuristic**. Importantly, currency and kWh are mixed in the raw objective, so the apparent 50/25/25 weights do not by themselves define a meaningful relative preference.

**Tools/libraries:** Python `random`, `itertools`, `dataclasses`, existing simulator/metrics. Later accelerated copy added `concurrent.futures.ProcessPoolExecutor` for parallel candidate evaluations. The journal records a small eight-choice GWO/exhaustive match; that is not a global-optimality proof for larger catalogs.

## 18-10-2026 — Load/PV uncertainty and scenario ranking

**What was built:** `uncertainty.py` generates possible future **load and PV power**, not future irradiance. It computes per-bus hourly baseline patterns, fits `statsmodels` ARIMA to normalized residuals, checks a held-out tail against a repeat-last-day benchmark, refits on all history, and draws seeded future residual paths. The default ARIMA order is $(1,0,0)$—technically an **AR(1)** residual model, although the configurable family is ARIMA. If a series has essentially no residual variation it becomes a deterministic hourly pattern. The current `automatic` mode (added later) can instead use residual bootstrap if ARIMA fails to converge or does not improve holdout RMSE; explicit `arima` mode still raises the fit error.

**Why:** One forecast hides variation in demand/PV. Separate generated scenarios allow the *same* BESS candidate to be checked over different future conditions. Fitting/holdout diagnostics are necessary because an optimizer should not treat every generated series as credible simply because the ARIMA function returned values.

For clock hour $h(t)$ and series scale $s$,

$$\bar P_h=\operatorname{mean}\{P_t:h(t)=h\},\qquad
\epsilon_t=\frac{P_t-\bar P_{h(t)}}{s},\qquad
P_t^{(s)}=\operatorname{clip}\!\left(\bar P_{h(t)}+s\epsilon_t^{(s)}\right).$$

Load is clipped to nonnegative; PV is also capped by installed rating and forced to zero at historically dark baseline hours. Reactive power uses the historical hourly ratio $Q_h/P_h$. The holdout errors include $RMSE=\sqrt{\operatorname{mean}[(P_{\mathrm{actual}}-P_{\mathrm{forecast}})^2]}$ and MAPE over nonzero actual samples.

**Scenario selection:** For each case compute positive net-import energy, peak net load, surplus energy and maximum hourly ramp. Each feature is min–max normalized *across the generated set* only for ranking:

$$S_s=0.35N(E_{\mathrm{net},s})+0.30N(P_{\mathrm{peak},s})+0.20N(E_{\mathrm{surplus},s})+0.15N(R_s).$$

The configured low-stress, high-stress and random cases form an equal-weight **stress portfolio**. Its selection deliberately overrepresents extremes; it is not an unbiased probability forecast. The default design described 100 generated and 15+15+15 retained cases, but counts are configurable. A candidate failing one retained case is rejected.

**Tools/libraries:** `numpy`, `pandas`, `statsmodels.tsa.arima.model.ARIMA`, standard-library random/CSV. A seeded NumPy generator makes paths reproducible for the same environment. Cross-bus and load–PV dependence is not calibrated.

## 18-10-2026 — Human-readable results and export

**What was built:** `results.py` formats simulation/optimization summaries and exports `hourly.csv`, `buses.csv`, `branches.csv`, `metrics.csv`, `evaluations.csv`, `convergence.csv` and scenario-evaluation tables when relevant. Optional baseline comparisons use

$$\mathrm{reduction}_{\%}=100\frac{M_{\mathrm{baseline}}-M_{\mathrm{candidate}}}{M_{\mathrm{baseline}}},$$

when the denominator is nonzero and both values exist.

**Why:** A result visible only in memory or a terminal is difficult to inspect and cite. Separating exports from `metrics.py` avoids recomputing physics while writing files. Exports refuse an existing directory, distinguish missing values/diagnostic failed FBS from valid values and write the summary last. A negative reduction can mean an increase; for some metrics (e.g., export) “reduction” is not automatically desirable.

**Tools/libraries:** Python `csv`, `pathlib`, `dataclasses`; UTF-8 CSV output. Exported optimization summaries do not automatically contain an hourly electrical replay of the selected candidate.

## 18-10-2026 — Excel feeder import

**What was built:** `network_loader.py` reads a strict project workbook schema and the supplied IEEE-33 workbook, then creates the same `NetworkModel` used by the solver. It reads literal numeric cells, source bases, bus/line/load/PV records and explicit line status; it rejects unsupported/meshed/generator cases rather than silently converting them into a radial feeder.

**Why:** `data_loader.py` only handles hourly power profiles. A separate script was needed to import the **electrical network**. The PJM 5-bus workbook caused confusion because its five buses are not a radial distribution example: it has looped branches and generator buses. That is a model mismatch, not a missing file extension or a load-profile problem.

**Tools/libraries:** `openpyxl` for `.xlsx` in read-only mode, Python `pathlib`/`zipfile`, existing network classes. Workbook formulas are not evaluated. The journal records 22 import tests and a converged IEEE-33 base-load check with approximately 0.91308 pu minimum voltage: **converged but below the default 0.95 pu limit**.

## 18-10-2026 — Irradiance conversion and synthetic demand

**What was built:** `pv_model.py` accepts prepared, Open-Meteo and NASA POWER hourly irradiance CSV variants. It converts irradiance into PV kW using installed ratings; `load_generator.py` builds an alternative synthetic hourly load when measured load CSV is unavailable. These create prepared profiles consumed by `data_loader.py`; they do not themselves run FBS.

**Why:** Available solar data were irradiance, not electrical PV output. Measured local load could be difficult to obtain, so the project needed an explicitly labeled synthetic fallback. The Sindi co-authored paper supplied hourly mean/SD percentages, not an actual local feeder measurement.

For irradiance $G$, critical threshold $G_c$ and standard threshold $G_{\mathrm{std}}$,

$$P_{PV}(G)=P_{\mathrm{rated}}
\begin{cases}
\dfrac{G}{G_{\mathrm{std}}}\dfrac{G}{G_c},&0\le G<G_c,\\
\dfrac{G}{G_{\mathrm{std}}},&G_c\le G<G_{\mathrm{std}},\\
1,&G\ge G_{\mathrm{std}}.
\end{cases}$$

For hour $h$, one shared sampled percentage $m_t\sim\mathcal N(\mu_h,\sigma_h)$ scales every bus's base load:

$$P_{L,i,t}=P_{L,i}^{\mathrm{base}}\frac{\max(0,m_t)}{100},\qquad
Q_{L,i,t}=Q_{L,i}^{\mathrm{base}}\frac{\max(0,m_t)}{100}.$$

PV uses a shared GHI proxy and unity power factor; no panel tilt, temperature or inverter model is present. Demand has independent hour-to-hour samples, no weekend/seasonal correction and no measured local calibration. The Term 1 report's PV saturation condition was ambiguous, so the code follows its explanatory prose; this was a documented interpretation, not an independently verified source equation.

**Tools/libraries:** `pandas` for provider CSV/timestamps, Python `random` with a documented seed, source paper Table 1. The journal records a Jan–Mar 2024 IEEE-33 synthetic-load/Open-Meteo integration run of 2,184 hours: it converged, but achieved voltage feasibility with about **956,001 kWh shed** out of about **6,024,522 kWh requested** (~15.9%). This is not evidence of fully served demand or validated measured-data performance.

## 18-10-2026 — Qt Designer interface and first desktop application

**What was built:** The user drew the screens in **Qt Designer** (`assets/*.ui`). `ui.py` loads those forms with **PySide6**, connects buttons to handlers and places backend calls in worker threads. `ui_workflow.py` prepares data, converts min/max/step entries into BESS catalogs, runs simulation/optimization and stores a result. `dispatch.py` supplies the user-set net-load-target policy; `network_layout.py` computes automatic radial placement; `network_diagram.py` draws a selectable vector single-line diagram. Load Data, Settings, Network and Results were the initial desktop workflow.

**Why:** The user wanted a local program with an auto-arranged network, not a website or a collection of console scripts. Qt Designer lets the screen layout remain editable. The earlier **Simple-PyQt5-Password-Manager** repository was used as a *structural reference* for named forms/handlers; its code was not copied and the application itself uses **PySide6**, not PyQt5. Background workers are necessary because a long FBS/GWO run would freeze a normal single-threaded GUI.

The net-load-target request is

$$P_{B,\mathrm{request},t}=\sum_iP_{L,i,t}-\sum_iP_{PV,i,t}-P_{\mathrm{target}}.$$

Positive requests discharge, negative requests charge; `bess.py` and network controls determine actual power. The target is a simple policy, not an optimized dispatch. The first UI also used a results text view because the optimizer keeps summary metrics rather than every possible candidate's hourly bus voltages.

**Tools/libraries:** Qt Designer; `PySide6.QtUiTools.QUiLoader`, widgets, `QGraphicsView/QGraphicsScene`, `QThread`/Qt signals; existing Python backend. The journal records an early worker-cleanup native abort that was corrected by retaining worker references until safe GUI-thread cleanup. UI responsiveness is not the same as cancelling a worker.

## 19-10-2026 — Diagram symbols, feeder distinction and accelerated copy

**What changed:** A rejected PJM file was diagnosed as a **meshed 230-kV generator** example, so the loader was not weakened to accept it. The diagram adopted busbars, load take-off arrows, solar-PV, BESS and external-grid vector symbols. The current layout calculates a feeder spine and lateral branches from topology instead of needing PNG pieces for every bus/line. Separate published radial test files were researched for later comparisons.

An accelerated copy under `src_accelerated` was then committed (`8c6ef58`). `accelerated_fbs.py` added array-backed FBS, optional **Numba** JIT CPU sweeps and experimental **CuPy** CUDA sweeps; `optimizer.py` gained optional multi-process CPU candidate evaluation. `progress.py` supplies nested step counters/elapsed formatting. The copy retained the original numerical modules, so an October 19 commit does not mean all modules were first implemented that day.

**Why:** The 33-bus, many-hour, many-candidate case was too slow to treat as a small demo. CPU worker processes can evaluate independent GWO candidates simultaneously; array/JIT backends may reduce one FBS cost. GPU was tried as an option but is hidden from the normal UI because this feeder's sequential backward/forward tree traversal and device transfer overhead did not show a useful speedup in the user's initial timing. “GPU available” is not “GPU faster.”

**Tools/libraries:** `numpy`, optional `numba`, optional CUDA-matched `cupy`, `concurrent.futures.ProcessPoolExecutor`, `perf_counter`; normal UI/engineering code still uses `PySide6` and the same FBS result contract. The user's timing observations are workload-specific and not a controlled benchmark.

## 20-10-2026 — Scenarios became a separate, saveable workflow

**What changed:** `assets/scenario_generator.ui`, `ScenarioGeneratorDialog`, `scenario_store.py` and `study_session.py` were added (`018d0c3`). The user can generate scenarios in their own window, inspect plots/ranking/validation, save **all** generated cases as individual CSVs, and activate only selected cases for optimization. When Load Data is accepted with **OK**, a session folder is created and input network/profile snapshots are saved. The generator's default `automatic` fit mode can fall back to hourly residual bootstrap when ARIMA is unsuitable; exact `arima` mode still reports nonconvergence.

**Why:** Generating scenarios implicitly inside a long optimization made it hard to see whether ARIMA worked or whether PV output existed. Saved CSVs make the inputs inspectable and reusable; a session connects a result to the exact accepted network/profile files and settings. The selected extreme-stress cases are not probability-preserving, so saving every generated case also avoids throwing away inspection evidence.

**Tools/libraries:** PySide6 dialog/plots, `statsmodels`/`numpy` for model generation, `csv`/`json`/`hashlib`/`shutil`/`pathlib` for packages and sessions. Each CSV has scenario ID, timestamp, bus ID, load P/Q and PV P/Q. `validation.csv` and `scenario_ranking.csv` remain even though the visible Validation tab was later removed.

## 20-10-2026 — Static base case, CPU settings and result presentation

**What changed:** A **Static Base Case** action was added (`10024f2`) for a one-step FBS calculation using original workbook base load and installed PV **rated kW** with BESS inactive. The normal Settings window exposes CPU workers/backends, allowed buses and a simple catalog; experimental GPU is not a normal user choice. Session scenario storage was refined so every generated scenario is saved and only the selected set is loaded for optimization. The visible Validation tab was removed but its CSV is retained.

Later (`f047976`), the static result gained bus-voltage and line-flow CSVs and could be shown on the network diagram. Bus/line IDs were placed in property/result text, repetitive base-voltage labels were removed, and session outputs were located under `src_accelerated/Results/`.

**Why:** A one-point result gives a quick electrical check independent of the hourly profile and battery policy. But it is **not** the same as a time-series simulation: it uses installed PV rating, which may not occur at the selected hour. Base-case and hourly results match only when their exact load/PV/BESS P/Q operating points and FBS settings match. IDs make diagram/result values traceable to a particular bus or line.

**Tools/libraries:** Existing `fbs.py`; `pandas` for static CSV files; PySide6 for result layer. No new static battery SOC computation was added—SOC alone cannot determine a kW injection.

## 20-10-2026 — Folder organization and Windows launcher

**What changed:** Module READMEs were moved into `src_accelerated/docs/`, leaving source code at the package top. `app.pyw` was added (`82890a4`) to start the PySide6 program by double-click on Windows and show startup errors without a console.

**Why:** Mixed source/readme files made navigation confusing, and `pythonw`/`.pyw` does not provide a useful terminal traceback by default. This is a launcher, **not** a built Windows executable.

**Tools/libraries:** Python `pathlib`, `sys`, `multiprocessing.freeze_support()`, PySide6 error dialog. Dependencies are declared in `07_Implementation/requirements.txt`, `requirements-ui.txt` and `requirements-accelerated.txt`: `pandas`, `numpy`, `statsmodels`, `openpyxl`, `PySide6`, optional `numba`, and optional CUDA-matched `cupy`. Installing a package does not by itself validate numerical results.

## 21-10-2026 — Documentation audit

The first documentation pass mistakenly organized the chronology as a presentation progress report. This version instead records **what happened at each development step** and identifies the calculations, software tools and important limitations so the team can write its own report. [SCRIPT_REFERENCE.md](SCRIPT_REFERENCE.md) remains the companion file for each current Python module and its inputs/outputs. No physics or application behavior changes merely because these documents were revised.

## Reading the chronology critically

- A tested code path is not the same as independently validated feeder behavior. Solver convergence, voltage feasibility, fully served demand and economic desirability are four different claims.
- The simulated costs are only two user-supplied coefficients. Missing local measured load, PV hardware specifications and supplier prices must be labeled as assumptions/placeholders in a report.
- `src_accelerated` contains an experimental GPU backend but the user's observed CPU advantage is plausible for small sequential FBS solves. Do not claim a universal CPU/GPU ranking from one run.
- Exact dates for some UI fine-tuning between 18 and 20 October are not independently committed one-by-one. This chronology groups them by the journaled or Git-recorded milestone rather than inventing a precise timestamp for each button adjustment.
