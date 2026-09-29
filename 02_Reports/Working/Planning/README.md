# Term 2 Planning — How to Use

## Current status — 26 Sep 2026

The early preparation stage is finished.

- Tasks 1–7: **Done** — data acquisition, checking, cleaning, alignment and the simulation-ready data package were completed last week.
- Task 9: **Done** — the implementation baseline is finalized.
- No separate advisor data presentation/package is planned.
- Task 8 Ethics runs **in parallel** with implementation and does not block coding.
- Current main work starts with **Task 10 — Set up the code structure from the design spec** and then V1/V2 implementation.

## Main working files

- Google Sheet schedule: https://docs.google.com/spreadsheets/d/1HE7RNvaZ-VkVMlozWfkfPbe23hywnEdOzuaI1CfAEcY/edit
- Chapters 4–6 Writing Map: https://docs.google.com/document/d/1raGucOGbKPVh9FvsIZkMzoAT2raXHNQTlgHec9KbwGo/edit
- `TERM2_SOFTWARE_DESIGN_SPEC.md` — **implementation handoff specification** for software architecture, module responsibilities, data structures, interfaces, file formats, units and required/optional outputs.
- `TERM2_SHADOW_DESIGN.md` — finished high-level technical baseline using stable `SD-1` to `SD-9` section IDs.
- `TERM2_DETAILED_TASK_GUIDE.md` — detailed explanation of the current tasks.
- `EE499_Team16_Term2_Task_Register.csv` — repo snapshot of the live Task Register.

The **live Task Register/Gantt is the source of truth for task numbers, dates, status and dependencies**.

## Design → implementation rule

The technical design documents define **what must be implemented**. Implementation tasks should not independently choose software architecture, module boundaries, data formats, sign conventions or public interfaces.

Use this sequence:

```text
Term 1 / project baseline
        ↓
TERM2_SHADOW_DESIGN.md
        ↓
TERM2_SOFTWARE_DESIGN_SPEC.md
        ↓
Current Gantt implementation task
        ↓
Coding + testing + debugging
        ↓
Implementation evidence / validation
```

The software design specification explicitly distinguishes:

- **existing baseline requirements**, and
- **proposed design decisions** where the existing requirements did not determine a software detail.

If the team rejects a proposed design decision, update the design specification first so different implementation owners do not create incompatible local solutions.

Examples of implementation handoff:

- `network_model.py` structure/fields/units are defined before Task 12.
- `fbs.py` inputs, outputs and convergence interface are defined before Task 13.
- load/PV CSV format and `ProfileData` interface are defined before Task 16.
- BESS structures, sign convention and step interface are defined before Tasks 20–23.
- future scenario and optimizer interfaces are reserved before V4/V5 implementation.

## Technical baseline ↔ Gantt relationship

The schedule implements the technical baseline; old design-task numbering is not used.

Examples:

- `SD-5 Network / FBS` → Tasks **12–19** and **60**.
- `SD-6 BESS` → Tasks **20–31**.
- `SD-7 Objective / GWO` → Tasks **32–40**.
- `SD-8 Uncertainty` → Tasks **42–50**.
- `SD-9 Verification / Validation` → verification tasks throughout implementation plus formal Tasks **41, 58–61**.

If implementation produces a real design change, update the technical design reference and justify the change in Chapter 4. Do **not** renumber technical-design sections to match future Gantt edits.

## Official Term 2 deadlines

The official Spring 2026 schedule controls the plan:

- **22 Oct 2026** — Progress Update submission.
- **25–29 Oct 2026** — Progress Update presentation window.
- **30 Nov 2026** — Final Term 2 report submission.
- **6–10 Dec 2026** — Final presentation window.

Because the report is due 30 Nov, implementation, validation, final figures/tables, and Chapters 4–6 must be substantially complete before then. December is mainly for the final presentation/demo.

Official schedule reference: `../../01_Official/Course_Guidance/Term2_Official_Schedule_2026.md`.

## Progress Update target

By 22 Oct, aim to show real implementation rather than only planning:

- V1 FBS network simulator working and checked,
- fixed-BESS V2 working,
- a small V3 manual placement/sizing comparison completed or nearly completed,
- Chapter 4 notes/figures ready to reuse,
- current problems and next steps clearly identified.

## Ethics / professional responsibility

Ethics is a **parallel task**. It should not delay Tasks 10 onward.

The separate ethics assignment is an **individual 3–5 page report**. Each member must analyze **two distinct ethical issues** and cover stakeholders, decision alternatives, safety/risk/compliance, data/privacy/security, broader impacts, professional integrity, IP/attribution, mitigation and reflection using the Saudi Council of Engineers Engineer Charter 2025.

References:

- `../../01_Official/Course_Guidance/Ethical_Analysis.md`
- `../../01_Official/Course_Guidance/SCE_Engineer_Charter_2025_Project_Reference.md`

Strong team-level material can later be reused in **Chapter 6.2** and **Appendix D**.

## Official final-report template

### Chapter 4 — Implementation

Include practical implementation details, multiple trials, related design calculations, justified changes from the Term 1 baseline, and final-product screenshots/images.

Write Chapter 4 gradually:

- Task 19 → V1
- Task 26 → V2
- Task 31 → V3 trials + Progress Update content
- Task 40 → V4
- Task 50 → V5
- Task 57 → V6/final product
- Task 64 → merge + official-template compliance check

### Chapter 5 — Validation Experiments

Formal experiments validate the Term 1 design specifications. Each experiment needs objective, background, detailed steps, tools, figures/tables/data, and analysis/conclusion.

- Task 58 → technical/economic performance
- Task 59 → optimizer/uncertainty requirements
- Task 60 → IEEE 33-bus/network scalability
- Task 61 → requirement-evidence summary

### Chapter 6 — Discussion and Conclusion

Use the exact template headings:

- **6.1 Evaluation of Solution**
- **6.2 Impact of Solution**
- **6.3 Future Work**
- **6.4 Conclusion**

## Weekly use

Update the **Task Register**. The Semester Gantt, Monthly Calendar and Weekly Schedule update automatically. Work in parallel where dependencies allow, especially Ethics, report writing, UI work and later validation preparation.
