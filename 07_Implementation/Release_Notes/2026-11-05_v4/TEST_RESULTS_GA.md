# Verification — conventional GA update

Command: `python -m pytest -q tests`

Result: **22 passed, 1 skipped**.

- Single-point paired offspring at both possible crossover points.
- No-crossover copies both parents.
- Whole-pair probability used only once.
- Odd and even population sizes (3, 4, 5, 6) retain exact configured numbers.
- GA independent population and generation settings tested through the end-to-end workflow.
- Source compiled successfully and Qt Designer XML parsed.
- `PySide6` and the real `statsforecast` package are unavailable in the present environment, so interactive Windows GUI and real-library forecasting remain unverified here.
