# Confirmed Project Decisions

Record only **actual team decisions** here. Do not use this file for brainstorming, AI suggestions, or choices inferred from old reports.

A technical method appearing in a submitted report is historical project context, not automatically a confirmed continuing decision.

## Current record

## 2026-10-15 — Use the GWO/WSM design baseline

**Decision:**
Implement the existing Grey Wolf Optimization (GWO) search with the Weighted
Sum Method (WSM) objective. Do not implement a separate two-stage stochastic
programming formulation. Uncertainty will be handled through the retained
ARIMA, Monte Carlo and scenario-evaluation workflow.

**Reason:**
The team is implementing and validating its established engineering design,
not opening a second optimization-method research track during Term 2.

**Decided by:**
Team decision confirmed by the user in chat.

**Related material:**
`02_Reports/Working/Planning/TERM2_SHADOW_DESIGN.md` SD-7 and SD-8;
`02_Reports/Working/Planning/TERM2_WORKING_CONTEXT.md`.

**Reporting note:**
The official project brief mentioned two-stage stochastic programming. Final
documentation must identify GWO/WSM as the implemented scope and explain the
deviation; it must not claim that GWO is mathematically equivalent to a
two-stage stochastic program.

## 2026-10-15 — Use a three-month initial simulation horizon

**Decision:**
Implement and validate the first integrated program using three continuous
months of hourly data. Preserve the interfaces so the horizon can later be
extended to a full year without changing the physical models.

**Reason:**
Three months provides a manageable first implementation and validation scope;
annual operation is deferred until the shorter workflow is stable.

**Decided by:**
Team decision confirmed by the user in chat.

**Related material:**
`02_Reports/Working/Planning/TERM2_WORKING_CONTEXT.md` and the Term 1 baseline.

**Reporting note:**
Three months does not demonstrate full seasonal/annual performance. Results
must be described as initial-period results until the horizon is extended.

## 2026-10-15 — Simplify the first working implementation

**Decision:**
Use the following first-version rules:

- keep the Term 1 raw WSM form without normalization for now;
- rank scenarios with a documented profile stress score using net-load energy,
  peak net load, PV-surplus energy and maximum hourly ramp, then retain 15
  highest, 15 lowest and 15 seeded-random remaining scenarios;
- reserve 10% of peak load for one hour as a configurable BESS reserve;
- model one generic BESS, using utility-scale lithium-ion LFP only as the
  reference technology behind later parameter values, not as an optimization
  variable;
- use only `cost = cost_per_kwh * E + cost_per_kw * P`, with both coefficients
  left as explicit inputs until the team supplies sourced values;
- leave emissions as an optional placeholder for later work;
- enforce the general `0.95 <= V <= 1.05 pu` voltage constraint;
- do not implement a thermal/ampacity constraint in the first version.

**Reason:**
The immediate objective is a small, understandable program that works. Extra
model detail is deferred until the integrated workflow is operational.

**Decided by:**
Team decision confirmed by the user in chat.

**Reporting note:**
Raw WSM terms mix SAR and kWh, so the nominal 0.50/0.25/0.25 weights do not
have a rigorous relative-importance interpretation. This is acceptable only
as a disclosed prototype limitation and should be revisited if the objective
produces implausible selections.

## 2026-10-18 — Desktop input preparation and initial results scope

**Decision:**
The user confirmed the following direction after reviewing the initial UI deck:

- Add a separate irradiance-to-PV-power preparation script, using the Term 1
  report's PV model as the starting point. Irradiance remains an accepted source
  input; the simulator continues to consume power profiles.
- Support both imported load profiles and synthetic load profiles based on the
  probability-distribution method in the paper co-authored by Hatem F. Sindi.
  A separate load-generation script is needed; measured profiles are not required
  to use the first prototype.
- Expose minimum/maximum BESS power and energy limits rather than requiring the
  user to supply a product-size catalog in the first UI. Battery CSV import is
  deferred, not technically impossible.
