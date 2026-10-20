# `uncertainty.py` — forecasting and scenario guide

This is the next backend module after simulation, metrics and optimization.
It generates possible future load/PV profiles and uses the same simulator for
every scenario. It does not contain another battery model or power-flow solver.

## Run and test

Run these commands from the repository root, `EE499-Team16`, not from `src`:

```powershell
python -m pip install -r .\07_Implementation\requirements.txt
python .\07_Implementation\examples\run_uncertainty.py
python -m unittest discover -s .\07_Implementation\tests -p test_uncertainty.py -v
```

Expected demo output: 100 generated, 45 selected, with 15 best, 15 worst and
15 random. Each case contains 24 future hours. It prints holdout errors for
each bus. All demo inputs are synthetic; these numbers are not real study results.

## Desktop scenario workflow and fallback

The accelerated desktop UI no longer fits ARIMA inside every optimization.
Use **Scenarios** to generate and save a scenario package first; uncertainty
optimization consumes the selected active package. Each package includes the
load/PV scenario CSV files, validation results, stress ranking, and a JSON
manifest containing the model settings and selected scenario IDs.

`UncertaintyConfig.model_mode` accepts:

- `automatic` (default): retain ARIMA only when it converges and its holdout
  RMSE improves on repeat-last-day; otherwise record and use the hourly
  residual-bootstrap fallback;
- `arima`: strict mode, retaining the previous stop-on-fit-failure behaviour;
- `bootstrap`: skip ARIMA and sample historical deviations from each hourly
  baseline.

The fallback avoids presenting a failed ARIMA fit as successful. It is still a
simple independent-residual model; it does not establish real forecast skill
from synthetic history or preserve a formal multivariate probability model.

For a 90-day/2,160-hour generation check:

```powershell
python .\07_Implementation\examples\run_uncertainty.py --forecast-hours 2160
```

For the full short demonstration, including GWO over all 45 selected cases:

```powershell
python .\07_Implementation\examples\run_uncertainty.py --optimize --cost-per-kwh 2 --cost-per-kw 3
```

The prices above are illustrative only. `--optimize` requires both coefficients;
there are no assumed real prices. This demo uses a deliberately small catalog
of four possible installations and two GWO generations. It is an integration
check, not evidence of a globally best battery. The no-BESS comparator must
still be evaluated separately before recommending an installation.

Generating a three-month scenario set and optimizing it are very different
workloads: optimization repeats 45 hourly simulations for each candidate.
Start with 24 hours, then increase the horizon. The code has no three-month cap.

## What happens in the script

1. Check historical `ProfileData`: aligned, hourly, finite P/Q values and one
   value per bus/hour. P cannot be negative. Signed Q is allowed, but this
   implementation requires zero Q wherever P is zero for its Q/P scaling rule.
2. Keep the last 24 hours aside. Learn each bus's typical active power at each
   hour of the day from the earlier training data only.
3. Fit ARIMA to the remaining variation around this hourly pattern. The
   initial configurable order is `(1, 0, 0)`: one autoregressive lag, no
   differencing, no moving-average terms. This is a working default, not a
   claim that this order is best for your data. Scaling internally improves
   numerical conditioning; this is **not WSM normalization**.
4. Forecast the held-out hours and calculate RMSE and MAPE. Compare with simply
   repeating the last training day. Nighttime zero actuals are excluded from
   MAPE, including numerical traces up to `1e-10 * max(max_actual_kw, 1)`;
   its sample count is recorded, and an all-zero series gives `None`.
5. Refit on all supplied history. Draw 100 conditional ARIMA paths, preserving
   the model's time dependence, then add back the hourly pattern. If the daily
   pattern repeats exactly, no noise is invented: the paths are deterministic
   and metadata says so. Failed ARIMA convergence raises an error.
6. Clip negative power to zero, limit PV to your supplied installed capacity,
   and keep historically all-zero PV hours at zero (including tiny numerical
   traces up to `1e-10 * max(capacity_kw, 1)`). Compute Q using each bus's
   historical hourly `sum(Q)/sum(P)` ratio. This uses supplied Q data rather
   than inventing a power factor.
7. Build ordinary `ProfileData` objects through the existing loader using
   in-memory CSV streams. No input CSV, BESS code or loader code is changed.
8. Rank/select scenarios using the agreed profile-stress rule below.
9. Optionally wrap the existing `SimulationEvaluator` in `ScenarioEvaluator`
   and give it to GWO. Each candidate is the same bus/kW/kWh installation in
   every case, with a fresh initial battery SOC for each independent case.

