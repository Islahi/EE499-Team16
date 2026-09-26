# EE499 Team 16 — Battery Storage Optimization

> **Read this file first.** This repository is a self-contained project knowledge base for humans and AI assistants. It is designed to remain understandable across different AI sessions, accounts, and tools without relying on prior chat history.

## Project

**Title:** Optimizing Battery Storage Deployment for Renewable Energy Integration Under Uncertainty  
**Project number:** 36  
**Course:** EE 499 Senior Design Project  
**Team:** 16 — Spring 2026 intake  
**Institution:** King Abdulaziz University

### Team

- Member 1 — PME
- Member 2 — ECE
- Member 3 — PME

Student IDs remain in the original official/submitted documents and are intentionally not repeated in the AI-facing context files.

## Current state

As of **2026-09-26**, the team is in **Term 2 implementation/validation**.

Data acquisition and preprocessing are complete, and the implementation baseline is finalized. The immediate work is to implement the predefined software design beginning with the module skeleton, 5-bus `NetworkModel`, one-step FBS, data-profile loader and BESS model. Ethics work runs in parallel.

The latest authoritative submitted project document is the **Term 1 final report** in `02_Reports/Submitted/Term_1_Final/`.

Official Term 2 timing currently recorded in the repository:

- **22 Oct 2026** — Progress Update submission
- **25–29 Oct 2026** — Progress Update presentation window
- **30 Nov 2026** — Final Term 2 report submission
- **6–10 Dec 2026** — Final presentation window

See:

- `PROJECT_STATE.md` — short current-state record,
- `02_Reports/Working/Planning/TERM2_WORKING_CONTEXT.md` — current Term 2 working direction,
- `02_Reports/Working/Planning/TERM2_SHADOW_DESIGN.md` — high-level technical design baseline,
- `02_Reports/Working/Planning/TERM2_SOFTWARE_DESIGN_SPEC.md` — detailed software implementation-handoff specification,
- `KNOWN_GAPS.md` — issues that need attention when relevant.

## How the AI should work with this repository

The AI is an **academic advisor, critical reviewer, and organizational assistant**, not an autonomous project worker. The user/team remains responsible for the engineering work and major technical decisions.

Read in this order:

1. `README.md`
2. `AI_GUIDE.md`
3. `PROJECT_STATE.md`
4. `02_Reports/Working/Planning/TERM2_WORKING_CONTEXT.md`
5. `REQUIREMENTS.md`
6. `KNOWN_GAPS.md`
7. `DECISIONS.md`
8. `USER_PREFERENCES.md` when working with the primary repository user
9. When the task involves implementation/design, read `02_Reports/Working/Planning/TERM2_SHADOW_DESIGN.md` and `02_Reports/Working/Planning/TERM2_SOFTWARE_DESIGN_SPEC.md` before implementation artifacts.
10. Then inspect the original files relevant to the current chat request.

When the user only says **“check the repository”** or equivalent, do not start project work. Give a short summary containing: project, phase, current focus, latest submitted work, deadline status, important open issues, and confirmation that the repository was read. Then wait for the user's task.

## Design vs implementation rule

The current software design is deliberately separated from coding:

- **Design documentation** owns architecture, module responsibilities, data structures, file formats, interfaces, units/sign conventions and algorithm/numerical contracts.
- **Implementation tasks** should code, test, debug and integrate those contracts rather than independently redesign them.
- Software choices that are not fixed by existing requirements are explicitly marked **proposed design decisions** in `TERM2_SOFTWARE_DESIGN_SPEC.md`; they are not automatically confirmed team decisions.
- If implementation reveals a needed design change, update the design documentation and record the reason rather than allowing different modules to diverge silently.

## Repository access modes

This project supports two equivalent working modes:

**GitHub connected:** use the authorized GitHub repository as the current working copy. When the user's task calls for permitted file changes, make them directly in the repository and maintain the context/journal files as required by `AI_GUIDE.md`.

**GitHub not connected:** ask for/use the latest full repository ZIP. Treat it as the working copy, make the same permitted changes inside it, and when persistent changes are made return a **new complete updated ZIP** so the project state can move to the next session/account and later be reconciled back into GitHub. Do not leave persistent project changes only in chat.

A purely advisory exchange that creates no project-state change does not require a new ZIP. Substantive feedback that should survive across sessions should be saved into the repository context/feedback/journal and included in the replacement ZIP.

The access mode changes only the persistence mechanism; it does not grant the AI broader authority over engineering decisions or project work.

## Repository map

- `01_Official/` — official project description, EE499 guidelines, schedule, template, team sheet
- `02_Reports/Submitted/` — immutable historical submissions and presentations
- `02_Reports/Working/` — drafts, planning material, and design-support documents
- `03_Feedback/` — grades, returned/alternate report copy, classroom guidance, and feedback index
- `04_Research/` — external papers, literature notes, and research data/workbooks
- `05_Meetings/` — raw meeting inputs and reviewed meeting documentation, separated by folder
- `06_Notes/` — Obsidian and miscellaneous project notes
- `07_Implementation/` — Term 2 code, model, data, results, and validation artifacts as they are created
- `tools/` — repository maintenance tools and the vendored local meeting-transcription utility
- `Exports/` — generated handoff ZIPs; not intended for Git tracking

`MIGRATION_MAP.csv` records where every file from the supplied project folder was moved. Nothing from the supplied folder was intentionally discarded.

## Source of truth and conflicts

Use the authority order defined in `AI_GUIDE.md`. If two authoritative sources conflict, **record/flag the conflict and discuss it with the user; never silently resolve it**.

Submitted reports are historical evidence of what the team previously proposed. They do not automatically override the official project description or become permanent technical decisions.

## Immediate tasks

There is intentionally **no permanent AI-generated task list**. The current task is supplied by the user in chat. Repository files preserve context, history, known gaps, decisions and design contracts so the AI can advise effectively.
