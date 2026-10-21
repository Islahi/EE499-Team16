# `src_accelerated` — detailed script and calculation reference

**Current program:** `07_Implementation/src_accelerated/`

**Checked against source:** 21 October 2026

**Dated development explanation:** [DEVELOPMENT_CHRONOLOGY.md](DEVELOPMENT_CHRONOLOGY.md)

This document describes the **implemented Python files**, not an idealized future architecture. The preserved `07_Implementation/src/` copy is not the current accelerated desktop program. Where the code contains a simple assumption or does **not** perform a calculation, that boundary is stated explicitly. Values in a guide case or default config are not a supplier specification.

## 1. How the scripts connect

```text
app.pyw → ui.py → ui_workflow.py
                     ├─ network_loader.py → network_model.py
                     ├─ pv_model.py / load_generator.py / imported CSV
                     │                     ↓
                     │                data_loader.py
                     ├─ static run: fbs.py → accelerated_fbs.py (optional)
                     ├─ hourly run: simulation.py → dispatch.py, bess.py, fbs.py
                     │                         ↓
                     │                     metrics.py → results.py
                     ├─ scenarios: uncertainty.py ↔ scenario_store.py
                     └─ optimization: optimizer.py → simulation.py / metrics.py

ui.py → network_layout.py → network_diagram.py → network_icons.py
ui.py → progress.py (worker counters/log); study_session.py (snapshots/manifests)
```

`network_model.py` defines **static equipment**. `data_loader.py` defines **time-varying power**. `fbs.py` solves **one electrical operating point**. `simulation.py` repeats that solver over time; `metrics.py` only summarizes results; `optimizer.py` repeatedly calls the simulator. This separation matters: changing how data is loaded does not itself change the physics, and the GUI does not implement its own solver.

### Shared units and signs

| Quantity | Unit / convention |
|---|---|
| Network bus base voltage | kV line-to-line, one voltage level per feeder in this version |
| Network power base | kVA (`base_power_kva`) |
| Line series parameters | Ω (`r_ohm`, `x_ohm`) |
| Load, PV, BESS, branch power | kW and kvar; **positive BESS kW means discharge/injection**, negative means charge |
| SOC | Fraction 0–1 in code; Qt settings display percentages and convert them |
| Solved voltage | Complex and magnitude per unit; angle degrees |
| Branch current and losses | A, kW and kvar |
| Profile step | Consecutive one-hour intervals; `Δt = 1 h` in the time-series simulator |
| Grid/slack real power | Positive import; negative export |

## 2. Entry points, UI and orchestration

### `app.pyw` — Windows launch

`main()` adds `07_Implementation` to the Python path and starts `src_accelerated.ui.main()`. `multiprocessing.freeze_support()` supports Windows worker-process startup. A `.pyw` launch has no console, so an unexpected startup error is shown in a Qt message box; if even Qt error display fails, it writes `app_startup_error.txt` beside the launcher. It does not perform electrical calculations. Double-clicking still requires the declared Python dependencies and a suitable environment; it is **not** an `.exe` package.

### `ui.py` — desktop interaction

Loads Designer forms from `assets/*.ui` with `QUiLoader`; named widgets are connected to explicit handlers. `LoadDataDialog` previews/imports the feeder, selects PV mode (`none`, prepared power, prepared/Open-Meteo/NASA irradiance) and load mode (imported/synthetic), and accepts only after preparation. `SettingsDialog` gathers voltage/reserve/grid limits, battery SOC/efficiency/sizes, cost coefficients, GWO population/iterations/CPU workers, allowed placement buses and net-load target. `ScenarioGeneratorDialog` generates/imports, plots, saves and activates scenario packages. `TimestampDialog` chooses an available retained simulation hour.

`MainWindow` runs static base case, hourly simulation and optimization in worker threads so the window can show progress, elapsed time and device-clock logs. It displays compact/full text results, stage/candidate counters, a selected bus or line, optional properties/results overlays, zoom/fit/wheel zoom, 90° rotation, and clear-results/workspace actions. The diagram moves the BESS symbol to the best candidate bus after optimization. **Important:** optimizer results keep aggregate metrics/evaluations; they do not retain a complete hourly best-candidate bus-voltage trace to show in the diagram. A manual simulation or separate replay is needed for that.

