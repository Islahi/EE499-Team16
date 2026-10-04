# Ethical Analysis — Islahi: Report Backbone

> Working outline for the individual Ethical Analysis report. This is intentionally written as paragraph-content points rather than finished prose.
>
> Workflow: **clarify backbone → targeted research → add evidence/citations → elaborate into sentences/paragraphs**.
>
> Based on the required structure in `01_Official/Course_Guidance/Ethical_Analysis.md` and the research collected in `Ethical-Islahi.md`.

## 3.1 Project Context and System Overview

### Paragraph 1 — What the system is and why it exists
- Purpose: help power-system planning engineers decide the **size and placement of a BESS** in a radial distribution system.
- Function: optimize BESS size and location while considering uncertainty in photovoltaic (PV) generation.
- Intended user: power/distribution planning engineer.
- Operating environment: planning-stage engineering work rather than real-time grid control.
- Main components:
  - GUI-based program.
  - Distribution-system model and power-flow calculation.
  - Grey Wolf Optimizer (GWO).
  - Monte Carlo scenarios for PV uncertainty.

### Paragraph 2 — Scope and limitations
- The program is a **decision-support tool**, not an autonomous controller or replacement for engineering judgment.
- Intended scope: radial distribution systems containing PV generation.
- Potential unsupported uses:
  - Applying it to non-radial/meshed networks without validation.
  - Applying the PV uncertainty model directly to other renewable sources such as wind.
  - Treating optimization output as a guaranteed solution without independent checks.
- Ethical connection: limitations must be communicated clearly because misuse outside the validated scope can produce misleading recommendations.

---

## 3.2 Stakeholder Identification and Interests

### Paragraph 1 — Stakeholder groups
- **Primary:** distribution/planning engineers who operate the program and interpret results.
- **Secondary:** utility/client/government entity responsible for the project; regulators/engineering authorities.
- **Indirect:** electricity users/public and the environment.
- Energy-storage manufacturers are not a major stakeholder unless the final tool recommends specific products/vendors.

### Stakeholder working table

| Level | Stakeholder | Interest | Main risk | Benefit | Possible harm |
|---|---|---|---|---|---|
| Primary | Planning engineer | Efficient, technically sound planning and trustworthy decision support | Over-reliance on output or incorrect inputs/model assumptions | Reduced manual work and planning time | Poor BESS decision, rework, professional responsibility for unsupported recommendation |
| Secondary | Utility/client/government | Reliable and economically justified planning | Acting on inaccurate/insufficiently validated recommendations | Better-informed BESS investment | Unnecessary investment, poor placement, reduced benefit, redesign |
| Secondary | Regulators/engineering authorities | Safety, reliability, compliance and truthful engineering practice | Hidden assumptions, uncertainty, limitations or non-compliance | Transparent/auditable decisions | Reduced trust and compliance/approval problems |
| Indirect | Public/electricity users | Reliable electricity and responsible infrastructure spending | Poor planning decisions affecting cost/performance | Potentially improved renewable integration | Indirect economic/service consequences |
| Indirect | Environment | Responsible renewable integration | Material/manufacturing/end-of-life impacts of BESS | Reduced curtailment and better renewable use | Unnecessary environmental burden from poorly planned/oversized storage |

### Paragraph 2 — Why stakeholder analysis matters
- Engineer receives the immediate productivity benefit but carries responsibility for interpreting output.
- Utility/client bears much of the financial and operational consequence.
- Public/environmental impacts are indirect because the program itself does not operate the grid.
- Reliability, transparency and responsible data handling therefore affect more than the direct software user.

---

## 3.3 Ethical Issue Identification

### Paragraph 1 — Issue 1: Confidentiality and security of power-system data
- Optimization requires distribution-system and operating/load information.
- In real deployment, network topology, parameters, operating data or demand records may be non-public or sensitive.
- Customer-level demand may additionally raise privacy concerns if it identifies/can identify individuals; aggregate bus-load/network data should not automatically be called personal data.
- Ethical concern: obtain, process, store, share and dispose of information responsibly.
- Professional connection: SCE Engineer Charter **Rule 9** on confidentiality — verify exact wording before final citation.

### Paragraph 2 — Issue 2: Reliability and responsible use of optimization results
- Output may appear authoritative despite uncertain inputs, simplified models, scenario limits, algorithm convergence or incorrect user input.
- A BESS size/location should be presented as a recommendation under defined assumptions, not a guaranteed optimum for every real condition.
- Ethical concern: poor decisions can follow if software/reporting overstates confidence.
- Professional connections to verify: SCE **Rules 14, 8 and 16** concerning reporting, responsibility, safety/quality/reliability.

---

## 3.4 Ethical Analysis and Decision-Making

### Issue 1 — Confidentiality and security

#### Dilemma
- Useful analysis may require detailed network/demand information.
- Detailed data may create greater harm if sensitive information is accessed/disclosed without authorization.
- Question: how can the software obtain enough information for useful analysis without unnecessarily exposing or retaining it?

