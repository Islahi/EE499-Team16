# Term 2 Implementation

Tasks **10, 12 and 13** implemented on 6 Oct 2026 against
`02_Reports/Working/Planning/TERM2_SOFTWARE_DESIGN_SPEC.md`.

## Run

Python 3.10 or newer. From the repository root:

```bash
cd 07_Implementation
python -m pip install -r requirements.txt
python -m src.main
python -m unittest discover -s tests -v
```

Network/FBS and their unit tests use the Python standard library. Pandas is
needed to import/use the existing profile loader and simulation skeleton.
The demo uses the guide's five-bus verification case with 180 kW PV at bus 4.
It prints convergence, bus voltages, slack power and total losses.

## Code and status

Member 1's 10 Oct FBS submission is preserved separately with unchanged originals,
a portable reproduction driver, results, and a task assessment:
[`Contributions/Member_1/2026-10-10_FBS/README.md`](Contributions/Member_1/2026-10-10_FBS/README.md).
It supports small-case Tasks 14/15 and a Task 19 draft; Tasks 17/18 still need
profile/interface integration and failure handling. It does not replace the
production modules or supply Task 16.

| Module | Current scope |
|---|---|
| `src/network_model.py` | Bus/Line/Load/PVUnit dataclasses, network validation, radial ordering |
| `src/network_cases.py` | Prepared five-bus feeder and separate guide verification cases |
| `src/fbs.py` | OperatingPoint, FBSConfig, PowerFlowResult, one-step run_fbs |
| `src/main.py` | Runnable fixed-input demo and base operating-point fixture |
| `src/data_loader.py` | Existing team implementation, preserved unchanged |
| `src/bess.py`, `src/simulation.py`, `src/metrics.py` | Importable skeletons; operations raise NotImplementedError |
| `src/optimizer.py`, `src/uncertainty.py` | Future V4/V5 placeholders |
| `src/results.py`, `src/ui.py` | Future results/UI placeholders |

## Network cases

- `build_5_bus_case(loads=None, pv_units=None)` represents the prepared **11 kV,
  10 MVA, 1→2→3→4→5** feeder. No arguments gives an unloaded topology because
  the published data contains no individual bus loads or PV ratings. Supply
  explicit `Load` and `PVUnit` lists for a loaded study. Default 60 Hz is a
  development configuration; frequency is not used by the supplied series R/X
  power-flow model. Grid-strength equivalents, transformers and shunts are not
  represented in the current design.
- `build_guide_3_bus_case()` and `build_guide_5_bus_case()` are fixtures from
  `Validation/FBS_Step_by_Step_Guide.pdf`. The latter is a **12.66 kV, 1 MVA,
  branched** feeder and is a distinct case from the prepared network.

## Public solver interface

```python
from src.network_cases import build_guide_5_bus_case
from src.main import base_operating_point
from src.fbs import FBSConfig, run_fbs

network = build_guide_5_bus_case()
point = base_operating_point(network)
result = run_fbs(network, point, FBSConfig())
if not result.converged:
    raise RuntimeError(result.message)
print(result.voltage_mag_pu)
print(result.total_loss_p_kw)
```

`base_operating_point()` is a demo fixture that uses rated PV output; a later
simulation layer will assemble actual profile values. All six OperatingPoint
mappings must include every bus, with explicit zeros. Load is positive demand,
PV positive generation, BESS positive discharge and negative charging.
Powers are three-phase kW/kvar, voltage bases line-to-line kV, line impedances
per-phase ohms and public current magnitudes A. Branch quantities follow the
derived slack-to-leaf direction even if input line endpoints are reversed.
`loads_by_bus()` and `pv_by_bus()` return bus-to-list mappings, including empty
lists, so multiple equipment objects at one bus can be aggregated.

FBS uses constant complex-power demand and flat initialization. Convergence
is `max(abs(V_new - V_old)) <= tolerance`, default 1e-6 pu, maximum 100 sweeps.
Optional history contains the initial flat start followed by each completed
sweep. `iterations` counts completed sweeps. Failed/non-converged results are
for diagnosis and must not be accepted by downstream simulation/optimization.
Voltage/thermal limit enforcement, curtailment, shedding and dispatch belong
to later tasks; convergence alone does not certify operational feasibility.

## Verification

See `Validation/FBS_Verification_Notes.md`. Twelve unit tests cover manual
first-sweep values, guide outputs, an analytic two-bus solution, power balance,
input validation, reversed lines, slack demand, injection signs and failures.
For the additional independent nodal-equation check:

```bash
python -m pip install -r Validation/requirements.txt
python -m Validation.verify_nodal_reference
```

This checks the implementation; it does not complete formal Chapter 5
validation or mark other scheduled tasks complete.
