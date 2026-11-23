# V15 — Dr. Sindi SESS Full Backend Integration (`fleet_dispatch_mode = "opf"`)

This release integrates the Stationary Energy Storage System (SESS, Eq. 53) planning and dispatch methodology from Ahmed, Sindi, Azzouz, & Awad (*Sustainable Energy, Grids and Networks*, 2023) directly into the `opf` backend mode while keeping your exact optimization objective (**minimizing annualized BESS CAPEX/O&M + Load Shedding + PV Curtailment + Grid Import/Export cost**), V14 2–12 h duration limits, fixed radial feeder physics, and desktop UI unchanged.

## What changed in the backend

1. **Coupled P/Q Look-Ahead LP (`src_accelerated/lookahead_dispatch.py`, `src_accelerated/voltage_dispatch.py`, `src_accelerated/multi_bess.py`):**
   - Added radial $X$-path reactive voltage sensitivity (`x_sensitivity`) alongside $R$-path sensitivity in `VoltageSupport`.
   - When `fleet_dispatch_mode == "opf"`, `DayAheadFleetPlanner` runs with `coupled_pq=True`, co-optimizing BESS active power ($P$), BESS reactive power ($Q$), PV reactive power ($Q$), and load shedding in the same multi-period LP subject to an inscribed inverter capability polygon ($P^2 + Q^2 \le S^2$).
   - Both planned $P_{ref}$ and $Q_{ref}$ are passed into `JointOPFController`.
2. **Damped Sequential Linearized AC OPF + Active Voltage Flattening (`src_accelerated/joint_opf.py`):**
   - Increased `linearization_iterations` from 2 to 4 with trust-region step-halving (`alpha = 0.5, 0.25`) if an undamped linear step fails Numba FBS convergence, reducing unnecessary fallbacks to load shedding.
   - Added secondary voltage-deviation flattening $\sum |V_i - 1.0|$ (Dr. Sindi Eq. 17) strictly subordinate to shedding ($12/kWh) and curtailment ($0.07/kWh) penalties, actively pulling voltages closer to 1.00 p.u. inside the hard 0.95–1.05 p.u. guardrail (Eq. 30).
3. **K-Means Representative-Day Scenario Clustering (`src_accelerated/sindi_scenarios.py`):**
   - Clusters the full annual chronology into probability-weighted real 24-hour medoid days (combining load, PV, and baseline electrical stress features) for unbiased annualized scenario screening during GA search.
4. **Joint Multi-BESS Stationary GA + Full 8,760h Verification (`src_accelerated/sindi_ga.py`, `src_accelerated/sequential_multi.py`):**
   - In `opf` mode, `optimize_sequential_multi` now routes to `_optimize_sindi_joint_sess`, encoding up to `max_units` (1–3) stationary batteries simultaneously in a single GA chromosome with roulette-wheel selection, scattered crossover, electrically ordered Gaussian mutation, stall-generation stopping, and V14 2–12 h duration repair.
   - Top diverse GA finalist fleets are independently verified on the **uninterrupted 8,760/8,784-hour chronological year** via nonlinear Numba FBS; the lowest verified annual total cost fleet strictly beating No-BESS is selected.

## How to run on Windows

1. Extract this ZIP into a new folder (do not overwrite V14.1).
2. Run `RUN_TESTS.bat` to verify all regression + V15 tests pass with your local Numba/Python environment.
3. Run `RUN_APP.bat`, go to **Settings → Optimization → Battery control**, and select **Coordinated P/Q OPF** (`opf` mode) to run the new Dr. Sindi SESS backend.
4. Historical modes (`predictive`, `predictive_v11`, `legacy`) remain intact for A/B comparison.