Worker `JobRunner` keeps Qt UI updates on the main thread. A closed window is guarded while work is active. A long-running process cannot be assumed cancellable merely because the UI remains responsive. The forms define layout/widgets, not physics.

### `ui_workflow.py` — bridge without Qt math

Public data types: `DataRequest` (paths, format, study start/months, PV/load modes), `PreparedStudy` (network, hourly profiles, provenance context, optional active scenarios), `RunSettings`, `RunReport`, `BaseCaseReport`. `prepare_study()` loads the network, builds a half-open calendar interval `[start, start + months)`, checks hourly coverage, creates or imports PV and load profiles and records source hashes. When PV is disabled it removes PV units from this prepared study and creates a zero-PV profile; when enabled, ratings come from explicit entries. `size_catalog(min,max,step)` includes the high endpoint even when it is not an exact multiple of the step.

`run_study(..., optimization=False)` runs `simulate_timeseries()` and, only for a completed converged run, `evaluate_results()`. With manual BESS omitted, the dispatch is not applied. `run_study(..., optimization=True)` builds battery power/energy catalogs and `SimulationEvaluator`; if an active `ScenarioSet` exists, it wraps this in `ScenarioEvaluator`; then it calls `optimize()`. A user-set net-load target and both economic coefficients are required for meaningful optimization. `finish_report()` records device-clock start/finish and elapsed wall duration. `run_and_export()` writes a numbered run.

`run_base_case()` is **one** FBS operating point: each bus receives its original `p_base_kw/q_base_kvar`, each installed PV contributes its **rated** `p_rated_kw` (Q = 0), and BESS contributes 0. `run_base_case_and_export()` writes `summary.txt`, `bus_voltages.csv` (bus ID, voltage pu) and `line_flows.csv` (line ID, P/Q/current/loss). This is a deterministic nameplate snapshot, not the time-series baseline. It is not guaranteed to equal any hourly result, and does not model battery SOC.

### `progress.py` — work counters and elapsed formatting

`ProgressEvent(phase, completed, total, detail)` computes `100 × completed/total` when total is known. `StageReporter` nests GWO → Candidate → Scenario → Simulation → Control → FBS counters and throttles routine UI snapshots to about four per second, while explicit boundaries can be logged. `format_duration()` formats elapsed seconds as `HH:MM:SS`. These are **work counters, not time-left estimates**: GWO iteration 1 may still contain hours × scenarios × FBS/control solves per candidate. With process workers, the parent sees completed candidate results, not every worker's inner FBS step. A “no worker counter update” heartbeat means no new result was received; it alone cannot establish a hang.

### `__init__.py`, `main.py` and `assets/*.ui`

`__init__.py` makes this an importable package. `main.py` is a console guide-five-bus FBS demonstration: `base_operating_point()` constructs fixed base loads and PV rated output; `main()` prints voltages, slack P/Q and losses. It is not the desktop application or an operational dispatch policy. The `.ui` files are editable Qt Designer layouts (`main_window.ui`, data/settings/scenario dialogs) loaded at runtime. They do not carry electrical equations.

## 3. Static network and Excel input

### `network_model.py` — network data and radial ordering

Defines `Bus`, `Line`, `Load`, `PVUnit`, `NetworkModel` and `RadialOrder`. `NetworkModel.validate()` checks IDs/references, finite physical data, **exactly one slack**, a single nominal voltage level, connected topology and `number of lines = number of buses − 1`. Together, connectivity and this line count imply a tree for the accepted undirected graph. It rejects self-connected lines and unknown load/PV buses. `radial_order()` roots the tree at the slack, returning parent/children maps and forward/backward branch order. FBS and the diagram use that order.

`Line.ampacity_a` and `PVUnit.q_capability_kvar` are representable data fields; that does **not** mean ampacity constraints or PV inverter reactive-power control are implemented. Transformers, multi-voltage feeders, meshed transmission and generator voltage-control buses are outside the model.

