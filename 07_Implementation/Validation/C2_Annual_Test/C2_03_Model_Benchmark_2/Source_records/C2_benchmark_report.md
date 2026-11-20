# C2 — full-year benchmark status and comparison

These results compare full-year forecasts generated once from historical data. The post-hoc test-year ranking is for evaluation, not production model selection.

Positive Bias = actual minus predicted: systematic underprediction.

MASE denominator is the training-only same-hour-previous-week MAE.

Models unable to fit a long season are marked SKIPPED_UNSUPPORTED; failures remain visible.

## Job status

status
OK                     245
SKIPPED_UNSUPPORTED    175
FAILED                  21

## LOAD — best held-out RMSE by dataset

- **A_GoiEner_Total_Load**: AutoETS / weekly: RMSE 437.702 kW, MAE 333.584 kW, WAPE 11.54%, MASE 1.903, Bias -115.707 kW, fit + predict 71.23 s
- **B_GoiEner_Distributed_15Bus**: AutoMFLES / daily_weekly_monthly_yearly: RMSE 224.201 kW, MAE 153.531 kW, WAPE 11.59%, MASE 1.112, Bias +40.439 kW, fit + predict 173.27 s

## PV — best held-out RMSE by dataset

- **PV_040d42N_003d70W**: SeasonalNaive / yearly_365d: RMSE 53.544 kW, MAE 24.242 kW, WAPE 25.13%, MASE 1.082, Bias +3.036 kW, fit + predict 0.00 s
- **PV_042d81N_001d65W**: SeasonalNaive / yearly_365d: RMSE 52.397 kW, MAE 25.378 kW, WAPE 29.08%, MASE 1.066, Bias +2.760 kW, fit + predict 0.00 s
- **PV_042d85N_002d67W**: AutoTBATS / daily_weekly_monthly_yearly: RMSE 56.293 kW, MAE 31.843 kW, WAPE 38.11%, MASE 1.193, Bias +5.853 kW, fit + predict 233.43 s
- **PV_043d26N_002d94W**: AutoMFLES / daily_weekly_monthly_yearly: RMSE 54.397 kW, MAE 30.900 kW, WAPE 40.60%, MASE 1.114, Bias +3.234 kW, fit + predict 140.13 s
- **PV_043d32N_001d98W**: AutoTBATS / daily_weekly_monthly_yearly: RMSE 54.591 kW, MAE 31.178 kW, WAPE 40.69%, MASE 1.122, Bias +2.930 kW, fit + predict 108.42 s

