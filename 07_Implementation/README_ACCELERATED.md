# BESS Planning Tool

For the current V15.6 app, see the [implementation README](README.md). The workflow below records earlier accelerated development and replay experiments.


Start with the [user guide](BESS_Planning_Tool_User_Guide.md) for the Windows launcher,
GoiEner folder import, solar input formats, technical simulations, annual optimization,
and saved study migration.

The desktop application in `src` uses Numba CPU FBS. Sector-sum demand
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

## Single-BESS study workflow

1. **Import data** and select the IEEE 33-bus workbook, GoiEner case folder, PV history and installed PV rows. The workspace header shows active branches, installed PV, study hours, feeder limits and cost inputs. Use **Study interval → Full calendar year** for annual optimization.
2. Under **Settings → Network constraints**, the default is **Balanced shedding**. Open **Show advanced shedding settings** to select **Minimum energy** or change the tier boundaries and weights. Under **Battery search**, Standard runs four representative weeks and then verifies finalists for the entire year. Quick uses two weeks and fewer iterations with the same full-year verification. Thorough runs full-year GWO directly. Search catalogs, site restrictions and worker settings are under Advanced.
3. Run **Base case**, **Simulate**, or **Optimize**. Base case is static FBS. Simulate supports zero or one manually configured battery. Optimization compares a verified single battery with the matched No BESS baseline. The Results tab opens the saved four-tab offline report. **Study → Save study setup** saves versioned JSON with settings, source paths and checksums. **Open study setup** checks those fingerprints before restoring the selected window and controls.

Balanced shedding uses marginal weights of 1, 3 and 10 on the first 50%, next 30% and final 20% of each bus's requested active demand. It can reduce full disconnections while increasing total unserved energy. The economic objective applies real VoLL and curtailment prices to unweighted physical energy. The controller score has separate export fields. A load counts as fully disconnected when requested demand exceeds `1e-6 kW` and served demand is at most `max(1e-6 kW, 1e-6 × requested demand)`. Unverified network hours have a separate count. `service_by_bus.csv` records served-energy percentage, share of shedding, outage duration and longest continuous outage.

Fast search uses Numba FBS and coordinated correction to rank bounded injection and charging probes. Window costs are screening estimates. Annual selection uses feasible results from the complete chronology. The verified minimum-shedding battery is included in the optimization details. Screening can miss a better design and can add overhead for a small catalog.

### Archived IEEE 33-bus validation

From `07_Implementation`, point the benchmark at a saved run containing `inputs/network.xlsx`, `inputs/load_profile.csv`, `inputs/pv_profile.csv` and `inputs/input_snapshot.json`.

```powershell
python benchmark_single_bess.py 'C:\Path\To\run_001' '.\paired.json' --window stress --window week --window year
python benchmark_single_bess.py 'C:\Path\To\run_001' '.\search.json' --workers 2 --search quick thorough standard
python benchmark_single_bess.py 'C:\Path\To\run_001' '.\workers.json' --worker-sweep 1 4 6 12
$env:QT_QPA_PLATFORM = 'offscreen'
python src/app.pyw --check-runtime '.\launcher-smoke.txt'
```

Use `--source 'C:\Path\To\extracted\src_accelerated' --policy minimum_energy` to replay the original single-BESS archive. Use `--dashboard '.\report'` to save the first replay with its normal exports. The JSON records input hashes, timestamps, settings, physical trace hashes, FBS and HiGHS call counts, and wall times. Worker CPU totals are separate from elapsed wall time. Annual costs require complete annual coverage.

The archived 2021 comparison uses five installed 1,200 kW PV rows (buses 6, 12, 18, 25 and 30), a 7,500 kW import limit, zero permitted export, 0.95–1.05 pu and a 10% reserve for the fixed bus-14 battery. The saved run workbook is the unmodified topology input. The five actual installation rows are in the saved run metadata.

| Policy | Battery | Unserved (MWh) | Fully disconnected bus-hours | PV curtailment (MWh) | Modeled cost (USD/year) |
| --- | --- | ---: | ---: | ---: | ---: |
| Minimum energy | No BESS | 3,502.61 | 19,058 | 367.86 | 44,305,792 |
| Minimum energy | Bus 14 | 3,292.78 | 17,274 | 178.37 | 42,311,162 |
| Balanced | No BESS | 4,319.37 | 0 | 367.86 | 54,023,147 |
| Balanced | Bus 14 | 4,053.35 | 0 | 178.37 | 51,360,206 |

All four annual cases passed the recorded network limits. The fixed battery closed at 50% SOC under both policies. The July 1 seven-day battery replay ended at about 30% SOC and failed the 50% terminal requirement with both policies. At January 11 20:00, balanced shedding changed 10 full disconnections to zero and increased unserved energy from 2.525 to 3.063 MWh. Zero observed disconnections on this run is a measured result, while physical feasibility remains the priority for other inputs.

The solver uses an inexpensive LP shortcut when a provably optimal solution to a one-row relaxation also satisfies every original LP constraint. All accepted actions still go through nonlinear FBS. Ambiguous ties, multi-constraint optima and difficult cases continue through HiGHS, its Phase I fallback and the verified line search. In the matched progressive seven-day B14 replay, the shortcut replaced 215 of 424 HiGHS calls, kept 1,923 FBS calls and reproduced the physical trace to the recorded precision. On the 12-candidate weekly worker sweep, four requested workers used 19.29 seconds versus 37.13 seconds for one. Host load and Windows process warm-up affect wall time.

Quick, Standard and Thorough chose bus 14 at 1,250 kW and 6,250 kWh from the two-site B14/B30 catalog. The verified result cost 51.36 million USD/year and shed 4,053.35 MWh. Excluding the common annual baseline, the observed wall times were about 165 seconds for Quick, 219 seconds for Standard and 191 seconds for Thorough. These runs establish agreement for the reduced catalog only. In this small search, reviewing additional representative weeks made Standard slower than Thorough.

The annual no-BESS offline HTML report was generated with 8,760 hours and canonical CSV/JSON exports. The Windows source launcher passed its runtime smoke check. Chromium startup and peak browser memory were unavailable in the test environment. The release does not include a rebuilt executable.
