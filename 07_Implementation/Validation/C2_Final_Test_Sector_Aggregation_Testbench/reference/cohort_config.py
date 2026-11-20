"""Benchmark configuration; all runs are 8760-hour single-shot holdout forecasts."""
from pathlib import Path
EXPERIMENT_VERSION='C2_FIXED_COHORT_RANKED22_V2'
ROOT=Path(__file__).resolve().parent
DATA=ROOT/'prepared_cases'
OUTPUT=ROOT/'results'
CLASSIC=('AutoARIMA','AutoETS','AutoCES','AutoTheta','MSTL','AutoTBATS','AutoMFLES','SeasonalNaive','HoltWinters')
EXTRAS=('FourierOLS','CalendarRidge','Prophet','LightGBM','XGBoost','FourierSARIMAX')
NEURAL=('AutoNHITS','AutoNBEATSx')
MODELS=CLASSIC+('Naive','YearAgoCalendarNaive')+EXTRAS+NEURAL
SEASONALITIES={
 'daily':(24,), 'weekly':(168,), 'monthly_30d':(720,), 'yearly_365d':(8760,),
 'daily_weekly':(24,168),'daily_weekly_monthly':(24,168,720),
 'daily_weekly_monthly_yearly':(24,168,720,8760)
}
MULTI_SEASON_MODELS=('MSTL','AutoTBATS','AutoMFLES')+EXTRAS+NEURAL
TBATS_USE_BOXCOX=False
TBATS_USE_ARMA_ERRORS=False
NORMALIZE_INPUTS=True
AUTOARIMA_MAX_P=2
AUTOARIMA_MAX_Q=2
AUTOARIMA_MAX_SEASONAL_P=1
AUTOARIMA_MAX_SEASONAL_Q=1
AUTOARIMA_NMODELS=20
AUTOMFLES_VALIDATION_HOURS=336
AUTOMFLES_N_WINDOWS=2
UNREALISTIC_MAX_MULTIPLE_OF_TRAIN_PEAK=100
DEFAULT_JOB_TIMEOUT_SECONDS=3600
DEFAULT_PROCESS_MEMORY_GB=8
VALIDATION_DAYS=120
