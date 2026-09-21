# Report 1 Feedback — Reanalysis Against the Submitted Report

**Source feedback:** `02_Reports/Submitted/Report_1/EE499-S26_Report-1_Team-16.txt`  
**Source report:** `02_Reports/Submitted/Report_1/EE499-S26_Report-1_Team-16.docx`  
**Purpose:** Explain what each reviewer comment refers to in the actual Report 1 submission, why it matters, and what should be improved in the later/final design.

> This file is an analytical interpretation of the reviewer comments. It does not change the historical submitted report.

## 1. Essential project details are missing in order to clearly define the problem

### What is visible in Report 1

The report discusses renewable uncertainty, curtailment, load shedding, voltage instability, battery capacity, power rating, charge/discharge limits, efficiency, degradation, and economic feasibility. It also states that a modified IEEE 33-bus system is assumed.

However, the exact engineering system is not consistently defined. The report uses terms such as:

- small microgrid systems,
- existing power systems,
- renewable-integrated systems,
- modified IEEE 33-bus distribution system,
- solar and wind.

It does not clearly freeze one system boundary and identify what is given and what the project is actually designing.

### Why the reviewer likely flagged it

A reviewer should be able to answer immediately:

- What network is being studied?
- Is it grid-connected or islanded?
- Is the study distribution-level or generation-system-level?
- Is PV the implemented renewable source, or PV + wind?
- Is the renewable plant already installed, or also part of the design?
- Is the project designing BESS only, or BESS + renewable generation?
- What specific operational problem must the BESS solve?

Those answers are not consistently clear from Report 1.

### How to improve

Define the system in one compact scope statement and use that definition everywhere. For example:

- radial distribution network,
- grid-connected,
- fixed network/load data,
- PV as the initial implemented RES,
- BESS location, power rating, and energy capacity are the planning decisions,
- uncertainty is represented through renewable/load profiles.

Also explicitly separate:

**Given inputs:** network, loads, renewable profiles, technical/economic parameters.  
**Design decisions:** BESS bus, power rating, energy capacity.  
**Evaluated outcomes:** cost, curtailment, load shedding, voltage, losses/reliability.

---

## 2. Optimization details are not clearly stated

### What is visible in Report 1

The report says it will:

- develop an optimization framework,
- determine battery capacity and power rating,
- consider battery lifecycle,
- reduce curtailment and load shedding,
- use stochastic optimization.

But Report 1 does not define a complete optimization problem.

The report does not clearly state:

- the full decision-variable vector,
- the objective function,
- constraints,
- variable bounds,
- treatment of discrete placement,
- battery dispatch logic,
- how uncertainty enters the fitness/objective,
- the optimization algorithm itself.

### Why the reviewer likely flagged it

Saying "optimization framework" is not enough to define an engineering optimization problem.

The reviewer needs to see something structurally like:

[
x=[B,P_{BESS},E_{BESS}]
]

subject to network and BESS constraints, minimizing a clearly defined objective.

Without this, it is impossible to judge whether the proposed optimization is feasible or whether the reported outputs actually solve the stated problem.

### How to improve

Create a dedicated optimization-formulation section containing:

1. **Decision variables**
   - BESS bus/location,
   - BESS power rating,
   - BESS energy capacity,
   - operational variables if optimized explicitly.

2. **Objective function**
   - cost,
   - curtailment,
   - load shedding,
   - or a defensible multi-objective/weighted formulation.

3. **Constraints**
   - SOC,
   - charge/discharge power,
   - voltage,
   - line/network limits,
   - battery size/power bounds,
   - final SOC if required.

4. **Uncertainty treatment**
   - deterministic profile vs scenarios,
   - how scenario performance is aggregated.

5. **Optimizer settings**
   - separate algorithm settings from engineering decision variables.

---

## 3. There are discrepancies between the title and the project specifications

### What is visible in Report 1

The title is:

**Optimizing Battery Storage Deployment for Renewable Energy Integration Under Uncertainty**

However, the report uses several different framings:

- renewable systems,
- small microgrids,
- existing power systems,
- modified IEEE 33-bus distribution test system,
- solar and wind,
- stationary BESS.

The reviewer also noted that the presentation discussed a mixed-generation system.