#### Course A — Basic file handling
- Import files and rely mainly on normal computer/organization file permissions.
- Advantage: simple and convenient.
- Disadvantage: little additional protection against unnecessary copies, retention or unauthorized access.

#### Course B — Local, access-controlled and protected processing
- Process project data locally where practical.
- Restrict access to authorized users/projects.
- Avoid unnecessary copies and retention.
- Protect sensitive stored data using encryption where appropriate.
- Define deletion/retention procedure.
- Advantage: reduces avoidable exposure.
- Trade-off: more software complexity and access/key management.

#### Evaluation / decision paragraph
- Compare A/B using confidentiality, stakeholder consequences, usability, SCE Rule 9, and relevant NCA guidance.
- **Provisional decision:** prefer Course B for future real deployment.
- Do not describe current academic/test data as confidential utility data unless evidence supports that claim.

### Issue 2 — Reliability and responsible use

#### Dilemma
- Automation saves engineering time and evaluates many alternatives.
- Wrong inputs, unsupported configurations, inadequate uncertainty representation, implementation/model errors or optimizer limitations may produce misleading recommendations.
- Question: how much should an engineer rely on the program and how should results be communicated?

#### Course A — Present optimizer result directly as the optimum
- Advantage: simple output and fast decision-making.
- Disadvantage: encourages overconfidence and hides assumptions/limitations.

#### Course B — Treat output as engineering decision support
- Present size/location with assumptions and validation information.
- State supported network/renewable scope.
- Validate inputs and flag unsupported conditions.
- Report constraint checks and failed/non-converged cases.
- Communicate uncertainty/scenario coverage and limitations.
- Require independent engineering review before implementation.

#### Evaluation / decision paragraph
- Compare using truthful engineering communication, professional accountability, stakeholder consequences, SCE Rules 14/8/16 and model credibility practices.
- **Provisional decision:** Course B.

---

## 3.5 Safety, Risk, and Compliance Analysis

### Paragraph 1 — Nature of hazard
- Software does **not directly control the grid**; it is planning-stage decision support.
- Main hazard is an incorrect/miscommunicated recommendation later used in engineering planning.
- Causes may include:
  - incorrect/incomplete inputs;
  - use outside validated RDS/PV scope;
  - model/implementation error;
  - inadequate uncertainty representation;
  - optimizer non-convergence/poor solution;
  - user misunderstanding.

### Paragraph 2 — Qualitative risk
- Do **not** automatically describe consequences as “not very severe.”
- Severity depends on deployment context and engineering review.
- Current prototype: limited direct physical harm because it is not real-time control.
- Future deployment: possible financial loss, unnecessary capacity, poor placement, reduced expected performance or redesign.
- Likelihood should be supported by testing/validation rather than guessed.

### Paragraph 3 — Compliance and mitigation
- Professional baseline: applicable SCE Charter responsibilities.
- Cybersecurity/data: discuss NCA DCC/ECC according to actual applicability.
- NASA-STD-7009B may support model-credibility discussion but is not a Saudi legal requirement.
- Mitigation: input validation, constraint/power-flow checks, convergence reporting, benchmark tests, uncertainty documentation, unsupported-configuration warnings and independent engineering review.

---

## 3.6 Data, Privacy, and Security

### Paragraph 1 — Data lifecycle
- Inputs may include network topology/parameters, load profiles, PV profiles/scenarios, BESS and economic parameters.
- Current direction: local processing.
- Clarify whether imported files are only read or copied into application storage.
- Define retained inputs/outputs/logs/configuration and retention duration.
- Avoid unnecessary collection/retention.

### Paragraph 2 — Confidentiality/privacy/access
- Utility/network data may be sensitive without being personal data.
- Customer-level records may become personal data if identifiable; assess PDPL applicability based on the actual dataset.
- Proposed safeguards: local processing, authorized access, protected storage where appropriate, no automatic external sharing, deletion/retention process, aggregation/anonymization where individual data are unnecessary.

### Paragraph 3 — Transparency/misuse
- Tell users what data are read, where they are stored and whether anything leaves the device.
- Misuse includes unauthorized copying/sharing or processing data the user is not authorized to access.
- Organizational procedures and user responsibility remain necessary.

---

## 3.7 Broader Impact Analysis

> Keep concise because the report is only 3–5 pages.

### Paragraph 1 — Global and economic
- Renewable/storage planning is internationally relevant, but do not claim universal applicability before validation across different systems/data/standards.
- Scalability must be demonstrated through testing.
- Economic benefit: reduce planning effort and help compare BESS alternatives.
- Economic risk: poor optimization may cause unnecessary capital expenditure, oversizing/undersizing, poor placement or redesign.
- Trade-off: model/computational complexity versus useful/explainable results.

