# EE499 Team 16 — Approach A Forecasting Integration Plan

**Status:** Approved load-design decision plus planned PV-winning-model integration / implementation deferred. **No application code changes are made by this document.**  
**Project:** [Islahi/EE499-Team16](https://github.com/Islahi/EE499-Team16.git)  
**Target implementation:** `07_Implementation/src_accelerated/` on the repository's `main` branch as reviewed on 2026-11-20. Recheck the branch before editing.  
**Evidence:** `EE499_Team16_Forecasting_Sector_Aggregation_Testbench_2021.zip` for the load experiment; original `C2_Analysis(2).7z` Recommendation B results and `C2_FixedCohort_Ranked22_Legacy_Distributor_Complete(1).zip` for the independent Bilbao modeled-PV benchmark and implementation.  
**Revision:** 2026-11-20 — added the selected PV forecasting implementation to the planned program changes.

## 1. Approved decision

Implement **Approach A: sum each load sector's historical hourly active demand (kW), train one sector model on the summed series, forecast the sector total once, and allocate its prediction back to the member buses**. The program must **not** fit a single demand model to the entire feeder. The total feeder forecast is the sum of the **three sector predictions**, not a fourth model.

This replaces the *load-model selection and grouping behavior* of the existing whole-feeder AutoARIMA path when the new mode is selected. In the same winning-model mode, **forecast one common modeled-PV output profile with the selected XGBoost PV model and scale it to the individual PV installations**; this is independent of the load-sector aggregation decision. Keep legacy ARIMA functionality accessible as a separate, explicitly named baseline/option; do not silently relabel it as the selected models.

### Why this decision was made

| Item | Approach A (chosen) | Approach B (comparison only) |
|---|---:|---:|
| Model fits in the tested 15-bus network | 3 | 14 |
| Main-fit wall time, same execution environment | **2.6069 s** | 14.2007 s |
| Relative speed | **~5.45× faster** | Reference |
| 2021 sector/feeder accuracy | Same as B to exported precision | Same as A to exported precision |
| Bus-level demand output | Requires training-only allocation | Direct |

The equality is specific to the **constructed test network**, in which buses sharing a sector have **identical hourly demand**. Do **not** claim that Approach A is generally more accurate on heterogeneous real feeders. Preserve the full validation results in the experiment package; do not use an unrelated Distributed_Total/Cohort-Sum benchmark or its prior improvement claim as evidence for this choice.

## 2. Approved winning configurations

All configurations use the **daily + weekly + monthly + yearly known-calendar features** recovered from the C2 model implementation.

| Load sector | Selected implementation | Fixed settings from the matched 15-bus rerun |
|---|---|---|
| Residential | `CalendarRidge__daily_weekly_monthly_yearly` | Fourier richness `0.5`; Ridge `alpha=0.1` |
| Commercial | `XGBoost__daily_weekly_monthly_yearly` | `n_estimators=300`, `learning_rate=0.05`, `max_depth=3` |
| Manufacturing | `LightGBM__daily_weekly_monthly_yearly` | `n_estimators=500`, `learning_rate=0.03`, `num_leaves=31` |
| Bilbao modeled PV (**now planned for integration**) | `XGBoost__daily_weekly_monthly_yearly` | Winning model family/features **verified in the independent C2 PV benchmark**; exact historical tuned XGBoost hyperparameters not recovered from the available comparison summaries—resolve in PV implementation using the archived fitted config if available, otherwise use the documented 120-day training-only grid described in §6 |

The C2 comparison archive did not preserve all exact historical per-job fitted settings and binary dependency versions. The three load settings above were selected in the **documented matched rerun** (`results/model_settings.json`), not certified as byte-identical to the historical Rank22 job. **First integration: use these fixed load settings** to preserve the tested method. The **PV XGBoost winner is separately verified**, but this load experiment did **not** select or time its fitted hyperparameters: see §6 for the PV-specific recovery/tuning rule. Never silently use the commercial XGBoost settings as if they were the PV winner's fitted settings. Make any subsequent production retuning an explicit, logged feature.

### Forecast model conventions to reproduce

- Use **bus demand `p_kw`**, never customer-average `kW/customer`, for both aggregation and scoring.
- Use calendar features only (future date/time information, **no observed future demand**). Match `forecast_models.py` in the evidence package, which mirrors the archived `extra_models.py`: linear trend; Fourier components for periods **24, 168, approximately 720, and approximately 8760 hours**; hour/day/month indicator and interaction terms. Preserve its time origin and numerical feature construction.
- For **each sector total** `y_train`, normalize with `scale=max(mean(abs(y_train)), 1e-6)` using **training observations only**; fit on `y_train/scale`, generate the horizon forecast, multiply by `scale`, and clamp negative *active-demand predictions* to zero.
- Use the tested deterministic settings: booster `random_state=16`, internal `n_jobs=2`; XGBoost `tree_method='hist'`, `objective='reg:squarederror'`; one sector fit at a time by default. The selected PV XGBoost uses the **same implementation family and seed policy**, but it needs its **own PV-specific fitted settings** (§6). Shared calendar arrays may be cached, but no model or prediction is taken from observed future data.
- The historical validation used the last **120 days of training** for hyperparameter selection on a representative bus; its selected settings were frozen before both methods ran. In the first production integration, **do not retune**: use the fixed table above and record it in every forecast manifest. If tuning is added later, it must occur before the forecast origin and use only training data.

## 3. Input and bus assignment contract

The current `ProfileData` accepts hourly CSVs with `timestamp,bus_id,p_kw,q_kvar`; it has **no sector/category field**. Sector assignment must therefore be supplied explicitly, not inferred from bus number, loading level, or the whole-feeder series.

**Recommended sidecar file:** `bus_assignments.csv` with required columns:

```csv
bus_id,category
2,residential
3,commercial
4,manufacturing
5,residential
```

The validated 15-bus example uses the `bus_assignments_used.csv` included in the test bench, which also has an optional `profile` column:

- Residential: **2, 5, 10, 13** (4 buses).
- Commercial: **3, 8, 9, 12, 14** (5 buses).
- Manufacturing: **4, 6, 7, 11, 15** (5 buses).
- Bus 1: **slack; zero active demand; never fitted**.

**Production behavior:** obtain mapping from an imported sidecar (or a properly defined network metadata source in a later revision); do **not** hardcode this bus list in the forecasting algorithm. Normalize category labels to the three supported canonical values. Require every non-slack bus with demand to have **exactly one** valid assignment; fail with an informative message on missing, conflicting, duplicated, invalid, or unknown categories. Validate IDs against the loaded network, and preserve the network's actual slack-bus ID rather than assuming it is always 1. Zero-demand non-slack buses can be emitted as zero without fitting; their handling and category should still be validated/documented.

Also validate hourly continuity, unique `(timestamp,bus_id)` entries, aligned series lengths, finite nonnegative `p_kw`, and that no future observations enter model fitting or preprocessing. Imported data and forecast timestamps must use one consistent, explicit clock.

## 4. Runtime algorithm (Approach A load; independent PV execution)

```text
INPUT:
  historical ProfileData; network bus IDs and slack ID;
  explicit bus_id -> sector mapping; forecast horizon H;
  fixed sector model settings; forecast start = history end + 1 hour

VALIDATE inputs, mapping, hourly timestamps, train/test boundary
BUILD future hourly calendar feature matrix (known timestamps only)

FOR sector in [residential, commercial, manufacturing]:
    members = mapped loaded buses belonging to sector
    y_sector_train[t] = sum(history.load_p_kw[bus][t] for bus in members)
    IF sector has no members or is all-zero:
        return zero prediction for members (record that no fit was needed)
    ELSE:
        fit the sector's selected model ON y_sector_train (not one bus)
        sector_pred[t] = max(0, model forecast in kW for each future hour)
        bus_pred[bus,t] = sector_pred[t] * training_only_share(bus,t)
    ASSERT sum(bus_pred[member,t]) == sector_pred[t] (tolerance)

SET slack bus forecast = 0
feeder_pred[t] = sum(sector_pred[sector,t] for sector in sectors)
ASSERT sum(bus_pred[all_load_buses,t]) == feeder_pred[t]
RUN the PV predictor independently as defined in §6 (or emit zero PV if no PV installed)
COMBINE forecast load and PV into the same hourly ProfileData/CSV format
      expected by simulation, retaining separate per-bus load/PV values
STORE sector predictions, allocated bus predictions, common PV reference/capacity
      factor, bus PV predictions, settings, timestamps, data provenance,
      allocation settings and load/PV runtimes in session outputs
```

**Important:** Aggregation must happen **before fitting**. `n_buses × one representative-bus forecast` is not a substitute for training the model on the sector sum, even though the two happened to agree in this particular test.

### Training interval and horizon

The reproduction fixture used training **2017-06-01 00:00 through 2020-12-31 23:00** (31,440 hours), a single forecast origin of **2021-01-01 00:00**, and **8,760 hours of 2021**. These are **test fixture dates**, not hardcoded production dates. Production forecasting should use the available historical window ending at its chosen origin; never read the future target interval. Keep arbitrary hourly horizon `H` supported, noting that only the full-year 2021 horizon has been validated in this comparison.

For the annual-feature mode, propose **at least one year of hourly history** (preferably more) or fail with a clear message until a shorter-history behavior is separately validated. The existing UI's 336-hour default and `train_hours` truncation must not silently replace the 31,440-hour tested fit when sector mode is selected.

## 5. Sector-to-bus allocation: required for FBS and BESS

**For the validated 15-bus fixture:** after confirming identical **training** profiles within the sector, assign equal hourly shares:

\[
\hat P_{b,t}=\frac{\hat P_{s,t}}{N_s},\quad b\in s.
\]

For a **general network with different demand histories**, retain the Approach A concept but allocate each sector forecast using **training-only bus proportions**. An acceptable first implementation is to adapt the existing `forecasting._allocate()` hour-of-day historical-share mechanism **within each sector**, rather than across the feeder. Let `m_b(h)` be the nonnegative historical mean kW for bus `b` at hour-of-day `h`, calculated only from the fitting window:

\[
w_b(h)=\frac{m_b(h)}{\sum_{j\in s}m_j(h)},\qquad
\hat P_{b,t}=w_b(h_t)\hat P_{s,t}.
\]

Where the denominator is zero, use a documented deterministic fallback: training-period overall shares if available, otherwise equal shares among assigned sector buses. **Do not use observed demand in the forecast horizon to calculate shares.** Normalize weights to sum exactly to one and validate that hourly allocated bus totals reconstruct sector predictions (recommended absolute tolerance `1e-8 kW`, with a sensible floating-point relative tolerance). An all-zero sector must remain zero; skip fitting it. This allocation is an **engineering approximation**, not proof of good bus-level forecast accuracy for heterogeneous feeders.

**Reactive load `q_kvar`:** the selected models predict `p_kw` only. Preserve the application's existing engineering approach of deriving bus `q_kvar` from a **training-only bus-specific historical Q/P ratio** (hour-of-day where possible, with explicit safe fallback at zero historical P). Do not simply copy future observed Q or assume equal reactive demand between unlike buses. Keep both `load_p_kw` and `load_q_kvar` aligned with the required `ProfileData` interface.

## 6. Integrate the selected PV winner (independent common-source forecast)

**Decision:** include **`XGBoost__daily_weekly_monthly_yearly`** as the PV forecasting engine in the new winning-model mode. It is **one additional PV fit for the common solar-generation reference**, **not** a fourth load-sector model, **not** a residential/commercial/manufacturing PV aggregation, and **not** an XGBoost regressor of raw irradiance unless a *separate* irradiance-forecast experiment authorizes that target.

### 6.1 What the C2 PV winner actually predicts

- **Verified source:** Recommendation B ranks `Bilbao_Modeled_PV` / `XGBoost__daily_weekly_monthly_yearly` first. The archived C2 summary reports **MAE 22.0941 kW, RMSE 42.3194 kW, and WAPE 30.3540%** on the **Bilbao 490 kW modeled-PV reference**; these are **not** forecasts from the 15-bus comparison and **not** proven Saudi-network PV performance.
- **Target:** hourly **modeled electrical PV power (`p_kw`)** derived historically from NASA POWER solar data. It is **not measured PV**, not raw global horizontal irradiance (`ghi_wh_m2`), and not an estimate of PV installation capacity. The C2 source includes `p_kw`, `ghi_wh_m2`, `site_lat`, and `site_lon`; it identifies the Bilbao benchmark site at approximately **43.26° N, −2.94° longitude** with a **490 kW reference nameplate**.
- **Forecast inputs:** future **known-calendar features only**, with periods **24, 168, 720 and 8760 hours**, generated using the same `extra_models.py:calendar_features()` as the load winners. **Do not provide observed future NASA irradiance, modeled PV output, or other future-target information** to the model. The historical NASA timestamps were labeled **UTC**; conversion into a local site clock is a deliberate, traceable operation, not a simple reinterpretation of timestamp labels.
- **Validation:** the archived PV benchmark used the same training window (**2017-06-01 to 2020-12-31**), independent 2021 test year (**8,760 hours**), and last **120 training days** for hyperparameter selection. These are reproduction settings, **not** production dates hardcoded into the program.

### 6.2 Historical PV source contract

Implement a **single historical common-source PV reference series**, time-aligned with the historical load data and labeled with its units and source clock. **Preferred production input** is a network-relevant historical irradiance record (NASA POWER, Open-Meteo, or an explicitly prepared source), transformed with the existing `pv_model.py:irradiance_to_power()` / `make_pv_profile()` assumptions into an hourly **modeled reference electrical PV output** for a documented `reference_capacity_kw`. An existing, explicitly labeled historical modeled-PV `p_kw` reference can also be accepted, but must include its known nameplate.

For the historical Bilbao comparison only, use `reference_capacity_kw=490.0` and the archived solar-derived `p_kw` series. **Do not assume** that a Bilbao-trained PV curve is accurate at a Saudi or other network site. For production use, fit the **selected model configuration** on a **site-appropriate historical reference series** whenever available; clearly label any Bilbao-to-other-site transfer as a demonstration/untested transfer, not a site-validated forecast.

If the existing historical network `pv_profile.csv` has several installation output series, construct a common reference only if they were demonstrably derived from the **same irradiance source and compatible PV conversion**. Convert each eligible series into `P_{i,t}/P_{rated,i}` and verify that their hourly capacity factors agree within tolerance; otherwise require an explicit source reference rather than averaging incompatible generation curves. A zero placeholder is **not valid historical PV training data** when PV capacity is nonzero. When the network has **zero installed PV**, emit zero PV forecasts and skip training cleanly.

### 6.3 PV training, settings and forecasting

Port the **archived XGBoost PV-winning family/features** using the same calendar construction as the benchmark. **Do not reuse the commercial-sector XGBoost hyperparameters without an independent PV check**. Source precedence for PV estimator settings:

1. Retrieve the exact winner's `results/pv/Bilbao_Modeled_PV/XGBoost__daily_weekly_monthly_yearly/fitted_configuration.json` or equivalent archived per-job configuration **if available**; preserve its metadata and dependency versions when known.
2. If the historical fitted settings are unavailable, reproduce the **documented PV-specific training-only chronological tuning** in `extra_models.py`: hold out the final **120 days of the available training interval** and minimize validation MAE over these **three XGBoost candidates**:

   | Candidate | `n_estimators` | `learning_rate` | `max_depth` |
   |---|---:|---:|---:|
   | 1 | 300 | 0.05 | 3 |
   | 2 | 500 | 0.03 | 5 |
   | 3 | 700 | 0.03 | 6 |

   Use `random_state=16`, `n_jobs=2`, `tree_method='hist'`, `objective='reg:squarederror'`, and only features/labels from before the forecast origin. **Select settings on the PV target itself**, then refit on all available historical PV training hours; save the selected parameters, validation scores, training interval, model/library versions and full reference-source provenance. Label this a **reselected PV winner / matched implementation** if exact historical settings could not be confirmed; do not claim it is the exact archived fitted model.
3. Match the original training-target preprocessing: `scale = max(mean(abs(P_reference_train_kw)), 1e-6)` **from training only**, train on `P_reference_train_kw / scale`, predict the future horizon using calendar features alone, then rescale into reference kW. The input time origin and period construction must match `extra_models.py` (its Fourier time anchor is `2017-01-01`).
4. Apply physical postprocessing in this order, matching the original *intent*: finite-value checks; clamp modeled PV output to `[0, reference_capacity_kw]`; then enforce **nighttime zero** using a documented site-position and timezone-aware daylight method. The historical `run_single_job.py:physical()` used an approximate solar-position mask for Bilbao using its UTC location. **Do not hardcode Bilbao's coordinates/UTC assumption for a different site**. If the required location/clock metadata are absent, fail clearly or require a separately justified physical treatment; never pass unexplained nighttime generation into the electrical simulation.

The winning feature set and estimator family are approved. **The exact historical PV fitted candidate remains unverified from the available C2 summary**; the procedure above specifies how to resolve it during implementation rather than inventing a value now.

### 6.4 Convert the one PV forecast to bus-level electrical power

The PV model outputs a single **modeled power** series for the historical reference nameplate. Convert it to a dimensionless reference **capacity factor** and scale by each network installation's actual installed rating:

\[
\hat c_t = \operatorname{clip}\left(\frac{\hat P_{\mathrm{PV,ref},t}}{P_{\mathrm{ref,rated}}},0,1\right),\qquad
\hat P_{\mathrm{PV},i,t}=P_{\mathrm{rated},i}\hat c_t.
\]

- **One XGBoost forecast** supplies the common capacity-factor trajectory; the application emits the corresponding `pv_p_kw[bus]` for **each installed PV bus**, based on its own rated kW. If a bus has multiple PV units, their nameplate ratings must be added consistently (as the existing `pv_model.py` already does).
- Check `0 <= pv_p_kw[i,t] <= rated_kw[i]`, set buses with no installed PV to zero or omit them consistently with the loader contract, and verify `sum_i(pv_p_kw[i,t]) = c_hat[t] * sum_i(rated_kw[i])` for all forecast hours.
- The current `pv_model.py` uses **unity power factor**, so **`pv_q_kvar = 0`** under the existing design unless an explicit separate inverter reactive-power model is introduced. Preserve the current physical modeling assumptions; do not invent inverter behavior.
- **Do not feed forecast electrical PV `p_kw` back through `irradiance_to_power()`**, which expects irradiance in W/m²; that would convert power twice. This direct capacity-factor scaling is appropriate specifically because the selected C2 model forecasts **modeled PV power**. If future irradiance is independently supplied, the existing irradiance-to-power path remains a separate, explicitly labeled operating mode.
- The common-source assumption does not account for different installation orientation, shading, losses, weather zones or technology. The PV winner's original accuracy is demonstrated for **modeled Bilbao PV**, not a validation of capacity-factor transfer between unrelated systems.

### 6.5 Coordinated production execution and output

```text
INPUT:
  trained-site historical PV reference (modeled p_kw and reference rated kW),
  site clock/location metadata, network PVUnit ratings, horizon H;
  optional explicit mode for externally supplied future irradiance/PV

IF no installed PV capacity:
    future pv_p_kw and pv_q_kvar = 0; status = 'pv_disabled_no_capacity'
ELSE IF winning-model PV mode selected:
    VALIDATE nonzero, complete historical PV reference and clock/location
    GET archived fitted PV settings, or tune on training only with 120-day holdout
    FIT XGBoost calendar model ON common PV reference power history
    P_ref_pred_kw = forecast H future hours (known calendar only)
    APPLY reference capacity cap and site-correct nighttime zero
    capacity_factor = clip(P_ref_pred_kw / reference_capacity_kw, 0, 1)
    FOR each installed PV unit/bus:
        pv_p_kw[bus] = capacity_factor * rated_kw[bus]
        pv_q_kvar[bus] = 0  # current unity-PF PV implementation
    ASSERT PV bus outputs respect ratings and reconstruct common forecast
ELSE:
    RUN explicit legacy/imported-future-PV path with its own provenance

ALIGN PV bus outputs and Approach A load outputs to identical future timestamps
RETURN one ProfileData with load_p_kw/load_q_kvar/pv_p_kw/pv_q_kvar
SAVE solar source/rating, model settings, normalization, clock/location,
     nighttime mask method, PV runtime, and status separately from load models
```

**Performance:** the prior **2.6069 s Approach A** figure covers **three demand-sector fits only**; the integrated XGBoost PV run adds another fit/tuning/forecast cost. Measure the end-to-end four-model workload separately; do **not** advertise 2.6069 s as the PV-inclusive runtime.

**Integration distinction:** the application already supports loading historical irradiance with `read_irradiance()` and building modeled electrical PV power with `make_pv_profile()` in `ui_workflow.prepare_study()`. The new stage is to create a forecast of the **common historical PV reference's future modeled output**, then scale that forecast by PVUnit ratings. This does **not** require fitting an independent PV regressor to every electrical bus.

## 7. Planned code touchpoints (change later, not now)

| Repository location | Planned work |
|---|---|
| `src_accelerated/forecasting.py` | Add separate **load** (`sector_sum` vs legacy ARIMA) and **PV** (`common_pv_xgboost` vs explicit existing alternatives) dispatch to `ForecastConfig` / `generate_forecast`, preserving the `ForecastReport` contract and output alignment. Do not use a **single whole-feeder** load fit in sector mode or mislabel the legacy PV AutoARIMA as winning PV. |
| `src_accelerated/forecast_models.py` **(new)** | Port tested `calendar_features`, training-only normalizer, fixed load-sector CalendarRidge/XGBoost/LightGBM estimators, and **common modeled-PV XGBoost** candidate grid/selection or verified stored settings. Maintain shared calendar features and separate load/PV postprocessing. |
| `src_accelerated/sector_forecast.py` **(new; optional separation)** | Mapping validation, sector aggregation, per-sector training/forecast, allocation, and conservation checks. Avoid duplicating unrelated legacy ARIMA logic. |
| `src_accelerated/pv_forecast.py` **(new; recommended)** | Build/validate common historical **modeled PV reference**; recover or training-only select PV XGBoost settings; produce one future reference forecast; apply site-appropriate physical constraints; convert to capacity factor and bus-level `pv_p_kw`, `pv_q_kvar`. Never refit per PV bus. |
| `src_accelerated/pv_model.py` | Reuse existing irradiance-to-modeled-PV reference generation and rated-capacity metadata; expose a clean historical reference-building helper only if necessary. Do not send predicted PV kW into an irradiance conversion function. |
| `src_accelerated/ui_workflow.py` | Add assignment-path and common PV reference source/rated-kW/site-clock metadata to `DataRequest`/`PreparedStudy`; retain existing `pv_source` distinctions (none, modeled power, NASA/Open-Meteo/prepared irradiance) and validate historical PV availability before fitting. |
| `src_accelerated/ui.py` | Add a clearly named **Winning models: sector sums + common PV XGBoost** forecasting mode, connect sector mapping and PV source/reference/site information, show separate model statuses/timings, and retain legacy ARIMA options. Preserve existing `forecast_ready()` output behavior. |
| `src_accelerated/assets/forecast_dialog.ui` | Update model choices, labels, training control, and explanatory text; explicitly show **PV mode / zero-capacity bypass**, reference capacity and site clock/location status. Winning-model mode should use sufficient training history, not silently default to 336 hours. |
| `src_accelerated/study_session.py` | Snapshot bus-assignment and historical common PV reference inputs; store hashes, separate selected load/PV estimators and actual PV candidate/settings, reference rated kW, site clock/location, normalization basis, caps/night mask, training range, allocation strategy, statuses and per-component timings in the manifest. |
| `src_accelerated/data_loader.py` | Continue accepting the existing `timestamp,bus_id,p_kw,q_kvar` CSVs; strengthen per-bus completeness validation if necessary, without breaking consumers. |
| App requirements file | Add compatible, tested `scikit-learn`, `xgboost`, and `lightgbm` dependencies alongside existing NumPy, pandas, PySide6 and StatsForecast. XGBoost is used for **commercial load and PV**, with independent fitted settings; pin tested versions in the run manifest. |
| New forecasting tests | Unit tests for sector grouping and allocation, PV modeled-output/reference/capacity-factor scaling, leakage/clock/nighttime guards, numerical conservation, UI/output integration, saved 15-bus load fixture, and independent Bilbao PV reproduction fixture. |

The paths above are relative to `07_Implementation/`. Existing consumers (`simulation.py`, FBS, optimization, and exported forecast profiles) should **continue receiving hourly per-bus `p_kw` and `q_kvar`**, without needing to know how sector models were fitted.

### Existing flow to preserve

1. `ui.py:ForecastDialog.start_forecast()` currently builds `ForecastConfig` and uses `generate_forecast(history, cfg)` in a background worker.
2. `forecasting.py:generate_forecast()` currently fits AutoARIMA on **the entire load sum** and separately on the PV sum, then calls `_allocate()` to create per-bus profiles. In the new winning-model mode, it must branch to **three sector demand fits and one common XGBoost modeled-PV fit** (when nonzero PV exists), then build compatible bus profiles. Other modes retain their explicitly named behavior.
3. `ui.py:ForecastDialog.forecast_ready()` writes `load_profile.csv` and `pv_profile.csv`, sets `study.historical_profiles`, replaces `study.profiles` with forecast profiles, and records `forecast_runs` in the session. Preserve that public behavior and extend the run metadata.
4. `simulation.py:simulate_timeseries()` requires continuous hourly, finite nonnegative bus-level load and PV inputs; forecast-output validation must check correct site-clock alignment, PV bus rated caps, and load/PV data contracts before simulations begin.

## 8. Acceptance tests before merging any future implementation

- [ ] The mapping is explicit; all non-slack loaded buses belong to exactly one supported sector, with meaningful errors for invalid assignments.
- [ ] **Exactly one fresh fit per nonzero sector**, with its sector **sum** as training target; no whole-feeder fit and no 14 independent fits in the chosen production path.
- [ ] Each load model uses the declared winning family, calendar features, fixed settings, random seed, training-only scaling and postprocessing; model versions and training dates are logged.
- [ ] No future observed `p_kw`/`q_kvar`, forecast-year labels, or normalization statistics can enter training, feature creation, or allocation.
- [ ] The validated 15-bus fixture yields 8,760 hourly predictions for every loaded bus and the feeder, zero slack demand, three distinct sector forecasts, and sector/bus/feeder conservation to the declared tolerance.
- [ ] Recompute 2021 annual and monthly accuracy from output CSVs; compare the new implementation with the packaged **Approach A** reference series and document version-related numerical drift, if any. Expected reference WAPE: residential **9.57657%**, commercial **12.78956%**, manufacturing **16.20245%**, feeder **11.22427%**.
- [ ] For the fixture, equal-share allocations reconstruct the sector forecast and match the expected per-bus results. For a deliberately *nonidentical* synthetic-bus fixture, hour-of-day training-only allocation is nonnegative, conservative, and reproducible (no accuracy superiority claim).
- [ ] Forecast-load CSV and forecast-PV CSV have aligned timestamps and the existing columns; a loaded `ProfileData` object can be fed to FBS/simulation/optimization without interface changes.
- [ ] The GUI and session manifest name the **three actual fitted load models plus selected PV XGBoost** (if installed capacity is nonzero); record whether the PV fitted settings were recovered exactly or training-only reselected. Never label an unimplemented PV model as active.
- [ ] Legacy AutoARIMA option and session history remain operable; runs are repeatable on the same inputs and software versions.
- [ ] **PV no-capacity case:** zero output with no model fit; historical `pv_profile.csv` zero placeholder must not trigger a fictitious PV fit.
- [ ] **PV nonzero case:** one common-site PV XGBoost fit (not per PV bus); use only past modeled-PV labels, training-only normalization/selection, deterministic seed and calendar features. Output `0 <= pv_p_kw <= rated_kw` and `pv_q_kvar=0` under unity PF; verify all PV buses sum to the common capacity-factor forecast times total installed capacity.
- [ ] **PV physical/clock case:** future-night generation is zero using correct site and source clock, future timestamps align with sector load, and UTC/local conversions are explicit. Reject missing/unfit source or placeholder history, not silently substitute observed future irradiance.
- [ ] **PV source-reproduction case:** reproduce archived `Bilbao_Modeled_PV` XGBoost model selection/forecast on its 490 kW reference, or label exact-setting gaps and report tolerance/drift; preserve C2 archived WAPE ~30.354% as PV-only benchmark reference, not an application acceptance threshold for other sites.
- [ ] **PV integration case:** `ProfileData` load and PV outputs have identical hourly timestamps; rerun FBS/simulation with nonzero installed PV and confirm correct PV capacity scaling and no double-conversion.

**Reference verification command** (for the completed standalone benchmark, not yet the app):

```powershell
py -3 forecast_bench.py --verify-only
```

The evidence package reports `results/verification.json` with `status: PASS`. Its comparison was a **matched rerun**, not a certified exact historical C2 reproduction. The upstream *distributor* used the entire 2017-06 through 2022-06 period when normalizing the supplied source data, including 2021; this is a known limitation of the saved fixture, **not** permission to use future data in the future production preprocessing pipeline.

## 9. Deferred implementation sequence

1. Confirm the current repository branch and create a separate development branch when modification is authorized; **do not modify the repo as part of this planning document**.
2. Add assignment metadata import and source snapshot support.
3. Port the matched model classes/features and fixed settings into the application package.
4. Implement three-sector sum-first fitting, training-only load allocation, Q generation, and conservation checks.
5. Integrate **common modeled-PV XGBoost**: recover/tune PV-specific candidate settings, build a site-appropriate historical modeled-PV reference, forecast its future output, cap/night-mask it, convert to capacity factor, and scale to PVUnit ratings with Q=0 under the current design.
6. Add GUI controls for winning **load + PV** mode and its required source/clock metadata, update requirements, and record independent model/source/runtimes in per-run provenance; retain existing legacy ARIMA and explicitly imported future-PV paths.
7. Test the 15-bus load fixture against saved Approach A results; test PV against the archived **Bilbao 490 kW modeled-PV** fixture separately; smoke-test nonzero-PV and zero-PV scenarios through FBS/simulation and validate the output session artifacts.
8. Consider future enhancements (e.g., optional per-sector retuning, **raw irradiance prediction**, alternative PV technologies or multiple weather zones) as **separate**, explicitly evaluated changes. The winning **modeled-PV XGBoost** integration itself is part of this plan, **not deferred**.

**Definition of done for this future change:** the selected winning-model mode runs end-to-end in the app with **Approach A (three load-sector fits) plus a single common XGBoost modeled-PV fit where PV is installed**. It outputs valid, aligned hourly bus-level active/reactive load **and PV** profiles; preserves load sector/feeder totals and PV capacity-factor/rating conservation; enforces zero PV at night and rated caps; records models, PV data provenance, fitted settings and runtime; reproduces the respective load/PV reference fixtures within documented tolerances or explicitly labels unmatched historical settings; and leaves legacy forecasting and electrical-simulation workflows intact.
