# Term 2 Working Context — Current Summary

**Last updated:** 2026-09-26

This file is the current working context for EE499 Team 16. It supersedes older planning statements that used a 31 Dec internal completion target.

> **Important:** Chapters 1–3 from Term 1 are frozen. Term 1 technical choices are the implementation baseline and should only be changed when implementation evidence, validation, unavailable data, or advisor feedback gives a clear reason. Important changes must be justified in Chapter 4.

## 1. Project direction

The Term 2 product is a **working BESS planning / decision-support software tool** for renewable-integrated radial distribution networks.

Main workflow:

```text
Network + load/PV data
    ↓
FBS baseline simulation
    ↓
BESS model
    ↓
Deterministic optimization
    ↓
ARIMA + Monte Carlo uncertainty
    ↓
GWO / WSM recommendation
    ↓
Validation + results/UI
```

Planning variables remain:

- `B` = BESS location/bus,
- `P` = BESS power rating,
- `E` = BESS energy capacity.

Keep P and E distinct.

## 2. Term 1 baseline to implement first

Initial implementation should preserve:

- Forward-Backward Sweep (FBS) power flow,
- Grey Wolf Optimization (GWO),
- ARIMA forecasting,
- Monte Carlo uncertainty generation,
- 100 generated scenarios → 45 retained scenarios using 15 best + 15 worst + 15 random,
- WSM baseline weights used in Term 1,
- IEEE 33-bus as the official larger/final network case,
- solar PV as the implemented renewable source,
- hourly time step,
- SOC limits 10%–90%,
- voltage limits 0.95–1.05 pu,
- BESS decision vector `[B,P,E]`,
- cost + curtailment + load-shedding performance objectives.

A small ~5-bus system is only an internal debugging/verification case. It is not the final product limit.

Do **not** replace FBS, GWO, ARIMA, the 45-scenario method or the WSM baseline just because an alternative looks better before implementation. Implement first, test, then change only when evidence supports it.

## 3. Implementation sequence

The current staged implementation is:

1. **V1 — Network simulator**
2. **V2 — Fixed BESS**
3. **V3 — Manual BESS sizing/placement trials**
4. **V4 — Automatic GWO optimization**
5. **V5 — ARIMA + Monte Carlo uncertainty workflow**
6. **V6 — Integrated decision-support software/UI**
7. **Formal Chapter 5 validation experiments**
8. **Final report**
9. **Final presentation/demo**

The shadow-design document fills missing implementation details such as architecture, interfaces, data flow and test logic without rewriting Chapters 1–3.

## 4. Official Spring 2026 Term 2 schedule

The official schedule now controls planning:

- **16 Sep 2026** — Concept Session 2.
- **22 Oct 2026** — Progress Update submission.
- **25–29 Oct 2026** — Progress Update presentation window.
- **30 Nov 2026** — Final Term 2 report submission.
- **6–10 Dec 2026** — Final presentation window.

The previous internal target of **31 Dec 2026 is cancelled**.

Because the report is due 30 Nov, implementation, formal validation, final figures/tables, Chapter 4, Chapter 5, Chapter 6 and Appendix D must be substantially finished before that date. December is mainly for final presentation/demo preparation and delivery.

The live Google Sheet has been compressed accordingly, with parallel work after the Progress Update where dependencies allow.

## 5. Progress Update target

By **22 Oct**, the team should aim to show real implementation evidence rather than only planning:

- V1 FBS network simulator working and verified,
- fixed-BESS V2 working and checked,
- at least a small V3 manual placement/sizing comparison,
- Chapter 4 notes/figures ready to reuse,
- current problems and next steps clearly identified.

Task 31 is used both for the V3 Chapter 4 draft and Progress Update technical content.

## 6. Final-report template alignment

The actual `EE499_Final_Report_Template_v2025_Fall` has been read directly and is the authority for Chapters 4 onward.

### Chapter 4 — Implementation

Must include:

- practical implementation details,
- multiple trials used to reach a satisfactory level,
- related design calculations,
- justified/documented changes from the baseline design,
- final-product assembly with multiple photographs/images.

For this software project, use clear screenshots/images of the integrated software, result screens and final workflow.

### Chapter 5 — Validation Experiments

Formal experiments may test major parts of the product and/or the final product to validate the design specifications.

Each experiment must include:

1. objective,
2. relevant background,
3. detailed work plan/steps,
4. appropriate tools,
5. collected data in organized figures/tables,
6. analysis/interpretation and conclusion.

Current formal experiments:

1. technical/economic performance,
2. optimizer/uncertainty requirements,
3. IEEE 33-bus/network scalability,
4. final requirement-evidence summary.

### Chapter 6 — Discussion and Conclusion

Use the exact template headings:

- **6.1 Evaluation of Solution**
- **6.2 Impact of Solution**
- **6.3 Future Work**
- **6.4 Conclusion**

Section 6.1 is where the team discusses whether the Term 1/customer design requirements were satisfied based on Chapter 5 results.

## 7. Validation vs implementation trials

Chapter 4 can contain implementation verification/trials such as:

