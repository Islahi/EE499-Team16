# EE499 BESS Planning V12 — 72h SOC-aware dispatch and energy-efficient sizing

**Project reference:** https://github.com/Islahi/EE499-Team16.git
**Development basis:** copied local V11 source; no GitHub pull, commit, or push.

## What changes

1. **PV scenario separate from source program**: The provided `IEEE33_PV_50pct_Nominal_Demand_2021_V12_Inputs.zip` contains unchanged network/load plus solar power scaled to 371.5 kW on each of Buses 6, 12, 18, 25, 30. IEEE 33-bus nominal load is 3,715 kW; installed PV is 1,857.5 kW (**50.0% capacity-to-nominal-load penetration**), corresponding to only **7.2764% annual available PV energy / annual demanded energy** with the historical 2021 profiles. This is NOT the same as 50% annual energy penetration and is NOT Karve's exact three-PV arrangement.
2. **72h daily-replanned predictive dispatch (default `fleet_dispatch_mode='predictive'`)**: Linearized LP anticipates up to three days of future loading and PV. Only the first 24 hours are executed before recomputing from *actual* SOC. Forecast baseline FBS solutions are cached across overlapping horizons, so FBS forecast calls remain near one per hour rather than three per hour. `predictive_v11` retains the earlier 24-hour LP; `legacy` retains voltage-triggered V10 control.
3. **Direct shedding-aware scheduling proxy**: LP includes monitored-bus load shedding variables with a configurable per-kWh penalty, radial common-path active-power voltage sensitivities, import/export envelopes and soft voltage slacks. **Predicted shedding in the LP is NOT physically implemented**; every real battery decision is independently checked by Numba FBS and the existing exact corrective shedding and curtailment controller.
4. **Soft energy reserve**: End-of-horizon target is the configured initial SOC, with a penalty for shortfall; it does not prohibit discharging below the target when operationally useful. Existing minimum/maximum SOC remain hard limits.
5. **Chronological candidate SOC warm starts**: GWO evaluates 72-hour windows using a **lightweight 8,760-hour candidate-specific energy proxy** to estimate stored energy at each selected event, rather than granting initial SOC anew. Previously accepted batteries use their *actual* annual SOC from the verified current fleet. The proxy is approximate and must not be presented as an exact year-long battery dispatch; all finalists still undergo full chronological 8,760/8,784-hour network simulation before acceptance.
6. **Post-selection energy-capacity check**: At a winner's fixed installation bus and power, up to four smaller energy catalog values receive full-year FBS verification. A smaller capacity can replace the winner only when it passes the original lateral acceptance and preserves annual technical benefit within a stated tolerance, while reducing **verified annual total cost**. This does not impose an arbitrary maximum battery duration. Extra annual simulations increase runtime.
7. **Annual terminal energy is priced**: Ending inventory deficits are charged an explicit accounting value of `missing_stored_kWh / eta_charge * grid_import_tariff`. No physical terminal-SOC closure is imposed, and charging feasibility for restoration is **not** assumed. Original hourly SOC and final energy deviations remain available for reporting.

## Run on Windows

1. Extract the V12 project ZIP beside, not over, your V11 folder.
2. Run `RUN_APP.bat` in your established Python environment (Numba/SciPy/PySide6 installed).
3. In the Settings dialog choose **Predictive 72h LP (V12 recommended)** or **Predictive 24h LP (V11 comparison)** for fixed-configuration A/B testing. Existing worker controls remain unchanged.
4. Load `network.xlsx`, `load_profile.csv`, `pv_profile.csv` from the **new 50%-of-nominal-demand PV dataset**. Do not multiply the solar CSV again.
5. Start with a *fixed BESS* comparison, then run GWO with the same initial candidate catalogs, seed, cost inputs, no-export policy and import limit as your previous tests. Expect GWO screening to take longer because each event is now 72 hours and each accepted stage can test additional annual energy capacities.
6. Use `python -m Validation.Controller_Comparisons.COMPARE_V11_V12_CONTROL --folder "C:\\path\\to\\new_inputs" --hours 8760 --buses 17 --power-kw 500 --energy-kwh 50000 --output results_v12.json` to compare both controllers without rerunning GWO.

## Validation and engineering limitations

- Automated regression tests: see `tests/test_v12_soc_72h.py` and existing suites. Qt launch on Windows still requires user validation; this Linux builder lacks PySide6 GUI runtime.
- Baseline power-flow is radial balanced forward/backward sweep. The scheduling LP uses a *linearized sensitivity* approximation, not AC OPF. The existing nonlinear network check and bus-specific LP corrective actions are the authoritative physics.
- LP uses independent nonnegative charging/discharging components with a combined rating constraint and positive cycling costs. Simultaneous charge/discharge is discouraged and **diagnosed**, but not strictly excluded through binary variables. Executed net P still satisfies `step_bess` limits. Future improvement may use a sign-constrained/MILP model if overlap is non-negligible.
- Proxies and controller see actual future hourly profiles during **offline simulation**. This is **perfect foresight** relative to the supplied CSV, not an evaluation of imperfect forecasts.
- The 72-hour reserve and shed estimates are engineering choices inspired by receding-horizon voltage/energy scheduling studies; **not a reproduction** of Karve's IGWO or any publication's controller. See DOI `10.1016/j.apenergy.2017.08.163` and `10.1109/TSG.2016.2636217` for background, not proof of numerical optimality of this custom implementation.
- An energy-capacity result at the upper catalog bound remains possible if it delivers material annual benefit; no rule forces a smaller battery.
- Results from V12 and V11 have different objective accounting for terminal deficits; for controller-only comparisons, compare technical MWh and SOC first and value both using the same V12 metrics.

## Completed fixed-BESS full-year validation on 50% nominal-demand PV scenario

With **Bus 17 / 500 kW / 50,000 kWh**, grid import limit 7,500 kW,
export 0 kW, SOC 20%–100% / initial 50%, efficiency 90% charge and discharge,
2021 8,760-hour input profile and identical V12 economic accounting:

| Metric | V11 24h control | V12 72h control |
|---|---:|---:|
| Full-year hours processed | 8,760 | 8,760 |
| Converged/feasible | Yes | Yes |
| Annual shedding | 5,615.345 MWh | 5,588.977 MWh |
| Annual battery charging | 65.773 MWh | 64.049 MWh |
| Annual battery discharge | 66.776 MWh | 65.380 MWh |
| Hours at minimum 20% SOC | 7,297 (83.30%) | 6,213 (70.93%) |
| Ending SOC | 20% | 20% |
| Annual total cost with terminal inventory accounting | $72,310,512.50 | $71,996,788.41 |
| Predictive LP failures | 0 | 0 |
| Forecast FBS calls | 8,760 | 8,760 (cached overlapping horizons) |
| Fixed-BESS wall time (Linux) | 123.64 s | 161.16 s |

This is **0.47% less annual shedding**, with **1,084 fewer hours at minimum SOC**
but **~30% longer runtime**. It does not prove that the V12 optimizer picks
smaller BESS or that severe energy scarcity disappears; an actual full-year
IEEE 33-bus GWO run is still required on the user's Windows setup.

Additional integration smoke: synthetic 8,760-hour sequential GWO completed
all three annual finalists, accepted one unit, and exported its results.
The `81` automated unit/regression tests passed on the Linux build environment.
