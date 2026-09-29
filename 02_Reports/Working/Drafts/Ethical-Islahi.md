# Ethical analysis — Islahi: initial sources

This is a working source list for the two selected issues in the individual [Ethical Analysis assignment](../../../01_Official/Course_Guidance/Ethical_Analysis.md). Priority is based on relevance to a BESS optimization tool that might later process real Saudi utility data. These are sources to read and cite in the analysis, not a claim that every listed regulation automatically applies to the student prototype.

## Issue 1 — Confidentiality and security of power-system data

A deployed tool could process non-public distribution-network topology, line parameters, operating conditions, and load profiles. Customer-level load records may also raise personal-data concerns. Sources are ordered from the most directly useful to more conditional or supporting material.

1. **Saudi Council of Engineers (SCE), [Engineer Charter 2025](https://www.saudieng.sa/Admin/Documents/EngineerCharter2025-Ar.pdf)** — Required ethical code for the assignment. **Rule 9** concerns confidentiality of engineering information and data and authorization before publication. Use the [repository's working rule index](../../../01_Official/Course_Guidance/SCE_Engineer_Charter_2025_Project_Reference.md) to locate the rule, then check the original Arabic charter when citing it.
2. **Saudi National Cybersecurity Authority (NCA), [Data Cybersecurity Controls (DCC-1:2022)](https://nca.gov.sa/en/regulatory-documents/controls-list/dcc/)** — Main Saudi technical source for protecting organizational data throughout its lifecycle. Examine collection/input, processing, access, storage, sharing, retention, and deletion in a real deployment.
3. **NCA, [Essential Cybersecurity Controls (ECC 2-2024)](https://nca.gov.sa/en/regulatory-documents/controls-list/ecc/)** — Broader cybersecurity baseline for information and technology assets. Use for access control and secure operation alongside DCC, after checking the deployment organization's applicable obligations.
4. **Saudi Data & AI Authority (SDAIA), [Personal Data Protection Law (PDPL)](https://sdaia.gov.sa/en/SDAIA/about/Documents/Personal%20Data%20English%20V2-23April2023-%20Reviewed-.pdf)** — **Conditional:** relevant when input load records identify, or could identify, an individual customer. Do not assume that aggregate bus-load or network data are personal data.
5. **SDAIA, [Data Classification Policy](https://sdaia.gov.sa/en/SDAIA/about/Documents/DataClassificationPolicy.pdf)** — Supporting Saudi source for assessing data sensitivity and handling. Its stated scope concerns data received, produced, or managed by public entities; check whether the intended operator falls within that scope before claiming it applies.
6. **U.S. NIST, [IR 7628 Rev. 1: Guidelines for Smart Grid Cybersecurity](https://csrc.nist.gov/pubs/ir/7628/r1/final)** — International, grid-specific risk and privacy guidance. Use for examples of utility cybersecurity risks and safeguards, without presenting it as Saudi law.
7. **U.S. NIST, [TN 2051: Cybersecurity Framework Smart Grid Profile](https://csrc.nist.gov/pubs/tn/2051/final)** — Additional guidance on prioritizing cybersecurity risk management for power-system owners and operators.

**First-source note:** The NCA DCC page identifies protection of organizational data over the entire data lifecycle as its purpose. If a utility later imports real feeder and demand data, the software team's ethical concern is who can access those files, where they are processed and stored, whether they are shared, and when they are deleted. SCE Rule 9 provides the professional confidentiality connection. The present academic test data should not be described as confidential utility data without evidence.

## Issue 2 — Reliability and responsible use of optimization results

A numerical recommendation can appear authoritative even when the network model, input data, scenarios, or optimization are limited. Sources are ordered by their role in this assignment.

1. **SCE, [Engineer Charter 2025](https://www.saudieng.sa/Admin/Documents/EngineerCharter2025-Ar.pdf)** — Required Saudi ethical source. The [repository's working rule index](../../../01_Official/Course_Guidance/SCE_Engineer_Charter_2025_Project_Reference.md) identifies **Rule 14** for accurate, objective, evidence-supported engineering reports and **Rules 8 and 16** for responsibility, safety, quality, and reliability. Confirm the wording against the original charter in the report.
2. **NASA, [NASA-STD-7009B: Standard for Models and Simulations](https://standards.nasa.gov/node/263)** — Technical supporting source on model and simulation credibility, verification, validation, sensitivity, uncertainty, and defined acceptance criteria. Use it as guidance for the tool's validation and communication of limitations; it is a NASA standard, not a Saudi requirement.

**First-source note:** The program should describe each BESS size/location as a result under specified data and model assumptions. The analysis should identify the validated network scope, data quality, scenario coverage, constraint checks, and failed or uncertain cases so that a future engineer can independently judge the recommendation. SCE Rule 14 grounds truthful reporting; NASA-STD-7009B offers technical practices for assessing model credibility.

## Related issue reserved for Section 3.9

**Software licensing, intellectual property, and attribution** remain relevant for libraries, datasets, algorithms, and copied code. The assignment explicitly addresses them in **Section 3.9**; SCE **Rule 6** is the related charter rule. They are not one of the two main issues selected above.
