# Known Gaps and Review Flags

This is **not a task list**. It is a persistent record of issues that a future AI should remember and raise when relevant to the user's current task.

## A. Alignment with the official project brief

These are important alignment questions visible from comparing the official project description with the submitted Term 1 baseline. They should be discussed/verified rather than silently resolved.

### Two-stage stochastic programming vs current heuristic baseline

The official project description explicitly calls for a **two-stage stochastic programming** framework with first-stage planning decisions and second-stage operations. The submitted Term 1 report instead centers on ARIMA + Monte Carlo + Grey Wolf Optimization and does not visibly formulate a two-stage stochastic program.

**Review flag:** clarify with the team/advisor how the Term 2 mathematical formulation will satisfy the official two-stage requirement, or whether an approved interpretation/change exists.

### Battery type selection

The official brief includes **battery type** among first-stage planning decisions. The submitted Term 1 baseline emphasizes battery size, power rating, and location; battery type optimization is not evident.

**Review flag:** determine whether battery type is a fixed assumption, a decision variable, or an approved scope reduction.

### Annual hourly operation vs three-month minimum

The official brief describes hourly operational decisions **over a year**. The Term 1 report states hourly simulation over a limited period with a **minimum of three months** because of computational/data constraints.

**Review flag:** this is a direct scope/alignment issue requiring justification or advisor clarification.

### Other brief items not yet clearly evidenced in the supplied Term 1 material

When relevant, verify the implementation of:

- reserve requirements,
- explicit environmental/emissions impact assessment,
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
