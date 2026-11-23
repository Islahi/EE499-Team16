# Production application modules

Install and launch using [the application instructions](../../README.md).
The Qt Designer forms remain under `assets/`; `app.pyw` and `python -m src.ui`
launch the same application.

| Module | Responsibility |
|---|---|
| `network_model.py`, `network_loader.py` | Validate and import balanced, single-voltage radial electrical networks |
| `fbs.py` | Mandatory Numba current-summation FBS; preserve bus injections and result units |
| `distributed_dataset.py` | Validate GoiEner folders, explicit sector assignments, metadata and PV placeholders |
| `data_loader.py` | Aligned hourly bus profiles and independent interval slices |
| `forecast_models.py`, `forecasting.py` | Archived calendar construction; fixed sector-sum winners and common modeled-PV XGBoost |
| `solar_source.py`, `pv_model.py` | Explicit site/clock, historical provider retrieval and irradiance-to-electrical-power conversion |
| `bess.py`, `simulation.py` | SOC/efficiencies, battery state, device controls and physical feasibility |
| `daily_milp_dispatch.py`, `joint_opf.py` | Multi-battery dispatch and coordinated P/Q control |
| `fleet_ga_optimizer.py`, `sequential_multi.py` | Joint fleet search and sequential planning |
| `model_information.py`, `dashboard.py` | Current and saved study methodology and HTML result reports |
| `metrics.py`, `optimizer.py` | Validated annual monetary objective shared by GWO, GA and exhaustive evaluation |
| `results.py`, `ui_presentation.py` | Technical/annual-cost summaries, CSV exports and no-BESS comparison |
| `study_session.py` | Source snapshots/provenance, read-only history and new-ID input migration |
| `ui.py`, `ui_workflow.py` | Existing dialogs, worker jobs, source/window selection and simulation orchestration |
| `network_diagram.py`, `network_layout.py` | Automatic radial diagrams and result overlays |

The independent validation implementations and historical development documents
are reference material. They do not add executable production solver or forecasting options.