### Why the reviewer likely flagged it

The title suggests the project is primarily about storage deployment for renewable integration, but the specifications/presentation apparently implied a broader mixed-generation design.

If conventional generation + renewable generation + storage are all being designed, then the scope is much larger than simply BESS planning. The renewable segment itself would need a design definition as well.

### How to improve

Choose one system scope and make the title, problem statement, requirements, diagrams, and implementation all match it.

A safer scope is:

- existing distribution network,
- existing/defined PV installation,
- BESS planning only.

If wind or other RES are not implemented, describe the framework as potentially extensible rather than claiming they are part of the implemented case.

---

## 4. The simulation model, along with its parameters, variables, and outcomes, is not clearly defined

### What is visible in Report 1

Report 1 gives assumptions such as:

- battery efficiency = 85%,
- SOC window = 10–90%,
- battery lifetime = 15 years,
- modified IEEE 33-bus network,
- public Saudi weather/load data.

But it does not define the complete simulation process.

There is no clear explanation of:

- what happens at each time step,
- how load and renewable data enter the network model,
- how battery dispatch is determined,
- when power flow is run,
- how constraints are checked,
- how curtailment/load shedding are calculated,
- how simulation outputs feed the optimizer.

### Why the reviewer likely flagged it

A list of assumptions is not a simulation design.

The reviewer needs to understand:

[
	ext{inputs} ightarrow 	ext{model calculations} ightarrow 	ext{outputs}
]

and the exact interfaces between these steps.

### How to improve

Define the simulation in operational order. For example:

1. load network data,
2. read load/PV value for time (t),
3. apply candidate BESS configuration,
4. determine BESS charge/discharge,
5. update SOC,
6. run power flow,
7. check voltage/network limits,
8. calculate cost, curtailment, shedding, and losses,
9. repeat for the full time horizon,
10. aggregate metrics,
11. return fitness/performance to optimizer.

Also create a parameter/variable table separating:

- fixed network parameters,
- battery parameters,
- economic parameters,
- uncertainty parameters,
- state variables,
- decision variables,
- outputs.

---

## 5. Problem Statement should be concise and to-the-point, just about the problem at hand, no background, no solutions

### What is visible in Report 1

The problem statement is already shorter than the Background, but it still includes solution language:

> "Therefore, this project aims to develop a model to optimize the deployment of battery energy storage systems..."

It also uses the specific framing "small microgrid systems," which is not fully consistent with the later IEEE 33-bus distribution-system assumption.

### Why the reviewer likely flagged it

A problem statement should describe the engineering problem, not advertise the proposed method.

Background belongs in Section 1.1. The proposed model/optimizer belongs in objectives or design/methodology.

### How to improve

Keep only:

- variable renewable generation creates mismatch/uncertainty,
- this can cause curtailment, load shedding, voltage/reliability problems,
- BESS planning is difficult because size/location/operation affect technical and economic performance under uncertain conditions.

Do not mention GWO, ARIMA, Monte Carlo, or "our model" in the problem statement.

---

## 6. All Design Specifications have several problems; they need to be thoroughly revised and fixed

### What is visible in Report 1

The design specifications are:

- deployable,
- technology-agnostic,
- scalable,
- ≥10% greenhouse-gas reduction,
- ≥1% curtailment reduction,
- stationary BESS,
- ≥5% operational-cost reduction.

Several of these are not measurable as written or are not clearly connected to the proposed model.

Examples:

- "deployable" has no test,
- "technology-agnostic" conflicts with a fixed 85% Li-ion assumption,
- "scalable" has no defined scale/test,
- 10% GHG reduction has no emissions model described,
- 1% and 5% targets are not justified in Report 1.

### Why the reviewer likely flagged it

A design specification should be:

- specific,
- measurable,
- testable,
- justified,
- directly related to the designed product/system.

Report 1 mixes aspirations, assumptions, technology choices, and performance targets.

### How to improve

Rewrite specifications as testable requirements.

Examples:

- Program shall support a user-defined radial network with at least a specified minimum number of buses.
- Valid optimized solutions shall satisfy adopted voltage limits.
- Program shall optimize BESS bus, power rating, and energy capacity within defined bounds.
- Program shall evaluate candidate designs across a defined uncertainty-scenario set.
- Optimizer shall be checked against exhaustive search on a small verification case.
- Software shall report before/after technical and economic metrics.

