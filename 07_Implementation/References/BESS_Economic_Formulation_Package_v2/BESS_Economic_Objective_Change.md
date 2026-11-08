# Proposed change: annual economic objective for BESS siting and sizing

**EE499 Team 16 · Revised proposal v2 · 2026-11-03**  
**Status:** This document describes a mathematical and software change; it **does not** claim that the application code has already been modified.  
**Basis:** Uploaded project snapshot (`07_Implementation/src/`), user-supplied excerpt of Ali, Shaaban & Sindi (2022) Table 3, and published sources [R1]–[R4] below.

## A. Scope and reason for the change

The existing implementation scores a BESS candidate by a **raw weighted sum**:

$$J_{\mathrm{old}}=0.50\,C_{\mathrm{BESS}}+0.25\,E_{\mathrm{curt}}+0.25\,E_{\mathrm{shed}}.$$

`metrics.py` computes `bess_cost` as a one-time amount in the chosen currency; `curtailment_energy_kwh` and `load_shedding_energy_kwh` are kWh over the simulated time series. `optimizer.py` then sums them in `weighted_sum()`. This adds **currency and kWh** as though they were comparable and also compares one-time CAPEX with a potentially short operating period. The nominal 50/25/25 weights do not fix this.

**Proposed change:** Minimize the annual *monetary* cost in USD/year (or SAR/year if **all** prices are converted) using annualized battery investment, annual O&M, net grid electricity purchases, a renewable-curtailment penalty, and a value of lost load. Retain voltage, SOC, reserve, power-flow convergence and enabled upstream import/export constraints. Keep GWO search and battery net-load-target dispatch separate from the objective calculation.

**Reference basis:** [R1] Sections 2.1–2.2, [R2] storage investment/operating-cost and load-shedding/curtailment formulations, [R3] page 11 (PDF page index 10) reported penalties, and [R4] alternative cost projection methodology. **The combined project objective is a new adaptation, not a verbatim formula from one paper.**

## B. Decision variables (unchanged)

$$\mathbf{x}=(b,P_B,E_B), \quad b\in\mathcal{B},\ P_B\in\mathcal{P},\ E_B\in\mathcal{E}.$$

- $b$: selected bus ID (discrete), $P_B$: battery power rating (kW), $E_B$: energy rating (kWh).
- The present GWO searches **indices** in predefined catalogs, not unconstrained real numbers (`optimizer.py`: `OptimizationBounds`, `_candidate_from_position`).

## C. Proposed economic equations — consistent units

Use **one currency** throughout. The following equations assume **USD**, since the cited papers tabulate USD costs. A conversion to SAR must apply to every monetary coefficient and result.

### C1. Capital investment — USD

$$\boxed{C_{\mathrm{cap}}(\mathbf{x})=c_PP_B+c_EE_B+C_{\mathrm{site}}} \tag{1}$$

- $c_P$ (USD/kW): power-related capital cost; $c_E$ (USD/kWh): energy-related capital cost.
- $C_{\mathrm{site}}$ (USD): **optional** extra fixed/site/interconnection cost **only if not already represented** in $c_P,c_E$; set to zero until separately substantiated.
- **Base scenario from [R1], Table 3:** $c_P=770$ USD/kW, $c_E=385$ USD/kWh. These are historical paper assumptions, **not** a current local supplier quotation. Table 3 attributes its inputs to [R1]'s own reference [2].
- **Alternative scenario from [R2], Table 3:** $c_P=320$ USD/kW, $c_E=360$ USD/kWh, plus a separately reported installation cost $c_{\mathrm{inst}}=15$ USD/kWh. If using [R2]'s basis, consider $C_{\mathrm{cap}}=c_PP_B+(c_E+c_{\mathrm{inst}})E_B$ without double counting installation.
- **Source:** [R1], capital-cost equation and Table 3; [R2], Table 3; [R4], battery-power/energy cost separation.

### C2. Capital recovery factor and annual ownership cost — USD/year

$$\boxed{\mathrm{CRF}(r,L)=\frac{r(1+r)^L}{(1+r)^L-1}}\quad (r>0), \qquad \mathrm{CRF}(0,L)=\frac{1}{L}.\tag{2}$$

$$\boxed{C_{\mathrm{BESS,yr}}=\mathrm{CRF}(r,L)\,C_{\mathrm{cap}}+C_{\mathrm{FOM,yr}}.}\tag{3}$$

