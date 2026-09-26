# Term 2 Working Context — Current Summary

**Last updated:** 2026-09-26

This file is the current working context for EE499 Team 16.

> **Important:** Chapters 1–3 from Term 1 are frozen. Term 1 technical choices are the implementation baseline and should only change when implementation evidence, validation, unavailable data, or advisor feedback gives a clear reason. Important changes must be justified in Chapter 4.

## 1. Current project status

The early preparation stage is finished.

- Tasks 1–7 are **Done**: load, PV/weather and network data were acquired, checked, cleaned/aligned and stored in simulation-ready form last week.
- No separate advisor data-presentation/package task is needed.
- The implementation baseline is finalized and is no longer an active planning task.
- Task 8 Ethics is a **parallel task** and must not block implementation.
- Current active work starts with Task 10: code structure, then V1/V2 implementation.

## 2. Project direction

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

## 3. Term 1 baseline to implement first

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

Do **not** replace FBS, GWO, ARIMA, the 45-scenario method or the WSM baseline simply because another method looks better before implementation. Implement first, test, then change only when evidence supports it.

## 4. Implementation sequence

The current staged implementation is:

1. **Setup** — code structure + basic interfaces
2. **V1 — Network simulator**
3. **V2 — Fixed BESS**
4. **V3 — Manual BESS sizing/placement trials**
5. **V4 — Automatic GWO optimization**
6. **V5 — ARIMA + Monte Carlo uncertainty workflow**
7. **V6 — Integrated decision-support software/UI**
8. **Formal Chapter 5 validation experiments**
9. **Final report**
10. **Final presentation/demo**

The implementation baseline is already finalized. Current planning should not describe it as an unfinished design phase.

## 5. Parallel Ethics work

Task 8 runs alongside implementation from **26 Sep to 7 Oct** as an internal draft target.

The ethics assignment is individual and requires a **3–5 page report**. Each member must analyze **two distinct ethical issues** and cover:

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

The official schedule supplied does not state an ethics-assignment due date. The current 7 Oct date is only an internal draft target.

## 6. Official Spring 2026 Term 2 schedule

The official schedule controls planning:

- **22 Oct 2026** — Progress Update submission.
- **25–29 Oct 2026** — Progress Update presentation window.
- **30 Nov 2026** — Final Term 2 report submission.
- **6–10 Dec 2026** — Final presentation window.

Because the report is due 30 Nov, implementation, formal validation, final figures/tables, Chapter 4, Chapter 5, Chapter 6 and Appendix D must be substantially finished before that date. December is mainly for final presentation/demo preparation and delivery.

## 7. Progress Update target

By **22 Oct**, the team should aim to show:

- V1 FBS network simulator working and verified,
- fixed-BESS V2 working and checked,
- a small V3 manual placement/sizing comparison,
- Chapter 4 notes/figures ready to reuse,
- current problems and next steps clearly identified.

Task 31 prepares both the V3 Chapter 4 draft and Progress Update technical content.

## 8. Final-report template alignment

The actual `EE499_Final_Report_Template_v2025_Fall` is the authority for Chapters 4 onward.

### Chapter 4 — Implementation

Must include:

- practical implementation details,
- multiple trials used to reach a satisfactory level,
- related design calculations,
- justified/documented changes from the baseline design,
- final-product assembly with multiple screenshots/images.

### Chapter 5 — Validation Experiments

Formal experiments may test major parts of the product and/or the final product to validate the design specifications.

Each experiment must include:

1. objective,
2. relevant background,
3. detailed work plan/steps,
4. appropriate tools,
5. collected data in organized figures/tables,
6. analysis/interpretation and conclusion.

Current planned experiments:

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

Section 6.1 discusses whether the Term 1/customer design requirements were satisfied based on Chapter 5 results.

## 9. Validation vs implementation trials

Chapter 4 can contain implementation verification/trials such as:

- FBS comparison against a trusted/manual result,
- SOC hand checks,
- GWO vs exhaustive search,
- GWO population/iteration trials,
- ARIMA RMSE/MAPE checks,
- scenario realism checks,
- software failure/input tests.

