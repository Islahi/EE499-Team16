# V11 — Paper-grounded predictive BESS control

**Based on the user-uploaded V10.2 Windows program, not GitHub code.** This is a separate folder/release. The program's home/reference is https://github.com/Islahi/EE499-Team16.git; the source was **not** fetched or modified for V11.

## What changed

V11 implements a **lightweight, centralized day-ahead LP scheduling adaptation** that follows the receding-horizon principle of Ratnam & Weller (2018) and the SOC-aware coordination motivation of Zeraati, Golshan & Guerrero (2018). This is **our EE499 engineering adaptation, not a verbatim implementation or verified replication of either paper.**

**Literature grounding**

1. Ratnam, E. L. and Weller, S. R., *Receding horizon optimization-based approaches to managing supply voltages and power flows in a distribution grid with battery storage co-located with solar PV*, Applied Energy 210 (2018), pp. 1017–1026, DOI: **10.1016/j.apenergy.2017.08.163**. The method uses future PV/load information for battery scheduling.
2. Zeraati, M., Golshan, M. E. H., and Guerrero, J. M., *Distributed Control of Battery Energy Storage Systems for Voltage Regulation in Distribution Networks with High PV Penetration*, IEEE Transactions on Smart Grid 9(4) (2018), DOI: **10.1109/TSG.2016.2636217**. SOC-sensitive coordination addresses excessive battery saturation/depletion.

**Implementation details**

- `lookahead_dispatch.py`: once every 24 hourly steps, compute the **next 24 supplied load/PV time steps** and baseline FBS voltages. Solve one **joint multi-BESS LP** with separate charging and discharging variables, exact hourly *linear SOC energy accounting*, capacity/power bounds, predicted linearized feeder voltage envelopes, and grid import/export envelopes.
- The study-specific objective penalizes **predicted voltage deficits** and grid import/export excess, estimates charging energy cost and cycling, and values remaining SOC to discourage unplanned depletion. Weights are **heuristic study parameters** and are **not published constants from these papers**.
- Installed BESSs coordinate in the LP rather than automatically sharing one global discharge request. The next day is re-planned using **actual** SOC resulting from the previous 24 hourly actions.
- The existing nonlinear **Numba FBS** verifies the joint charging/discharging command at **every actual hour**, the battery model enforces SOC/efficiency, and the existing LP network corrector handles remaining shedding/curtailment. A failed day-ahead LP falls back to V10's verified local rule for that day; fallback counts/reasons are recorded.
- BESS continues to use **active-power P only**. Reactive power, inverter kVA/Volt-VAR, replacement of the corrective LP, and probabilistic/MPC forecast errors are not implemented.
- New GUI selector: **Settings → Optimization → Sequential battery placement → Battery control**. Choose `Predictive 24h LP (recommended)` or `Legacy voltage-triggered (V10)` for comparison. The selected mode is saved in study settings and reported in simulation timing.
- **No changes** to GWO, converged FBS numerical kernel, full-year finalist coverage gate, staging logic, sequential reassessment, parallel worker limits, or GUI worker controls. Each independent candidate still runs with its own SOC history. Annual finalists still require all 8,760/8,784 chronological hours.

## Critical caveat — forecast information

The controller uses *future values from the supplied CSV* for each 24-hour horizon, without creating a new day-ahead forecast. If your CSV represents the year's known actual data rather than an independently generated forecast, the method has **perfect foresight within the provided dataset** and is an upper-bound diagnostic, **not a real operational forecasting result**. Use true day-ahead forecasts, aligned to the simulation timestamp, in a later forecasting/backtesting study to measure robustness.

No method can recharge batteries without available supply, grid capacity, and electrically safe charging opportunities. A large BESS may still remain near minimum SOC in chronically weak feeders. A successful objective LP is not proof of physical feasibility; FBS and corrective checks remain authoritative. Screening results over shortened periods are **not annual evidence**.

## Running and A/B validation