Base **interpretation** of [R1]'s 2% annual O&M assumption:

$$\boxed{C_{\mathrm{FOM,yr}}=k_{\mathrm{FOM}}C_{\mathrm{cap}},\quad k_{\mathrm{FOM}}=0.02/\mathrm{year}.}\tag{4}$$

- $r$ (1/year): selected annual discount or financing rate; $L$ (years): economic lifetime; $k_{\mathrm{FOM}}$ (1/year): annual fixed O&M rate.
- **Verified [R1]**: $L=10$ years from Table 3; 2% of initial investment is stated in the paper's explanatory text. **6% is retained below only as an illustrative/project-assumed rate; do not attribute it to [R1] without checking the full source.**
- [R1]'s displayed O&M expression and description can be read inconsistently depending on whether investment has already been annualized. Equation (4) states exactly how this project will interpret the 2% rate: **2% of initial CAPEX per year.**
- [R2] instead reports annual fixed O&M for Li-ion as **5 USD/(kW·year)**: $C_{\mathrm{FOM,yr}}=5P_B$, if you choose the alternative [R2] scenario. Do **not** add this to [R1]'s 2% O&M; pick one convention.
- **Sources:** [R1], Section 2.1 cost and CRF discussion; [R2], Table 3; [R4], modern cost/lifetime sensitivity methodology.

### C3. Import/export electricity cost — USD/year

For hourly time steps or representative day/scenario $s$ with annual occurrence weight $n_s$:

$$\boxed{C_{\mathrm{grid,yr}}=\sum_s n_s\sum_{t\in\mathcal T_s}\big(\pi^{\mathrm{buy}}_{s,t} P^{\mathrm{imp}}_{s,t}-\pi^{\mathrm{sell}}_{s,t} P^{\mathrm{exp}}_{s,t}\big)\Delta t.}\tag{5}$$

- $P^{\mathrm{imp}}=\max(P_{\mathrm{slack}},0)$ and $P^{\mathrm{exp}}=\max(-P_{\mathrm{slack}},0)$ (kW); $\pi$ in USD/kWh; $\Delta t$ in hours.
- For a full-year hourly dataset, use each hour once (all $n_s=1$). For representative days, the day weights must sum to 365 (or 366, for leap years) and reflect seasonal diversity. **Do not multiply an arbitrary single 24-hour day by 365 without justification.**
- An export tariff cannot be invented: set $\pi^{\mathrm{sell}}=0$ only if non-compensated export is the study's explicit assumption.
- **Source:** [R1], Section 2.1 grid purchase term; [R2], grid exchange cost formulations. **The separate import-minus-export expression is a project adaptation.**

### C4. Renewable-energy curtailment cost — USD/year

$$\boxed{E_{\mathrm{curt,yr}}=\sum_s n_s\sum_t\sum_i (P^{\mathrm{PV,avail}}_{i,s,t}-P^{\mathrm{PV,used}}_{i,s,t})\Delta t.}\tag{6}$$

$$\boxed{C_{\mathrm{curt,yr}}=\sum_s n_s\sum_t\sum_i c^{\mathrm{curt}}_{i,s,t}\,P^{\mathrm{curt}}_{i,s,t}\Delta t.}\tag{7}$$

- $P^{\mathrm{curt}}=P^{\mathrm{PV,avail}}-P^{\mathrm{PV,used}}\ge0$ (kW); $c^{\mathrm{curt}}$ (USD/kWh).
- **Base sensitivity value [R3]: 0.07 USD/kWh**, reported as a study assumption linked by its authors to renewable LCOE. It is **not** an established universal compensation price.
- **Avoid double-counting:** if this term represents foregone export revenue already implicit in the grid revenue calculation, **do not count both**. Keep $0.07$/kWh only as a **distinct penalty** (e.g., policy/contract/environmental opportunity cost) and state that interpretation.
- **Sources:** [R2], curtailment-cost component; [R3], PDF p. 11.

### C5. Unserved energy / load shedding cost — USD/year

$$\boxed{E_{\mathrm{shed,yr}}=\sum_s n_s\sum_t\sum_i(P^{\mathrm{load,req}}_{i,s,t}-P^{\mathrm{load,served}}_{i,s,t})\Delta t.}\tag{8}$$

$$\boxed{C_{\mathrm{shed,yr}}=\sum_s n_s\sum_t\sum_i c^{\mathrm{VoLL}}_{i,s,t}\,P^{\mathrm{shed}}_{i,s,t}\Delta t.}\tag{9}$$

