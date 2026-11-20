# EE499 Team 16 — FBS Numba Final Decision and Integration Plan

**Status:** **Final decision approved; implementation deferred.** This file is a specification for a later program change, **not** an implementation or authorization to edit the repository.  
**Project:** [Islahi/EE499-Team16](https://github.com/Islahi/EE499-Team16.git)  
**Target application:** `07_Implementation/src_accelerated/` on `main`, reviewed 2026-11-20. Recheck the actual development branch and commit before changing code.  
**Decision date:** 2026-11-20  
**Evidence:** `EE499_C1_Benchmark_Results.7z`, `EE499_C1_Weighted_Ranking_Report.md`, `EE499_C1_weighted_ranking.csv`, `EE499_C1_per_network_weighted_ranking.csv`, and the historical C1 validation package.  
**Related implementation decision:** `EE499_Approach_A_Integration_Plan(2).md` (three aggregated load-sector forecasts plus one common PV forecast).  
**Change authority:** No program source, requirements, GUIs, tests, study results, or GitHub branches were modified by preparation of this document.

## 1. Approved decision

**Use the existing Forward/Backward Sweep (FBS) numerical algorithm exclusively through the Numba-compiled CPU backend for all production power-flow operations.** This applies to static/base-case checks, hourly simulations, PV/BESS operational studies, constraint evaluations, and every power-flow evaluation performed by GWO, GA, exhaustive search, or future optimization methods.

**Production backend identifier: `numba`.** The user must not be offered a choice among Python, NumPy, Numba, GPU, SciPy, pandapower, OpenDSS, or MATPOWER in the EE499 application. The solver configuration, GUI, and public API must all enforce this rule. If the required Numba runtime/compilation fails, **stop with an informative error**; do not silently switch to Python/NumPy or another method.

This is a choice of **implementation backend**, not a new electrical algorithm. Numba compiles the existing FBS current-summation sweeps; it does not change the FBS equations, network input model, load/PV/BESS sign conventions, convergence criteria, or engineering constraints.

**Independent solvers remain available only in separate development/validation tooling.** Preserve the original Python FBS, SciPy NR, and MATLAB/MATPOWER as archived references for regression and independent cross-checks. They are **not** authorized production fallback options. The earlier C1 ranking report's suggestion of a Python FBS fallback is **superseded by this explicit final production-only decision**.

### What “Numba only” means

| Context | Accepted behavior | Prohibited behavior |
|---|---|---|
| GUI power-flow setting | Display `FBS (Numba CPU)` as fixed/read-only information | Dropdown permitting Python, NumPy or any other backend |
| `FBSConfig` | Default to `numba`; reject any other backend | Defaulting to `python`; accepting `python`, `numpy`, or `gpu` |
| `run_fbs()` / internal array execution | Execute the Numba-compiled FBS kernel only | Branching to uncompiled FBS or changing algorithms on failure |
| `SimulationConfig()` | Use Numba by default, including headless calls | Relying on a GUI selection to enforce Numba |
| Optimization workers | Numba in **every** worker process | Worker falling back to Python when JIT/cache is cold |
| External C1 benchmark and academic validation | Maintain separately, unchanged | Embedding other solver engines in the production execution path |

## 2. Evidence and reason for the decision

### C1 weighted ranking

The agreed weighted score was

\[
S = \frac{2A + V}{3},
\]

where `A` is the percentage score for full-workload numerical qualification/reliability and `V` is the per-network normalized warm-speed score. **Accuracy weight = 2; speed weight = 1.** This is a project decision aid, not a universally standardized power-flow ranking.

| Rank | Implementation | Accuracy score | Speed score | Weighted score |
|---:|---|---:|---:|---:|
| **1** | **FBS Numba** | **90.91** | **99.81** | **93.88** |
| 2 | FBS Python | 90.91 | 71.82 | 84.55 |
| 3 | FBS NumPy | 90.91 | 48.09 | 76.64 |
| 4 | SciPy Newton–Raphson | 90.91 | 40.92 | 74.25 |
| 5 | MATLAB/MATPOWER | 90.91 | 0.36 | 60.73 |

The benchmark covered **22 network cases** and eight submitted solver adapters. The five ranked solvers solved all **22 nominal cases**. They each qualified **20/22 full stress workloads**, with two shared extreme low-voltage stress failures on the 118- and 136-bus cases. Thus, `90.91` **does not mean 9.09% voltage error**. The FBS Numba solution matched the original FBS nominal voltage output to the recorded precision, and it was fastest among the five broadly accurate solvers on **21/22 networks**.

| Representative network | Numba FBS median warm time | Python FBS median warm time | Numba speedup |
|---|---:|---:|---:|
| 15-bus System 1 | 0.246 ms | 0.279 ms | 1.13× |
| 33-bus | 0.448 ms | 0.714 ms | 1.60× |
| 69-bus | 0.774 ms | 1.383 ms | 1.79× |
| 118-bus | 1.540 ms | 2.532 ms | 1.64× |
| 136-bus | 1.617 ms | 2.797 ms | 1.73× |

The consolidated ranking reports a **0.458 ms median** Numba warm latency over the archived cases and a **93.88/100** weighted score. These numbers are from **the benchmark machine and measured network/operating-point workloads**, not guaranteed production end-to-end or cold-start timings. Do not claim Numba solves every stress point: the two shared stress failures remain recorded.

**Other libraries:** pandapower BFSW/NR and OpenDSS did not meet the benchmark's strict common-model numerical qualifications. Those observations require adapter/model-equivalence investigation and **must not be generalized as defects in the underlying libraries**. Their richer native PV/BESS/inverter features do not outweigh the current project's integration and validation costs.

### Why this fits EE499

The project already implements a balanced, constant-power radial FBS solver, a separate battery SOC/efficiency/dispatch model, and a PV power model. The Numba backend therefore supports the project requirements **through the existing EE499 device models**, not through native `Storage` or `PVSystem` objects. The program does not currently require a dedicated unbalanced three-phase solver, tap-changing transformer controls, detailed inverter Volt–Var functions, or meshed-network power flow.

## 3. Functional scope and preserved electrical model

### Existing physical interface

`fbs.py` defines `OperatingPoint` with one explicit entry for every network bus in each field:

```python
p_load_kw: dict[int, float]
q_load_kvar: dict[int, float]
p_pv_kw: dict[int, float]
q_pv_kvar: dict[int, float]
p_bess_kw: dict[int, float]
q_bess_kvar: dict[int, float]
```

The solver forms the complex **net demand** per bus:

\[
S_{i,\mathrm{net}} = (P_{L,i}-P_{PV,i}-P_{BESS,i})
                 + j(Q_{L,i}-Q_{PV,i}-Q_{BESS,i}).
\]

**Preserve the existing sign convention:** positive `p_bess_kw` represents discharge/injection; negative represents charging/absorption. Preserve the external BESS power/SOC limits; **the FBS solver itself does not update battery energy**. It solves only the electrical operating point passed to it.

`network_model.py` currently accepts one slack bus, one nominal voltage level, and a connected radial network (`n_lines = n_buses - 1`). The chosen Numba backend **does not expand that scope**. Reject unsupported multi-voltage/transformer, unbalanced, or meshed cases using the current network validation rather than quietly approximating them.

The `PowerFlowResult` contract must be preserved: per-bus complex voltage, magnitude and angle; branch current and P/Q flows; line P/Q losses; total losses; slack P/Q; convergence flag; iterations; maximum voltage delta; messages; and optional history. Do not change engineering units at the public boundary.

### No changes to BESS, PV, or forecasting decisions

- `bess.py` owns SOC, energy capacity, charging/discharging efficiencies and requested-versus-actual battery power.
- `simulation.py` owns hourly BESS dispatch, PV curtailment/load shedding, voltage/import/export/line-limit checks and convergence handling.
- `pv_model.py` supplies modeled electrical PV injections from irradiance; `PVUnit` supplies installed capacities.
- The separately approved forecasting design remains **Approach A** (residential CalendarRidge, commercial XGBoost, manufacturing LightGBM, each fitted to its sector sum) plus **one common modeled-PV XGBoost** forecast. Its resulting bus-level load/PV profiles feed Numba FBS without changing the forecasting method.
- No new battery siting study, PV fitting, optimization objective, battery-physics revision, or inverter-control model is authorized by this FBS-backend decision.

## 4. Required production execution contract

```text
APP STARTUP:
    VERIFY Numba + required numerical dependencies load in selected Python
    VERIFY the Numba FBS kernel can compile/run on a small valid case
    IF unavailable or compilation fails: show a clear blocking error

CREATE FBS CONFIG:
    backend = 'numba'                    # fixed, only accepted option
    max_iterations = existing setting   # preserve unless separately approved
    voltage_tolerance_pu = existing setting
    slack_angle_deg = existing setting
    record_history = existing setting

ALL EXECUTION PATHS:
    imported network + per-bus load/PV/BESS operating point
      -> run_fbs(network, point, approved_config)
      -> the Numba FBS kernel
      -> unchanged PowerFlowResult
      -> same simulation, optimization, constraints, and result export

IF network unsupported: reject with original network-model validation error
IF electrical nonconvergence: return/report nonconverged result, never substitute
                         a Python/NumPy/NR/OpenDSS solution
IF Numba runtime/JIT fails: fail explicitly, never silently fall back
```

**Critical enforcement rule:** The restriction must hold at the **solver API boundary**, not only in the GUI. Calls from Python scripts, default `SimulationConfig()`, parallel GWO workers, static base-case validation, and future programs importing `run_fbs` must not bypass it.

## 5. Exact repository touchpoints and planned changes

| Location under `07_Implementation/` | Change planned **later** |
|---|---|
| `src_accelerated/fbs.py` | Make `FBSConfig.backend` default to **`"numba"`** and reject any other backend immediately (e.g., validated frozen dataclass). Require Numba through `run_fbs()` and `run_array_fbs()`; remove or isolate selectable Python/NumPy/GPU dispatch. Preserve `OperatingPoint`, `PowerFlowResult`, iteration rules, equations, conversion, and diagnostics. **Keep `_cpu_sweeps` or equivalent source** because Numba's `njit` compiles this function; deleting it would remove the compiled kernel. |
| `src_accelerated/simulation.py` | Ensure `SimulationConfig()` defaults to the fixed Numba `FBSConfig`. Validate any provided custom `fbs_config` at construction and before critical execution, preserving all `simulate_step()` / `simulate_timeseries()` behavior. All internal constraint-control trial power flows must use the same Numba configuration. |
| `src_accelerated/ui.py` | Remove `combo_compute_backend` selections and related `currentData()`/restore/capture/read logic. Show read-only **FBS — Numba (CPU)** status and a clear availability/JIT error. Instantiate approved `FBSConfig()` directly instead of reading a user-selected backend. Ensure Apply and Run cannot proceed when unavailable. |
| `src_accelerated/assets/settings_dialog.ui` | In the existing Computation group, replace the backend dropdown and its associated label/tooltips with a fixed read-only label. **Keep CPU workers**; they control GWO parallel evaluation, not the choice of solver algorithm. Update tab order if the dropdown is removed. |
| `src_accelerated/ui_workflow.py` | Ensure hourly simulation, static base case, no-storage baseline, optimization, and exports all consistently declare/use Numba. Preserve `settings.simulation.fbs_config` and its data contract; improve provenance labels. |
| `src_accelerated/optimizer.py` | Verify `SimulationEvaluator` and GWO `ProcessPoolExecutor` workers receive validated Numba settings. Explicitly handle Windows process-spawn/JIT warm-up, so workers never use an unapproved backend. GA and exhaustive search must also invoke Numba when using the shared evaluator. |
| `src_accelerated/results.py` | Ensure result summaries and CSV/export metadata label the actual `FBS Numba` engine and preserved convergence settings; do not alter numerical result schemas unnecessarily. |
| `src_accelerated/study_session.py` | Record fixed backend, Python/Numba/NumPy/llvmlite versions, convergence limits, source revision, first-JIT versus warm timing where captured, and explicit failure status in manifest/logs. Existing study history remains readable. |
| `src_accelerated/docs/` and app README | Update public descriptions, screenshots, requirements, and help text to state that **FBS Numba is the only production solver** and that validation frameworks are external. |
| Application dependency file / installation instructions | Make compatible **Numba mandatory**, not optional. Maintain NumPy and other existing application dependencies. Verify versions on the actual Python installation (including the project's Python 3.14 deployment) before pinning; avoid an unnecessary new virtual environment. |
| New/revised tests | Add backend-enforcement, numerical-regression, PV/BESS, optimizer-worker, GUI, and study-export tests described in §9. Keep benchmark reference data separate from the application package. |

**Verified current-state details (2026-11-20):** `fbs.py:FBSConfig.backend` defaults to `"python"`; `run_fbs()` accepts `python`, `numpy`, `numba`, and `gpu`; `run_array_fbs()` dispatches among array variants. `simulation.py:SimulationConfig` constructs a default `FBSConfig`; `ui.py:SettingsDialog` reads `combo_compute_backend` and uses its selection to construct `FBSConfig(backend=...)`. `assets/settings_dialog.ui` lists Python, NumPy and Numba. These must **all** be addressed to make “only accept Numba” true.

### A proposed compatible configuration contract

Keep the `backend` attribute for compatibility with existing result/context serialization, but make its accepted value fixed:

```python
@dataclass(frozen=True)
class FBSConfig:
    max_iterations: int = 100
    voltage_tolerance_pu: float = 1e-6
    slack_angle_deg: float = 0.0
    record_history: bool = False
    backend: str = "numba"

    def __post_init__(self):
        if self.backend != "numba":
            raise ValueError("Only the FBS Numba backend is supported")
```

This is **illustrative integration guidance**, not a drop-in replacement: preserve the current numerical validation and add guards to both public solver entry points. `FBSConfig` alone cannot prevent an internal direct call to `run_array_fbs` with a forged/unvalidated configuration, so the solver must enforce `backend == 'numba'` at execution as well. Do not silently rewrite an explicitly supplied invalid backend string to `'numba'`.

### Saved settings and old results

- Old session snapshots and C1 validation results can be opened for **read-only historical inspection**, even when they mention `python` or `numpy`.
- A newly executed or resumed study must **use `numba` only**. Do not resume an old partly completed optimization while mixing backend outputs under the same run identity.
- When loading settings that contain a retired backend, provide an explicit *settings migration* message; write new Numba settings under a new run record with a new identity. Never silently overwrite the historical execution record.
- Preserve existing case inputs and archived numerical outputs for traceability; do not delete old reference implementations or change the external test bench.

## 6. Installation, startup, and JIT behavior

**Mandatory requirement:** `numba` must be importable and compilable in the interpreter actually used to run the application. `numpy` and the relevant compiled/runtime dependencies must also be compatible. The project's Windows user currently uses **Python 3.14** for the C1 benchmark; its availability on that machine is an observed benchmark result, not a guarantee that every later Numba version supports every Python release.

Proposed checks before enabling simulation/optimization:

1. Verify Python executable and `python --version` (or `py -3.14 --version` when this is the selected interpreter).
2. Verify `import numpy, numba, llvmlite` and capture their versions.
3. Execute a tiny valid radial power-flow case with `FBSConfig()` and assert the Numba-compiled kernel has a usable compiled signature and finite converged results. A successful import **alone** is not a complete runtime test.
4. Report an actionable error when the compiled backend is missing or fails. Provide installation guidance using the **same interpreter** as the application; do not select a different backend.
5. Warm the compiled signature **outside measured power-flow throughput** if appropriate. When GWO runs multiple processes on Windows, ensure each worker can compile/load the cached signature safely and record startup overhead separately.

The current kernel uses `numba.njit(cache=True)` around `_cpu_sweeps`. **Preserve that relationship.** JIT compilation and worker startup can take longer than warm repeated solves; the benchmark's 0.458 ms figure must not be advertised as cold launch or full optimization runtime.

For first integration, **avoid unnecessary solver refactoring**. Later speed enhancements (caching radial order, line arrays, per-unit impedance, bus-to-array indexing; reusing structures between hourly/BESS evaluations) may improve performance, but they must be proposed and validated in a separately measured change. The current `run_array_fbs()` rebuilds these structures each call, and the archived ranking reflects that overhead. Do not mix a new caching design into this backend-only decision without its own numerical regression tests.

## 7. Forecast, PV, BESS, and optimization interaction

### Load forecasting

The approved Approach A integration produces three sector-level predictions and training-only allocated **per-bus** `p_kw`/`q_kvar` profiles. Numba FBS receives the same resulting `ProfileData`/`OperatingPoint` as the old solver did. **Do not put sector aggregation logic in the FBS kernel.** The electrical solver must always see bus-resolved demand.

### Solar PV

The separate winning common modeled-PV XGBoost forecast is converted to per-installation electrical power using rated capacities. Numba FBS must receive its resulting `p_pv_kw` and existing unity-PF `q_pv_kvar=0` assumptions. It must not forecast irradiance, reapply the irradiance-to-power conversion, or impose new PV inverter behavior.

### BESS

`step_bess` remains responsible for enforcing energy/SOC limits, charging and discharging efficiency, and the accepted battery dispatch power. `simulate_step` applies battery power at the candidate bus to the `OperatingPoint`, then runs Numba FBS. Do not let Numba independently mutate BESS SOC. Preserve both battery charge (negative injection) and discharge (positive injection) cases and confirm the power-flow results reflect changing bus location.

### Simulation and optimization

The static base-case FBS, 24-hour and full-year time series, feasibility checks, curtailment/shedding retries, GA/GWO/exhaustive evaluations, and no-BESS baseline must all call the *same* approved `run_fbs` interface. Nonconvergence must retain its actual failure status; do **not** substitute a different solver to force feasibility or continue optimization silently. Optimization results must remain reproducible under fixed random seeds and the same numerical tolerance/configuration.

## 8. Numerical equivalence and boundaries

The production switch should preserve the pre-existing FBS equations and sign conventions. Use the external C1 results as validation evidence, not as replacement runtime dependencies.

**Reference conditions to reproduce:** historical C1 used `max_iterations=100`, `voltage_tolerance_pu=1e-8`, backend `python`; the application's current default `FBSConfig` uses `max_iterations=100` and `voltage_tolerance_pu=1e-6`. When comparing two implementations, run **the same explicitly selected tolerances** rather than attributing tolerance differences to Numba.

Compare at least the existing 15-, 33-, 69-, 118-, and 136-bus supported test cases, plus representative PV, charging, discharging and reverse-flow scenarios. Validate:

- Maximum absolute bus voltage-magnitude difference against the **archived same-input Python-FBS reference** (C1 criterion `<= 1e-6 pu`).
- Voltage angles, branch current, slack P/Q, active/reactive losses, and weakest bus within documented tolerances. Compare with **independent** SciPy NR or MATPOWER where the electrical input case is equivalent.
- Independent nodal P and Q mismatch (`<= 1e-3 kW/kvar` was the C1 criterion) and overall power balance.
- Same convergence and physically feasible/infeasible classifications on nominal and defined stress points; discrepancies need investigation rather than automatic acceptance.
- The two historical extreme **118-/136-bus low-voltage stress** failures must remain visible and must not be presented as Numba-only faults or automatically fixed by changing the backend.
- Published 33-bus and 69-bus workbook-versus-paper discrepancies need to remain flagged. An imported workbook difference is not itself a numerical-solver error.

These are validation criteria and prior findings, **not claims that new integration tests have been performed**.

## 9. Acceptance checklist for the later code change

### Enforcement and GUI

- [ ] `FBSConfig()` defaults to `backend='numba'`; unsupported values raise a meaningful error.
- [ ] Calling `run_fbs()` and `run_array_fbs()` cannot select Python, NumPy, GPU, SciPy, pandapower, OpenDSS or MATPOWER by argument, hidden defaults, saved settings, or fallback paths.
- [ ] `SimulationConfig()` and every headless simulation path default to Numba and reject unapproved configurations.
- [ ] Backend dropdown is removed/replaced by read-only `FBS — Numba (CPU)` information; the CPU-worker control remains usable.
- [ ] Missing Numba, incompatible versions, JIT compilation failure, and unsupported network models produce an explicit error; no silent fallback.
- [ ] Old settings are migrated transparently for **new** runs; historic result records stay untouched.

### Numerical operation

- [ ] Nominal 15-, 33-, 69-, 118- and 136-bus outputs agree with the archived Python FBS at matched tolerances, with independent residual/energy-balance checks.
- [ ] Static base case, no-BESS case, time-series simulation, and optimized BESS cases all use Numba.
- [ ] Load/PV/BESS active and reactive sign conventions, line current/loss units, slack calculations, and bus/line identifiers remain unchanged.
- [ ] PV-only, BESS charge/discharge, reverse flow, curtailment, shedding, and no-PV/no-BESS scenarios produce finite, physically consistent results or a documented nonconvergence status.
- [ ] Nonconvergent extreme cases do not generate fabricated feasible candidates or auto-switch solver implementations.
- [ ] `PowerFlowResult` and exported CSV/result contracts remain compatible with downstream plotting and economics.

### Runtime and reproducibility

- [ ] Python/Numba/NumPy/llvmlite versions and exact backend are logged; Numba is mandatory in requirements.
- [ ] JIT cold-start vs warmed solve is separately measured; the benchmark speed figure is not reused as an unmeasured new runtime claim.
- [ ] GA and GWO (including Windows multi-process workers) use Numba and have no Python fallback.
- [ ] A fixed-seed optimization run and reference time-series run reproduce key metrics before/after the backend restriction within declared tolerances.
- [ ] All tests run against both ordinary historical inputs and approved Approach A + common PV forecast profiles once that separate forecast change has been implemented.
- [ ] Static tests/grep or equivalent confirm no selectable legacy production backend remains in GUI, config, code, or workflow documentation.
- [ ] The external C1 benchmark remains independently runnable for future academic validation; repository changes are reviewed and committed only after explicit user approval.

## 10. Deferred implementation sequence

1. Create an implementation branch **only when the program change is requested**; record the precise source commit and take a baseline test snapshot.
2. Make Numba an enforced, mandatory backend in `fbs.py`, retaining the current compiled `_cpu_sweeps` kernel and numerical result contract.
3. Change `SimulationConfig` and all headless entry points so that Numba is the default and only allowable backend; test rejection of invalid values and of missing/JIT-failed Numba.
4. Update `settings_dialog.ui`, `ui.py`, and settings migration to show a fixed solver and preserve the independent GWO worker setting.
5. Verify static base-case, hour-by-hour simulation, no-BESS baseline, GWO/GA/exhaustive candidate evaluation, PV curtailment/load shedding, and result exports.
6. Add startup compile/availability check, Numba dependency installation documentation, version/source provenance, and separate JIT/warm runtime logging.
7. Execute the C1 numerical equivalence/regression tests and the project PV/BESS/optimization integration tests. Keep external solvers outside production code.
8. Review final UI screenshots and generated manifests, document known stress-case limitations, and merge only after tests and user approval.

## 11. Limitations and future changes

The selection is valid for the existing **balanced, constant-power, single-voltage radial** feeder model and the currently defined BESS planning objectives. It does not imply that Numba FBS can natively model storage SOC, inverter controls, transformers, unbalanced phases, or meshed-network physics. Those require separate validated component models or a future solver/framework decision.

A later requirement for meshed systems, unbalanced three-phase analysis, tap-changing transformers, or detailed inverter controls would justify **reopening** the solver architecture decision. It does not authorize adding a production backend dropdown now.

Any future Numba optimization, input-conversion change, library upgrade, or wider electrical-model support must have explicit reproducibility and accuracy checks before replacing the verified implementation.

## 12. Definition of done

The later integration is complete when **every EE499 application power-flow evaluation uses the Numba FBS CPU kernel**, the GUI and programmatic configurations **cannot select any alternative solver**, all existing bus-level load/PV/BESS inputs and `PowerFlowResult` outputs remain compatible, numerical and physical validation passes within documented tolerances, worker/JIT failures are explicit, and the session/report provenance records the fixed engine and exact runtime versions. Independent validation engines and historical C1 artifacts remain outside the production execution path.

**Current status: decision documented only. No EE499 application code or GitHub repository changes were made.**