Chapter 5 contains the **formal validation experiments** tied to Term 1 design specifications.

Chapter 6.1 gives the final interpretation of whether requirements were met.

## 10. Saudi Council of Engineers Engineer Charter 2025

The SCE Engineer Charter 2025 is the project ethics-code source.

Especially relevant rules include:

- honesty/integrity/public interest,
- intellectual-property rights,
- responsibility for engineering work and safety,
- confidentiality of information/data,
- conflict-of-interest disclosure,
- public interest and competent cost estimation,
- accurate/objective/independent technical reporting supported by evidence,
- public interest and safety standards,
- quality, sustainability and reliability.

Two strong project-specific ethical issues are:

1. **Truthful reporting under model uncertainty** — avoiding overstatement of optimizer/forecast/scenario reliability.
2. **Economic optimization versus reliability/public safety** — avoiding a cheaper BESS recommendation that violates technical/reliability constraints.

## 11. Appendix D and Chapter 6.2 reuse

For **Appendix D**:

- use the SCE Engineer Charter 2025,
- select one suitable project ethical issue,
- identify relevant Charter rules,
- analyze the issue,
- make an informed decision.

For **Chapter 6.2 Impact of Solution**, reuse suitable team-level material about safety, sustainability, environmental/economic/social impacts and responsible communication.

## 12. Important implementation checks

### V1 / FBS
Use the small radial case to verify voltage, power balance and losses. A trusted external solver can be used as an independent reference, but FBS remains the baseline solver unless evidence requires a change.

### V2 / BESS
Verify SOC and energy updates manually for simple charge/discharge cases before using BESS in optimization.

### V4 / GWO
Use a deliberately small finite search space and exhaustive search as a reference. GWO stays the baseline optimizer unless evidence shows a real problem.

### V5 / uncertainty
Implement Term 1 ARIMA + Monte Carlo + 100→45 selection first. Validate ARIMA with held-out data/RMSE/MAPE and check scenario realism.

### Potential two-stage stochastic issue
The original project brief asks for a two-stage stochastic planning structure. If the implemented Term 1 workflow produces different physical B/P/E deployments for different future scenarios, demonstrate the inconsistency first, then justify any refinement in Chapter 4 rather than silently replacing the baseline.

## 13. Data status

Data acquisition and preprocessing are complete as of **25 Sep 2026**.

The current simulation-ready package includes:

- historical load data,
- PV/weather/irradiance data,
- 5-bus development network,
- IEEE 33-bus network,
- source/unit notes and cleaned/aligned files.

Future data work should only happen when implementation reveals a specific missing field/parameter or quality problem.

## 14. Planning artifacts

Live Google Sheet:

https://docs.google.com/spreadsheets/d/1HE7RNvaZ-VkVMlozWfkfPbe23hywnEdOzuaI1CfAEcY/edit

Writing map:

https://docs.google.com/document/d/1raGucOGbKPVh9FvsIZkMzoAT2raXHNQTlgHec9KbwGo/edit

Current repository planning files:

- `README.md`
- `TERM2_DETAILED_TASK_GUIDE.md`
- `EE499_Team16_Term2_Task_Register.csv`
- `TERM2_WORKING_CONTEXT.md`

The earlier implementation-baseline working document is retained only as historical/reference material and is not an active scheduled task.

Official/reference additions:

- `01_Official/Course_Guidance/Ethical_Analysis.md`
- `01_Official/Course_Guidance/Term2_Official_Schedule_2026.md`
- `01_Official/Course_Guidance/SCE_Engineer_Charter_2025_Project_Reference.md`

## 15. Overall current interpretation

The project is now in implementation mode:

> **data ready → code setup → V1/V2/V3 → optimization/uncertainty/UI → formal validation → final report by 30 Nov → final presentation/demo in Dec.**

Ethics runs in parallel. The live Google Sheet is the primary schedule. If an older discussion/file conflicts with the current sheet or official schedule, use the current sheet and official schedule.