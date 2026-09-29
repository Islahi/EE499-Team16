# Software GUI and Library References

This note collects software references that are relevant to the EE499 Team 16 project. These tools are references for **software architecture, GUI/workflow ideas, power-flow validation, distribution-system modelling, storage modelling, time-series simulation, and optimization**. They are not automatically part of the project implementation unless the team explicitly decides to adopt them.

Project repository: https://github.com/Islahi/EE499-Team16.git

## GUI / Desktop / Engineering Programs

| Program | Type | Relevance to the project | Link |
|---|---|---|---|
| **GLOW (GridLAB-D Open Workspace)** | Distribution-system GUI / workspace | Useful reference for model setup, simulation workflow, scenario management, and result visualization around GridLAB-D. | https://www.energy.ca.gov/publications/2024/glow-user-friendly-interface-gridlab-d |
| **OpenDSS Designer** | Graphical OpenDSS interface | Useful reference for one-line network visualization, editing network elements, running distribution studies, and presenting bus/branch results. | https://pypi.org/project/opendss-designer/ |
| **GridCal** | Open-source power-system GUI and Python framework | Useful reference for Python GUI structure, network visualization, case loading, power-flow studies, result tables, plotting, and separating the GUI from solver logic. | https://github.com/SanPen/GridCal |
| **DIgSILENT PowerFactory** | Commercial power-system analysis software | Industry reference for load flow, distribution/transmission studies, DER, storage, time-series analysis, and professional result presentation. | https://www.digsilent.de/en/powerfactory.html |
| **ETAP** | Commercial electrical power-system analysis software | Industry reference for one-line diagrams, load flow, renewable/storage studies, network limits, and engineering dashboards. | https://etap.com/ |
| **CYME Power Engineering Software** | Commercial distribution-system planning software | Relevant to distribution planning, voltage/loading analysis, DER integration, feeder studies, and utility-style workflows. | https://www.eaton.com/us/en-us/products/utility-grid-solutions/software-modules/cyme-power-engineering-software.html |
| **PowerWorld Simulator** | Commercial power-system analysis GUI | Useful reference for interactive network diagrams, power-flow visualization, contingency/result presentation, and user-facing study controls. It is more transmission-oriented than this project. | https://www.powerworld.com/ |

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

- **GUI/workflow inspiration:** GLOW, OpenDSS Designer, GridCal, PowerFactory, ETAP, CYME, PowerWorld.
- **Python architecture inspiration:** pandapower and GridCal.
- **Distribution-system behaviour and validation:** OpenDSS, OpenDSSDirect.py, GridLAB-D.
- **Power-flow benchmark/reference:** MATPOWER and pandapower.
- **Storage/renewable/optimization concepts:** PyPSA.

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