- FBS comparison against a trusted/manual result,
- SOC hand checks,
- GWO vs exhaustive search,
- GWO population/iteration trials,
- ARIMA RMSE/MAPE checks,
- scenario realism checks,
- software failure/input tests.

Chapter 5 contains the **formal validation experiments** written in the template format and tied to the Term 1 design specifications.

Chapter 6.1 gives the final interpretation of whether requirements were met.

## 8. Ethical analysis assignment

A new official ethics instruction has been added to the repository.

The ethics assignment is **individual** and requires a **3–5 page report**. Each member must analyze **two distinct ethical issues** and cover:

- project context/system overview,
- stakeholders and interests,
- two ethical/professional issues,
- at least two possible actions for each issue,
- ethical principles and professional responsibilities,
- stakeholder impact,
- relevant Saudi Council of Engineers Engineer Charter 2025 rules,
- safety, risk and compliance,
- data/privacy/security,
- global/economic/environmental/societal impacts,
- professional integrity and truthful communication,
- intellectual property/attribution/licensing,
- recommendations/mitigation,
- personal professional-responsibility reflection.

The supplied official schedule does **not** state an ethics-assignment due date. The current Task 8 deadline of **7 Oct** is only an internal draft target.

## 9. Saudi Council of Engineers Engineer Charter 2025

The SCE Engineer Charter 2025 is now the project ethics-code source.

Especially relevant rules for this project include:

- honesty/integrity/public interest,
- intellectual-property rights,
- responsibility for engineering work and safety,
- confidentiality of information/data,
- conflict-of-interest disclosure,
- public interest and competent cost estimation,
- accurate/objective/independent technical reporting supported by evidence,
- public interest and safety standards,
- quality, sustainability and reliability.

Two strong project-specific ethical issues for the individual assignment are:

1. **Truthful reporting under model uncertainty** — avoiding overstatement of optimizer/forecast/scenario reliability.
2. **Economic optimization versus reliability/public safety** — avoiding a cheaper BESS recommendation that violates technical/reliability constraints.

Other relevant topics include dataset confidentiality and IP/attribution for code, algorithms, datasets and papers.

## 10. Appendix D and Chapter 6.2 reuse

The individual ethics assignment is broader than the final-report Appendix D.

For **Appendix D**:

- use the SCE Engineer Charter 2025,
- select one suitable project ethical issue,
- identify relevant Charter rules,
- analyze the issue,
- make an informed decision.

For **Chapter 6.2 Impact of Solution**, reuse appropriate team-level material about safety, sustainability, environmental/economic/social impacts and responsible communication.

## 11. Important implementation checks

### V1 / FBS

Use the small radial case to verify voltage, power balance and losses. A trusted external solver can be used as an independent reference, but FBS remains the baseline solver unless evidence requires a change.

### V2 / BESS

Verify SOC and energy updates manually for simple charge/discharge cases before using BESS in optimization.

### V4 / GWO

Use a deliberately small finite search space and exhaustive search as a reference. GWO stays the baseline optimizer; reconsider only if it performs poorly or creates a real implementation problem.

### V5 / uncertainty

Implement Term 1 ARIMA + Monte Carlo + 100→45 selection first. Validate ARIMA with held-out data/RMSE/MAPE and check scenario realism. Only change the selection/forecast workflow when evidence justifies it.

### Potential two-stage stochastic issue

The original project brief asks for a two-stage stochastic planning structure. If the implemented Term 1 workflow produces different physical B/P/E deployments for different future scenarios, demonstrate the inconsistency first, then justify any refinement in Chapter 4 rather than silently replacing the baseline.

## 12. Data priority

The immediate early-term work remains:

- historical load time series,
- PV/weather/irradiance data,
- 5-bus + IEEE33 network data,
- later BESS technical/economic parameters.

A dataset is not considered ready merely because a link exists. Record source, variables, units, sampling interval, period, missing/outlier behavior, usage/license considerations and compatibility with the other datasets.

## 13. Planning artifacts

Live Google Sheet:

https://docs.google.com/spreadsheets/d/1HE7RNvaZ-VkVMlozWfkfPbe23hywnEdOzuaI1CfAEcY/edit

Writing map:

https://docs.google.com/document/d/1raGucOGbKPVh9FvsIZkMzoAT2raXHNQTlgHec9KbwGo/edit

Repository planning files:

- `README.md`
- `TERM2_SHADOW_DESIGN.md`
- `TERM2_DETAILED_TASK_GUIDE.md`
- `EE499_Team16_Term2_Task_Register.csv`

Official/reference additions:

- `01_Official/Course_Guidance/Ethical_Analysis.md`
- `01_Official/Course_Guidance/Term2_Official_Schedule_2026.md`
- `01_Official/Course_Guidance/SCE_Engineer_Charter_2025_Project_Reference.md`

## 14. Overall current interpretation

The project is not starting from zero. Term 1 provided a substantial technical foundation, but Term 2 must turn it into:

> **an implementable engineering system → working integrated software → formal validation evidence → final report by 30 Nov → final presentation/demo in Dec.**

The live Google Sheet is the primary schedule. If dates in an older discussion/file conflict with the live sheet or official schedule, use the official schedule and current sheet.