### `network_loader.py` — strict workbook adapter

`load_network(path, workbook_format='auto', frequency_hz=...)` accepts `.xlsx` only. The project template uses `Network`, `Buses`, `Lines` and optional `Loads`/`PV`; the bundled IEEE-33 workbook uses `Overview`, `Bus Data`, `Branch Data`. It reads literal Excel cell values using `openpyxl`, converts source units where documented, constructs `NetworkModel` and calls `validate()`. The IEEE-33 source's overview quantities and open/closed lines are handled explicitly; it does not drop closed lines to force a radial result. A frequency absent from the workbook must be supplied by the caller. Formula cells are not evaluated as physical data. The PJM/generator workbook is rejected rather than misinterpreting a generator-type “PV bus” as a photovoltaic installation.

Input: source workbook and optional format/frequency. Output: validated `NetworkModel`, not an hourly profile or solved power flow. The source workbook is opened read-only and closed; it is not rewritten.

### `network_cases.py` — code fixtures, not acquired measurements

`build_5_bus_case()` constructs a prepared 11 kV / 10 MVA chain; by default it has **no loads or PV** because its source did not supply them. `build_guide_3_bus_case()` and `build_guide_5_bus_case()` create named guide examples for solver verification. The guide five-bus case is a different **12.66 kV branched** network with explicit loads and one PV rating. Do not conflate either with the meshed PJM five-bus workbook or label fixture values as local measured data.

## 4. One-operating-point power flow

### `fbs.py` — balanced radial Forward/Backward Sweep

`OperatingPoint` requires explicit dictionaries for every network bus: load P/Q, PV P/Q, BESS P/Q. `FBSConfig` selects backend, maximum sweeps (default 100), voltage-change tolerance (default `1e-6 pu`) and optional history. `run_fbs()` validates the network and operating point, calls the Python solver or `accelerated_fbs.run_array_fbs`, and returns `PowerFlowResult` with complex/magnitude/angle bus voltages, branch currents and sending-end P/Q, per-line/total losses, slack P/Q, convergence flag, sweep count and diagnostics.

With line-line $V_{\mathrm{base}}$ and three-phase $S_{\mathrm{base}}$ (use kV/MVA for $Z_{\mathrm{base}}$ and kVA/kV for $I_{\mathrm{base}}$):

$$Z_{\mathrm{base}}=\frac{V_{\mathrm{base}}^2}{S_{\mathrm{base}}},\qquad
I_{\mathrm{base}}=\frac{S_{\mathrm{base}}}{\sqrt{3}V_{\mathrm{base}}},\qquad
Z_{\ell,\mathrm{pu}}=\frac{R_\ell+jX_\ell}{Z_{\mathrm{base}}}.$$

$$S_{i,\mathrm{net}}=(P_{L,i}-P_{PV,i}-P_{B,i})+j(Q_{L,i}-Q_{PV,i}-Q_{B,i}),\qquad
I_i=\left(\frac{S_{i,\mathrm{net,pu}}}{V_{i,\mathrm{pu}}}\right)^*.$$

$$I_{p\to i}=I_i+\sum_{k\in\mathrm{children}(i)}I_{i\to k}
\quad\text{(backward sweep)},\qquad
V_i=V_p-Z_{p\to i}I_{p\to i}
\quad\text{(forward sweep)}.$$

Start is flat at the configured slack voltage/angle. Repeat until $\Delta V=\max_i|V_i^{(n+1)}-V_i^{(n)}|\le\varepsilon$ or the sweep limit. On a converged iterate,

$$S_{\mathrm{send},\ell}=V_pI_\ell^*S_{\mathrm{base}},\qquad
S_{\mathrm{loss},\ell}=|I_\ell|^2Z_{\ell,\mathrm{pu}}S_{\mathrm{base}},\qquad
I_{\ell,\mathrm{A}}=|I_{\ell,\mathrm{pu}}|I_{\mathrm{base}}.$$

