"""C2 year-ahead comparison settings. All models share ONE untouched 8,784-hour test year.
https://github.com/Islahi/EE499-Team16.git
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'C2_model_benchmark_results'
TRAIN_START = '2017-06-01 00:00:00'
TEST_START = '2019-03-01 00:00:00'
TEST_END = '2020-02-29 23:00:00'

MODELS = (
    'AutoARIMA', 'AutoETS', 'AutoCES', 'AutoTheta', 'MSTL',
    'AutoTBATS', 'AutoMFLES', 'SeasonalNaive', 'HoltWinters',
)
# Hours per season; monthly and yearly are approximations for hourly fixed-period models.
SEASONALITIES = {
    'daily': (24,),
    'weekly': (168,),
    'monthly_30d': (720,),
    'yearly_365d': (8760,),
    # Additional multi-season configurations are meaningful only for these 3 models.
    'daily_weekly': (24, 168),
    'daily_weekly_monthly': (24, 168, 720),
    'daily_weekly_monthly_yearly': (24, 168, 720, 8760),
}
MULTI_SEASON_MODELS = ('MSTL', 'AutoTBATS', 'AutoMFLES')

RUN_GOIENER_TOTAL = True
RUN_DISTRIBUTED_15BUS = True
RUN_SOLAR_SITES = True
# A site's NASA GHI -> project-modelled PV electrical power at an illustrative 490kW site.
PV_RATED_KW = 490.0
PV_BUS_ID = 13
PV_CRITICAL_IRRADIANCE_W_M2 = 150.0
PV_STANDARD_IRRADIANCE_W_M2 = 1000.0
# Solar geometry removes nonphysical night generation from every model equally.
FORCE_NIGHT_ZERO = True

# Timing includes each estimator's fit and predict separately; it does not include data reading.
# Run smaller subsets first with command-line options before attempting all 9 models x 7 seasons x 7 datasets.
AUTOARIMA_MAX_P = 2
AUTOARIMA_MAX_Q = 2
AUTOARIMA_MAX_SEASONAL_P = 1
AUTOARIMA_MAX_SEASONAL_Q = 1
AUTOARIMA_NMODELS = 20
AUTOMFLES_VALIDATION_HOURS = 336   # two weeks in the training period, not test year
AUTOMFLES_N_WINDOWS = 2
# With less than 2 full yearly cycles, some methods cannot fit a genuine yearly seasonality.
# For AutoTBATS and AutoMFLES, one-cycle Fourier fitting is attempted and explicitly flagged.
ALLOW_SINGLE_CYCLE_FOURIER_YEARLY = True
# Set True to retry known-insufficient annual variants anyway (can be extremely slow).
TRY_INSUFFICIENT_YEARLY_MODELS = False

DATA_LOAD = ROOT / 'C2_annual_results' / 'prepared_inputs'
DATA_SOLAR = ROOT / 'Data' / 'NASA_POWER'