1. Extract V11 into a new folder. Run `CHECK_WINDOWS_GUI.bat`, `RUN_TESTS.bat`, then `RUN_APP.bat`.
2. Load the same network and load/PV profiles, SOC, tariffs, GWO size ranges, and random seed as V10. Keep your Windows worker counts at **6 GWO and 2 annual** on your 16 logical processor / 16 GB RAM PC.
3. Select **Predictive 24h LP** for the new run. To reproduce the historical V10 control, choose **Legacy** instead. Do not compare different battery placements or sizes as evidence of dispatch quality.
4. For a *fixed* BESS configuration without GWO, run:
   `python COMPARE_V10_V11_CONTROL.py --folder "C:\\your\\inputs" --hours 168`
   or replace 168 with 8760 for a full 2021 annual comparison. Your input folder must contain `network.xlsx`, `load_profile.csv`, `pv_profile.csv`. Ratings default to 500 kW / 50 MWh at Buses 17, 33 and 14; supply CLI flags if needed. The comparison saves JSON and never overwrites input data.
5. Compare `fleet_hourly.csv`, `service_by_bus.csv`, `annual_finalist_checks.csv`, `lateral_improvement_by_stage.csv`, and the dashboard. Look at SOC-min hours, charge/discharge, **pre-shedding voltage deficits**, shed kWh, annual cost, verified coverage, and runtime. The LP runtime/failure count appears in `dispatch_timing`.

## Validation limits

- Unit and integration tests use synthetic small networks, plus a fixed-location diagnostic on the **user-uploaded IEEE 33-bus input profiles**. Sampled comparisons are *not* claims of annual superiority.
- Python source, Qt `.ui` XML, and dashboard JS syntax can be checked here; **PySide6 and the Windows desktop GUI are not installed in this environment**. The Windows GUI must be launched and checked on your own PC.
- As with v10, optimization is not guaranteed to attain zero shedding or discover the global optimal combination. The LP is a linearized surrogate whose actions require nonlinear FBS verification.

## Measured full-year IEEE 33-bus fixed-fleet A/B result (uploaded 2021 data)

V10-style legacy and V11 predictive controls were run with identical input profiles, grid constraints, and three BESS units: Buses 17, 33, 14, each 500 kW / 50,000 kWh; SOC 20–100% initially 50%; charge/discharge efficiency 90%. These are **fixed BESS** evaluations, not GWO-placement results. Both simulations processed **8,760/8,760 consecutive hours**, converged and met post-correction network feasibility checks.

| Metric | Legacy | Predictive V11 |
|---|---:|---:|
| Annual shedding | 4,123.41 MWh | **4,001.53 MWh** |
| Accumulated pre-shedding voltage deficit | 2,774.29 pu·h | **2,692.47 pu·h** |
| Charging AC energy | 509.76 MWh | **706.82 MWh** |
| Discharging AC energy | 453.41 MWh | **613.02 MWh** |
| Annual total cost | $58,740,161 | **$57,292,643** |
| Wall time on the analysis host | 76.3 s | 87.5 s |
| Minimum-SOC hours at Buses 17/33/14 | 7077 / 7045 / 6832 | **6055 / 5868 / 5770** |

The predictive simulation completed **365 day-ahead LPs**, with **zero LP failures**. Savings are **relative to legacy control of the same fleet**, and cannot be attributed to improved GWO siting. Each simulated horizon reads *future* values from the supplied CSV—perfect foresight relative to that file. The result can overestimate benefits relative to real forecasts. All three batteries still end at 20% SOC; the controller does **not** solve chronic winter charging scarcity.


### End-to-end optimization smoke check

A complete **synthetic 8,760-hour GWO single-placement run** completed; three diverse annual finalists each had **8,760/8,760-hour coverage**, one installation was accepted on technical criteria, and a 2-worker annual verification pool worked. This test verifies integration, **not** global optimality or performance of a full IEEE 33-bus GWO search.


### Test suite and integration checks

**75 automated Python tests passed.** Windows-style `spawn` multiprocessing was tested with 6 GWO workers and 2 annual finalist workers; all 5 Qt `.ui` XML files and dashboard JavaScript parsed; Python code compiled. PySide6 runtime startup is **not available** on the analysis host and must be checked on the user’s Windows computer.
