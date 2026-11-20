# C2 full-history, annual 2021 benchmark

One forecast of 8,760 hours for 2021 from 2017-06-01 through 2020-12-31 training.
Results are after nonnegative and (for PV) physical night/rating constraints. Warning-containing results remain visible.
Model fits were normalized to mean≈1; AutoTBATS used Box-Cox=False and ARMA errors=False for stability.
NASA PV output is modeled, GoiEner sector load profiles are per-customer or variable-cohort totals, and the 15-bus profile is constructed.
All results are exploratory test-year comparisons. Do not choose a model on this test year then claim independent accuracy.

## Status counts

status
SKIPPED_UNSUPPORTED    162
OK                     118
OK_WITH_WARNINGS        56
MEMORY_LIMIT            42

## LOAD best recorded runs (lowest RMSE)

- Distributed_15Bus_Load: MSTL / daily_weekly_monthly_yearly: RMSE=310.708 kW; MAE=236.380; WAPE=14.88%; fit+forecast=449.17s; warnings=0.
- GoiEner_Commercial_PerMeter: MSTL / daily_weekly_monthly_yearly: RMSE=0.265 kW/customer; MAE=0.180; WAPE=15.43%; fit+forecast=451.95s; warnings=0.
- GoiEner_Manufacturing_PerMeter: MSTL / daily_weekly_monthly_yearly: RMSE=0.936 kW/customer; MAE=0.735; WAPE=19.12%; fit+forecast=461.92s; warnings=0.
- GoiEner_Residential_PerMeter: SeasonalNaive / yearly_365d: RMSE=0.043 kW/customer; MAE=0.031; WAPE=10.44%; fit+forecast=0.00s; warnings=0.
- GoiEner_ThreeSector_SummedMeters: AutoTheta / weekly: RMSE=1003.007 kW; MAE=785.187; WAPE=13.51%; fit+forecast=160.97s; warnings=0.

## PV best recorded runs (lowest RMSE)

- Bilbao_Modelled_PV: SeasonalNaive / yearly_365d: RMSE=60.357 kW; MAE=30.168; WAPE=41.45%; fit+forecast=0.00s; warnings=0.