- $c^{\mathrm{VoLL}}$ (USD/kWh): assigned value of lost load, possibly dependent on customer class and time.
- **Base sensitivity value [R3]: 12 USD/kWh** in its isolated-microgrid study.
- **Alternative high-penalty scenario [R2], Table 4: 50,000 USD/MWh = 50 USD/kWh** (not a tariff).
- **Sources:** [R2], load-shedding cost and Table 4; [R3], PDF p. 11. Customer-specific VoLL is not available from the uploaded network data; a uniform penalty is an approximation.

### C6. Full annual objective — USD/year

$$\boxed{\min_{\mathbf{x}}J_{\mathrm{annual}}(\mathbf{x})=C_{\mathrm{BESS,yr}}+C_{\mathrm{grid,yr}}+C_{\mathrm{curt,yr}}+C_{\mathrm{shed,yr}}.}\tag{10}$$

If $C_{\mathrm{site}}=0$ and the [R1] + [R3] scenario is adopted, with $r=0.06$ **as a declared project assumption**, $L=10$:

$$\mathrm{CRF}=0.13586796,\qquad \mathrm{CRF}+0.02=0.15586796.\tag{11}$$

$$\boxed{J_{\mathrm{annual}}=0.15586796(770P_B+385E_B)+C_{\mathrm{grid,yr}}+0.07E_{\mathrm{curt,yr}}+12E_{\mathrm{shed,yr}}.}\tag{12}$$

All quantities on the right are **USD/year** when energy totals are annual kWh and $P_B,E_B$ use kW/kWh. **Equation (12) is a proposed combination of cited parameter sets, not a quoted paper equation.** [R1], [R3].

**Illustration (not project result):** $P_B=200$ kW, $E_B=500$ kWh. Initial battery CAPEX is $770(200)+385(500)=346{,}500$ USD. Annual ownership cost at the illustrative 6% and [R1] 2% O&M convention is about $54{,}009$ USD/year. Add annually weighted electricity, curtailment and shedding costs from the simulator.

### C7. Baseline and feasibility

$$\boxed{\Delta J=J_{\mathrm{annual,BESS}}-J_{\mathrm{annual,noBESS}}.}\tag{13}$$

A negative value indicates lower annual modeled cost with BESS, assuming the **same** load/PV profiles, tariffs, operating limits, time horizon and accounting convention. If no-BESS cannot meet a required hard constraint, compare performance transparently and distinguish infeasibility from cost.

Any infeasible candidate remains assigned $+\infty$ as its minimization score. Infeasibility is based on the **existing simulator's** constraints and corrective actions, not on cost.

## D. Retained technical equations and constraints (not GWO/GA update equations)

### D1. Battery SOC and energy conservation

$$SOC_t=E_t/E_B,\qquad SOC_{\min}\le SOC_t\le SOC_{\max}.\tag{14}$$

$$\boxed{E_{t+1}=E_t+\eta_{\mathrm{ch}}P_{\mathrm{ch},t}\Delta t-\frac{P_{\mathrm{dis},t}}{\eta_{\mathrm{dis}}}\Delta t.}\tag{15}$$

$$0\le P_{\mathrm{ch},t}\le P_B,\qquad0\le P_{\mathrm{dis},t}\le P_B.\tag{16}$$

Use signed net power $P_{\mathrm{BESS},t}=P_{\mathrm{dis},t}-P_{\mathrm{ch},t}$ (positive discharge). The existing battery model does not charge and discharge simultaneously. Source: [R1] ESS operating limits, [R2] battery operating constraints; implemented in `bess.py`.

**Parameter scenario issue:** [R1] uses $SOC_{\min}=0.20$, $SOC_{\max}=1.00$, $\eta_{\mathrm{ch}}=0.90$, $\eta_{\mathrm{dis}}=0.90$, giving round-trip efficiency 0.81. Current project defaults are 0.10–0.90 SOC. Changing to [R1] is a **deliberate software/model assumption change**. [R2] reports **0.95 round-trip** efficiency, not 0.95 charging *and* discharging efficiency.

### D2. Initial and terminal SOC

$$E_0=SOC_0E_B.\tag{17}$$

**Recommended new constraint**, for representative-day studies:

$$\boxed{SOC_{\mathrm{end}}=SOC_{\mathrm{start}}.}\tag{18}$$

