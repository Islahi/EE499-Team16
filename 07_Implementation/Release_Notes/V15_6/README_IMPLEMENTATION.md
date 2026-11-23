# BESS Planning Tool · V15.6 cleanup

Start with the [V15.6 cleanup quick start](V15_6_CLEANUP_QUICKSTART.md) and the [system validation report](docs/FULL_SYSTEM_TEST_REPORT.md).

## Historical release · V14 duration-constrained BESS sizing

See [V14_CHANGES.md](V14_CHANGES.md). V14 is built from the uploaded V13, retains V13 P/Q OPF, and enforces configurable 2–12 h nameplate E/P limits across candidate creation, GWO, probes, energy refinement, final verification and manual batteries. The default search grid is 250–2500 kW and 250–15000 kWh, in 50-unit increments. Compare against V12/V13 with matched bounds and study conditions.

---

## Historical release · V13 coordinated P/Q OPF

See [V13_CHANGES.md](V13_CHANGES.md) for the current controller, parameter assumptions, comparison commands and validation. The historical documentation below describes earlier versions and is retained for reference. The V13 default inverter kVA multipliers are 1.00×; experimental 1.2×/1.1× oversizing must be explicitly selected.

---

> **Historical version: V12** — see [`V12_CHANGES.md`](V12_CHANGES.md) for the 72-hour predictive controller, chronological GWO SOC warm-starts, annual energy-capacity refinement, terminal inventory accounting, and the separate 50%-of-nominal-demand PV test dataset. Sections below document earlier implementation milestones and may describe historical V10/V11 behavior.

# Historical release — BESS Planning V11 (predictive multi-BESS control)

Read **`V11_CHANGES.md`** first. V11 adds paper-grounded 24-hour coordinated LP scheduling and a simple **Battery control** selector under Settings → Optimization → Sequential battery placement. The default is Predictive; Legacy reproduces the V10 voltage-triggered controller for fixed-location A/B evaluation. The study continues to use Numba FBS, GWO convergence, adaptive annual finalists, 8,760/8,784-hour verification, and 16 GB-friendly parallel worker controls. This is a new adaptation of published research, **not an exact implementation of those papers**.

For a quick fixed-battery experiment (without running GWO):

`python COMPARE_V10_V11_CONTROL.py --folder "C:\\your\\inputs" --hours 168`

**CAUTION:** 24-hour future data are read from the supplied load/PV CSV. If these are hindsight actuals instead of genuine forecasts, the outcome is a perfect-foresight backtest. See `V11_CHANGES.md` for the research references, mathematical assumptions, validation and limitations.

---

# EE499 BESS Planning v10.2 — Worker Controls and Simplified Settings

**Current release: V10.2.** Read [`V10_2_CHANGES.md`](V10_2_CHANGES.md) first. Choose Settings → Optimization → Computation → **Auto** or uncheck Auto to enter independent **GWO workers** and **Annual verification workers**. On 16 logical processors with 16 GB RAM, Auto uses 4/2; Manual 6/2 is a reasonable next benchmark. The obsolete 10% voltage-improvement and cumulative shedding-target input boxes are hidden, but historical saved configurations remain readable. CPU worker settings apply to subsequent runs after saving.

**Source:** V10.1 uploaded source package, not GitHub. Numerical solver and v10 objective logic unchanged.

---

# EE499 BESS Planning v10 — Adaptive Voltage Compliance and Parallel Optimization

**Current release: v10.** Start with [`V10_CHANGES.md`](V10_CHANGES.md) for active methods, settings, comparisons and validation. The v9/v8 material below is retained as historical documentation and **does not override v10's voltage acceptance or screening rules**.

---

# EE499 BESS Planning v9 — Cumulative Reliability and Annual Coverage

**Current release: v9.** Read **`V9_CHANGES.md`** first for the changes since v8, test evidence, limitations, and how to read the new coverage audit files. The v8 notes below are retained as historical implementation documentation; their per-installation 10% gate and final-selection explanation have been superseded by v9.

---

