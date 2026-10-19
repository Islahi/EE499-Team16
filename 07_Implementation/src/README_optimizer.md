# Understanding `optimizer.py`

[optimizer.py](optimizer.py) searches battery location, power rating and energy
capacity using Grey Wolf Optimization (GWO). It evaluates each choice through
the actual simulation and metrics modules.

## Run it from the repository root

When PowerShell shows `PS C:\Users\ISLAHI\Documents\EE499-Team16>`, run:

```powershell
python .\07_Implementation\examples\run_optimization.py --cost-per-kwh 2 --cost-per-kw 3 --compare-exhaustive
python -m unittest discover -s .\07_Implementation\tests -p test_optimizer.py -v
```

The first command runs a synthetic 24-hour guide-feeder case with an eight-choice
BESS catalog, followed by a full check of that same catalog. The second runs
15 optimizer tests. The coefficients 2 and 3 are illustrative arithmetic inputs,
not researched prices. Replace them when the team supplies suitable values.

The example prints the best sampled battery, its raw score, cost, curtailment,
shedding, voltages, history, runtime and evaluator-call count. It also prints
the no-BESS baseline. With these illustrative coefficients, the baseline score
is approximately 1620.28 and the best battery score is approximately 2141.40.
Lower is better, so the example does not justify buying that battery. It
demonstrates that the search and evaluation path work.

## How the pieces connect

```text
Allowed buses / powers / capacities + optimizer settings
                           |
                     GWO positions
                           |
                 BESSCandidate [B, P, E]
                           |
                 SimulationEvaluator
                   |               |
          simulate_timeseries   evaluate_results
                           |
                Raw weighted objective
                           |
            CandidateEvaluation -> next GWO generation
                           |
                  OptimizationResult
```

No power-flow or battery energy equations are duplicated in the optimizer.
`SimulationEvaluator` constructs the public battery configuration, runs the
simulation, obtains metrics and calculates a score.

## Objects and functions

| Name | Responsibility |
|---|---|
| `BESSCandidate` | One proposed installation: `bus_id`, `power_rating_kw`, `energy_capacity_kwh`. |
| `OptimizationBounds` | Finite lists of permitted bus IDs, power ratings and energy capacities. |
| `BESSParameters` | Fixed efficiencies and SOC settings shared by candidates. Builds each candidate's `BESSConfig`. |
| `ObjectiveWeights` | Configurable cost/curtailment/shedding weights, default 0.50/0.25/0.25. |
| `weighted_sum()` | Calculates the raw objective from available metrics. |
| `SimulationEvaluator` | Evaluates a candidate through simulation and metrics under a supplied dispatch policy. |
| `CandidateEvaluation` | Stores the candidate, objective, feasibility, metrics and diagnostic message. |
| `OptimizerConfig` | Population, iterations, seed, caching and optional initial candidates. |
| `OptimizationResult` | Best sampled feasible result, history, evaluated candidates and search metadata. |
| `optimize()` | Runs the GWO search. |
| `exhaustive_search()` | Evaluates every combination as an independent small-case reference. |

Helpers beginning with `_` handle catalog conversion, evaluator checks, leader
movement and result assembly. Other program modules should use the public
interfaces above.

## What to fill or change

### Search catalogs

```python
from src.optimizer import OptimizationBounds

bounds = OptimizationBounds(
    allowed_bus_ids=(2, 4),
    power_ratings_kw=(100.0, 200.0),
    energy_capacities_kwh=(500.0, 1000.0),
)
```

This defines `2 * 2 * 2 = 8` possible installations. GWO returns values from
these catalogs, not arbitrary sizes between entries. Catalog values are sorted,
must be unique and cannot be empty. Bus IDs must belong to the selected
network; they need not be consecutive. Power and capacity must be positive.

The no-BESS case is a separate baseline, not a candidate with zero capacity.
If it has the lower score, report that comparison rather than claiming a
benefit from the best available positive battery installation.

### Economic and battery parameters

```python
from src.metrics import EconomicConfig
from src.optimizer import BESSParameters

# Illustrative values for demonstrating the API only.
economics = EconomicConfig(cost_per_kwh=2.0, cost_per_kw=3.0, currency="SAR")
battery = BESSParameters(
    eta_charge=0.95,
    eta_discharge=0.95,
    soc_min=0.1,
    soc_max=0.9,
    soc_initial=0.5,
)
```

Both prices are required for the built-in evaluator. No missing price is
silently replaced with zero. Efficiencies must also be supplied explicitly;
the example's 95% per direction does not settle the project's unresolved
interpretation of the 85% baseline value.

Each candidate gets its own nominal power/energy/bus. Charge/discharge limits
default to that candidate's nominal power, avoiding an inherited limit from
another battery size. SOC/efficiency settings stay fixed across candidates.
`bess.py` is used unchanged.

### Dispatch and simulation settings

```python
from src.optimizer import SimulationEvaluator
from src.simulation import SimulationConfig

def dispatch_policy(index, profile, state):
    net_load_kw = sum(profile.p_load_kw.values()) - sum(profile.p_pv_kw.values())
    return net_load_kw - 400.0  # Demonstration net-load target.

evaluator = SimulationEvaluator(
    economic_config=economics,
    battery_parameters=battery,
    dispatch_policy=dispatch_policy,
    simulation_config=SimulationConfig(
        grid_import_limit_kw=400.0,
        grid_export_limit_kw=0.0,
    ),
)
```

The policy is required, because searching battery size with an accidentally
idle battery would not evaluate its intended operation. The sample targets
400 kW before losses; positive requests discharge and negative requests charge.
The existing simulator clips requests for power, SOC, reserve and network
conditions and records actual curtailment/shedding. This policy is a simple
study input, not a separately optimized dispatch schedule.