Slack power is slack net demand plus outgoing sending-end powers. A non-converged last iterate remains *diagnostic only*; voltage feasibility and FBS numerical convergence are separate questions. The model is balanced, constant-power and single-voltage-level; it is not a three-phase unbalanced load flow.

### `accelerated_fbs.py` — alternative numerical execution

`backend_status()`/`backend_available()` report Python, NumPy, optional Numba and experimental CuPy availability. `run_array_fbs()` converts the radial tree and operating point into indexed arrays, invokes `_cpu_sweeps` for NumPy, a JIT-compiled version for Numba, or `_gpu_sweeps` for CuPy, and reconstructs the same `PowerFlowResult` dictionary interface. The underlying backward/forward equations are intended to match `fbs.py`. The current normal UI exposes CPU choices; GPU code remains experimental. Repeated host/device transfers and sequential parent-child dependencies can erase GPU advantages on a small feeder. Numba may incur first-use compilation overhead. No backend should be described as *verified equivalent* or *faster* without controlled comparison at the same inputs and tolerance.

## 5. Profiles, PV and battery

### `data_loader.py` — standard hourly profile container

`ProfileData(csv_load, csv_pv)` reads two long-format CSV streams/files with columns `timestamp,bus_id,p_kw,q_kvar`, rejects duplicate `(timestamp,bus_id)` entries and mismatched load/PV timestamp sets, converts timestamps, stores values as per-bus lists and requires at least two consecutive hourly timestamps. `profile_at(profile_data,index)` produces `ProfileSlice` dictionaries for one hour. The loader does not solve FBS, invent PV, scale demand or select BESS settings. The upstream `ui_workflow._read_power_csv` and simulator perform additional coverage/network checks; do not credit **all** input validation to `data_loader.py` alone. This file also retains an old `__main__` example with absolute paths; it is not the current app entry point.

### `pv_model.py` — irradiance to PV **power**

`read_irradiance()` accepts prepared `timestamp,irradiance_w_m2`, Open-Meteo `shortwave_radiation (W/m²)` or NASA POWER `ALLSKY_SFC_SW_DWN` hourly energy-density CSV. NASA hourly Wh/m² divided by a one-hour interval is numerically mean W/m². Inputs must be continuous, timezone-naive hourly data with finite nonnegative values. `PVModelConfig` requires `0 < G_c < G_std` (default standard irradiance 1000 W/m²).

$$P_{PV}(G)=P_{\mathrm{rated}}
\begin{cases}
\dfrac{G}{G_{\mathrm{std}}}\dfrac{G}{G_c},&0\le G<G_c,\\
\dfrac{G}{G_{\mathrm{std}}},&G_c\le G<G_{\mathrm{std}},\\
1,&G\ge G_{\mathrm{std}}.
\end{cases}
\qquad Q_{PV}(G)=0.$$

`make_pv_profile()` sums installed PV ratings by bus and writes long-format absolute kW/kvar. If no PV units exist, it emits a zero profile at the slack bus so the shared profile loader still has a timestamped PV table. It uses the same irradiance for all PV buses as a **GHI resource proxy**. There is no panel tilt/plane-of-array conversion, temperature derating, inverter curve or reactive-power dispatch. The saturation boundary follows the report prose; a Term 1 equation typo/ambiguity was documented during implementation. A generated PV-power scenario later uses these kW histories; ARIMA does **not** regenerate irradiance.

### `load_generator.py` — synthetic hourly demand

`LoadGenerationConfig` contains the 24 hourly mean/standard-deviation percentages transcribed from Ali, Shaaban and Sindi (2022), Table 1, plus an explicit random seed. For each timestamp hour $h$, the generator draws **one** normal percentage $m_t\sim\mathcal N(\mu_h,\sigma_h)$, clips it at zero and applies the same $m_t/100$ to every bus's summed base P and Q:

$$P_{L,i,t}=P_{L,i}^{\mathrm{base}}\frac{\max(0,m_t)}{100},\qquad
Q_{L,i,t}=Q_{L,i}^{\mathrm{base}}\frac{\max(0,m_t)}{100}.$$