# EE499 BESS Planning v8 — Accelerated Lateral-Aware Technical Placement

**Project:** EE499 Team 16. v8 is based on the v7 ZIP created from the user-uploaded v6 program. Neither v6 nor v7 was overwritten. Project identifier: https://github.com/Islahi/EE499-Team16.git (not used as source for this build).

## Why this version exists

In v6 the IEEE 33-bus run selected 250 kW / 10,000 kWh batteries near Buses 17 and 14. Annual voltage-deficit improvement at nearby buses was modest. v6 ranked buses by shedding and pre-shedding voltage, but its **battery dispatch shared one global power target** and its **annual finalists all came from the same lateral**. This does not establish that the other heavily shed lateral (e.g. Buses 26–33) is inferior.

v8 retains the existing Windows desktop UI, **Numba Forward/Backward Sweep**, bus-specific progressive load-shedding control, GWO, independent SOC for up to three batteries, annual economics, and the self-contained HTML dashboard. It changes the sequential multi-BESS algorithm as described below.

## What changed

1. **Voltage-aware active-power dispatch.** `src_accelerated/voltage_dispatch.py` calculates a fast radial common-path resistance sensitivity (pu/kW) from the *loaded network topology*, identifies each bus currently below the voltage minimum, and allocates available battery discharge to the locations predicted to relieve those undervoltages most effectively. It also considers the grid import cap. **All proposed injections are verified jointly with the original nonlinear FBS solver**, which refuses actions that create or worsen an already satisfied electrical constraint. Sensitivity is only a dispatch guide, not a replacement for FBS.
2. **Better charging utilization.** BESS units charge toward configured **maximum SOC** (not merely initial SOC), but only when the minimum network voltage has a safety margin of **0.015 pu** above the configured lower limit, or when absorbing an overvoltage is needed. Grid import limits, BESS kW, kWh, efficiencies, and SOC limits still apply. The simulation **does not** force year-end SOC equality or value the inventory difference economically. If the feeder is undervoltage for most hours, insufficient safe charging opportunities can still leave BESS units depleted.
3. **Electrical-lateral screening.** `feeder_aware.py` discovers radial laterals using branching junctions (not numeric closeness). IEEE 33: Bus 14 and 17 share lateral `6->7`, while Bus 30/32 is on `6->26`. Annual per-bus ranking still uses **50% pre-correction voltage rank + 50% local shedding rank**; the shortlisted buses are now balanced across laterals with unresolved problems. The top roughly one-third remains the basic budget, with minimum group coverage when necessary.
4. **Lateral-aware critical weeks.** The two 168-hour windows are selected from different major stressed laterals where possible, instead of only using system-wide peak weeks. Screened operational scores are **94% normalized total shedding/voltage deficit and 6% annual cost ratio** when technical problems exist; this is a heuristic *screening score*, **not annual cost or a published Karve equation**.
5. **Deliberate sizing probes.** Each shortlisted lateral gets a few extra catalog-valid configurations including the **maximum permitted power** (e.g. 2,500 kW) and maximum energy. This addresses the v6 tendency to have all annual finalists at the lowest permitted power. v8 adds convergence-based GWO early stopping; the maximum remains user-configurable.
6. **Adaptive full-year finalists.** Up to **three** lateral-diverse GWO/probe candidates are checked first. If none is technically acceptable, continue up to the configured maximum (default six). The annual simulation includes all previously installed batteries. This is still a greedy sequential heuristic, not globally optimal multi-BESS sizing.
7. **Technical acceptance before economic selection.** A candidate must improve its own electrical lateral by at least the specified **shedding reduction OR pre-shedding voltage-deficit reduction** (both default to **10%**) without exceeding the allowed deterioration (default **1%**) in its complementary measure, other laterals, or system totals. This is a study-specific *experimental requirement*, not an IEEE standard or a guarantee of zero shedding. **Among annual technically acceptable candidates, lowest annual cost wins.** Unlike v6, a technically improving BESS **may increase annual cost**; it must be reported clearly rather than described as savings.
8. **Optional hard lateral exclusion.** By default **OFF**, “Exclude previously installed laterals” removes candidate buses on an already-used lateral if unresolved alternative laterals exist. This provides the experiment you requested; it can rule out a genuinely beneficial second BESS on the same weak lateral. Prefer OFF for the principal optimization, ON for sensitivity testing.
9. **Traceability.** See `annual_finalist_checks.csv`, `lateral_improvement_by_stage.csv`, expanded `sequential_stages.csv`, and `bus_ranking_by_stage.csv`, plus the Summary tab in saved HTML. All figures distinguish **pre-shedding** voltage deficit from the final voltages obtained after demand shedding.

