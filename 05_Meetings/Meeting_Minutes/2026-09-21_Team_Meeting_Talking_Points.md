# Team 16 Weekly Meeting Talking Points

**Week:** 20–26 September 2026  
**Meeting type:** Internal team meeting — no advisor  
**Main outcome:** Leave with named owners, concrete data deliverables, and a checkpoint before the next advisor meeting.

## 1. Open with the current position

- Term 2 is the implementation and validation phase.
- Our intended product is a working BESS planning and decision-support tool, not a collection of disconnected simulations.
- The main Term 1 weakness was incomplete engineering design and unclear integration between modules.
- The immediate priority is obtaining and evaluating usable project data before the next advisor meeting.
- The next advisor-meeting date is still TBA, so we need an internal deadline rather than waiting for it.

## 2. Resolve ownership immediately

The task register currently assigns all active tasks to **Team**. That is not specific enough to manage progress.

Assign one accountable owner for each stream:

| Data stream | Owner | Required handoff |
|---|---|---|
| Load data | TBD in meeting | Source, file/sample, columns, units, time interval, coverage, quality notes, and one plot |
| PV/weather data | TBD in meeting | Source, file/sample, columns, units, time interval, coverage, quality notes, and one plot |
| Network data | TBD in meeting | A usable 5-bus test case and an IEEE 33-bus dataset, with parameters, units, and source documented |

Also assign:

- one person to consolidate the three handoffs;
- one reviewer to check units, timestamps, missing values, and compatibility;
- one person to update the Task Register after the meeting.

Ownership means responsibility for producing the handoff, not doing every step alone.

## 3. Agree on the minimum data checklist

A link to a dataset is not a completed deliverable. Each dataset must show:

- original source and provenance;
- what system, region, or case it represents;
- variables/columns and their meanings;
- units;
- sampling interval and total date range;
- missing values, duplicates, obvious outliers, and timezone assumptions;
- license or usage restrictions, if any;
- compatibility with the other selected datasets;
- the original file or a representative sample;
- at least one simple plot demonstrating the data's behavior.

Questions to settle internally:

1. Can the load and PV/weather data be aligned to a common hourly timeline?
2. Is there enough continuous coverage for the intended study period?
3. Are the values measured, simulated, or normalized profiles?
4. What transformations would be required before simulation?
5. What weaknesses must be disclosed to the advisor rather than hidden?

## 4. Review this week's tasks and deadlines

| ID | Task | Deadline | Meeting decision needed |
|---:|---|---|---|
| 1 | Define the data we need | 21 Sep | Confirm the checklist and mark complete only if it is written down |
| 2 | Get load data | 24 Sep | Name owner and candidate source |
| 3 | Get PV/weather data | 24 Sep | Name owner and candidate source |
| 4 | Get network data | 24 Sep | Name owner and define 5-bus plus IEEE 33-bus deliverables |
| 5 | Check selected data | 25 Sep | Name reviewer and agree acceptance checks |
| 6 | Clean and align data | 26 Sep | Agree common time resolution, units, and output format |
| 7 | Prepare data for advisor | 27 Sep | Name consolidator and define the advisor-ready package |

Do not mark a task complete because a source was found. Mark it complete only when its definition of done is satisfied.

## 5. Confirm a provisional technical rule

Use **hourly resolution as the working alignment target** for this week's data evaluation because it is practical for load/PV alignment, SOC updates, time-series power flow, and debugging.

This is not yet a permanent technical decision. Preserve higher-resolution source data and record any information lost during resampling. Escalate the choice to the advisor if the available datasets or intended validation make hourly resolution unsuitable.

## 6. Keep scope discussion short and evidence-based

Confirm that the team understands the provisional implementation path:

1. V1 — network simulator;
2. V2 — fixed BESS;
3. V3 — manual sizing/placement comparison;
4. V4 — automatic optimization;
5. V5 — uncertainty-aware optimization;
6. V6 — final decision-support software.

Do not spend this meeting choosing final algorithms, objective weights, or uncertainty methods. Those remain open decisions and should be informed by the data, implementation evidence, and advisor guidance.

## 7. Risks to raise directly

- Generic team ownership will allow urgent tasks to remain unclaimed.
- Load and PV data from incompatible locations or periods may produce a technically weak case study.
- Normalized profiles can be useful, but they must not be presented as measured local power without explicit scaling and disclosure.
- A three-month study period may conflict with the official brief's annual hourly-operation expectation.
- The Term 1 GWO/Monte Carlo baseline does not by itself demonstrate the required two-stage stochastic formulation.
- The 5-bus system is suitable for debugging, but it cannot replace later IEEE 33-bus validation.
- Starting implementation before documenting units and interfaces will recreate the integration problem identified in Term 1 feedback.

## 8. Prepare questions for the next advisor meeting

The internal team should prepare concise questions, not silently make major scope decisions:

1. Is annual hourly simulation required, or can a shorter representative period be accepted with justification?
2. How strictly must the final formulation follow two-stage stochastic programming?
3. Must battery type remain an optimization decision, or may it be fixed and justified?
4. Is hourly resolution acceptable for the main case study?
5. Are the proposed data sources and geographic assumptions acceptable?
6. Is the 5-bus-to-IEEE-33-bus implementation and validation path acceptable?

## 9. Close with recorded commitments

Before ending the meeting, complete this table:

| Commitment | Owner | Due date/time | Evidence/location | Status |
|---|---|---|---|---|
| Finalize written data checklist |  |  |  |  |
| Deliver load-data handoff |  |  |  |  |
| Deliver PV/weather-data handoff |  |  |  |  |
| Deliver network-data handoff |  |  |  |  |
| Review data quality and compatibility |  |  |  |  |
| Consolidate advisor-ready package |  |  |  |  |
| Update Task Register |  |  |  |  |

Set one internal checkpoint before 27 September. At that checkpoint, each owner should show the actual data/sample, documentation, quality notes, and plot—not only report verbal progress.

## Definition of a successful meeting

The meeting is successful only if:

- every active task has one accountable owner;
- the team agrees on the dataset acceptance checklist;
- each owner has a dated, inspectable deliverable;
- an internal review/checkpoint is scheduled;
- unresolved major technical questions are captured for the advisor;
- the Task Register is updated to reflect the commitments.