The fixed seed makes one run reproducible. The same multiplier means buses move together within an hour; samples are independent between hours. No weekend/seasonal factor or local measured-load calibration is coded. The paper labels periods 1–24; mapping them to clock hours 00–23 is an explicit prototype assumption. A zero-P/nonzero-Q base load is rejected for this generator. Its output is a prepared CSV-shaped DataFrame, not a feeder result.

### `bess.py` — one battery timestep

`BESSConfig` stores bus, rated kWh/kW, minimum/maximum/initial SOC, separate charge/discharge efficiencies and optional directional kW caps. `BESSState` stores energy and SOC. `step_bess(config,state,requested_power_kw,dt_hours)` returns **actual** signed battery kW, energy/SOC before/after and a limit reason; it does not choose the requested kW or solve power flow.

For discharge request $P_{\mathrm{req}}>0$:

$$P_{\mathrm{SOC,max}}=\max\left(0,\frac{(E_t-SOC_{\min}E_{\mathrm{rated}})\eta_{\mathrm{dis}}}{\Delta t}\right),\qquad
P_{\mathrm{actual}}=\min(P_{\mathrm{req}},P_{\mathrm{rated}},P_{\mathrm{dis,max}},P_{\mathrm{SOC,max}}),\qquad
E_{t+1}=E_t-\frac{P_{\mathrm{actual}}\Delta t}{\eta_{\mathrm{dis}}}.$$

For charge request $P_{\mathrm{req}}<0$, use positive charge magnitude

$$p=\min\left(|P_{\mathrm{req}}|,P_{\mathrm{rated}},P_{\mathrm{ch,max}},
\frac{SOC_{\max}E_{\mathrm{rated}}-E_t}{\eta_{\mathrm{ch}}\Delta t}\right),\qquad
P_{\mathrm{actual}}=-p,\qquad E_{t+1}=E_t+p\Delta t\eta_{\mathrm{ch}},\qquad
SOC_{t+1}=\frac{E_{t+1}}{E_{\mathrm{rated}}}.$$

`simulation.py` uses this public step with an operating SOC floor raised for reserve. There is no chemistry, degradation, temperature or cycle-life model. Settings validation around this simple class is important; the class itself is not a comprehensive supplier-data validator.

### `dispatch.py` — requested net-load-target operation

`NetLoadTargetPolicy(target_kw)` returns $P_{B,\mathrm{request},t}=\sum_iP_{L,i,t}-\sum_iP_{PV,i,t}-P_{\mathrm{target}}$ for the current `ProfileSlice`. Positive means request discharge; negative means request charge. `bess.py` and `simulation.py` may clip or pause that request. This policy can charge from the grid below the target. It does not use a price signal, forecast or optimal control.

## 6. Hourly simulation, feasibility and metrics

### `simulation.py` — actual time progression

`SimulationConfig` sets FBS backend/tolerance, voltage bounds (defaults 0.95–1.05 pu), reserve fraction (default 0.10), reserve duration (default 1 hour), optional grid import/export kW caps and control flags/iteration limit. `simulate_timeseries()` checks hourly data, computes peak requested load over the supplied profile, initializes BESS energy at `E_rated × SOC_initial`, and processes hours in timestamp order. For each hour, it gets a slice, asks the dispatch policy for kW (or 0 if none), calls `simulate_step()`, retains the accepted BESS state, emits progress and optionally stops at the first failed FBS.

Within `simulate_step()`:

1. Fill every network bus with explicit load/PV P/Q and zero BESS injection; reject missing configured load/PV buses.
2. If BESS exists, define $P_{\mathrm{reserve}}=r_{\mathrm{reserve}}P_{L,\mathrm{peak}}$, require a battery-energy margin $E_{\mathrm{reserve}}=P_{\mathrm{reserve}}T_{\mathrm{reserve}}/\eta_{\mathrm{dis}}$ above minimum SOC, and limit discharge so remaining kW headroom also covers reserve. Call `step_bess()` at one hour.
3. Solve FBS at the resulting operating point. A failed FBS cannot be treated as an accepted physical result; attempted battery energy remains diagnostic.
4. If a battery action pushes an already identified network limit the wrong way, try idling it. For overvoltage/excess export, optionally reduce all PV P and Q by a common fraction; for undervoltage/excess import, optionally reduce all load P and Q by a common fraction. `_reduce_until_allowed()` tests full reduction then uses at most `control_max_iterations` bisection trials to find an allowed fraction. Each trial solves FBS again. The reduced P/Q retain each device's original power factor.
5. Record actual curtailed PV and shed load by bus, voltage violations, reserve shortfalls, feasibility and messages. A converged result can remain infeasible if limits cannot be cleared.

