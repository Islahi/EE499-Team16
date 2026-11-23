# EE499 BESS Planning Tool — V13 Coordinated P/Q OPF

## Scope

V13 is a **separate local working copy** of V12. It retains the fixed IEEE 33-bus radial network, GWO BESS placement/sizing, 72-hour SOC-aware battery scheduling, Numba Forward/Backward Sweep (FBS), bus-specific progressive shedding, annual cost metrics, GUI, and HTML results. Nothing is pulled from or pushed to GitHub. Reference repository: https://github.com/Islahi/EE499-Team16.git.

V13 adds a selectable **Coordinated P/Q OPF (V13 experimental)** dispatch mode. The existing V12 (`predictive`), V11 (`predictive_v11`), and legacy modes remain available. All GWO candidate and annual-finalist multiprocessing pathways remain enabled.

## What the new mode actually does

1. The **72-hour look-ahead LP** schedules interday BESS *active-power* (P) references, replanned every 24 h with actual SOC. The supplied future load/PV data is treated as **perfect foresight** in offline studies, not a deployed forecast.
2. An **hourly joint LP**, invoked when the reference point violates network constraints, coordinates:
   - Battery net active-power corrections (positive discharge / negative charge), within available SOC and kW limits.
   - Battery reactive-power injection/absorption (Q), subject to the inverter kVA capability polygon.
   - PV reactive-power injection/absorption and PV curtailment at each PV bus.
   - Bus-specific, power-factor-consistent load shedding with progressive priority tiers.
   - Grid import/export restrictions; bus-voltage limits; branch ampacity *where ratings exist*.
3. Electrical sensitivities are calculated around a **converged nonlinear FBS operating point**. The LP uses first-order linearized AC sensitivities and conservative inscribed 16-sided inverter capability polygons. A second linearization may be attempted if the first LP point is still infeasible.
4. The **actual nonlinear Numba FBS** solver verifies the proposed operating point. If it fails, the existing corrective controller is retained as fallback; failures and fallback counts are reported. No unverified OPF result is marked physically feasible.
5. The BESS state advances from executed **net active power**, never from unrealized LP commands. Net-P representation precludes simultaneous physical charge/discharge in the executed state.
6. When evaluating an *empty fleet* in V13 OPF mode, the same OPF control policy is used for the No-BESS baseline, to avoid comparing mismatched control policies.

### Important mathematical limitation

This is **sequential, FBS-linearized OPF**, not full nonconvex AC OPF or globally optimal AC dispatch. The 72-hour P reference and the hourly P/Q LP are consecutive coordination layers, not one multi-period P/Q OPF. Voltage/current/transformer feasibility is established by nonlinear FBS, not guaranteed by the linear model alone. As with any local LP, cost-optimality is only for its local approximation and configured controls.

## Inverter assumptions and economics

- V13 defaults to **BESS inverter kVA = 1.0 × battery power (kW)** and **PV inverter kVA = 1.0 × PV rated power (kW)**. These are *study assumptions*, not hardware nameplates. The GUI makes both multipliers configurable from 1.0 to 3.0.
- The optional **1.2× BESS / 1.1× PV** scenario was used for a separate sensitivity experiment. Higher converter kVA may enable additional reactive support, but V13 does **not separately price** inverter upsizing. Do not report those sensitivity results as a fully costed investment case.
- Reactive power is physically bounded by `P² + Q² <= S²`; converter no-load power and incremental losses due to reactive current are **not explicitly priced**, and PV Q is unavailable at night by default. BESS Q can remain possible when SOC is low if the inverter remains energized.
- Annual economic results depend strongly on the chosen **$12/kWh** value of lost load; this must be justified or varied in sensitivity analysis. In particular, large avoided-shedding costs should not be interpreted as market-revenue or guaranteed savings.
- V13 only accepts a new OPF-mode GWO placement if it improves **verified annual total cost** as well as satisfying technical/lateral feasibility checks. V12's historical placement acceptance remains untouched for comparison. Marginal energy refinement remains in place.

## Parallel and performance design

- GWO screening uses existing `ProcessPoolExecutor` multiworkers (auto/manual setting preserved).
- Finalist annual verification likewise uses existing independently configured workers; no global optimizer is moved into the GUI process.
- Numba FBS still handles the nonlinear network equations and is reused for derivatives and final physical checks.
- Feasible hours bypass the hourly OPF LP; linear constraints proven nonbinding are omitted before SciPy HiGHS.
- `RUN_APP.bat` and `RUN_TESTS.bat` default BLAS/OpenMP/MKL to one math-library thread **per worker**, unless users explicitly override environment variables, preventing nested native-thread oversubscription.
- Runtime may be longer than V12 on the same fixed BESS because the network-constrained LP is more expensive. Benchmark actual machine before raising worker counts; on a 16-thread/16-GB PC the prior recommendation remains 6 GWO and 2 finalist workers.

## How to run