The terminal equality is a **project recommendation** to avoid using free energy from the battery's initial charge. Alternatively, explicitly value the difference in terminal stored energy. This is **not currently enforced** by the uploaded code. It needs careful implementation when reserve constraints are active.

### D3. Network and operational feasibility — existing project

$$\boxed{0.95\le|V_{i,t}|_{\mathrm{pu}}\le1.05.}\tag{19}$$

$$\boxed{-P_{\mathrm{export,max}}\le P_{\mathrm{slack},t}\le P_{\mathrm{import,max}}}\tag{20}$$

The import and export bounds only apply when they are configured, and power flow must converge. The simulator may proportionally curtail PV or shed load to restore acceptable network conditions; those corrective actions are then **penalized economically** rather than automatically forbidden. It also enforces BESS reserve requirements. No dynamic frequency constraint or line thermal enforcement can be claimed without additional simulation logic. Sources: project `simulation.py`, `fbs.py` and `bess.py`; [R1] discusses distribution network operating limits.

### D4. Existing battery dispatch — unchanged for this proposal

$$\boxed{P_{\mathrm{BESS,request},t}=P_{\mathrm{load},t}-P_{\mathrm{PV},t}-P_{\mathrm{target}}.}\tag{21}$$

`dispatch.py` computes the request; `bess.py` applies actual battery limits; `simulation.py` evaluates voltage and grid-flow constraints. **The new annual economic score does not itself optimize the hourly dispatch.** This mismatch should be acknowledged, especially when grid electricity prices vary by hour.

## E. Verified relevant published parameters

**Do not silently combine papers' battery CAPEX, O&M and efficiency assumptions into one synthetic technology.** The base scenario uses [R1] for battery technical/economic inputs and [R3] for penalties. Alternative [R2] inputs should be evaluated as a separate scenario.

| Parameter | Base: Ali–Shaaban–Sindi 2022 [R1] | Alternative: Minh et al. 2026 [R2] | Relation to project |
|---|---:|---:|---|
| Li-ion cost per power rating | **770 USD/kW** (Table 3) | **320 USD/kW** (Table 3) | Required for CAPEX |
| Li-ion cost per energy capacity | **385 USD/kWh** (Table 3) | **360 USD/kWh** (Table 3) | Required for CAPEX |
| Additional installation cost | Not separately extracted | **15 USD/kWh** (Table 3) | Alternative CAPEX component |
| Li-ion lifetime | **10 years** | **10 years** (float life) | Annualized cost assumption |
| Minimum SOC | **20%** (Table 3) | Not adopted from Table 3 | Battery feasible range |
| Maximum SOC | **100%** (Table 3) | Not adopted from Table 3 | Battery feasible range |
| Charging efficiency | **90%** (Table 3) | Not given separately in cited Table 3 | State update |
| Discharging efficiency | **90%** (Table 3) | Not given separately in cited Table 3 | State update |
| Round-trip efficiency | **81% derived** (0.9 × 0.9) | **95%** (Table 3) | Use correct efficiency definition |
| Self-discharge | Not reported in supplied Table 3 | **0.2% per day** (Table 3) | Optional new battery feature |
| O&M | **2% of initial investment annually**, paper text | **5 USD/(kW·year)** (Table 3) | Choose one model |
| Value of lost load | Not reported in supplied table | **50,000 USD/MWh** (Table 4) | Alternate reliability scenario |
| Discount rate | **Not independently verified in R1 from supplied table** | Not selected here | **Project must specify**; 6% is only an illustrative working assumption |
| Grid buy/sell tariffs | Figure/assumptions need numerical selection | Case-specific | **Not yet supplied** |

| Other source parameter | Value | Source | How used |
|---|---:|---|---|
| Curtailment penalty | **0.07 USD/kWh** | [R3], PDF p. 11 | Base sensitivity scenario |
| Unserved-energy penalty | **12 USD/kWh** | [R3], PDF p. 11 | Base sensitivity scenario |
| Contemporary BESS cost forecast | Varies by year and scenario | [R4] | Economic sensitivity, not a direct drop-in for [R1] |

### Important distinctions

1. The [R1] excerpt supplied by the user shows **Li-ion** values; omit the paper's supercapacitor and CAES columns because this project currently models only Li-ion BESS.
2. The $12/kWh and $0.07/kWh coefficients are from a study of an **isolated** microgrid [R3], whereas our network is grid-connected. They are appropriate as transparently stated research-based **sensitivity assumptions**, not mandated Saudi tariff values.
3. A **no-BESS** alternative should be considered. Selecting a positive BESS size in a restricted catalog cannot demonstrate that any battery is economically necessary.
4. Discount rate, Saudi system scale, grid import tariff, export compensation, life-cycle horizon, and interconnection/site costs still require project decisions and citations.


