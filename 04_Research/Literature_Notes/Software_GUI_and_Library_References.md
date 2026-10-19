# Software GUI and Library References

This note collects software references that are relevant to the EE499 Team 16 project. These tools are references for **software architecture, GUI/workflow ideas, power-flow validation, distribution-system modelling, storage modelling, time-series simulation, and optimization**. They are not automatically part of the project implementation unless the team explicitly decides to adopt them.

Project repository: https://github.com/Islahi/EE499-Team16.git

## GUI / Desktop / Engineering Programs

| Program | Type | Relevance to the project | Link |
|---|---|---|---|
| **Simple-PyQt5-Password-Manager (Islahi)** | User's small Qt desktop project | User-requested reference for Designer forms, focused window classes and named signal handlers; not an engineering solver or mandatory PyQt5 dependency. See the project-specific implementation guide. | https://github.com/Islahi/Simple-PyQt5-Password-Manager |
| **GLOW (GridLAB-D Open Workspace)** | Distribution-system GUI / workspace | Useful reference for model setup, simulation workflow, scenario management, and result visualization around GridLAB-D. | https://www.energy.ca.gov/publications/2024/glow-user-friendly-interface-gridlab-d |
| **OpenDSS Designer** | Graphical OpenDSS interface | Useful reference for one-line network visualization, editing network elements, running distribution studies, and presenting bus/branch results. | https://pypi.org/project/opendss-designer/ |
| **GridCal** | Open-source power-system GUI and Python framework | Useful reference for Python GUI structure, network visualization, case loading, power-flow studies, result tables, plotting, and separating the GUI from solver logic. | https://github.com/SanPen/GridCal |
| **VeraGrid** | Power-system analysis application and Python framework | Added for later review of uncertainty/scenario methods, investment evaluation, Qt network diagrams and time-series results. Reference only; not an adopted dependency or replacement backend. See the focused review links below. | https://veragrid.readthedocs.io/ |
| **DIgSILENT PowerFactory** | Commercial power-system analysis software | Industry reference for load flow, distribution/transmission studies, DER, storage, time-series analysis, and professional result presentation. | https://www.digsilent.de/en/powerfactory.html |
| **ETAP** | Commercial electrical power-system analysis software | Industry reference for one-line diagrams, load flow, renewable/storage studies, network limits, and engineering dashboards. | https://etap.com/ |
| **CYME Power Engineering Software** | Commercial distribution-system planning software | Relevant to distribution planning, voltage/loading analysis, DER integration, feeder studies, and utility-style workflows. | https://www.eaton.com/us/en-us/products/utility-grid-solutions/software-modules/cyme-power-engineering-software.html |
| **PowerWorld Simulator** | Commercial power-system analysis GUI | Useful reference for interactive network diagrams, power-flow visualization, contingency/result presentation, and user-facing study controls. It is more transmission-oriented than this project. | https://www.powerworld.com/ |

The password-manager source was statically rechecked on 18 Oct 2026 at commit
`6f8273cd04d73368403db75bb23e84b5ef2141d8`; its GUI was not executed.
[Qt desktop implementation guidance](../../07_Implementation/Qt_Desktop_Implementation_Guide.md)
separates observed patterns from our safety/threading/drawing adaptations.
The user's PowerPoint remains the layout reference; do not copy the password
manager's appearance or unrelated security/database features.

## Libraries / Simulation Frameworks

| Library / Framework | Type | Relevance to the project | Link |
|---|---|---|---|
| **pandapower** | Python power-system modelling library | Strong reference for Python network data structures, buses, lines, loads, generators, storage-related elements, time-series simulation, and validation of network calculations. | https://www.pandapower.org/ |
| **PyPSA** | Python energy-system / power-system optimization framework | Relevant to renewable generation, storage, time series, capacity planning, operational optimization, and stochastic/two-stage optimization concepts. | https://pypsa.org/ |
| **OpenDSS** | Distribution-system simulator | Strong reference for radial distribution feeders, time-series studies, PV, storage, voltage analysis, losses, and distribution-system behaviour. | https://sourceforge.net/projects/electricdss/ |
| **OpenDSSDirect.py** | Python interface to OpenDSS | Useful if Python-based cross-checking of OpenDSS results is later needed without building the project around the OpenDSS GUI. | https://github.com/dss-extensions/OpenDSSDirect.py |
| **MATPOWER** | MATLAB/Octave power-flow and OPF package | Useful benchmark/reference for AC power flow, optimal power flow, standard test cases, and numerical result comparison. | https://matpower.org/ |
| **GridLAB-D** | Distribution-system simulation platform | Relevant to distribution power flow, load/DER modelling, time-series behaviour, and the broader ecosystem behind GLOW. | https://www.gridlabd.org/ |

