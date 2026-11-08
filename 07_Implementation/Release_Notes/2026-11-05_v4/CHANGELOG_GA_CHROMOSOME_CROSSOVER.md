> **Historical revision — superseded by `CHANGELOG_STANDARD_GA_TWO_OFFSPRING.md`. The current source generates two complementary offspring, not one.**

# GA single-decision crossover update

The user selected a simple standard crossover mechanism. The algorithm now makes **one crossover decision per parent pair / child**, at the whole-chromosome level, rather than testing crossover separately on each of the three genes.

- With probability `crossover_rate` (default 0.80), choose a random crossover point after the first or second gene, and concatenate Parent A's prefix with Parent B's suffix.
- Otherwise copy Parent A without crossover.
- Each of the three genes still has an independent `mutation_rate` chance (default 0.12) of being replaced by a valid catalog item.
- Produce one child per selected parent pair; preserve tournament selection, elitism, evaluation caching, annual economics and GWO.
- No changes to UI, forecasting, economics, power flow or battery policy.

Tests: `python -m pytest -q tests` — 17 passed, 1 skipped (optional StatsForecast installation test). PySide6/real StatsForecast runtime not verified in this environment.
