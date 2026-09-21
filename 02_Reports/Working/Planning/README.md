# Term 2 Gantt Schedule — How to Use

## Main working files

- Google Sheet schedule: https://docs.google.com/spreadsheets/d/1HE7RNvaZ-VkVMlozWfkfPbe23hywnEdOzuaI1CfAEcY/edit
- Report writing map (Google Doc): https://docs.google.com/document/d/1raGucOGbKPVh9FvsIZkMzoAT2raXHNQTlgHec9KbwGo/edit
- `TERM2_SHADOW_DESIGN.md` — starting implementation baseline for Tasks 9–17.
- `TERM2_DETAILED_TASK_GUIDE.md` — detailed explanation of all current tasks.
- `EE499_Team16_Term2_Task_Register.csv` — version-controlled snapshot of the live Task Register.

The internal target is to finish by **31 December 2026**.

## Main rule

Chapters 1–3 stay frozen. Start from the Term 1 design, implement it, validate it, and only change a method when implementation evidence or advisor feedback gives a clear reason. Important changes are explained in Chapter 4.

## Writing while implementing

Do not wait until the end to start Chapter 4.

Each implementation stage now has a matching writing task:

- Task 19 → write V1 network implementation.
- Task 26 → write V2 BESS implementation.
- Task 31 → write V3 manual comparison.
- Task 40 → write V4 GWO implementation.
- Task 50 → write V5 uncertainty implementation.
- Task 57 → write V6 software integration.
- Task 64 → merge and polish the complete Chapter 4.

Task 41 prepares the Chapter 5 format before the final tests. Tasks 58–62 generate the main validation evidence. Task 61 is the final **Term 1 requirement-validation matrix**.

## Final validation rule

The original Term 1 requirements remain the reference. Do not rewrite a requirement to make it easier to pass.

For each requirement, report:

`Requirement → Target → Test → Measured result → Met / Partially Met / Not Met → Evidence`

Examples include network size, PV penetration, scenario count, load-shedding reduction, optimizer iteration limit, curtailment reduction, cost reduction, voltage limits and SOC limits.

## Current schedule structure

| Tasks | Main work |
|---|---|
| 1–7 | Data |
| 8 | Ethics / responsibility |
| 9–11 | Shadow baseline + code setup |
| 12–19 | V1 network + Chapter 4 writing |
| 20–26 | V2 fixed BESS + Chapter 4 writing |
| 27–31 | V3 manual comparison + Chapter 4 writing |
| 32–40 | V4 WSM/GWO + Chapter 4 writing |
| 41 | Prepare Chapter 5 validation structure |
| 42–50 | V5 uncertainty + Chapter 4 writing |
| 51–57 | V6 software + Chapter 4 writing |
| 58–63 | Final validation/testing/results |
| 64–65 | Final Chapter 4–6 + ethics |
| 66 | Demo and final QA |

## Weekly use

Update the **Task Register**, not the Gantt bars directly. Update Owner, Status, Progress, Start/End dates and dependencies. The Semester Gantt updates automatically.
