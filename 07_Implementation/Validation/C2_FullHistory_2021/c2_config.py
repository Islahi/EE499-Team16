"""Configuration for C2 full-history single-shot 2021 forecasting comparison.
Project: https://github.com/Islahi/EE499-Team16.git
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
OUTPUT = ROOT / 'results'
TRAIN_START = '2017-06-01 00:00:00'
TEST_START = '2021-01-01 00:00:00'
TEST_END = '2021-12-31 23:00:00'
MODELS = ('AutoARIMA','AutoETS','AutoCES','AutoTheta','MSTL','AutoTBATS',
          'AutoMFLES','SeasonalNaive','HoltWinters')
SEASONALITIES = {
 'daily':(24,), 'weekly':(168,), 'monthly_30d':(720,), 'yearly_365d':(8760,),
 'daily_weekly':(24,168), 'daily_weekly_monthly':(24,168,720),
 'daily_weekly_monthly_yearly':(24,168,720,8760),
}
MULTI_SEASON_MODELS = ('MSTL','AutoTBATS','AutoMFLES')
# AutoTBATS stability-oriented settings (configurable; DIFFERENT from automatic defaults).
TBATS_USE_BOXCOX = False
TBATS_USE_ARMA_ERRORS = False
# The model is fitted to y/mean(y) and forecasts are returned to original units.
NORMALIZE_INPUTS = True
AUTOARIMA_MAX_P, AUTOARIMA_MAX_Q = 2, 2
AUTOARIMA_MAX_SEASONAL_P, AUTOARIMA_MAX_SEASONAL_Q = 1, 1
AUTOARIMA_NMODELS = 20
AUTOMFLES_VALIDATION_HOURS = 336
AUTOMFLES_N_WINDOWS = 2
PV_RATED_KW = 490.0
FORCE_NIGHT_ZERO = True
# Mark extreme raw predictions invalid instead of allowing unrealistic values to dominate.
# No clipping of excessively HIGH load predictions is used.
UNREALISTIC_MAX_MULTIPLE_OF_TRAIN_PEAK = 100.0
# Memory limit applies to each child process, not whole computer. 0 means disabled.
DEFAULT_JOB_TIMEOUT_SECONDS = 3600
DEFAULT_PROCESS_MEMORY_GB = 8.0
