# GA correction: conventional two-offspring crossover and independent GA controls

- Replaced the previous one-child variant with standard **single-point two-offspring crossover**: one decision per parent pair, a single gene cut, and two complementary children.
- When crossover is skipped, the algorithm retains *both* parents as children (before independent mutations).
- Retained tournament selection, per-gene mutation, elitism, caching, the candidate catalogs, and the shared GA/GWO objective and constraint evaluator.
- Children are truncated to the configured population size if the final pairing exceeds the remaining slots (odd population / elitism).
- Added **GA population size (default 12)** and **GA generations (default 20)** to the existing Search algorithm group. GWO population and iterations remain separate.
- Both algorithms share the existing random-seed field, now labeled **Random seed (GA and GWO)**. GA's population and generations no longer silently inherit GWO values.
- `run_study` uses independent GA population/generation settings, with fallback to old GWO keys for older programmatic callers.
- All other features, forecasting library, and original application style remain unchanged.

## Run

On Windows: `start_windows.bat` or `py -m src_accelerated.ui` after installing `requirements.txt`.

Test: `py -m pytest -q tests`

Real `StatsForecast` fit and interactive PySide6 Windows UI were not independently verified by these algorithmic regression tests.