## E2. Explicit proposed parameter set (v2 implementation checklist)

**Clarification:** The previous version **already contained** published values in Section E, but did **not** supply a complete implementable case because grid purchase/export tariffs and point-of-common-coupling (PCC) limits were unchosen. The table below distinguishes **literature-sourced numerical values** from **project choices** and **required network data**. Values in different papers are not to be mixed without declaring a scenario.

| Parameter / config field | Recommended base-case input | Units | Status / provenance |
|---|---:|---|---|
| `power_cost_per_kw` (`c_P`) | **770** | USD/kW | **Published:** Ali, Shaaban & Sindi (2022), Table 3 [R1] (their Table 3 cites an earlier source) |
| `energy_cost_per_kwh` (`c_E`) | **385** | USD/kWh | **Published:** [R1], Table 3 |
| `lifetime_years` (`L`) | **10** | years | **Published:** [R1], Table 3 |
| `soc_min` | **0.20** | fraction | **Published:** [R1], Table 3; would change current project default 0.10 |
| `soc_max` | **1.00** | fraction | **Published:** [R1], Table 3; would change current project default 0.90 |
| `eta_charge` | **0.90** | fraction | **Published:** [R1], Table 3 |
| `eta_discharge` | **0.90** | fraction | **Published:** [R1], Table 3 (round trip 81%) |
| `annual_om_fraction` | **0.02** | per year | **Literature-based convention:** [R1] paper text, defined here as share of *initial* CAPEX |
| `curtailment_penalty` | **0.07** | USD/kWh | **Published case-study penalty:** Córdova et al. [R3] (isolated microgrid), not local tariff |
| `unserved_energy_penalty` | **12.00** | USD/kWh | **Published case-study penalty:** [R3], not established Saudi VoLL |
| `discount_rate` | **0.06** | per year | **Project illustrative assumption:** rate not independently verified from [R1]'s supplied table; requires justification |
| `voltage_min_pu`, `voltage_max_pu` | **0.95**, **1.05** | pu | **Existing project design defaults**, not taken from [R1] |
| `reserve_fraction`, `reserve_duration_hours` | **0.10**, **1.0** | fraction, h | **Existing project defaults**, not from [R1] |
| `grid_import_limit_kw` | **TBD from PCC/transformer rating** | kW | **Required network/interconnection input**; literature supports constraint, not one universal number [R5–R8] |
| `grid_export_limit_kw` | **TBD from export agreement/network rating** | kW | **Required network/contract input**; `0` only for a *chosen non-export scenario* [R7] |
| `import_price` | **TBD from applicable economic perspective** | USD/kWh | **Required tariff/wholesale price input** |
| `export_compensation` | **TBD from applicable agreement** | USD/kWh | **Required tariff/contract input**; zero only if non-compensated exports explicitly assumed |
| `terminal_soc` | **equal to initial SOC**, recommended | fraction | **Proposed extension**, not presently enforced |

**Proposed first experiment:** keep all source-based base-case BESS assumptions above, calculate results for (i) the present unbounded-PCC software baseline, and (ii) physically supported limited-import / limited-export scenarios once the PCC equipment rating and permission to export are documented. Consider a zero-export **scenario** only when the study intends to model a non-export interconnection. Do **not** present a trial number such as 100 kW as a cited universal interconnection limit.

## E3. Grid import/export: peer-reviewed research basis and proposed equations

### Published motivation

