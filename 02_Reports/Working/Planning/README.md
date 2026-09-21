# Term 2 Gantt Schedule — How to Use

## Primary schedule

The working Term 2 schedule is here:

https://docs.google.com/spreadsheets/d/1HE7RNvaZ-VkVMlozWfkfPbe23hywnEdOzuaI1CfAEcY/edit

The target is to finish the internal project plan by **31 December 2026**.

The Google Sheet is the main working copy.  
`EE499_Team16_Term2_Task_Register.csv` is the repo snapshot.

## Main idea

We are not doing another long design phase before coding.

Chapters 1–3 are treated as frozen. We use the Term 1 design as the starting baseline, then fill the missing details through the shadow design while we implement the program.

The rule is simple:

```text
Term 1 design
    ↓
Implement it
    ↓
Test it
    ↓
Keep it if it works
    ↓
Change only when there is a clear reason
```

If we change something important, the reason should be written in Chapter 4.

The current shadow design is:

- `TERM2_SHADOW_DESIGN.md`

## Development path

The project is built in six versions:

1. **V1 — Network simulator**
2. **V2 — Fixed BESS**
3. **V3 — Manual sizing / placement comparison**
4. **V4 — Automatic optimization**
5. **V5 — Uncertainty-aware optimization**
6. **V6 — Final decision-support software**

The point is to understand and validate each layer before adding the next one.

## Schedule summary

| Tasks | Stage | Dates | Main result |
|---|---|---|---|
| 1–7 | Data | 20–27 Sep | Load, PV/weather and network data ready |
| 8 | Ethics | 27 Sep–3 Oct | Working ethics/responsibility note |
| 9–11 | Shadow baseline + setup | 27 Sep–4 Oct | Initial implementation structure ready |
| 12–18 | V1 — Network | 2–21 Oct | Validated 5-bus FBS network simulator |
| 19–24 | V2 — Fixed BESS | 18 Oct–2 Nov | Fixed BESS model working and validated |
| 25–28 | V3 — Manual comparison | 1–9 Nov | Understand effect of BESS location, P and E |
| 29–36 | V4 — GWO optimization | 7–29 Nov | Term 1 WSM + GWO implemented and checked |
| 37–44 | V5 — Uncertainty | 22 Nov–14 Dec | ARIMA + Monte Carlo + 45-scenario workflow working |
| 45–50 | V6 — Software | 1–18 Dec | Simple end-to-end decision-support UI |
| 51–55 | Final validation | 17–26 Dec | Before/after, sensitivity, IEEE 33-bus and final outputs |
| 56–58 | Documentation + finalization | 18–31 Dec | Chapter 4/5 updates, final discussion, demo and QA |

Some stages overlap on purpose. For example, the UI can start while V5 is finishing, and report writing starts before all final testing is complete.

## What each version means

### V1 — Network simulator

Build the small 5-bus radial network using the **Forward-Backward Sweep (FBS)** method from Term 1.

Done when:

- power flow runs,
- bus voltage is shown,
- line/current/loading is shown,
- losses and power balance are available,
- load/PV time series can be simulated,
- the result has been checked against a trusted/reference result.

### V2 — Fixed BESS

Add one battery with manually selected:

- bus (B),
- power (P),
- energy (E).

Done when SOC, charging/discharging, efficiency and limits work correctly and the BESS changes the network power flow correctly.

### V3 — Manual comparison

Before using GWO, manually try a few:

- bus locations,
- power ratings,
- energy capacities.

The goal is to understand what should happen and create a reference for the optimizer.

### V4 — Automatic optimization

Implement the Term 1 baseline:

- cost / curtailment / load shedding metrics,
- WSM with the initial 0.50 / 0.25 / 0.25 weights,
- GWO using (B,P,E).

Then compare GWO with exhaustive search on the small case.

Do not replace GWO before this test unless there is a clear technical/advisor reason.

### V5 — Uncertainty

Implement the Term 1 uncertainty path first:

```text
Historical data
    ↓
ARIMA
    ↓
Monte Carlo
    ↓
100 scenarios
    ↓
15 best + 15 worst + 15 random
    ↓
45 scenarios
    ↓
GWO / WSM
```

Then validate:

- ARIMA using RMSE/MAPE,
- scenario realism,
- whether the 45-scenario workflow gives a clear usable BESS result.

Only change the method after a real problem is found.

### V6 — Final software

Put the working backend into a simple UI.

Minimum flow:

```text
Load network/data
    ↓
Run baseline
    ↓
Run BESS optimization
    ↓
Show selected B, P, E
    ↓
Show before/after results
```

The UI does not need to be fancy. The engineering model is more important.

## Final validation

Tasks 51–55 answer the questions reviewers previously raised:

- Does BESS actually improve the system?
- Does changing scenario count affect the result?
- Do GWO population/iterations matter?
- Do WSM weights strongly change the recommendation?
- Does the program still work on IEEE 33-bus?
- Can the result be reproduced?

These results mainly belong in **Chapter 5**.

## Report connection

Because Chapters 1–3 are frozen:

- **Task 8** → Appendix D / ethics material and Chapter 6.2 where useful.
- **Tasks 9–17 shadow design** → internal implementation support; do not rewrite Chapters 1–3.
- **V1–V6 implementation** → Chapter 4.
- **Validation tasks** → Chapter 5.
- **Evaluation/discussion** → Chapter 6.
- Important changes from Term 1 → explain and justify in Chapter 4.

## Google Sheet structure

### Task Register

This is the main tab to edit.

Update:

- **Owner**
- **Status**
- **Progress**
- **Start / End**
- **Dependency**

The task wording is intentionally short and simple.  
The `Task Explanation` column tells you what you actually need to do.  
The `Deliverable / Definition of Done` column tells you when the task is finished.

### Semester Gantt

Do not manually draw the bars.

The Gantt reads the Task Register automatically.

Status colors:

- **Not Started** — gray
- **In Progress** — blue
- **Blocked** — red
- **Done** — green
- **TBA** — yellow

The current weekly window ends with the week of **27 December**, which covers the internal finish date of **31 December 2026**.

### Instructions

Contains the short version of this workflow inside the Google Sheet.

## Weekly routine

Once a week:

1. Check the active tasks.
2. Update owner.
3. Update status and progress.
4. Move dates if reality changed.
5. Check blocked tasks.
6. Check the Gantt for later tasks that are affected.
7. Save evidence of completed work: code, plots, test results, or notes.

## Important rule

The schedule is not the permanent technical decision record.

Confirmed major project changes should still be recorded in `DECISIONS.md`.

The schedule tells us **what to work on and when**.  
The shadow design tells us **how we currently plan to build it**.  
Chapter 4 later records **what we actually built and what changed**.
