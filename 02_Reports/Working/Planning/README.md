# Term 2 Gantt Schedule — How to Use

## Main working files

- Google Sheet schedule: https://docs.google.com/spreadsheets/d/1HE7RNvaZ-VkVMlozWfkfPbe23hywnEdOzuaI1CfAEcY/edit
- Chapters 4–6 Writing Map: https://docs.google.com/document/d/1raGucOGbKPVh9FvsIZkMzoAT2raXHNQTlgHec9KbwGo/edit
- `TERM2_SHADOW_DESIGN.md` — starting implementation baseline.
- `TERM2_DETAILED_TASK_GUIDE.md` — detailed explanation of all tasks.
- `EE499_Team16_Term2_Task_Register.csv` — repo snapshot of the live Task Register.

## Core rule

**Chapter 4 = implementation + verification.**  
**Chapter 5 = validation against the original Term 1 requirements.**  
**Chapter 6 = discussion and conclusion.**

Verification means checking that a module/code implementation works correctly. Examples: FBS reference check, SOC hand check, GWO vs exhaustive search, ARIMA error check, scenario realism, software failure cases.

Validation means checking whether the final product satisfies the requirements already written in Term 1. Examples: load-shedding reduction, curtailment reduction, operational-cost reduction, voltage/SOC limits, scenario count, optimizer iteration limit, PV penetration and network size/scalability.

## Chapter 4 writing while implementing

Write each section while the implementation is fresh:

- Task 19 → V1 network simulator
- Task 26 → V2 BESS integration
- Task 31 → V3 manual BESS trials
- Task 40 → V4 deterministic optimization
- Task 50 → V5 uncertainty implementation
- Task 57 → V6 software integration
- Task 64 → merge and polish the complete Chapter 4

Task 59 sensitivity/robustness and Task 62 software-failure testing are also implementation verification, so their main evidence belongs with Chapter 4.

## Chapter 5

Task 41 prepares the validation plan from the Term 1 requirements.

Main final validation tasks:

- Task 58 → performance requirements
- Task 60 → network-size / scalability requirement
- Task 61 → complete Term 1 requirement-validation matrix

The final matrix uses:

`Requirement → Target → Test → Measured result → Met / Partially Met / Not Met → Evidence`

Do not rewrite a requirement to make it easier to pass.

## Chapter 4.9

Chapter 4.9 is the **final integrated system**. It does not introduce new algorithms. It shows how everything connects after V1–V6:

`Inputs → FBS/network → BESS → uncertainty → GWO/WSM → selected B,P,E → results/UI`

Explain what the user provides, what the program does internally, how modules connect, and what outputs are produced.

## Weekly use

Update the **Task Register**. The Semester Gantt updates automatically.
