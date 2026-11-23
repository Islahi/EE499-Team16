# Historical controller comparisons

These scripts accompanied earlier fixed-fleet and single-battery studies. Each
comparison relies on the controller options and inputs from its release. For
reproduction, see the [release notes](../../Release_Notes/) and use the source
snapshot for that comparison if the current solver's options differ.

| Script | Comparison |
| --- | --- |
| [COMPARE_V10_V11_CONTROL.py](COMPARE_V10_V11_CONTROL.py) | V10 and V11 dispatch |
| [COMPARE_V11_V12_CONTROL.py](COMPARE_V11_V12_CONTROL.py) | V11 and V12 dispatch |
| [COMPARE_V12_V13_OPF.py](COMPARE_V12_V13_OPF.py) | V12 dispatch and V13 OPF |
| [benchmark_single_bess.py](benchmark_single_bess.py) | Saved single-battery run replay and timing |

From `07_Implementation`, use module invocation so Python can import the
application package. For example, `python -m Validation.Controller_Comparisons.COMPARE_V12_V13_OPF --help`
lists the required input folder and available settings.
