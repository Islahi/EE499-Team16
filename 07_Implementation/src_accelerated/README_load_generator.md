# `load_generator.py` - synthetic hourly demand

This library creates hourly load profiles when measured demand is unavailable.
It is separate from the unchanged `data_loader.py`, which reads the final CSVs.
No supplier battery catalog is needed.

## Source and model

Source: Ali, A.; Shaaban, M. F.; Sindi, H. F. (2022), *Optimal Operational Planning
of RES and HESS in Smart Grids Considering Demand Response and DSTATCOM
Functionality of the Interfacing Inverters*, Sustainability 14, 13209.
[DOI](https://doi.org/10.3390/su142013209), CC BY 4.0.
Local original: `04_Research/Papers/sustainability-14-13209.pdf`.

Section 3 describes normal load probability distributions. Table 1 (pages 11-12)
gives 24 hourly load means and standard deviations in **percent**. Both arrays
are explicitly included in `SINDI_MEAN_PERCENT` / `SINDI_SD_PERCENT`, not invented
noise levels. The paper derived its statistics from three years of historical
data; using them here does NOT make our output measured local demand.

For every requested timestamp:

1. Map paper period 1 to 00:00, ..., period 24 to 23:00. This is an explicit
   project convention; change/justify it if the study uses another clock mapping.
2. Draw `x ~ Normal(mean_percent[hour], sd_percent[hour])` using a local seeded
   random generator. The global Python random state is not changed.
3. Set `m = max(0, x) / 100`. Report the count of negative samples clipped to zero.
4. Set `P_bus = m * P_base_bus`, `Q_bus = m * Q_base_bus`.

Multiple base-load devices at one bus are summed. Every bus uses the **same**
hourly multiplier: bus proportions and base power factors stay unchanged.
This is full shared-bus correlation, not a claim that real bus loads behave
identically. Independent hourly draws have no temporal/weekday/seasonal model.
Do not cap the multiplier at 1: network base demand is a reference, not an
enforced physical maximum. Do not add base demand again in simulation.

Zero base P/Q loads remain zero. Missing base loads are rejected. Q-only base
loads require a separate model and are rejected for compatibility with the
later uncertainty module's Q/P treatment.

## Run and change variables

From the repository root, prepare matching load/PV files together:

```powershell
python .\07_Implementation\examples\prepare_profiles.py --frequency-hz 60 --pv-bus 6 --pv-rating-kw 1000 --critical-irradiance 120 --hours 24 --simulate --output-dir .\07_Implementation\Results\prepared_check_01
```

Those frequency/PV parameters are illustrative study inputs, not measured source
values or a storage recommendation. Use a NEW directory each run. Omit
`--hours 24` for three calendar months, or specify `--months 3`. The default
start is 1 Jan 2024, so three months produces 2,184 hourly steps (leap year).
Add `--seed 43` for a different sample; repeat the same seed and inputs to repeat
the profile. `preparation.json` saves source hashes, times, the hourly statistics,
seed, sampling assumptions, PV ratings and clipping count. Keep it with the CSVs.

For the complete CLI variable list and source formats, see
[README_pv_model.md](README_pv_model.md).

### Use the library independently

```python
import pandas as pd
from src.load_generator import LoadGenerationConfig, generate_load_profile

times = pd.date_range("2024-01-01", "2024-04-01", inclusive="left", freq="h")
settings = LoadGenerationConfig(seed=42)
load_frame = generate_load_profile(network, times, settings)
load_frame.to_csv(new_load_path, index=False, mode="x")
```

Supply the actual loaded network. Its `Load.p_base_kw` and `q_base_kvar` values
set the scale; never replace them with a single arbitrary fixed feeder demand.
The output is long-format `timestamp,bus_id,p_kw,q_kvar`, one row per load bus
and timestamp, including explicit zero-load devices. Source network/timestamps
are not mutated. DataFrame `.attrs` contains provenance and the clipping count;
CSV alone does not retain attrs, so save a manifest as the example does.

To use other justified hourly statistics, supply your own **24-value**
`mean_percent` and `sd_percent` tuples to `LoadGenerationConfig`. Values must be
finite, nonnegative percentages, with a nonnegative integer seed. Setting SD to
zero gives a deterministic hourly mean profile, useful for hand checks.

### Use measured profiles instead

Skip generation. Pair your imported load CSV with the generated PV CSV using
the existing interface:

```python
from src.data_loader import ProfileData

profiles = ProfileData(csv_load=measured_load_path, csv_pv=prepared_pv_path)
```

Both files need the same continuous hourly timestamps, known network bus IDs,
one row per required bus/hour, and `timestamp,bus_id,p_kw,q_kvar` columns. Do
not combine synthetic and measured demand by addition. Missing-Q preprocessing
needs a documented rule; the unchanged loader expects the Q column.

## What this does NOT implement

- It does not reproduce the paper's full probability-state, wind, demand-response
  or nested optimization model. It adapts its hourly normal statistics for
  sampling synthetic time series.
- Three months from a repeated 24-hour statistical pattern is not three months
  of measured seasonal variation.
- It does not replace `uncertainty.py`. Generated data can serve as synthetic
  history for a software check, but ARIMA fitted to invented data does not
  establish real-world forecasting skill or independent statistical validation.
- It does not choose battery bounds, technology, efficiencies or prices.

## Tests

```powershell
python -m unittest discover -s .\07_Implementation\tests -p test_load_generator.py -v
```

Checks cover P/Q hand calculations, 24-hour mapping, aggregation, same/different
seeds, shared scaling, clipping, values over base load, invalid inputs,
non-mutation, leap-day coverage and seeded sample mean/SD plausibility.