## New Settings > Optimization controls

| Setting | Default | Meaning |
|---|---:|---|
| Minimum lateral shedding reduction | 10% | One possible annual technical acceptance condition |
| Minimum lateral voltage-deficit reduction | 10% | Alternative condition; not necessarily both |
| Maximum deterioration elsewhere | 1% | Limit worsening of other areas and complementary metric |
| Maximum annual finalists (adaptive) | 6 | First 3 verified; more only if no acceptable finalist is found |
| Exclude previously installed laterals | OFF | Optional location-diversity experiment |

Remaining battery settings are unchanged; maximum power and energy are values **entered by the user**, not hardcoded in v7.

## Windows instructions

1. Extract the new ZIP to a **new folder**. Do not mix it with v6.
2. Run `CHECK_WINDOWS_GUI.bat` to check Python/Numba/PySide6 environment (existing global Python, no venv created).
3. Run `RUN_TESTS.bat`.
4. Run `RUN_APP.bat` and import your network plus original input profile folder.
5. For comparison against v6, use the **same 8,760-hour year, same source data, same prices, same voltage/SOC limits, same GWO seed/population/iterations and battery rating catalog**. Run once with lateral exclusion OFF, and optionally again with it ON.
6. Review `annual_finalist_checks.csv`, `lateral_improvement_by_stage.csv`, `fleet_hourly.csv`, `service_by_bus.csv`, and dashboard. In particular, inspect actual discharge and charging, SOC, and both before/after shedding voltages.

## Verification and limitations

- Linux numerical regression tests: **43 passed** (`python -m unittest discover -s tests -p 'test_*.py' -q`). Python compilation, UI XML parsing, and Node dashboard JavaScript syntax also passed.
- A **synthetic 24-hour smoke test** using the user-uploaded IEEE 33-bus network workbook and 130% of its static P/Q loads (no PV) completed with both No-BESS and Bus-17 BESS. At the first hour, Bus 18 pre-shedding voltage improved **0.88391 → 0.90309 pu**, demonstrating the BESS supports its electrical path. System shedding decreased under these synthetic conditions, but another lateral's shedding increased; technical acceptance is intended to detect such trade-offs. **This does not predict the annual results.**
- **Not yet validated:** full 8,760-hour Windows GWO, real GoiEner+PV outcomes, desktop PySide6 appearance, and performance on the user's actual Windows hardware. PySide6 is unavailable in this build environment. Finalist diversity increases full-year runs and may make v7 slower than v6.
- **No reactive-power support (Q = 0):** For improved voltage control from BESS inverter VARs, a separate inverter apparent-power and control model is necessary. v7 is active-power-only and will not automatically cure a feeder that cannot be served under SOC and electrical constraints.
- No hard zero-shedding guarantee. The 10% condition checks improvement, not full feeder health; a feeder may remain severely undersupplied after an accepted installation.
- Network grouping refers to **electrical laterals**, not multiple independent utility feeders. Real voltage, shedding and economics depend on topology, load/PV chronology, and tariff/penalty assumptions.

For the performance changes, validation and cache-convergence details see **`PERFORMANCE_V8.md`**.

**Recommended experiment:** Keep the new hard-exclusion option OFF first. Check whether the new controller and sizing probes yield larger kW at Bus 17 or a location on lateral `6->26`, and compare the annual local shedding and pre-shedding voltage changes before considering exclusion as a permanent rule.
