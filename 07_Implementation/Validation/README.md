# Validation kits and evidence

Run each kit from its own directory using its documented setup. The bundled
solver copies, test inputs, and recorded results preserve the versions used in
each experiment. Use the [active app test instructions](../README.md#verify-and-maintain)
to check the current desktop application.

| Kit | Scope | Start here |
| --- | --- | --- |
| C1 nominal feeder check | Static FBS across the supplied radial network workbooks | [C1 validation](C1_Validation_Test/README.md) |
| C1 solver benchmark | Accuracy and timing comparison against independent solvers | [C1 benchmark](EE499_C1_Benchmark/README.md) |
| C2 fixed-cohort benchmark | Ranked 2021 forecasts for GoiEner load and Bilbao PV | [Fixed cohort](C2_FixedCohort_Ranked22_Updated/START_HERE.md) |
| C2 sector aggregation | 15-bus comparison of forecasting sector totals versus summing individual bus forecasts | [Sector aggregation](C2_Final_Test_Sector_Aggregation_Testbench/README.md) |
| C2 earlier annual experiments | Preserved year-ahead inputs, runners, and results | [Annual test](C2_Annual_Test/README.md), [variant 1](C2_Annual_Test_1/README.md), [variant 2](C2_Annual_Test_2/README.md), [nine-model 2021 benchmark](C2_FullHistory_2021/START_HERE.md) |
| C5 all-bus sweep | January 2019 sizing and placement on 15-bus System 1 | [All-bus sweep](C5_System1_AllBuses_Test/README.md) |
| C5 extreme stress test | Synthetic constrained-load and PV test on the same feeder | [Stress test](C5_Extreme_15Bus/README.md) |
| Historical controller comparisons | Fixed-battery comparisons and single-battery replay scripts | [Controller comparisons](Controller_Comparisons/README.md) |

- [Program validation process](MISC/EE499_BESS_Program_Validation_Process.pdf)
- [C1 and C2 integration approach](EE499_Approach_A_Integration_Plan.md)
- [FBS Numba integration decision](EE499_FBS_Numba_Integration_Decision_and_Plan.md)
- [October implementation and validation audit](MISC/2026-10-24_Accelerated_Task_Audit.md)

The `GoiEner_15_Busses` and `GoiEner_Combined` folders hold prepared validation
inputs. Source download and preprocessing scripts are indexed in [Tools](../Tools/README.md).
