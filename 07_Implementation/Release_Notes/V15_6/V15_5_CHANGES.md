# V15.5 — Full-Bus Sindi-Style Static BESS Optimization

## Scope and baseline
Based on **V15.4 Sindi SESS Joint GA**. This version changes search, candidate-screening/annual verification, optimizer Settings, inverter-kVA reporting, and safe results export. The active strict Sindi operating equations, 24-hour SOC restoration, FBS network verification and economic inputs are retained.

> **Research provenance:** This is a **static** BESS adaptation of the Ahmed–Sindi approach. It is not an exact simulation of the original **mobile** MESS paper, whose vehicle routing, monthly relocations, PV/wind/FCS expansion and transportation economics are intentionally not represented.

## 1. Full eligible-bus search
- In strict Sindi Joint GA, **no `screen_buses()` weakest-bus gate or `balanced_shortlist()` top-third filter** precedes optimization.
- All user-selected eligible non-slack buses are available to initial GA chromosomes and to global GA mutation, including electrically distant laterals.
- Electrical-lateral grouping and cumulative line-impedance distance order local mutations; a 35% bus-gene mutation probability uses a global jump to a randomly eligible bus.
- The optimization record includes eligible bus IDs, GA-visited bus IDs and both counts. **Eligible does not mean every location was actually evaluated.** Increase GA population/generations as needed.

## 2. Faster numerical computation and final checks
- Preserve Numba FBS and Windows `spawn`-compatible multiprocessing for GA screening; worker limit 1–8.
- Reduce strict daily scheduler binary count by using one charge/discharge-mode flag per battery-hour instead of two. Enforces `C ≤ Cmax Z` and `D ≤ Dmax (1−Z)` with the same physical constraint.
- Match representative-day screening CAPEX to annual verification (inverter **kVA**, not kW; **real discounted CRF**, not straight-line). Avoid ranking candidates with an inconsistent economic formula.
- GA screens 12 weighted 24-hour medoid scenarios (288 hours/candidate for a full year); independently stress-screens up to six distinct days (load/PV extremes and seasonal high net demand); stress days do not overlap the training medoids.
- Check the best surviving fleet for the complete 8,760/8,784 chronological hours **first**. If it fails technical requirements or annual savings, check the next ranked fleet until one passes or the configured fallback budget is exhausted (default **3**, previously six annual finalists before selection).
- Full-year verification remains mandatory to claim annual results. Early stop on failed technical feasibility when possible. This reduces **routine** repeated annual simulations, but will not guarantee faster runs if most candidates are infeasible or the GA explores more designs.
- No comparison with alternate controller modes is automatically run.

## 3. Paper-style operating requirements kept
- Strict Sindi mode: charge and discharge never simultaneously; scheduled and executed active dispatch checked; positive BESS Q bounded by actual discharge: `0 ≤ Q ≤ P_dis tan(acos(PF_min))`; configured inverter kVA also constrains apparent power; battery SOC bounded and reset to its starting level every day; 95% charge and discharge efficiencies at paper-reference settings.
- IEEE 33-bus static network, fixed PV locations, FBS nonlinear voltage verification and the solver's control and failure audits remain.
- Investment cost includes energy (USD/kWh) and converter (USD/kVA), using the configured discounted real capital recovery factor and annual O&M. Grid tariffs, shedding and curtailment penalties remain configurable.

## 4. Dashboard, results, and GUI
- Added inverter apparent capacity in kVA beside power kW, energy kWh, and E/P duration. The hourly chart estimates inverter apparent dispatch as `sqrt(P²+Q²)` kVA.
- Dashboard now presents Joint GA finalists, eligible/visited buses, holdout screening, and complete-year verification. Old GWO-style weak-bus rankings are not presented for strict Joint GA runs.
- `fleet_units.csv` includes `inverter_rating_kva`. Summary capital-cost explanations distinguish discounted CRF and kVA-converter investment.
- Fixed the earlier strict-run results exporter `sindi_strict_pf_min` missing-key failure with safe recorded-config fallback; `sindi_daily_audit.csv` retains SOC and PF compliance.
- GUI now displays **GA population, generations, crossover and mutation** in strict mode; all four controls feed the actual Joint GA backend (previously some GA settings were hidden, and two were inert). Default mutation 0.20.
- Saved numerical run registration and asynchronous dashboard creation from V15.3/V15.4 are retained.

## 5. Test coverage and limitations
- Python unit/regression suite: **127 passed; 21 subtests passed** (warnings unrelated to validation failure).
- Real 48-hour **synthetic radial feeder** strict Sindi simulation + exporter + daily SOC/PF audit + regenerated HTML: passed; battery restored SOC each day, zero PF violations.
- Python syntax (`compileall`) and dashboard JavaScript syntax (`node --check`): passed.
- **Not tested:** native Windows/PySide6 GUI (Qt package unavailable in the test runtime), full 8,760-hour V15.5 optimization, or empirical runtime savings against V15.4. For a full report, run annual IEEE 33-bus study on the same input/settings and retain `session.log`, `sindi_daily_audit.csv`, `fleet_units.csv` and `metrics.csv`.
- Best-first full-year verification verifies the **first economically acceptable** annual candidate; it does not guarantee the annual global optimum among unverified GA candidates.

## Research reference
- Ahmed, Sindi, Azzouz and Awad (2022), *Optimal Sizing and Scheduling of Mobile Energy Storage Toward High Penetration Levels of Renewable Energy and Fast Charging Stations*, DOI: `10.1109/TEC.2021.3116234`.
- Project repository: https://github.com/Islahi/EE499-Team16.git