The ARIMA implementation uses the official statsmodels
[ARIMA model](https://www.statsmodels.org/v0.14.6/generated/statsmodels.tsa.arima.model.ARIMA.html)
and conditional future-path
[simulation API](https://www.statsmodels.org/v0.14.6/generated/statsmodels.tsa.arima.model.ARIMAResults.simulate.html).

## Variables to fill or change

| Setting | What you supply/change |
|---|---|
| Historical `ProfileData` | Your prepared historical load and available-PV CSVs, including Q, using `timestamp,bus_id,p_kw,q_kvar`. Do not use served load or already-curtailed PV as if it were original demand/available generation. |
| `forecast_hours` | Required. Use `24` for a quick check; `2160` is 90 days. Forecast begins one hour after the last historical timestamp. |
| `pv_capacity_kw` | Required dict of **total installed PV kW per profile bus**, e.g. `{4: 1200.0}`. Sum multiple units at one bus. Use actual ratings, not the historical maximum. |
| `scenario_count` | Default `100`; fewer than 45 requires smaller selection counts too. |
| `arima_order` | Default `(1,0,0)`; change only after checking held-out errors and fit warnings. |
| `validation_hours` | Default `24`; more hours provide a longer holdout. Need at least 48 training hours in addition to the holdout for the default model. Longer history is preferable. |
| `seed` | Default `42`; controls generation randomness. Same settings/data/library versions give repeatable paths. |
| `SelectionConfig` | `best_count=15`, `worst_count=15`, `random_count=15`, `seed=42`. Counts must fit the generated population. |
| Economics, BESS efficiency/SOC, bounds, dispatch | Still configured in the optimizer/simulator, not inferred by uncertainty. Supply team values for real studies. |
| Curtailment/shedding and grid/voltage limits | Still configured by `SimulationConfig`; metrics reads the simulator's actual actions. Do not fill artificial curtailment/shedding into the generated profiles. |

Example in a driver that already imports the `src` package:

```python
from pathlib import Path
from src.data_loader import ProfileData
from src.uncertainty import (
    UncertaintyConfig, SelectionConfig, ScenarioEvaluator,
    generate_scenarios, select_scenarios,
)

# Replace these paths and the PV rating with the actual study inputs.
history = ProfileData(Path("load_history.csv"), Path("pv_history.csv"))
settings = UncertaintyConfig(forecast_hours=2160, pv_capacity_kw={4: 1200.0})
generated = generate_scenarios(history, settings)
selected = select_scenarios(generated, SelectionConfig())

# Existing optimizer setup supplies network, bounds, single_evaluator and config.
# result = optimize(network, selected, bounds,
#                   ScenarioEvaluator(single_evaluator), optimizer_config)
```

Source CSVs need a common hourly timeline and rows for every represented bus
at every timestamp. Forecasting does not map raw total-system data to feeder
buses or decide how to convert missing reactive power. Those remain explicit
data-preparation tasks. Forecast profiles must use bus IDs matching your network.

## Selection: what best and worst mean

For each generated case, use original `net = total_load - total_PV`:

```text
E_net     = sum(max(net, 0)) * dt
P_peak    = max(net)
E_surplus = sum(max(-net, 0)) * dt
Ramp      = max(abs(net[t] - net[t-1]))

Stress = 0.35 * E_net_norm + 0.30 * P_peak_norm
       + 0.20 * E_surplus_norm + 0.15 * Ramp_norm
```

Feature normalization is `(value-min)/(max-min)` across the generated set;
a constant feature contributes zero. **Only scenario ranking is normalized.**
The agreed raw WSM is unchanged. Lowest 15 stress scores are "best", highest
15 are "worst", and 15 are sampled without replacement from the remaining 70.
Ties use scenario ID order, so the groups remain distinct even for identical
profiles. Best/worst describes this stress proxy, not proven operating cost or
electrical feasibility; the simulator still checks each case.

## Returned objects and optimizer score

`Scenario` contains its ID, ordinary profiles, optional probability and metadata.
`ScenarioSet` contains the list plus forecasts, model type/order/warnings,
per-bus holdout errors, source horizon and assumptions. Selection adds group,
stress features/score and original probability to each new scenario wrapper.
It does not mutate the generated set. The underlying profile objects are
shared read-only by convention: do not edit selected profiles in place.

Generated cases have equal Monte Carlo mass `1/N`. The selected set intentionally
oversamples extremes, so selected `probability` is `None`. No statistically
corrected probability reduction is claimed.

`ScenarioEvaluator` explicitly uses the arithmetic mean of raw WSM across the
stress set, regardless of optional probability labels. Cost is counted **once**,
not once per case. Energy and violation-duration metrics are case means;
voltage/SOC extremes and peak grid import are worst-case values. Individual
`scenario_evaluations` retain each case's metrics. Any failed/infeasible case
rejects the candidate immediately and records the failing ID; later cases may
then be unevaluated. Source profiles and battery state are not carried between
independent scenarios. This is not two-stage stochastic programming.

## What to check before trusting study results

- Confirm prepared historical inputs, per-bus scaling and installed PV ratings.
- Compare ARIMA with the repeat-last-day baseline. A worse ARIMA RMSE is possible;
  the program reports it instead of pretending ARIMA must be better.
- Check MAPE sample counts, warnings, generated daily curves and historical
  energy/peak/ramp ranges. A passing code test does not establish forecast quality.
- Independently test the chosen common battery on additional unseen scenarios
  and compare it with no-BESS. Feasibility in 45 cases is not a reliability guarantee.

Current model limitations: independent bus/load/PV innovations (no learned
cross-series correlation), fixed historical hourly/daylight patterns, Gaussian
errors with clipping, fixed hourly Q/P ratios, no weekday/weather/seasonal
predictors, and no parameter uncertainty or automated model-order search.
Three-month synthetic generation is an execution check, not proof that a week
of history can accurately predict three months. Real-data calibration,
distribution comparison and longer out-of-sample validation remain pending.
