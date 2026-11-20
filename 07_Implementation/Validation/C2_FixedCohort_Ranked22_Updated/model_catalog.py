"""Auditable C2 forecast candidate selection.

The 22 retained configurations are exactly the top 20 *overall* from the
user's ordinal-priority ranking plus two specialist configurations. These are
model/seasonality pairs, not 22 distinct forecasting algorithms.
"""
from cohort_config import EXTRAS, NEURAL, SEASONALITIES

# Prior published overall rank. Preserve this order in all plans.
RANKED_TOP_20 = (
    ('MSTL', 'daily_weekly_monthly_yearly'),
    ('HoltWinters', 'weekly'),
    ('AutoTheta', 'weekly'),
    ('AutoTBATS', 'daily_weekly'),
    ('MSTL', 'weekly'),
    ('AutoTBATS', 'weekly'),
    ('AutoTheta', 'monthly_30d'),
    ('SeasonalNaive', 'weekly'),
    ('MSTL', 'daily'),
    ('SeasonalNaive', 'yearly_365d'),
    ('AutoARIMA', 'weekly'),
    ('AutoTBATS', 'daily'),
    ('AutoCES', 'weekly'),
    ('AutoTheta', 'daily'),
    ('AutoTBATS', 'daily_weekly_monthly'),
    ('MSTL', 'monthly_30d'),
    ('MSTL', 'daily_weekly_monthly'),
    ('AutoARIMA', 'daily'),
    ('MSTL', 'daily_weekly'),
    ('SeasonalNaive', 'monthly_30d'),
)
# Extra specialists from previous ranking (21 and 22):
SPECIALISTS = (
    ('AutoTBATS', 'daily_weekly_monthly_yearly'),
    ('AutoETS', 'weekly'),
)

# Essential controls (counted separately from the 22 retained choices).
BASELINES = (
    ('Naive', 'daily'),
    ('SeasonalNaive', 'daily'),
    ('YearAgoCalendarNaive', 'yearly_365d'),
)

# Every additional non-neural model performs training-only chronological tuning.
NEW_OPTIMIZED = tuple((name, season) for name in EXTRAS for season in SEASONALITIES)
# Neural models are experimental; their seasonality is learned, not controlled via
# fixed season_length. The label is for plan consistency only.
EXPERIMENTAL_NEURAL = tuple((name, 'daily_weekly_monthly_yearly') for name in NEURAL)

RANKED_22 = RANKED_TOP_20 + SPECIALISTS
assert len(RANKED_TOP_20) == 20
assert len(RANKED_22) == len(set(RANKED_22)) == 22
assert not set(BASELINES).intersection(set(RANKED_22))
assert len(NEW_OPTIMIZED) == len(EXTRAS) * len(SEASONALITIES)


def select_pairs(group='all', include_neural=False, suite='selected'):
    """Return unique (model, seasonality, source_group) triples in planned order."""
    candidates = []
    if group in ('all', 'legacy22'):
        candidates += [(model, season, 'ranked_top20') for model, season in RANKED_TOP_20]
        candidates += [(model, season, 'specialist') for model, season in SPECIALISTS]
    if group in ('all', 'baselines'):
        candidates += [(model, season, 'baseline') for model, season in BASELINES]
    if group in ('all', 'new'):
        candidates += [(model, season, 'new_optimized') for model, season in NEW_OPTIMIZED]
    if suite == 'all' and group == 'all':
        # Optional broader grid of classic families, never part of selected 22.
        from cohort_config import CLASSIC
        candidates += [(model, season, 'expanded_classic') for model in CLASSIC for season in SEASONALITIES]
    if include_neural and group in ('all', 'neural'):
        candidates += [(model, season, 'experimental_neural') for model, season in EXPERIMENTAL_NEURAL]

    dedup = {}
    for model, season, source in candidates:
        dedup.setdefault((model, season), (model, season, source))
    return list(dedup.values())
