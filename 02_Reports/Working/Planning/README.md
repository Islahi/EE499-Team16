# Term 2 Gantt Schedule — How to Use

This folder contains the working semester schedule for EE499 Team 16:

- `EE499_Team16_Term2_Gantt_Schedule.xlsx`

The workbook is an **internal planning tool**, not an official EE499 schedule. Official Term 2 deadlines are still TBA and should replace the internal dates when announced.

## Immediate priority

The advisors asked the team to **get the required project data before the next meeting (date TBA)**.

Therefore, Tasks **1–7** are the current priority:

1. Define required datasets and fields.
2. Acquire load-demand time-series data.
3. Acquire solar/weather/PV data.
4. Acquire distribution-network reference data.
5. Check source, license, units, resolution, timestamps, and data quality.
6. Clean/resample/synchronize the datasets.
7. Prepare a short data package for the next advisor meeting.

The meeting package should contain the data sources, sample plots, quality/coverage notes, and unresolved questions.

## Workbook structure

### 1. Semester Gantt

This sheet gives the full semester timeline from **20 September 2026 to 7 January 2027**.

Use it to see:

- project phases,
- task start/end dates,
- weekly activity blocks,
- critical tasks,
- overall progress,
- the next-advisor-meeting gate.

The weekly bars are generated from each task's Start and End dates.

### 2. Task Register

This is the main sheet to update during the semester.

For each task, maintain:

- **Owner** — Team, Muhammad, Mohammed, or Fahad.
- **Status** — Not Started, In Progress, Blocked, Done, or TBA.
- **Progress** — percentage from 0% to 100%.
- **Start / End** — revise when the real schedule changes.
- **Dependency** — tasks or decisions that must be completed first.

The `Deliverable / Definition of Done` column states what must exist before a task should be considered complete.

### 3. Lists

This sheet contains the values used by the dropdown menus in the Task Register. It usually does not need editing.

## Weekly workflow

At least once each week:

1. Open the **Task Register**.
2. Update each active task's Owner, Status, and Progress.
3. Adjust dates when necessary.
4. Mark blocked tasks and note the dependency/problem.
5. Review the **Semester Gantt** to check whether later tasks are being affected.
6. Before advisor meetings, review the current critical tasks and prepare evidence/results rather than only reporting activity.

## When official dates are announced

The current workbook uses internal planning dates because formal Term 2 deadlines are not yet available.

When the university/advisor announces a submission, presentation, or meeting date:

1. Update the affected task dates in the Task Register.
2. Move upstream tasks earlier if required.
3. Preserve a reasonable validation/reporting buffer near the end of the term.
4. Do not treat **7 January 2027** as an official deadline unless confirmed by the course.

## Planning logic

The schedule follows the classroom engineering-design guidance:

1. **Data acquisition**
2. **Product and software design**
3. **Simulation/mathematical design**
4. **Minimal deterministic 5-bus implementation**
5. **BESS model and deterministic optimization**
6. **Uncertainty modelling and scenario generation**
7. **Uncertainty-aware BESS optimization**
8. **Decision-support program integration**
9. **Validation and sensitivity analysis**
10. **IEEE 33-bus scalability/benchmark testing**
11. **Final documentation, presentation, and demo**

The intention is to avoid jumping directly into coding before the architecture, mathematical model, interfaces, assumptions, and validation plan are sufficiently defined.

## Important planning rule

The schedule is **not a permanent technical decision record**.

Changes to algorithms, network models, optimization methods, uncertainty methods, or other major technical choices become project decisions only after the team/advisor confirms them and they are recorded in `DECISIONS.md`.