`SimulationStepResult` retains one timestamp's operating point, `PowerFlowResult`, request/actual BESS action, accepted state, controls and violations. `TimeSeriesSimulationResult` retains the step list plus `completed` (all requested hours processed), `converged` (all FBS runs succeeded) and `feasible` (all constraints cleared). These three flags are **not synonyms**. No thermal/ampacity check is implemented. If shedding is allowed, a feeder can become voltage-feasible by **not serving** part of the requested demand; that must remain visible in reports.

### `metrics.py` — aggregate, never dispatch

`evaluate_results()` requires a completed, converged time series and the same BESS config if one was simulated. It sums per-step outputs using $\Delta t$:

$$E_{\mathrm{served}}=\sum_t\sum_iP_{L,i,t}^{\mathrm{served}}\Delta t,\qquad
E_{\mathrm{requested}}=E_{\mathrm{served}}+E_{\mathrm{shed}},\qquad
E_{PV,\mathrm{available}}=E_{PV,\mathrm{used}}+E_{PV,\mathrm{curtailed}}.$$

$$E_{\mathrm{import}}=\sum_t\max(P_{\mathrm{slack},t},0)\Delta t,\qquad
E_{\mathrm{export}}=\sum_t\max(-P_{\mathrm{slack},t},0)\Delta t,\qquad
E_{\mathrm{loss}}=\sum_tP_{\mathrm{loss},t}\Delta t.$$

$$E_{\mathrm{charge}}=\sum_t\max(-P_{B,t},0)\Delta t,\qquad
E_{\mathrm{discharge}}=\sum_t\max(P_{B,t},0)\Delta t,\qquad
C_{\mathrm{BESS}}=c_EE_{\mathrm{rated}}+c_PP_{\mathrm{rated}}.$$

It also records peak import, voltage min/max, voltage violation hours and **bus-hours**, reserve violation hours, BESS SOC extrema, curtailment/shedding energy, feasibility and notes. Cost is `None` if either coefficient is missing; no price is invented. Curtailment/shedding normally come from the simulator's own actions; separately supplied legacy series are checked against them. `percentage_reduction(baseline,candidate)` uses $100(M_{\mathrm{baseline}}-M_{\mathrm{candidate}})/M_{\mathrm{baseline}}$ when defined; negative means an increase. Comparing two runs fairly also requires identical profiles/settings, which this helper alone cannot prove.

## 7. Candidate search and uncertainty

### `optimizer.py` — discrete GWO and raw WSM

`BESSCandidate = (bus_id, power_rating_kw, energy_capacity_kwh)` is one installation. `OptimizationBounds` holds allowed bus IDs and explicit rating/capacity catalogs. `BESSParameters` converts a candidate into `BESSConfig`. `SimulationEvaluator` runs the **same** `simulate_timeseries()` and `evaluate_results()` as a manual study. If simulation is incomplete/non-converged or metrics are infeasible, the candidate objective is `∞`. Both economic coefficients must be supplied.

The first-version unnormalized objective is:

$$J(x)=0.50C_{\mathrm{BESS}}(x)+0.25E_{PV,\mathrm{curtailed}}(x)
+0.25E_{\mathrm{load,shed}}(x).$$

The default weights sum to one, but the components have mixed **currency and kWh units**. Thus a numerically cheaper design can be selected because of scale, not because a meaningful trade-off ratio was established. The optimizer searches discrete catalog indices, not continuous equipment sizes. For each dimension/leader, it draws

