# Project Journal

A lightweight record of **meaningful project events**, not a transcript of chats.

Log items such as confirmed decisions, important advisor guidance, meaningful results, major technical problems/discoveries, major project-state changes, or significant repository changes. Do not log routine definitions or trivial questions.

## 2026-09-20 — Portable project knowledge base established

- The project is beginning Term 2.
- Repository organization was redesigned to be portable across AI sessions/accounts and suitable for later use as a private GitHub repository.
- AI role/boundaries were clarified: advisor, critical reviewer, examiner only when requested, and organizational assistant; the team retains engineering ownership.
- Submitted reports were separated from working material and are treated as immutable history.
- Official requirements, feedback, research, meeting minutes, notes, and future implementation artifacts were separated into explicit categories.
- Term 1 technical content is preserved as a submitted baseline, not automatically promoted to confirmed Term 2 decisions.
- No new technical project decision was recorded during this repository-organization session.

## 2026-09-20 — GitHub/ZIP continuity and academic-quality preference added

- Repository instructions now explicitly support a ZIP fallback whenever GitHub/repository access is unavailable.
- A new AI must ask for the latest ZIP rather than pretending it accessed a repository or relying on stale cross-session memory.
- The primary user's working preferences now record an A-level academic-performance target and a concern that continuing at Term 1 quality/effort could materially hurt the final grade.
- The AI should proactively identify must-fix grading risks while avoiding any guarantee of a particular grade.

## Entry template

```markdown
## YYYY-MM-DD — Event title

- What materially changed or was learned.
- Why it matters, if not obvious.
- Related files/evidence: `path/to/file`
```
## 2026-09-20 — Repository access modes clarified

- GitHub-connected sessions should persist permitted changes directly to the repository.
- Sessions without GitHub access should use the latest uploaded repository ZIP as the working copy and return a complete updated ZIP when persistent changes are made.
- Substantive feedback worth carrying across sessions should be saved into the repository rather than existing only in chat.
- The primary user's academic priority was clarified as recovering from a perceived C-level trajectory toward A-level performance; this is a quality target/risk framing, not a grade prediction or guarantee.


## 2026-09-20 — Term 2 semester schedule added

- Added a repository-tracked Term 2 task register under `02_Reports/Working/Planning/`.
- The schedule covers data acquisition, product/software design, simulation design, 5-bus implementation, BESS optimization, uncertainty modelling, software integration, validation, IEEE 33-bus scaling, and final documentation/demo work.
- Data acquisition is the immediate priority because the advisors requested project data before the next meeting (date TBA).
- Added usage instructions explaining ownership, status/progress updates, dependencies, weekly review, and how to revise dates once official deadlines are announced.
- The schedule is an internal planning artifact and does not replace official EE499 deadlines or confirmed technical decisions.


## 2026-09-20 — Google Sheet schedule adopted and ethics prioritized

- The Term 2 working schedule is now maintained as a native Google Sheet for easier team access and collaboration.
- Repository planning instructions now link to the Google Sheet and keep the CSV as a version-controlled snapshot.
- Added an early critical task for ethics/professional responsibility covering data integrity/provenance, transparent assumptions, reliability/safety implications, model limitations, environmental/economic trade-offs, responsible use, and final-report considerations.
- Data acquisition remains the immediate advisor-meeting gate: Tasks 1–7 should be completed before the next meeting (date TBA).
- Google Sheet: https://docs.google.com/spreadsheets/d/1HE7RNvaZ-VkVMlozWfkfPbe23hywnEdOzuaI1CfAEcY/edit


## 2026-09-20 — Term 2 Gantt made dynamic

- The Google Sheet Semester Gantt is now formula-linked to the Task Register.
- Changes to task name, phase, Start/End dates, priority, status, and progress automatically propagate to the Gantt.
- Weekly bars move automatically when dates change and use status-based formatting for Not Started, In Progress, Blocked, Done, and TBA.
- The Task Register is the intended editing surface; the Gantt is now primarily a generated planning view.


## 2026-09-21 — Term 2 discussion context consolidated for AI continuity