1. Extract the V13 ZIP into a new directory (do not overwrite V12).
2. Use `RUN_APP.bat` on Windows; PySide6 is needed on the target PC.
3. Import the actual network and hourly load/PV files. The tested 2021 dataset was the *uploaded V12 run* using **1,200 kW per PV installation**, not the separately prepared 371.5 kW/site PV study.
4. In Settings → Optimization → Battery control, select **Coordinated P/Q OPF (V13 experimental)**. The default inverter kVA multipliers are 1.00×. Choose greater values only with an explicitly documented inverter-oversizing assumption.
5. Run a small fixed-fleet comparison first, then GWO. Keep import/export limits, tariff, load-shedding penalty, search bounds, seed, and input profiles identical for V12/V13 comparisons.
6. Run full regression tests with `RUN_TESTS.bat`. GUI startup and local Windows dependency installation must be checked on the destination PC; they were not executed in this Linux development environment.

### Command-line fixed-fleet comparison

```bat
py -3.14 COMPARE_V12_V13_OPF.py --folder "C:\path\to\inputs" --hours 168 --bess "8:1750:33250,29:250:250,16:250:250"
```

For full annual evaluation use `--hours 8760`; the CLI saves `V13_FIXED_FLEET_COMPARISON.json`. To test equipment oversizing explicitly, add `--bess-kva-multiplier 1.2 --pv-kva-multiplier 1.1`.

## Verified full-year fixed-fleet results (uploaded 1,200 kW/site dataset)

All listed simulations completed **8,760/8,760** hours, were converged and physically feasible after verified corrections. Both V13 cases use the **same** battery fleet chosen in the original V12 run: Bus 8 (1,750 kW/33,250 kWh), Bus 29 (250 kW/250 kWh), Bus 16 (250 kW/250 kWh). No V13 GWO optimization has been performed.

| Measure | Uploaded V12 optimized | V13 default 1.0× BESS/PV kVA | V13 optional sensitivity 1.2× BESS /1.1× PV kVA |
|---|---:|---:|---:|
| Annual shedding, MWh | 3,943.03 | **864.93** | 589.77 |
| Annual total cost, USD | $51.31M | **$14.74M** | $11.48M |
| Annual BESS charging, MWh | 1,380.59 | **3,214.45** | 3,525.57 |
| Annual BESS discharging, MWh | 1,127.39 | **2,612.82** | 2,864.82 |
| Absolute BESS reactive dispatch, Mvarh | Not enabled | **11,086.78** | 12,671.89 |
| Full-year run time, seconds | Whole GWO run; not directly comparable | **143.14** fixed fleet | 147.40 fixed fleet |

V13's No-BESS policy baseline is $53.63M and 4,286.14 MWh of shedding (8,760 h, 1.0× and 1.2× cases). Relative to the **same-policy V13 No-BESS baseline**, the default 1.0× case reduces shedding by **79.82%** and saves approximately **$38.90M/year** under the study's configured penalties. The default V13 cost is also $36.58M lower than the uploaded V12 selected-fleet cost, though this cross-version comparison additionally changes the controller's operating policy.

**Cost and scientific caution:** These are *modeled avoided reliability penalties*, not realized revenue. The annual objective uses **$12/kWh** for shed load. Inverter reactive losses and inverter-capability upgrades are not separately priced. The original **$14.73M upfront BESS capital cost does not decrease** in this fixed-fleet comparison. Only a new full GWO search or a controlled energy-size sweep can demonstrate less expensive installed batteries.

## Verification and research limitations

- The unmodified V12 regression suite plus V13 tests passed **85/85**.
- Spawn-style GWO and annual-finalist multiprocessing smoke tests passed, including separate worker processes.
- Fixed-fleet seven-day and full 8,760-hour simulations were completed against the uploaded 2021 profiles; figures and assumptions are stored in `V13_VALIDATION.json`.
- **No new real IEEE 33-bus GWO optimization was run with the V13 dispatch mode.** Thus the future optimal BESS **location, kW, and kWh remain unknown**. The fixed BESS used in comparisons is the one chosen by the uploaded V12 run.
- OpenDSS, with native PV and Storage objects, remains a potential **independent** future validator; not integrated or speed-benchmarked in V13. The accepted solver remains Numba FBS.
- This is an EE499-derived implementation informed by published P/Q OPF and BESS planning concepts, **not an exact reproduction** of the Sindi mobile-BESS model or Chowdhury et al.'s robust planning method.

Papers for formulation context:
- Ahmed, Sindi et al., *Optimal Sizing and Scheduling of Mobile Energy Storage Toward High Penetration Levels of Renewable Energy and Fast Charging Stations*, IEEE Transactions on Energy Conversion (2022), https://doi.org/10.1109/TEC.2021.3116234
- Chowdhury, Pilo & Pisano, *Optimal Energy Storage System Positioning and Sizing with Robust Optimization*, Energies (2020), https://doi.org/10.3390/en13030512