### Paragraph 2 — Environmental and societal
- Environmental benefit: better storage planning may support renewable integration and reduce curtailment.
- Environmental trade-off: batteries have material, manufacturing and end-of-life impacts; unnecessary oversizing increases burden.
- Avoid specific mining/location claims without evidence.
- Societal benefit: indirectly support reliable service and responsible infrastructure spending.
- Negative effects are indirect: unnecessary cost, loss of trust, confidentiality/privacy problems or system-performance consequences.

---

## 3.8 Professional Integrity and Communication

### Paragraph 1 — Truthful representation
- Do not call a result universally “optimal” without objective function, constraints, data, scenarios, assumptions and validated scope.
- Avoid exaggerated claims from limited tests.
- Do not hide failed convergence, constraint violations or unfavorable scenarios.
- Distinguish validated results from expected future capability.

### Paragraph 2 — Limitations and accountability
- Communicate supported RDS/PV scope, assumptions, scenario coverage, convergence/validation status and known limitations.
- Engineer remains responsible for reviewing output.
- If an error is found, correct software/report, identify affected results and communicate corrections.
- Reuse Issue 2 research here rather than duplicating research.

---

## 3.9 Intellectual Property and Attribution

### Paragraph 1 — External resources
- Possible external resources: Python libraries, network/test data, PV/load datasets, optimization algorithms from papers, equations/models, documentation and standards.
- Open source does **not** mean no attribution/license obligations.

### Paragraph 2 — Citation/licensing/reuse
- Cite papers, datasets, standards, equations/models and documentation that materially contribute.
- Check each library/software license before redistribution/modification/packaging.
- Keep third-party notices where required.
- Check provenance/license compatibility before copying code from repositories, papers, forums or AI-generated examples.
- Distinguish implementing a published algorithm from reusing source code and redistributing dependencies.
- SCE Rule 6 connection: verify exact wording.

---

## 3.10 Recommendations and Mitigation Plan

### Paragraph 1 — Preventive actions
1. **Validate before trust:** reference/benchmark tests and documented validated scope.
2. **Communicate uncertainty/limitations:** assumptions, scenarios, convergence/constraints and unsupported uses.
3. **Protect real utility data:** local processing, authorized access, minimal retention and protected storage where needed.
4. **Validate inputs:** reject missing/invalid/unsupported configurations.
5. **Require engineering review:** decision support, not automatic deployment approval.

### Paragraph 2 — Corrective actions
- Validation/software failure: stop affected results, identify affected runs, correct/retest, document issue and communicate revisions.
- Data exposure: stop further unauthorized access/sharing, follow organization incident procedures, identify affected data and strengthen controls.
- Unsupported use: mark result unvalidated instead of presenting it as accepted recommendation.

### Paragraph 3 — Priority rationale
- Prioritize preventing **misleading engineering decisions** and **unauthorized data exposure**, directly matching the two ethical issues.
- Usability, broader model support and automation follow after reliability/confidentiality controls.

---

## 3.11 Reflection and Professional Responsibility

> Write this late. These are prompts, not final personal prose.

### Paragraph 1 — Main ethical challenge/trade-off
- Candidate challenge: making automation useful without encouraging trust beyond available evidence.
- Trade-off: convenience/automation versus verification, transparency and professional judgment.
- Data trade-off: detailed information improves modeling but increases protection responsibility.

### Paragraph 2 — Professional responsibility
- Responsibility does not end when code executes successfully.
- Understand and communicate model limits.
- Protect entrusted information.
- Report limitations, uncertainty, failures and validation truthfully.
- Do not recommend real implementation solely because the optimizer returns a numerical optimum; verify using engineering checks and required organizational review.
- Rewrite final reflection in the author's own voice.

---

# Parallel Research + Writing Workflow

For each Ethics morning:

1. **Clarify the target paragraph** — decide what it must communicate.
2. **Targeted research** — find only evidence needed for those points.
3. **Update backbone** — replace uncertainty with supported claims/citations.
4. **Write immediately** — elaborate the completed backbone into rough prose while research is fresh.
5. **Mark unresolved items** — keep `?`/TODO only where evidence or a design decision is genuinely missing.

Research clusters:
- **Issue 1 → 3.3 + 3.4 + 3.6 + 3.10**
- **Issue 2 → 3.3 + 3.4 + 3.5 + 3.8 + 3.10**
- **IP/licensing → 3.9**
- **Broader impact → 3.7**
- **Reflection → 3.11 after the main analysis**

# Remaining Clarifications / Research Checklist

- [ ] Verify exact wording/applicability of SCE Rules 6, 8, 9, 14 and 16 against the original Engineer Charter.
- [ ] Confirm final data-storage behavior: read-only import vs copied application data; logs; retention/deletion.
- [ ] Confirm whether encryption/access controls will be implemented or proposed as future safeguards.
- [ ] Confirm actual libraries/datasets and inspect their licenses before writing 3.9 as fact.
- [ ] Determine risk severity/likelihood from actual validation/deployment context rather than guessing.
- [ ] Add evidence for specific environmental/material claims retained in the final report.
- [ ] Rewrite 3.11 in the author's own voice after completing the analysis.