$$A=2ar_1-a,\qquad C=2r_2,\qquad D=|CX_{\mathrm{leader}}-X_{\mathrm{wolf}}|,\qquad
X_{\mathrm{estimate}}=X_{\mathrm{leader}}-AD.$$

It averages three leader estimates, clips positions to catalog-index bounds and rounds back to a valid candidate. $a$ decreases over scheduled iterations. It caches repeated candidate evaluations and can run distinct pending candidates in separate CPU processes. On Windows, worker inputs must be picklable. Progress at one GWO iteration boundary hides the many hours/scenarios/FBS solves inside it.

`OptimizationResult` contains best **evaluated feasible** candidate, objective/metrics, convergence history, evaluations and search metadata. It is a heuristic, not a proof of global optimum. `exhaustive_search()` evaluates every catalog combination for **small-case verification**; a large product catalog can make that reference impractical. If no feasible candidate was evaluated, `success=False` and `best_candidate=None`.

### `uncertainty.py` — conditional load/PV-power scenarios

`UncertaintyConfig` sets forecast hours, installed PV capacities, scenario count, seed, ARIMA `(p,d,q)` order (default `(1,0,0)`, so **AR(1)** by default), holdout length and mode (`automatic`, `arima`, `bootstrap`). `_series_parts()` computes a separate historical mean P for each clock hour and a historical hourly $Q/P$ ratio. Define $h(t)$ as hour-of-day and $s=\max(\operatorname{mean}(P),1)$:

$$\bar P_h=\operatorname{mean}\{P_t:h(t)=h\},\qquad
\epsilon_t=\frac{P_t-\bar P_{h(t)}}{s},\qquad
P_{t}^{(s)}=\operatorname{clip}_{\ge0}(\bar P_{h(t)}+s\epsilon_t^{(s)}),\qquad
Q_t^{(s)}=P_t^{(s)}(Q/P)_{h(t)}.$$

For PV, output is additionally capped at installed rating and set to zero at historically dark baseline hours. This is a **PV-power** scenario, not solar-irradiance generation. ARIMA from `statsmodels` fits normalized residuals with the selected order, not raw demand directly. If residuals are essentially zero, the model is deterministic hourly pattern. A holdout tail checks RMSE and MAPE (MAPE excludes near-zero actuals) against repeat-last-day. In `automatic` mode, non-convergent/invalid ARIMA fits or no RMSE improvement trigger hourly-residual bootstrap; explicit `arima` mode raises an error instead. The code then refits the chosen method to all history and draws seeded conditional paths. Bootstrap draws residuals with replacement; it is not the same temporal model as ARIMA.

`Scenario` wraps one shared `ProfileData`; `ScenarioSet.validate()` checks IDs, aligned timestamps and bus keys. `scenario_features()` calculates positive net-import energy, peak net load, surplus energy and largest hourly net-load ramp. `select_scenarios()` min-max normalizes **each feature across generated cases** and scores

$$\mathrm{stress}_s=0.35N(E_{\mathrm{net},s})+0.30N(P_{\mathrm{peak},s})
+0.20N(E_{\mathrm{surplus},s})+0.15N(R_s).$$

It picks configured low (“best”), high (“worst”) and seeded random distinct cases. This normalization is **only for scenario ranking**, not the GWO weighted-sum objective. Generated scenarios initially have equal `1/N` probabilities, but selected cases have `probability=None`: the stress-selected portfolio is not probability-preserving. `ScenarioEvaluator` evaluates the candidate on each retained case and rejects it if **any** case is infeasible; otherwise it averages objectives/energy metrics equally and retains worst-case extrema. Independent per-bus/load–PV innovation, fixed hourly patterns and absent seasonal/parameter uncertainty limit statistical credibility.

### `scenario_store.py` — inspectable package

`save_scenario_package()` refuses an existing output folder and writes **every** generated case as `all_scenarios/S###_scenario_###.csv`, with columns `scenario_id,timestamp,bus_id,load_p_kw,load_q_kvar,pv_p_kw,pv_q_kvar`. It also writes `validation.csv` (model/holdout errors and warnings), `scenario_ranking.csv` (stress/selection) and `manifest.json` (generation settings, selected IDs, file mapping). `load_scenario_package()` reopens the **selected** cases using the manifest and shared `ProfileData`; it rejects legacy package formats. Inspect an individual CSV when investigating “zero PV”: night hours and zero installed PV legitimately produce zeros, but an all-zero daylight PV series requires checking rated PV, input irradiance/history and selected scenario.