- Keep the initial Results page as a simple text specification/summary rather
  than requiring plots. Detailed operation labels and additional uncertainty
  controls will be supplied during UI implementation.

**Decided by:**
Team direction confirmed by the user in chat; not advisor approval.

**Implementation status and unresolved details:**
The two preparation scripts were subsequently implemented on 18 Oct 2026;
see their READMEs and the project journal for verified scope. The later desktop
implementation and explicit min/max/step decision are recorded below.
`optimizer.py` continues searching explicit catalogs; the UI constructs these
from user-entered bounds/steps without changing the engine. The report's page
24 PV equation has an overlapping
last condition (`s >= R_CR`) while its prose says saturation begins at standard
irradiance. The implementation follows the prose (`s >= R_SRS`) and records
the discrepancy without editing the submitted report. PV ratings, bus
assignments and irradiance-unit handling must remain explicit inputs.

The Sindi paper uses a normal load pdf (Section 3) and provides 24 hourly
means/standard deviations as percentages (Table 1, pages 11–12). Sampling a
multi-month series from those statistics is a project adaptation, not a replay
of measured local demand or an implementation of the paper's full optimizer.
The implemented adaptation uses one shared hourly multiplier on aggregated base
P/Q, preserves power factor and documents independent hours/no seasonal model.
This input generator does not replace the confirmed
ARIMA/Monte Carlo/100-to-45 uncertainty workflow without a further decision.

**Related material:**
`02_Reports/Working/Drafts/UI.pptx`;
`02_Reports/Submitted/Term_1_Final/EE499-S26_Report-Term_1_Team-16.pdf`, page 24;
`04_Research/Papers/sustainability-14-13209.pdf`, Section 3 and Table 1.

## 2026-10-18 — Desktop sizing resolution and starting dispatch confirmed

**Decision:**
In direct answers to the implementation questions, the user selected:

- Minimum/maximum battery power and energy **plus configurable steps**, keeping
  the current catalog-based optimizer instead of introducing continuous sizing.
- A **user-set net-load target** as the simple starting operating policy:
  request = original load minus available PV minus target; discharge above,
  charge below. There is no fixed 600 kW target in the application.

**Implementation detail:**
The UI creates endpoint-inclusive generic study catalogs (last interval may be
shorter), not claims of available supplier products. Target/ranges/steps,
efficiencies and prices remain explicit user inputs. A positive target may
charge from the grid; rating/SOC/reserve/network constraints may prevent tracking.
No-BESS simulation remains available and ignores the configured battery policy.

**Decided by:**
User confirmation in chat; not an advisor-approved dispatch strategy or a
validation of objective weights/engineering performance.

**Related material:**
`07_Implementation/src/README_ui.md`; desktop implementation contract in
`02_Reports/Working/Planning/TERM2_SOFTWARE_DESIGN_SPEC.md`.

## Entry template

```markdown
## YYYY-MM-DD — Short decision title

**Decision:**  
What the team explicitly decided.

**Reason:**  
Short rationale, if known.

**Decided by:**  
Team / advisor-approved / named meeting.

**Related material:**  
Repository paths to meeting minutes, analysis, report, or evidence.
```

When a major decision is confirmed in chat and repository write access is available, the AI may add it directly without requesting separate approval for the markdown update.

## 2026-10-13 — GUI scope and earlier full-program testing

**Decision:** The GUI takes network data and automatically builds the distribution-system diagram, including buses, lines, PV and BESS locations. It does not require manual drag-and-drop network construction. Schedule GWO development for 18–24 Oct, uncertainty for 25–31 Oct, GUI development for 1–7 Nov and complete-program testing from 8 Nov.

**Reason:** Reserve more time to find, fix and retest bugs before formal validation and the 30 Nov report deadline.

**Decided by:** Primary repository user, confirmed in chat on 13 Oct; repository synchronization requested on 15 Oct.

**Related material:** Live Google Sheet; `02_Reports/Working/Planning/TERM2_DETAILED_TASK_GUIDE.md`; `02_Reports/Working/Planning/EE499_Team16_Term2_Task_Register.csv`.
