# Known Gaps and Review Flags

This is **not a task list**. It is a persistent record of issues that a future AI should remember and raise when relevant to the user's current task.

## A. Alignment with the official project brief

These are important alignment questions visible from comparing the official project description with the submitted Term 1 baseline. They should be discussed/verified rather than silently resolved.

### Resolved scope decision: GWO/WSM instead of two-stage stochastic programming

The official project description explicitly calls for a **two-stage stochastic programming** framework with first-stage planning decisions and second-stage operations. The submitted Term 1 report instead centers on ARIMA + Monte Carlo + Grey Wolf Optimization and does not visibly formulate a two-stage stochastic program.

**Team decision (15 Oct 2026):** implement the established GWO/WSM design and
do not build a separate two-stage stochastic program. This resolves the
implementation choice, but remains a deviation from the official brief that
must be disclosed and justified in the final report rather than hidden.

### Resolved initial scope: generic fixed BESS technology

The official brief includes **battery type** among first-stage planning decisions. The submitted Term 1 baseline emphasizes battery size, power rating, and location; battery type optimization is not evident.

**Team decision (15 Oct 2026):** battery type is not an optimization variable
in the first program. Use one generic BESS model. Utility-scale lithium-ion LFP
may provide reference parameters later, but the code should optimize only bus,
power and energy capacity.

### Resolved initial scope: three continuous months of hourly operation

The official brief describes hourly operational decisions **over a year**. The Term 1 report states hourly simulation over a limited period with a **minimum of three months** because of computational/data constraints.

**Team decision (15 Oct 2026):** implement and validate three continuous months
first, then extend toward a full year if time and compute permit. This is an
initial implementation horizon, not evidence of annual or full-seasonal
performance, and the limitation must be stated in reported conclusions.

### Other brief items not yet clearly evidenced in the supplied Term 1 material

When relevant, verify the implementation of:

- reserve requirements beyond the initial configurable 10%-of-peak, one-hour
  engineering assumption,
- explicit environmental/emissions impact assessment, which is deferred as an
  optional placeholder,
- the final decision-support tool,
- reproducibility/adaptation documentation,
- and the full economic treatment requested in the brief.

Do not mark these “missing” permanently without checking the latest working implementation; this list reflects the supplied starting snapshot.

## B. Report 1 feedback

Key issues preserved in `02_Reports/Submitted/Report_1/EE499-S26_Report-1_Team-16.txt` include:

- essential project details were missing,
- optimization details were unclear,
- title/specification discrepancies,
- simulation parameters, variables, and outcomes were not clearly defined,
- problem statement needed to be more concise,
- design specifications required major revision,
- deliverables needed clearer definition,
- optimization parameters needed clarification.

## C. Report 2 feedback

Key issues preserved in `02_Reports/Submitted/Report_2/EE499-S26_Report-2_Team-16.txt` include:

- objectives should be outcome-focused and measurable,
- quantitative targets/validation methods needed improvement,
- 45-scenario choice required justification,
- GWO parameter effects/sensitivity were not discussed,
- ARIMA needed validation with metrics such as RMSE/MAPE,
- Weighted Sum Method weights lacked justification/sensitivity analysis,
- generated scenarios were not compared adequately with historical data,
- design-spec target values needed justification,
- constraints/standards needed clearer application,
- literature-review critiques needed stronger evidence,
- alternatives were variations of the same general approach,
- objective function and validation workflow needed refinement.

Some of these points were subsequently addressed narratively in the Term 1 report (for example RMSE/MAPE language and a 45-scenario rationale), but do not assume a written explanation is equivalent to implemented/validated engineering design.

## D. Final Term 1 feedback

The final Term 1 assessment is especially important for Term 2. The preserved feedback states that:

- proposed alternatives were not conceptually distinct enough,
- evaluation was primarily qualitative with insufficient quantitative analysis,
- **no actual design was presented; the project remained largely conceptual**,
- key simulation-model details were missing,
- relationships, interfaces, and functionality of the statistical modules were unclear.

Source: `02_Reports/Submitted/Term_1_Final/EE499-S26_Report-Term_1_Team-16.txt`.

## E. Design vs implementation distinction

The classroom guidance preserved under `03_Feedback/General_Guidance/` distinguishes simulation-project work as:

- **Engineering design:** mathematical model, assumptions, parameters, numerical method, validation plan.
- **Implementation:** running simulations, collecting outputs, checking behavior.

This is why Term 2 should not merely “run code” if the design/model definition remains incomplete. Missing design elements that affect implementation or validation still need repair.

A detailed software handoff specification now exists at `02_Reports/Working/Planning/TERM2_SOFTWARE_DESIGN_SPEC.md`. Architecture, module boundaries, network/FBS/BESS data structures, profile format, interfaces, units and future module placeholders should be resolved there before implementation owners code them independently.

### Remaining design gates before later tasks

The following are still design questions and must not be silently decided inside implementation code:

1. **Raw WSM units** — the team chose no normalization for the first prototype.
   Because SAR and kWh are mixed directly, the nominal weights cannot be
   interpreted as rigorous relative importance. Revisit only if results are
   implausible or a stronger final evaluation is required.
2. **Interpretation of the approximately 85% BESS efficiency value** — verify whether the retained value is intended as a directional charge/discharge efficiency, a round-trip efficiency, or another convention before assigning `eta_charge` and `eta_discharge` numerically. Do not silently assume one interpretation.
3. **Reactive-load profile handling when source data lacks time-varying Q** — the simulation boundary requires active/reactive demand, but the source load data may not directly provide both. If Q is not present, confirm/document the preprocessing assumption (for example a justified power-factor rule) before producing final simulation profile files.

These are design gates, not new customer requirements. Once confirmed, update the design specification and then implement them consistently.

### Desktop prototype boundary (18 Oct 2026)

The supplied forms and first PySide6 desktop are now implemented; do not list
`ui.py` or automatic radial layout as missing scripts. The user confirmed
min/max/step search catalogs and explicit net-load-target dispatch. No supplier
catalog, price, efficiency convention or optimal target is inferred by the UI.
Sources/settings are recorded, and missing prices are distinct from zero.
Closing/conflicting actions are blocked during jobs; cooperative cancellation,
reliable percentage progress, Windows EXE packaging, display-scaling acceptance
and independent real-study validation remain outstanding. Optional uncertainty
can fail ARIMA convergence; the UI reports that failure without a fallback.
See `07_Implementation/src/README_ui.md` for implemented behavior and tests.

### Uncertainty implementation limits (18 Oct 2026)

The ARIMA/Monte Carlo/100-to-45 backend is implemented and synthetically tested;
this is not completed statistical validation. It uses independent per-bus,
load/PV Gaussian ARIMA residual paths around fixed hourly historical patterns,
historical hourly Q/P ratios, and physical clipping. Cross-series correlation,
seasonal/daylight changes, parameter uncertainty, real-data calibration and
historical-versus-generated distribution checks remain pending. Holdout
RMSE/MAPE and a repeat-last-day comparator are available; ARIMA can perform worse.

The 15/15/15 subset deliberately oversamples extremes. Its equal-weight WSM
is a stress-portfolio score, not an unbiased expected cost or a statistically
probability-preserving reduction. Feasibility in all selected cases does not
establish out-of-sample reliability; compare the common candidate with no-BESS
and additional unseen cases before making a recommendation.