- **[R5] Novoa, Flores & Brouwer (2020)** explicitly include **distribution-transformer limits** when optimizing DER/PV/battery sizing and siting, and explain that assuming unlimited distribution infrastructure can produce infeasible planning outcomes. They constrain transformer **apparent power**, not merely the battery's kW rating. DOI: <https://doi.org/10.1016/j.apenergy.2019.113926>.
- **[R6] Dong et al. (2026), Equation (1)** explicitly model import-positive/export-negative PCC active power using a **bounded bidirectional grid-interface constraint**. Their simplified equivalent limit depends on transformer/line capabilities. DOI: <https://doi.org/10.3390/a19040320>.
- **[R8] Xuan, Zhao & Ding (2026), Equation (19)** bound bought and sold grid power by the interconnection limit and use mutually exclusive buy/sell states. They identify transformer transfer capability as the rationale. DOI: <https://doi.org/10.1049/stg2.70058>.
- **[R7] BATRIES / IREC interconnection toolkit** explicitly discusses **non-export and limited-export** configurations, in which the allowable export capacity is an interconnection-agreement setting. It is technical guidance **not a peer-reviewed numeric tariff or Saudi regulation**: <https://energystorageinterconnection.org/iii-requirements-for-limited-and-non-export-controls/e-recommendations/>.
- **[R9] Alguhi & Alotaibi (2025)**, an additional Saudi-affiliated case study, models BESS power exchange with an IEEE-33 feeder and enforces feeder voltage and thermal limits. It is relevant context but **does not supply a transferable rating** for the user's feeder. DOI: <https://doi.org/10.3390/en18236335>.

### Proposed constraint A: import/export active-power caps (compatible with current code)

Define the FBS slack-bus output so **positive** $P_{\mathrm{slack},t}$ is **import** and negative is **export**:

$$\boxed{P_{\mathrm{imp},t}=\max(P_{\mathrm{slack},t},0),\quad P_{\mathrm{exp},t}=\max(-P_{\mathrm{slack},t},0).}\tag{22}$$

$$\boxed{0\le P_{\mathrm{imp},t}\le P_{\mathrm{imp,max}},\qquad 0\le P_{\mathrm{exp},t}\le P_{\mathrm{exp,max}}.}\tag{23}$$

Equivalently:

$$\boxed{-P_{\mathrm{exp,max}}\le P_{\mathrm{slack},t}\le P_{\mathrm{imp,max}}.}\tag{24}$$

This is already the **sign convention and inequality** used in `src/simulation.py` (`grid_import_limit_kw`, `grid_export_limit_kw`, `flow.slack_p_kw`), when these optional limits are specified. A numeric grid **target** from the dispatch strategy does **not** replace these hard operating caps. Literature support: [R6] Eq. (1); [R8] Eq. (19); [R7] interconnection limits.

### Proposed constraint B: PCC transformer rating (more physical, needs input/model work)

The transformer and point-of-connection equipment are rated by **apparent power** $S$ (kVA), not generally by active-power kW alone. If the transformer has a rated capacity $S_{\mathrm{PCC,max}}$ and the simulator calculates the slack-bus reactive-power exchange $Q_{\mathrm{slack},t}$, a more physically meaningful constraint is:

$$\boxed{\sqrt{P_{\mathrm{slack},t}^2+Q_{\mathrm{slack},t}^2}\le S_{\mathrm{PCC,max}}.}\tag{25}$$

Equivalently for a given $Q_{\mathrm{slack},t}$:

$$\boxed{|P_{\mathrm{slack},t}|\le\sqrt{S_{\mathrm{PCC,max}}^2-Q_{\mathrm{slack},t}^2}.}\tag{26}$$

If $|Q_{\mathrm{slack},t}|>S_{\mathrm{PCC,max}}$, the point is infeasible regardless of active power. These equations are standard AC apparent-power relationships applied to the PCC, consistent with transformer constraints in [R5] and thermal limits modeled in [R9]. To enforce (25), a **documented PCC transformer rating and a corresponding physical transformer/network interface model** are required; the uploaded project currently includes optional active-power caps but should not be claimed to have a validated transformer overload constraint.

### Determining **numerical** limits responsibly

1. Obtain the **PCC transformer apparent-power rating** and, where relevant, head-feeder/cable continuous ratings (kVA or A). Use that hardware basis for transfer-capacity studies [R5], [R6].
2. Establish whether reverse/export power is authorized and, if so, its permitted **export capacity** under the connection agreement. A **zero-export** option is meaningful when explicitly studying a non-export interconnection [R7].
3. Set `grid_import_limit_kw` and `grid_export_limit_kw` to **case-specific active-power caps**, accounting for the anticipated power factor and any site/utility limitations. If only kVA is available, do not equate kVA to kW except under an explicitly declared unity-power-factor approximation.
4. Analyze sensitivity to limits and document the physical basis. Published import/export **equations do not validate a particular 100/250/500 kW cap** for an unknown feeder.

**Illustrative calculation only (NOT sourced parameter):** If $S_{\mathrm{PCC,max}}=500$ kVA and $|\mathrm{pf}|=0.95$ at the PCC, then the corresponding active power magnitude would be about $475$ kW at that operating point. This does not define a contractual export allowance; it also does not guarantee thermal feasibility for every different $Q$ and operating condition.

