# BESS Planning Tool

Start with the [user guide](BESS_Planning_Tool_User_Guide.md) for the Windows launcher,
GoiEner folder import, solar input formats, technical simulations, annual optimization,
and saved study migration.

The desktop application in `src_accelerated` uses Numba CPU FBS. Sector-sum demand
forecasts use CalendarRidge, XGBoost, and LightGBM. The common PV forecast uses
XGBoost trained on historical modeled power. Use the repository's existing Windows
Python 3.14 installation with the pinned dependencies in `requirements-accelerated.txt`.

An imported study selects its first 24 hours while retaining the full history for
later selections and forecast training. Annual economic optimization requires a
complete calendar year and explicit import and export tariffs. The annual objective
is reported in USD/year and includes ownership, net grid purchases, curtailment,
unserved energy, and any priced terminal energy difference.

The equal-SOC policy bounds each dispatch request so that the remaining hours can
restore the starting SOC at the configured battery charge and discharge limits.
Network and reserve constraints still apply to every hourly step. The terminal
check marks a candidate infeasible if this schedule fails to close. The alternate
priced policy accounts for the energy difference in the annual objective and
requires an explicit positive replacement price. The dispatch policy evaluates
each candidate using rules for local PV and demand rather than optimizing the
entire annual operating schedule.

Run the regression suite from `07_Implementation` in PowerShell:

```powershell
python -m pip install -r requirements-test.txt
$env:QT_QPA_PLATFORM = 'offscreen'
python -m pytest tests -q -ra
```

The suite uses the repository's `Validation` directory for archived C1 and C2
fixtures. Set `EE499_VALIDATION_ROOT` to the extracted Validation directory if
it is stored separately. Missing fixtures are reported as explicit skips.

## Network-guided fleet planning

In Settings, enable **Network-guided fleet study** under **Battery search**. Choose
one, two, or three sites, or compare all three against one shared No-BESS baseline.
Equal total capacity uses the entered fleet kW and kWh exactly. Flexible sizing
uses them as upper limits. Set the existing per-unit rating ranges and increments
so each requested fleet count can reach the budgets. A 250 kW and 250 kWh grid with
matching minima supports the 1,250 kW and 6,250 kWh comparison. Leave the fixed
installation cost at zero for the original cost assumptions. A configured fixed
cost applies once per site. For a manual fleet, enter `bus,kW,kWh` for each battery
in the **Manual fleet** field, with a semicolon between units. Turn off **Manual
BESS** to run the original No-BESS simulation.

Grid reserve is one requirement against the peak of the full selected horizon.
Shares are allocated by each site's discharge power and reserve energy available
at its initial and target SOC. The reserve reference is held constant within
representative windows. Multi-unit dispatch tests a shared vector of injections
then checks the corrected Numba FBS solution. Its rolling scheduler conserves
an individual terminal target when overlapping electrical charging envelopes
could otherwise promise the same headroom to several units. A single unit with
default fleet options uses the original one-battery scheduler.

Screening uses bounded, corrected Numba FBS probes at the most heavily shed and
PV-rich or low-import baseline hours. Its published scores combine shedding relief
(70%), weak-bus voltage support (20%), and charge acceptance (10%). The score
has placement value for the tested hours. The export records component scores,
branch paths, exclusions, and the actual injections. GWO retains finalists for
both reliability and economics, including a small exploration quota. The archived
bus-14 design is a comparison candidate when the chosen catalog and fleet limits
allow it. Annual winners always come from chronological Stage B evaluations.
Reliability ranks unserved energy, then cost, subject to optional budget limits.
Economics ranks the existing annual cost. Stage A resets SOC at separate windows
and uses an annual cost estimate for screening. Stage B uses the exact selected
time grid. There is no automatic rerouting of a failed finalist into a feasible one.

From `07_Implementation` on Windows, use the existing Python installation and an
exported run containing `dashboard_run.json` and `inputs/`:

```powershell
python -m src_accelerated.fleet_cli 'C:\Path\To\run_001' '.\fleet_2021' --reserve-percent 10 --workers 4
```

Use `--hours 168 --start 2021-07-01` for a reduced comparison. Add `--full-horizon`
to evaluate every sampled GWO candidate over the selected time grid, and
`--capacity flexible` for flexible sizing. `--help` lists the remaining settings.
The run includes `fleet_comparison.csv`, `location_screening.csv`,
`branch_severity.csv`, full Stage A/B records in `fleet_experiment.json`, and
per-unit time series and cost summaries for exported fleet replays. The offline
dashboard opens the fleet comparison under **Analysis → Optimization** and
per-unit plots under **Analysis → BESS**.

### Reduced IEEE 33-bus validation

The July 1, 2021 snapshot and seven-day window used the archived 6 MW PV case,
0.95–1.05 pu limits, 7,500 kW import cap, zero export, and reserve at 10 percent
of the selected comparison horizon's peak. Each installed fleet had a total
1,250 kW and 6,250 kWh. In the first 24 hours, verified designs for 0–3 units all
shed 6.771 MWh. Over seven days, the baseline shed 34.859 MWh, the screened
two-unit design at buses 18 and 20 shed 30.361 MWh, and the unfiltered two-unit
design at buses 11 and 31 shed 31.120 MWh. Single-unit finalists failed terminal
SOC closure in that window. A separate seven-day run starting July 2 at 12:00
verified the archived single unit at bus 14 and a two-unit design at buses 18
and 20. Shedding was 33.525 MWh with No BESS, 28.622 MWh with one unit, and
30.358 MWh with two units.

On the July 1 seven-day comparison with six wolves, three generations, seed 42,
and one worker, the measured timings were:

| Metric | Screened | Unfiltered |
|---|---:|---:|
| Search wall time, including shared baseline and site diagnostics (s) | 41.81 | 72.26 |
| Candidate CPU time (s) | 35.16 | 70.75 |
| Candidate corrective controller time (s) | 25.54 | 53.65 |
| Candidate FBS calls | 41,506 | 75,021 |
| Candidate-hours | 2,688 | 5,544 |
| Peak worker working set (MiB) | 241 | 241 |

These measurements cover the reduced search. IEEE 33-bus annual fleet
optimization remains a separate run using the complete snapshot.