The 400 kW import cap and zero export cap above are demonstration settings,
not verified project network ratings. The library's default simulation settings
have unlimited import/export, 0.95–1.05 pu voltage bounds and the agreed reserve.
Keep settings, profiles and policy consistent between baseline and candidates.

### Search controls

```python
from src.optimizer import OptimizerConfig, optimize

settings = OptimizerConfig(
    population_size=12,
    max_iterations=20,
    seed=42,
    cache_evaluations=True,
)

result = optimize(network, profiles, bounds, evaluator, settings)
```

| Setting | Meaning |
|---|---|
| `population_size` | Number of wolves evaluated in a generation; minimum 3. |
| `max_iterations` | Number of evaluated generations; minimum 1. |
| `seed` | Reproducible local random generator; does not modify Python's global random state. |
| `cache_evaluations` | Reuse repeated candidate scores inside this search. |
| `initial_candidates` | Optional tuple of `BESSCandidate` starting points from the catalog. |

The library defaults are 12 wolves and 20 generations. The small command-line
demo uses 8 wolves and 8 generations for speed. Its corresponding flags are
`--population-size`, `--iterations` and `--seed`.

Without initial candidates, the pack includes the smallest and largest catalog
combinations plus random positions. Explicit initial candidates replace pack
slots. Caching assumes the evaluator/policy is deterministic for identical
inputs. Cache scope is one search; full hourly traces are not stored there.

## How GWO moves the candidates

GWO uses three leading solutions (alpha, beta and delta) to update the pack.
The coefficient controlling exploration decreases toward zero as the search
progresses. The mathematical reference is the
[author's GWO reference code](https://github.com/alimirjalili/GWO/blob/master/GWO.m).

This implementation adapts those equations to discrete catalogs. It uses
positive one-based catalog coordinates, clips them to their bounds, and rounds
to a catalog entry for evaluation. Positive coordinates avoid an absorbing
zero boundary when several leaders choose the first catalog value. Catalog
order is a numerical search device, not a physical distance between buses.

The three best distinct feasible candidates seen so far are retained as leaders.
If fewer than three exist, available leaders are repeated. If none exist yet,
the next pack is resampled rather than reporting an invalid solution. The
best-so-far history therefore cannot worsen, but a flat history alone does not
prove the global optimum was found.

## Objective and failure handling

```text
J = 0.50 * BESS investment cost
  + 0.25 * curtailed PV energy
  + 0.25 * shed load energy
```

Cost comes from the two-coefficient model; the energies use kWh over the
supplied horizon. This uses the agreed raw WSM with no normalization. Its
nominal weights mix currency and kWh, so display the component values beside
the score. Do not silently change units or horizon between comparisons.

Weights can be changed with `ObjectiveWeights`; values must be nonnegative
and sum to one. Every component must be available even if its weight is zero.
There is no extra loss, emissions, thermal or operating-cost term.

Failed/incomplete FBS runs and remaining voltage/grid/reserve violations cannot
win: their fitness is infinity. A run that shed demand can still be electrically
feasible; its shed energy contributes to the objective. Unexpected programming
or profile-input errors propagate so they can be corrected.

## Reading the result

| Field | Meaning |
|---|---|
| `success` | At least one sampled feasible candidate exists. |
| `best_candidate` | Best sampled installation, or None if none were feasible. |
| `best_objective` | Its raw score, or infinity on failure. |
| `metrics` | Its performance summary, or None on failure. |
| `convergence_history` | Best sampled feasible score after each generation; infinity until one is found. |
| `iterations` | Evaluated generations for GWO. |
| `evaluations` | Actual evaluator results; repeated cached requests do not add calls. |
| `metadata` | Algorithm, seed, population, catalog size and evaluation counts. |
| `message` | Human-readable success/failure status. |

Rerun `simulate_timeseries` with the selected battery configuration and the same
policy/settings if you need its full hourly traces. The optimizer keeps metrics
summaries to avoid caching a three-month trace for every candidate.

## Exhaustive comparison and current scope

`exhaustive_search(network, profiles, bounds, evaluator)` tries every catalog
combination independently. It returns the same result structure. Its history
and iteration count refer to evaluated candidates rather than generations;
`metadata['history_axis']` identifies the distinction.

Use it on a small catalog to check the GWO gap. GWO does not secretly perform
an exhaustive pass, and need not match it in every search. The provided seeded
tests cover a known optimum and a real simulator-backed catalog comparison.

The built-in `SimulationEvaluator` accepts one `ProfileData`. For generated or
selected cases, wrap it in `uncertainty.ScenarioEvaluator` and pass a
`ScenarioSet` to the same GWO entry point. See
[`README_uncertainty.md`](README_uncertainty.md): it uses an explicitly
equal-weight stress-set mean and rejects a candidate if any case is infeasible.
No GWO equations change. There is no optimal hourly-dispatch solver, terminal-SOC
constraint or real-data engineering validation added by this module.

To change the demo catalog from the repository root:

```powershell
python .\07_Implementation\examples\run_optimization.py --cost-per-kwh 2 --cost-per-kw 3 --bus-ids 2 3 4 5 --power-ratings-kw 100 200 --energy-capacities-kwh 500 1000 --population-size 12 --iterations 20 --seed 42
```

Other demo flags include `--hours`, `--pv-rating-kw`, `--grid-import-limit-kw`,
`--grid-export-limit-kw`, `--dispatch-target-kw`, `--eta-charge`,
`--eta-discharge` and `--currency`. All demo defaults are visible in
[run_optimization.py](../examples/run_optimization.py). Start with a short
horizon and small catalog before requesting a three-month optimization.