## 8. Results, session state and drawing

### `results.py` — format and export, no new power flow

`format_summary()` renders simulation/optimizer metrics and context. `export_results()` creates a **new** directory, never overwrites it, and writes only data retained in the result. Simulation exports include `hourly.csv`, `buses.csv` and `branches.csv` with timestamps and bus/line IDs, plus `metrics.csv` when available. Optimization exports include `evaluations.csv`, `convergence.csv` and `scenario_evaluations.csv` if applicable. Optional comparison writes `comparison.csv` only when baseline metrics are supplied. `summary.md` is published last. Unconverged power-flow values are diagnostic, missing metrics remain missing, and a rejected candidate's `∞` objective is not disguised as a finite optimum. The optimizer export is **not** an automatic detailed hour-by-hour replay of its best candidate.

### `study_session.py` — one accepted study's provenance

`StudySession.create()` makes `Results/Sessions/<timestamp>_<network>/` after Load Data is accepted, copies the network/source inputs, writes prepared load/PV snapshots, `session.json` (request/context/fingerprint, scenario/run lists) and timestamped `session.log`. `next_*_path()` makes numbered non-overwriting run paths; `record_scenario_set`, `activate_scenario_set`, `record_run` and `record_base_case` update the manifest. `study_fingerprint()` hashes selected input identifiers and context. The session permits auditing/reuse of **stored inputs** but is not a guarantee that two program versions or dependency environments reproduce bitwise-identical stochastic/optimizer results.

### `network_layout.py` — schematic placement

`build_layout()` roots the validated radial tree at the slack, computes subtree depth/bus count/width/equipment count, chooses a longest spine and balances lateral envelopes above/below using weighted size. It then reserves ports/annotation space, shortens busbars to attached items, and routes orthogonal branch take-offs. Bus IDs break ties; the arrangement is a **diagram heuristic**, not geographic coordinate data or an electrical calculation. `arrange_network()` is a coordinate-only compatibility wrapper. Branch-side overrides can be supplied in code, while normal UI auto-arranges behind the scenes. Rotation is a rendering/view choice and cannot change simulated power.

### `network_diagram.py` and `network_icons.py` — visible network

`NetworkView` supports fitting/zooming and wheel-centered zoom. `NetworkScene.draw_network()` renders busbars, selectable lines and buses, external grid, load arrows, PV and BESS symbols, optional base properties/result annotations, voltage coloring and 90°-increment orientation. `NetworkLine`/scene item data make line selection possible even with a slim visible stroke. A result overlay needs a retained static or hourly step; an optimizer summary alone cannot supply bus-by-bus voltages. `network_icons.network_icon()` draws compact palette-aware Fit/Zoom button icons. These files do not solve FBS or change source network topology.

## 9. What this reference does **not** certify

1. The code being present does not prove numerical correctness. An independent FBS comparison and formal experiment matrix remain necessary.
2. Numerical FBS convergence does not imply voltage feasibility, reserve sufficiency or fully served demand. Curtailment/shedding can make a case feasible by reducing injection/demand.
3. A static base case using rated PV is not a particular solar hour. Compare it to an hourly run only when P/Q inputs and BESS power truly match.
4. An automatic uncertainty fallback is not a successful ARIMA fit. Default `(1,0,0)` is AR(1) residual modeling, though the UI's algorithm is described as the broader ARIMA family.
5. The raw WSM mixes units; its default weights are implementation choices, not calibrated stakeholder preferences.
6. Neither stored line ampacity nor a generic battery config establishes thermal/supplier compliance. No emissions metric is computed.

For the dated story of what was built, why it changed, and which libraries were used, read [DEVELOPMENT_CHRONOLOGY.md](DEVELOPMENT_CHRONOLOGY.md). It is explanatory source material, not a report draft.
