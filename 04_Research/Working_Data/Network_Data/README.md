# Distribution Network Data

## Files

- `EE499_Team16_5Bus_Network_Data.pdf` — a project reference for the 11 kV, 10 MVA radial five-bus development case. It records topology, published line impedances, grid-strength cases and PV-placement scenarios.
- `PJM_5Bus_Network_Data.xlsx` — the MATPOWER/PJM five-bus test system for power-flow, optimal-power-flow and BESS-integration reference work.
- `IEEE_33Bus_Network_Data.xlsx` — the standard Baran and Wu 33-bus radial distribution system, with overview, bus-load and branch-impedance sheets.

## Validation summary

The five-bus source provides four line impedances but does **not** provide individual bus-load magnitudes in its network-parameter table. Any five-bus load allocation must therefore be labelled as a project assumption or derived profile, not published source data.

The PJM five-bus workbook opens successfully and contains:

- 5 buses, 6 branches and 5 generators;
- a looped 230 kV network on a 100 MVA base;
- 1,000 MW / 328.69 MVAr connected load;
- 1,000 MW initial generation and 1,530 MW total generation capacity;
- linear generator-cost coefficients and branch ratings from MATPOWER `case5`.

This PJM case is a compact transmission/economic-dispatch test system. It is **not** a radial distribution feeder and is therefore not a direct substitute for the 11 kV five-bus Forward–Backward Sweep development case. Use it as a secondary power-flow/OPF/BESS reference or comparison case.

The 33-bus workbook opens successfully and contains:

- 33 buses and 32 branches;
- 12.66 kV base voltage and 100 MVA base power;
- 3,715 kW total real load and 2,300 kVAr total reactive load;
- formulas reconciling the load totals on the bus and branch sheets.

The workbook is suitable as source data, but its existing print areas split wide sheets across multiple pages. That is a presentation limitation only; no workbook data or formatting was altered while adding it to the repository.

## Source cautions

- Preserve the five-bus and IEEE 33-bus systems as separate test cases; their base values and published purposes differ.
- Keep the radial 11 kV five-bus case and the looped 230 kV PJM five-bus case distinct in code, results and report labels.
- Document any per-unit conversion or base-MVA rescaling explicitly.
- Do not transfer the IEEE 33-bus loads to the five-bus feeder and describe them as published five-bus measurements.
- Keep project-selected BESS limits, state-of-charge constraints and candidate locations separate from source network data.