### Interconnection scenarios for experiment design (research-supported *types*, researcher-selected numbers)

| Scenario | Import | Export | Interpretation |
|---|---|---|---|
| Existing software baseline | Uncapped (`None`) | Uncapped (`None`) | Useful comparison but not evidence of physically infinite transformer capacity |
| No-export DER | Hardware/contract-derived cap | **0 kW** | Model a deliberately non-exporting connection; supported as an operating *mode* by [R7] |
| Limited-export DER | Hardware/contract-derived cap | Connection-agreement value | A limited-export *mode*; [R7] |
| Bidirectional equipment-rated connection | Equipment-based cap | Equipment-based cap | Evaluate against PCC transformer $S$ rating and power factor [R5], [R6], [R8] |

**Operational consequence in this simulator:** If the import cap is breached, simulation can pause competing battery charging and shed load to restore constraints. If the export cap is breached, it can pause conflicting battery discharge and curtail PV. These actions are **simulation controls**, not physical operating rules automatically commanded by the paper sources. Curtailment and shedding enter the monetary objective in (7) and (9).

**Do not reuse a literature case-study transformer/PCC rating as the user's rating merely because the paper used the IEEE-33 feeder.** Obtain or explicitly assume the network ratings in our actual test system.


## F. Changes required to the project code (not performed)

| Source file | Proposed change | Verification/test |
|---|---|---|
| `src/metrics.py` `EconomicConfig` | Add discount rate, lifetime, annual O&M model, curtailment penalty, VoLL, tariff arrays or constants, annualization weights, currency | Unit validation and no ambiguous default tariffs |
| `src/metrics.py` `PerformanceMetrics` | Add annual CAPEX recovery, fixed O&M, import/export cost, annual curtailment and shedding cost, total annual cost | Check each component has USD/year |
| `src/metrics.py` `evaluate_results()` | Aggregate annual energies from hourly series (actual/available PV and served/requested load are already tracked) | Full-year vs weighted representative day |
| `src/optimizer.py` | Replace `weighted_sum()` in `SimulationEvaluator` with `annual_economic_objective(metrics, config)` | Compare ordering on controlled candidate examples; infeasible → `inf` |
| `src/dispatch.py` | No mandatory initial change; document that dispatch is net-load target, not price-optimal | Charging from grid can incur cost |
| `src/bess.py` | Set SOC and efficiency inputs to selected scenario; optionally add self-discharge / terminal SOC | SOC bounds, energy conservation |
| `src/simulation.py` | Keep existing configurable active-power import/export caps; add optional PCC apparent-power rating validation **only if transformer data/model supports it**; optionally enforce terminal SOC | Test both positive import and negative export signs, as well as feasible/infeasible grid exchange |
| Tests | New `test_economics.py`: CRF, O&M, energy units, buy-sell sign, annual weighting, double-count guard, no BESS and infeasibility | Automated regression coverage |

**Critical software note:** If a 24-hour profile is used for investment planning, a terminal SOC rule or terminal-energy adjustment should be implemented *before* treating annual cost rankings as economically reliable.

## G. Paper references and direct open-access download locations

**[R1]** Ali, A., Shaaban, M. F., & Sindi, H. F. (2022). *Optimal Operational Planning of RES and HESS in Smart Grids Considering Demand Response and DSTATCOM Functionality of the Interfacing Inverters*. **Sustainability**, 14(20), 13209. DOI: https://doi.org/10.3390/su142013209  
Full text: https://www.mdpi.com/2071-1050/14/20/13209  
PDF: https://www.mdpi.com/2071-1050/14/20/13209/pdf  
Supports: battery power/energy cost coefficients, lifetime, SOC, efficiencies, O&M convention, CRF and grid energy-cost methodology. **Table 3 credits its own reference [2] for storage parameters.**

**[R2]** Minh, N. Q., Dai, T. V., Hoang, P. M., Hai, P. H., & Chau, L. T. M. (2026). *A mixed-integer linear programming model for BESS sizing optimization considering aging effects and emission costs*. **Smart Energy**, 21, 100225. DOI: https://doi.org/10.1016/j.segy.2025.100225  
Publisher: https://www.sciencedirect.com/science/article/pii/S266695522500053X  
Open-access PDF mirror (university-hosted): https://storage.googleapis.com/hust-files/2026-01-06/1767694932859/5261733430034432/1-s2.0-s266695522500053x-main_4.2m.pdf  
Supports: Table 3 Li-ion costs, lifetime, round-trip efficiency, O&M; Table 4 VoLL and study's annual-cost modeling.

