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