- Added `02_Reports/Working/Planning/TERM2_WORKING_CONTEXT.md` to preserve the recent Term 2 discussion across AI sessions/accounts.
- The context document records the working software/decision-support direction, the interpretation of Term 1 gaps, recommended implementation sequence, uncertainty-aware planning concept, small-system validation strategy, data requirements, ethics work, Gantt workflow, weekly-meeting focus, and open decisions.
- Recommendations and working assumptions are explicitly separated from confirmed technical decisions; `DECISIONS.md` remains unchanged because no new major Term 2 technical choice has yet been explicitly confirmed.
- `README.md` and `PROJECT_STATE.md` now point future AI assistants to the new context document early in the repository read order.


## 2026-09-21 — Report 1 feedback reanalyzed against original submission

- Added `03_Feedback/Term_1/Report_1_Feedback_Reanalysis.md`.
- The analysis compares each preserved Report 1 reviewer comment directly against the actual Report 1 submission and explains the underlying engineering issue and concrete improvement.
- Main recurring issue: the project topic was relevant, but scope, optimization formulation, simulation workflow, measurable design specifications, variable roles, and tangible deliverables were not yet connected into one precise/testable engineering design.


## 2026-09-21 — Local meeting-transcription workflow added

- Vendored the MIT-licensed DataAnts-AI VideoTranscriber at upstream commit `d1e1fedcaeefa812868cc73fa216b3424c7cb915` under `tools/VideoTranscriber/`.
- Reorganized `05_Meetings/` into `Raw_Recordings/` and `Meeting_Minutes/` and moved the existing meeting documents without changing their contents.
- Added consent, privacy, review, retention, and transcription-quality guidance; raw audio/video formats are ignored by Git by default.
- Machine transcripts and summaries remain drafts until a team member verifies names, technical terms, numerical values, decisions, owners, and deadlines against the recording.
- Added the repository-wide commands “write meeting minutes” and “write MM,” with safeguards against inventing missing meeting facts. The commands now use the official `EE499MeetingMinutes.docx` Word form as the authoritative template and preserve its section/table structure.
- Added `tools/VideoCompressor/`, a local Streamlit interface for extracting transcription-ready M4A audio or compressing meeting video with FFmpeg without overwriting the source.

## 2026-09-26 — Weather, PV and network datasets added

- Added the supplied Jeddah weather/PV summary, five-bus network reference and IEEE 33-bus workbook under `04_Research/Working_Data/`.
- Downloaded complete 2024 hourly Jeddah datasets from NASA POWER and Open-Meteo using the APIs identified in the supplied weather/PV summary.
- Verified 8,784 hourly records in each source (2024 is a leap year), with no missing values in the requested variables.
- Documented time standards, units, wind-height differences, source limitations and the distinction between published network data and project assumptions.
- Added the MATPOWER/PJM five-bus workbook as a complementary power-flow/OPF reference, explicitly distinguishing its looped 230 kV topology from the radial 11 kV development feeder.

## 2026-09-26 — Software design separated from implementation

- Added `02_Reports/Working/Planning/TERM2_SOFTWARE_DESIGN_SPEC.md` as the software implementation-handoff specification.
- Moved module architecture, `network_model.py` representation, `fbs.py` interface/convergence/result contract, load/PV file formats, BESS data/interface, shared units/sign conventions, and future optimizer/scenario interfaces out of implementation tasks and into design documentation.
- Reworked `TERM2_SHADOW_DESIGN.md` into a high-level technical design baseline that points to the detailed software specification rather than asking implementation owners to invent local architecture/interfaces.
- The new specification explicitly separates existing baseline requirements from **proposed design decisions** where the existing project material did not determine a software detail. These proposals are not recorded as confirmed team decisions in `DECISIONS.md`.
- Updated the live Google Sheet Task Register so Tasks 10–23, selected V4/V5 tasks, and UI-integration tasks implement/reference the predefined design contracts instead of redefining architecture or data formats during coding.
- Two design gates remain explicit before later implementation: confirm the WSM normalization method before Task 33 and confirm the best/worst scenario ranking rule before Task 45; implementation code must not silently invent either rule.
- Related files: `02_Reports/Working/Planning/TERM2_SOFTWARE_DESIGN_SPEC.md`, `02_Reports/Working/Planning/TERM2_SHADOW_DESIGN.md`, `02_Reports/Working/Planning/README.md`.