**[R3]** Córdova, S., Cañizares, C. A., Lorca, Á., & Olivares, D. E. (2022). *Frequency-Constrained Energy Management System for Isolated Microgrids*. **IEEE Transactions on Smart Grid**, 13(5), 3394–3407. DOI: https://doi.org/10.1109/TSG.2022.3170871  
Open-access accepted manuscript (University of Waterloo): https://uwspace.uwaterloo.ca/bitstreams/61ce0587-9c74-4d54-aead-b9e31ad79e71/download  
Repository: https://uwspace.uwaterloo.ca/items/6b498463-e57d-4ca3-82d6-31121d3501b4  
Supports: reported **12 USD/kWh** load shedding cost and **0.07 USD/kWh** renewable curtailment cost, in PDF p. 11.

**[R4]** Cole, W., Ramasamy, V., & Turan, M. (2025). *Cost Projections for Utility-Scale Battery Storage: 2025 Update*. NREL/TP-6A40-93281. DOI: https://doi.org/10.2172/2583471  
Public report PDF: https://www.nrel.gov/docs/fy25osti/93281.pdf  
Publication record: https://research-hub.nlr.gov/en/publications/cost-projections-for-utility-scale-battery-storage-2025-update/  
Related technology-cost guidance: https://atb.nlr.gov/electricity/2025/utility-scale_battery_storage  
Supports: updated battery cost projections and methodology for separate power/energy cost components. **Do not combine a single 4-hour $/kWh system benchmark with existing $/kW coefficients without reconciling coverage.**

**[R5]** Novoa, L., Flores, R., & Brouwer, J. (2020). *Optimal renewable generation and battery storage sizing and siting considering local transformer limits*. **Applied Energy**, article 113926. DOI: https://doi.org/10.1016/j.apenergy.2019.113926  
Supports: distribution transformer apparent-power limits in DER/BESS sizing and siting; **no universal numerical PCC rating**.

**[R6]** Dong, X., Liu, C., Li, J., Zhu, Q., Wang, Y., & Zhu, J. (2026). *Assessment of Distributed PV Hosting Capacity in Distribution Areas Based on Operating Region Analysis*. **Algorithms**, 19(4), 320. DOI: https://doi.org/10.3390/a19040320  
Supports: explicit bidirectional grid-interface power bound in Equation (1), related to transformer/line transfer capability.

**[R7]** BATRIES. *Storage Interconnection Solutions: Requirements for Limited- and Non-Export Controls — Recommendations*. https://energystorageinterconnection.org/iii-requirements-for-limited-and-non-export-controls/e-recommendations/  
Supports: why export capacity is an interconnection-agreement parameter, and when zero-export/limited-export modes are justified. **Technical guidance, not a research paper and not Saudi grid code**.

**[R8]** Xuan, W., Zhao, D., & Ding, R. (2026). *Climate-Driven Low-Carbon Dispatch Strategy for Photovoltaic-Storage-Charging Microgrids*. **IET Smart Grid**, 9(1), e70058. DOI: https://doi.org/10.1049/stg2.70058  
Supports: explicit bound on imported and exported grid power, Equation (19), with a transformer-related grid transfer limit.

**[R9]** Alguhi, A. A., & Alotaibi, M. A. (2025). *Optimal Operation of Battery Energy Storage Systems in Microgrid-Connected Distribution Networks for Economic Efficiency and Grid Security*. **Energies**, 18(23), 6335. DOI: https://doi.org/10.3390/en18236335  
Supports: BESS power exchange, voltage and feeder thermal constraints in a Saudi-affiliated research case study; not a site-specific PCC import/export numerical rating.

## H. Citation and download integrity

- The supplied project's paper directory contains a Git LFS **pointer** named `sustainability-14-13209.pdf`, not an embedded PDF in the uploaded ZIP; do not treat that pointer as the paper itself.
- See `papers/PAPER_DOWNLOADS.md` for URLs, availability, and a script that downloads the official/open-access PDFs on a computer with internet access. **No paper PDF is represented as included if the file was not actually retrieved.**
- Original PDF articles are linked, not reproduced or rewritten as substitute PDFs. The included user-supplied image is only the Table 3 excerpt.
