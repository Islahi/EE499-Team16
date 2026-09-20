# Term 2 Gantt Schedule — How to Use

## Primary working schedule

The current semester schedule is maintained as a native Google Sheet:

https://docs.google.com/spreadsheets/d/1HE7RNvaZ-VkVMlozWfkfPbe23hywnEdOzuaI1CfAEcY/edit

Use the Google Sheet as the **primary working copy** because it is easier for the team to access and update collaboratively.

This repository also keeps `EE499_Team16_Term2_Task_Register.csv` as a version-controlled snapshot of the task register.

The schedule is an **internal planning tool**, not an official EE499 schedule. Official Term 2 deadlines are still TBA and should replace the internal dates when announced.

## Immediate priorities

### 1. Data before the next advisor meeting

The advisors asked the team to obtain the required project data before the next meeting (date TBA).

Tasks **1–7** therefore remain the immediate delivery gate:

1. Define required datasets and fields.
2. Acquire load-demand time-series data.
3. Acquire solar/weather/PV data.
4. Acquire distribution-network reference data.
5. Check source, license, units, resolution, timestamps, and data quality.
6. Clean/resample/synchronize the datasets.
7. Prepare the advisor-meeting data package.

The meeting package should contain the data sources, sample plots, quality/coverage notes, and unresolved questions.

### 2. Ethics and professional responsibility

Task **8** is also an early priority rather than an end-of-term writing exercise.

The team should define the project's ethics/professional-responsibility considerations while the design is still being developed, including:

- data integrity and provenance,
- transparent assumptions and limitations,
- grid reliability and safety implications,
- environmental/economic trade-offs,
- responsible interpretation/use of optimization recommendations,
- and points that may need to be carried into the final report.

At present this is treated as a prudent project/report task; the repository search did not independently verify a specifically named mandatory "Ethics" section in the official material.

## Google Sheet structure

### Semester Gantt

Use this tab for the weekly semester overview. A filled square means that the task is active during that week.

### Task Register

This is the main tab to edit.

For each task, maintain:

- **Task Explanation** — what the task actually involves and what work should be carried out.
- **Owner** — Team, Muhammad, Mohammed, or Fahad.
- **Status** — Not Started, In Progress, Blocked, Done, or TBA.
- **Progress** — update as work advances.
- **Start / End** — revise when real dates change.
- **Dependency** — note prerequisite tasks or decisions.

The `Deliverable / Definition of Done` column defines what should exist before a task is considered complete.

### Instructions

This tab contains a short in-sheet reminder of the workflow and priorities.


## Dynamic Gantt behavior

The **Semester Gantt** is now automatically linked to the **Task Register**.

Do **not** manually edit the task rows or weekly bars in the Gantt tab. Instead, update the Task Register:

- changing **Start** or **End** moves the weekly Gantt bar automatically;
- changing **Status** updates the Gantt status display and bar formatting;
- changing **Progress** updates the percentage shown in the Gantt;
- changing the task name, phase, or priority is also reflected automatically.

Current status colors are:

- **Not Started** — gray
- **In Progress** — blue
- **Blocked** — red
- **Done** — green
- **TBA** — yellow

The weekly columns are fixed to the current internal semester planning window. If the official semester end moves outside that window, extend the weekly columns/formulas accordingly.

## Weekly workflow

At least once each week:

1. Open the Google Sheet.
2. Update active tasks in **Task Register**.
3. Assign or revise owners.
4. Update status and progress.
5. Adjust dates when required.
6. Mark blocked tasks and their dependencies.
7. Check the **Semester Gantt** for downstream impact.
8. Before advisor meetings, prepare evidence/results rather than only reporting activity.

## When official dates are announced

When the university or advisor announces a submission, presentation, or meeting date:

1. Update the affected task dates in the Google Sheet.
2. Move dependent/upstream work earlier if required.
3. Preserve a reasonable validation/reporting buffer.
4. Do not treat **7 January 2027** as an official deadline unless confirmed by the course.

## Planning logic

The schedule currently follows this sequence:

1. **Data acquisition**
2. **Ethics / professional responsibility**
3. **Product and software design**
4. **Simulation/mathematical design**
5. **Minimal deterministic 5-bus implementation**
6. **BESS model and deterministic optimization**
7. **Uncertainty modelling and scenario generation**
8. **Uncertainty-aware BESS optimization**
9. **Decision-support program integration**
10. **Validation and sensitivity analysis**
11. **IEEE 33-bus scalability/benchmark testing**
12. **Final documentation, presentation, and demo**

The intention is to avoid jumping directly into coding before the architecture, mathematical model, interfaces, assumptions, ethical considerations, and validation plan are sufficiently defined.

## Important planning rule

The schedule is **not a permanent technical decision record**.

Changes to algorithms, network models, optimization methods, uncertainty methods, or other major technical choices become project decisions only after the team/advisor confirms them and they are recorded in `DECISIONS.md`.
