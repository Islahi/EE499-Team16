# Term 2 Planning — How to Use

## Main working files

- Google Sheet schedule: https://docs.google.com/spreadsheets/d/1HE7RNvaZ-VkVMlozWfkfPbe23hywnEdOzuaI1CfAEcY/edit
- Chapters 4–6 Writing Map: https://docs.google.com/document/d/1raGucOGbKPVh9FvsIZkMzoAT2raXHNQTlgHec9KbwGo/edit
- `TERM2_SHADOW_DESIGN.md` — implementation baseline.
- `TERM2_DETAILED_TASK_GUIDE.md` — detailed explanation of the current tasks.
- `EE499_Team16_Term2_Task_Register.csv` — repo snapshot of the Task Register.

## Official Term 2 deadlines

The official Spring 2026 schedule now controls the plan:

- **22 Oct 2026** — Progress Update submission.
- **25–29 Oct 2026** — Progress Update presentation window.
- **30 Nov 2026** — Final Term 2 report submission.
- **6–10 Dec 2026** — Final presentation window.

The old internal target of 31 Dec is cancelled. Because the report is due 30 Nov, implementation, validation, final figures/tables, and Chapters 4–6 must be substantially complete before then. December is mainly for the final presentation/demo.

Official schedule reference: `../../01_Official/Course_Guidance/Term2_Official_Schedule_2026.md`.

## Progress Update target

By 22 Oct, aim to show real implementation rather than only planning:

- V1 FBS network simulator working and checked,
- fixed-BESS V2 working,
- a small V3 manual placement/sizing comparison started or completed,
- Chapter 4 notes/figures ready to reuse in the progress submission and presentation.

## Official final-report template

Planning is aligned to **EE499_Final_Report_Template_v2025_Fall**.

### Chapter 4 — Implementation

The template requires:

- practical implementation details,
- subsections showing multiple trials used to reach a satisfactory level,
- related design calculations,
- justified/documented changes from the baseline design,
- final-product assembly with multiple photographs/images.

For our software project, V1–V6 provide the implementation subsections. Manual BESS trials, GWO/exhaustive-search trials, forecast/scenario checks, sensitivity work and software failure-case trials are useful Chapter 4 evidence. The final software section should include multiple screenshots/images.

### Chapter 5 — Validation Experiments

Chapter 5 is not only a pass/fail matrix. The template allows validation experiments on **major parts and/or the final product** to validate the design specifications.

Every formal experiment needs:

1. experiment objective,
2. relevant background,
3. detailed work plan/steps,
4. appropriate tools,
5. collected data in organized figures/tables,
6. analysis/interpretation and conclusion.

Current formal experiments:

- Task 58 → Experiment 1: technical/economic performance
- Task 59 → Experiment 2: optimizer/uncertainty requirements
- Task 60 → Experiment 3: IEEE 33-bus/network scalability
- Task 61 → requirement-evidence summary

The original Term 1 requirements/specifications remain the validation targets.

### Chapter 6 — Discussion and Conclusion

Use the exact template headings:

- **6.1 Evaluation of Solution** — discuss whether customer/design requirements were satisfied based on Chapter 5 results.
- **6.2 Impact of Solution** — global/social/environmental/economic/safety impacts as relevant.
- **6.3 Future Work** — recommended future improvements.
- **6.4 Conclusion** — summarize the need, solution and final achievements.

## Ethics / professional responsibility

The new ethics assignment is **separate from Appendix D** and is an **individual 3–5 page report**. Each member must analyze **two distinct ethical issues** and cover stakeholders, decision alternatives, safety/risk/compliance, data/privacy/security, broader impacts, professional integrity, IP/attribution, mitigation and reflection using the Saudi Council of Engineers Engineer Charter 2025.

Official/working references in the repo:

- `../../01_Official/Course_Guidance/Ethical_Analysis.md`
- `../../01_Official/Course_Guidance/SCE_Engineer_Charter_2025_Project_Reference.md`

Strong team-level material from the individual ethical analyses can later be reused in **Chapter 6.2** and **Appendix D**.

### Appendix D

Use the **Saudi Council of Engineers Engineer Charter 2025** as the ethics-code source. Appendix D is smaller than the individual assignment: select one suitable project ethical issue, identify relevant Charter rule(s), analyze it, and make an informed decision.

## Writing while implementing

Write Chapter 4 gradually:

- Task 19 → V1
- Task 26 → V2
- Task 31 → V3 trials + Progress Update content
- Task 40 → V4
- Task 50 → V5
- Task 57 → V6/final product
- Task 64 → merge + official-template compliance check

## Weekly use

Update the **Task Register**. The Semester Gantt updates automatically. After 22 Oct, several tasks intentionally overlap because the official final-report deadline is 30 Nov; work in parallel where dependencies allow.
