# V15.6 cleanup · controls and changes

## Follow-up desktop refinement

| Change | Result |
|---|---|
| Demand browsing | The folder and CSV/XLSX buttons are enabled as soon as Load Data opens. Selecting a parent of several GoiEner cases opens the case picker. The dialog is shorter and retains its three tabs. |
| Main window | Removed the Study menu and the subtitle. Open setup and Save setup appear in the header. |
| Settings | Population, maximum generations and parallel workers are visible on Optimization. The operating defaults are a 24-hour daily MILP schedule, PF ≥ 0.95, efficiencies of 95% per direction and inverter capability derived from rated power. The Methodology pop-up and button were removed. |
| Results | The effective engineering and optimizer settings remain in session and run metadata. The new battery audit export is `battery_daily_audit.csv`. |
| Logs | The application log records levels and worker tracebacks. Simulation logs use periodic counters, and report generation reports a separate outcome. |

The earlier cleanup is recorded below as release history.

The historical approved UI review is included with the source. The current [per-widget inventory](UI_CONTROL_AUDIT.csv) records each Designer control retained, removed, added or handled internally. Dynamic desktop actions are summarized here.

| Workflow | Current behavior |
|---|---|
| Main window | Load Data, Forecast, Simulation, Optimize, Study interval, Settings, network display, logs and Dashboard remain in place. Stop run appears during a numerical job. |
| Load data | Choose a prepared folder or hourly file. The source determines the timeline. Workbook format, declared clocks, site coordinates and PV reference capacity are taken from the applicable source. |
| Manual simulation | A manual battery uses its own non-slack bus, kW and kWh. An optimized fleet uses the selected design from the GA. The network labels every selected installation. |
| Optimization | Joint GA is the routine desktop method. The finite search catalogs, eligible non-slack buses, nameplate duration bounds and maximum units remain editable. |
| Internal settings | The desktop policy supplies population, generations, crossover, mutation, stall threshold, seed and worker count. The 15- and 33-bus defaults remain at 12 chromosomes and 20 maximum generations. Smaller and larger bus sets use a bounded population of 8–24. Annual finalist verification uses one worker at a time with up to three fallbacks in order of rank. Effective settings are recorded in the run. |
| Economics | The active CAPEX fields appear together on the Economics page in USD/kWh and USD/kVA. The methodology summary displays the current study inputs, PF, SOC policy, efficiencies and calculated CRF. |
| Results | Annual metrics use the battery state structure returned by strict Sindi. Numerical CSVs are committed separately from optional HTML rendering and manifest registration. A recoverable write error retries the export without rerunning the numerical task. |
| Dashboard | Manual, optimized and no-storage reports are labeled according to the actual run. The Charts view gives time-dependent feeder readings when saved data is available. The comparison view opens saved dashboard HTML files from disk. |

Stop is cooperative. During a MILP solve or parallel evaluation it takes effect at the next numerical checkpoint. When the numerical result enters its commit phase, the save completes as a unit. New desktop runs created from a saved legacy dispatch setup require a tariff review as they use strict Sindi. Previously saved result records remain readable.