## Suggested use for this project

These references are useful in different ways:

- **GUI/workflow inspiration:** GLOW, OpenDSS Designer, GridCal, VeraGrid, PowerFactory, ETAP, CYME, PowerWorld.
- **Python architecture inspiration:** pandapower, GridCal and VeraGrid.
- **Distribution-system behaviour and validation:** OpenDSS, OpenDSSDirect.py, GridLAB-D.
- **Power-flow benchmark/reference:** MATPOWER and pandapower.
- **Storage/renewable/optimization concepts:** PyPSA.
- **Uncertainty and investment-workflow comparison:** VeraGrid; use the focused links and cautions below.

For the current project architecture, the team should still implement the design contracts defined in the repository, including the project's own `network_model.py`, `fbs.py`, BESS model, uncertainty workflow, and optimization workflow, unless a later team decision explicitly changes that plan.

## GUI ideas worth studying

When reviewing the GUI programs above, focus on features that could inform the final decision-support application:

- one-line or feeder visualization;
- bus voltage and branch loading display;
- load/PV profile import and preview;
- simulation configuration panels;
- BESS location, power, energy and SOC display;
- optimization progress/status;
- baseline-vs-optimized comparison;
- voltage, SOC, curtailment, load-shedding and cost plots;
- clear separation between the GUI layer and the numerical/optimization modules.

These are **reference ideas only**, not new project requirements.

## VeraGrid — focused reference for later review

**Added at the user's request on 18 Oct 2026.** Revisit relevant parts when
reviewing our uncertainty, optimization, results and interface modules. This
does not authorize installing VeraGrid, copying its code/assets or replacing
our existing implementation.

| Our area | Official reference | What to examine later |
|---|---|---|
| `uncertainty.py` | [Stochastic power flow](https://veragrid.readthedocs.io/en/latest/md_source/stochastic_power_flow.html) | Sampling assumptions, Monte Carlo/Latin Hypercube alternatives, statistical outputs and convergence checks. Compare these with our time-dependent ARIMA paths and 100-to-45 stress selection; do not assume equivalent uncertainty models. |
| `optimizer.py` / BESS planning | [Investment optimization](https://veragrid.readthedocs.io/en/stable/md_source/investment_optimization.html) | Candidate-asset evaluation, technical/economic objective definitions, scenario aggregation and result reporting. Its documented NSGA/MVRSM approaches are references, not a decision to replace our GWO/raw WSM. |
| `ui.py` / network visualization | [User interface: diagram view](https://veragrid.readthedocs.io/en/stable/md_source/user_interface.html#diagram-view) | Central schematic, side panels, automatic-layout controls, selected-element information and time-step navigation. Our agreed first drawing scope is automatic arrangement of an existing radial network, not a manual network editor. |
| `results.py` / simulation inspection | [User interface: results](https://veragrid.readthedocs.io/en/stable/md_source/user_interface.html#results) | Linking diagram colours to a selected result/time step, result tables, units, plots and exports. Treat these as presentation ideas, not new calculation requirements. |

The documentation was checked on 18 Oct 2026. The `stable` and `latest` links
can change over time; record the actual software/documentation version if a
later comparison is used as validation evidence.

VeraGrid has substantial functional overlap with this project, including
power-system studies, uncertainty analysis and investment evaluation. We have
**not established** that it provides our exact ARIMA → 100 cases → 45 selected
cases → GWO/raw-WSM workflow. Neither claim that our entire concept is unique
nor claim exact equivalence without a specific comparison.

Any future numerical cross-check must align network data, units, operating
profiles, battery/dispatch assumptions, constraints and objective definitions.
A matching-looking diagram or similar feature name is not validation evidence.
Review licensing and attribution before reusing external code or assets.