Only keep numerical improvement targets when they have a credible source, customer requirement, benchmark, or validation rationale.

---

## 7. What exactly will be the deliverables?

### What is visible in Report 1

Report 1 lists:

1. a deployable optimization framework,
2. a quantitative case study,
3. a comprehensive report.

However, the first deliverable is very broad and includes:

- optimal battery capacity,
- placement,
- deployment timing,
- technology type.

Those outputs are not all defined elsewhere in the report as actual optimization variables.

### Why the reviewer likely flagged it

The reviewer could not tell what tangible artifact the team would demonstrate or submit.

An "optimization framework" could mean equations, MATLAB code, a script, a GUI, or a research methodology.

### How to improve

Define tangible deliverables.

For the current Term 2 direction, these can be:

1. working BESS planning software,
2. validated simulation/optimization backend,
3. small-system verification case,
4. IEEE 33-bus case study,
5. before/after and uncertainty-aware results,
6. user/technical documentation,
7. final report and demonstration.

Avoid promising optimization outputs such as technology type or deployment timing unless they are actually implemented as decision variables.

---

## 8. Project title is only about the Renewable Energy System while the presentation was about mixed generation system

### What is visible in Report 1

The written report emphasizes renewable integration and a modified IEEE 33-bus system, but the reviewer states the presentation used a mixed-generation-system framing.

This indicates inconsistency between project artifacts, even if it is not fully visible from the Report 1 text alone.

### Why the reviewer likely flagged it

If the actual system contains non-renewable generation plus newly designed renewable generation plus BESS, the engineering problem includes more than battery optimization.

The renewable-generation segment then needs its own sizing, placement, operating assumptions, and interfaces.

### How to improve

Do not maintain two competing system definitions.

Choose either:

- **BESS planning for an existing renewable-integrated distribution system**, or
- a broader generation-expansion/design problem.

The current working direction is much more manageable if the renewable installation/network are treated as input/given system data and BESS is the primary design object.

---

## 9. What exactly will be the parameters used in optimization problem?

### What is visible in Report 1

Different parameter types are mixed together:

- battery efficiency,
- SOC,
- lifetime,
- network model,
- renewable/load uncertainty,
- capacity,
- power rating,
- placement,
- lifecycle,
- deployment timing,
- technology type.

It is not clear which of these are:

- fixed parameters,
- decision variables,
- state variables,
- uncertain variables,
- output metrics.

### Why the reviewer likely flagged it

Optimization requires precise mathematical roles.

For example:

**Decision variables** are changed by the optimizer.  
**Parameters** are fixed input values.  
**State variables** evolve during simulation.  
**Uncertain variables** vary by scenario.  
**Outputs** are performance results.

Report 1 does not separate these roles clearly.

### How to improve

Use a table such as:

| Category | Examples |
|---|---|
| Planning decision variables | bus (B), power (P_{BESS}), energy (E_{BESS}) |
| Operational/state variables | SOC, charge/discharge power |
| Network parameters | line (R/X), loads, base voltage |
| BESS parameters | efficiency, SOC bounds |
| Uncertain variables | PV output, load demand |
| Economic parameters | capex, tariff, VoLL |
| Performance outputs | cost, curtailment, shedding, voltage violations |
| Optimizer settings | population, iterations, tolerance |

This removes ambiguity and makes the implementation traceable.

---

## Overall interpretation

The Report 1 feedback can be summarized as:

> The project topic is technically meaningful, but the submitted report did not yet define a sufficiently precise engineering system. The report discusses relevant concepts, but the scope, optimization formulation, simulation workflow, specifications, variables, and deliverables are not connected into one clear and testable design.

The most important improvement is therefore not simply adding more literature or more algorithms.

The project should first define:

[
oxed{	ext{System} ightarrow 	ext{Inputs} ightarrow 	ext{Decision Variables} ightarrow 	ext{Model} ightarrow 	ext{Constraints} ightarrow 	ext{Outputs} ightarrow 	ext{Validation}}
]

Only after that should methods such as ARIMA, Monte Carlo, GWO, or scenario reduction be selected and justified.
