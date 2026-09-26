# Research Source Index

This index separates **external research evidence** from the team's own notes/data. The official project description was moved to `01_Official/Project_Description/` because it is a project requirement, not a literature source.

## External papers / reference material

### `Papers/2508.12526v1.pdf`

**Title:** *Techno-Economic Planning of Spatially-Resolved Battery Storage Systems in Renewable-Dominant Grids Under Weather Variability*  
Relevant to battery-storage planning, renewable-dominant grids, weather variability, and techno-economic analysis.

### `Papers/90517.pdf`

**Title/topic:** *What Is Power System Curtailment?*  
A Global Power System Transformation Consortium reference/fact sheet useful for definitions and context around power-system curtailment.

### `Papers/An_Optimal_Energy_Management_System_for_Islanded_Microgrids_Based_on_Multiperiod_Artificial_Bee_Colony_Combined_With_Markov_Chain.pdf`

**Title:** *An Optimal Energy Management System for Islanded Microgrids Based on Multiperiod Artificial Bee Colony Combined With Markov Chain*  
IEEE Systems Journal, 2017. Relevant to microgrid energy management, uncertainty, and optimization methodology.

### `Papers/Potentials and opportunities of solar PV and wind energy sources in Saudi Arabia_ Land suitability, techno-socio-economic feasibility, and future variability - ScienceDirect.mht`

**Title:** *Potentials and opportunities of solar PV and wind energy sources in Saudi Arabia: Land suitability, techno-socio-economic feasibility, and future variability*  
DOI visible in the saved page: `10.1016/j.rineng.2024.101785`. Relevant to Saudi renewable-energy context and resource feasibility.

## Internal research material

### `Literature_Notes/Paper Reviews.docx`

Team literature-review notes. Treat as secondary/internal notes and verify claims against the actual source papers before citing.

### `Working_Data/My Project.xlsx`

Internal project workbook. It is not categorized as an external academic source. Inspect its contents for the current task before relying on it as data/evidence.

### `Working_Data/Jeddah_Weather_PV/`

Contains the supplied Jeddah weather/PV research summary and complete 2024 hourly downloads from NASA POWER and Open-Meteo. Each CSV has 8,784 records because 2024 is a leap year. See the folder README for exact API queries, variables, units, time standards and modeling cautions.

### `Working_Data/Network_Data/EE499_Team16_5Bus_Network_Data.pdf`

Project reference for an 11 kV, 10 MVA radial five-bus development case based on Basabain and Ajour (2026). The published parameter table supplies line impedances but not individual bus-load magnitudes; project load allocations must not be presented as published measurements.

### `Working_Data/Network_Data/PJM_5Bus_Network_Data.xlsx`

MATPOWER/PJM five-bus test system based on Li and Bo (2010), with bus loads, five generators, six branches, limits and linear cost coefficients. This is a looped 230 kV transmission/OPF case on a 100 MVA base, not a radial distribution feeder; use it as a complementary reference rather than a direct replacement for the project's radial five-bus development case.

### `Working_Data/Network_Data/IEEE_33Bus_Network_Data.xlsx`

Baran and Wu IEEE 33-bus radial distribution-system data with 33 buses, 32 branches, 3,715 kW real load and 2,300 kVAr reactive load. Suitable as a larger validation case after documenting base conversions and any project-specific additions.
