# `pv_model.py` - irradiance to PV power

This is an input-preparation library, not a power-flow solver. It reads your
irradiance data and makes the PV power CSV consumed by the existing
`data_loader.py` and `simulation.py`. The original weather files are never edited.

## Run from the repository root

```powershell
python .\07_Implementation\examples\prepare_profiles.py --frequency-hz 60 --pv-bus 6 --pv-rating-kw 1000 --critical-irradiance 120 --hours 24 --simulate --output-dir .\07_Implementation\Results\prepared_check_01
```

This is an illustrative integration check, NOT a recommended PV size/location.
It uses the supplied IEEE33 workbook, Open-Meteo weather and synthetic load.
60 Hz is an explicit study input. The workbook does not provide frequency/PV.
The 120 W/m² critical value is a literature example (Sindi co-authored paper,
Table 2), not a verified manufacturer parameter for a chosen panel.
The numeric inputs are visible command arguments, not fixed engineering values.

Remove `--hours 24` to prepare **three calendar months**, or use `--months 3`.
January-March 2024 contains **2,184 hours**, not 2,160 (2024 is a leap year).
`--simulate` is optional; without it, only the profiles and manifest are produced.
Use a NEW output directory on every run. Existing results are not overwritten.

Outputs:

- `pv_profile.csv`: `timestamp,bus_id,p_kw,q_kvar`
- `load_profile.csv`: synthetic demand from `load_generator.py`
- `preparation.json`: inputs, source hashes, interval, PV devices, model,
  seed, all 24 hourly load statistics and limitations
- `simulation/`: optional no-BESS simulation summary/CSVs

## Variables to fill or change

| Argument | Meaning |
|---|---|
| `--network` | Supported `.xlsx`; defaults to the repository IEEE33 workbook |
| `--frequency-hz` | Required study frequency; no inferred source frequency |
| `--source` | `open_meteo` (default), `nasa_power` or `prepared` |
| `--irradiance-file` | Defaults to the matching repository provider file; required for `prepared` |
| `--start` | Inclusive timestamp in source clock; default `2024-01-01T00:00:00` |
| `--hours` / `--months` | Mutually exclusive duration; default three calendar months |
| `--pv-bus` | Required existing bus for an additional study PV installation |
| `--pv-rating-kw` | Required total installed array rating in kW, NOT panel count |
| `--critical-irradiance` | Required low-light threshold Rc in W/m² |
| `--standard-irradiance` | Standard irradiance Rstd, default 1000 W/m² |
| `--seed` | Synthetic load seed; default 42 |
| `--output-dir` | Required NEW directory |

The example adds the requested PV installation to any devices already in the
network. The manifest lists ALL units so this is not mistaken for a replacement.
For multiple installations, use the Python API and supply explicit `PVUnit`s.

To use the other weather source, add `--source nasa_power`. Do not average the
providers or combine their rows: they have different source/time definitions.
No supplier battery data is needed to run this preparation step.

## Equation and units

The Term 1 report, page 24, defines a three-region output model. Implemented in kW:

```text
P = P_rated * s² / (Rstd * Rc)    0 <= s < Rc
P = P_rated * s / Rstd           Rc <= s < Rstd
P = P_rated                     s >= Rstd
```

The report equation prints `s >= Rc` for its last condition, overlapping the
middle branch. Its prose says `s >= Rstd`; this implementation explicitly follows
that prose. Do not edit the frozen submitted report. The original cited article
is [Karve et al. (2025)](https://doi.org/10.3390/en18092340); its equation could not
be independently retrieved during this implementation. The correction is a
documented interpretation, not a claimed comparison with that source.

PV rating is already TOTAL kW, so do not multiply by panel count again. The
function returns power, not kWh. Hourly energy is the power times one hour.
Multiple PV units at the same bus are summed before making one row per hour/bus.
Reactive injection is zero (unity power factor). No PV units means explicit zero
rows at the slack, keeping no-PV cases compatible with the unchanged CSV loader.

### Accepted source formats

- `prepared`: CSV columns `timestamp,irradiance_w_m2`, for example ISO timestamp
  `2024-01-01T00:00:00` and numeric `0`. Extra columns are ignored.
- `open_meteo`: the supplied export, with metadata then `time` and
  `shortwave_radiation (W/m²)`. Radiation is already hourly mean W/m².
- `nasa_power`: the supplied header plus YEAR/MO/DY/HR and
  `ALLSKY_SFC_SW_DWN`. Radiation is Wh/m² over each one-hour interval: divide by
  one hour for mean W/m², so the numbers happen to be equal. This is NOT a rule
  for daily data or other time steps.

Provider headers are found by name, not a fixed number of metadata lines.
Require >=2 increasing, unique, continuous hourly timestamps. NaN, missing,
negative, infinity and NASA `-999` are rejected, not interpolated or replaced.
Timezone-aware inputs are rejected: prepare one documented clock first. NASA
LST is preserved; no conversion or claim of equivalence to civil time is made.

## Public functions

```python
from src.pv_model import PVModelConfig, read_irradiance, make_pv_profile

weather = read_irradiance(weather_path, source="open_meteo")
config = PVModelConfig(critical_irradiance_w_m2=120)
pv_frame = make_pv_profile(network, weather, config)
# Save to a NEW path; can pair with imported or generated load CSV.
pv_frame.to_csv(new_pv_path, index=False, mode="x")
```

`irradiance_to_power(s, rated_power_kw, config)` is independently callable for a
single value. It validates finite nonnegative inputs and `0 < Rc < Rstd`.

## Limits and tests

GHI is used as a **resource proxy** for the simple report model. It is not
plane-of-array irradiance for a specified tilted array. Temperature, shading,
orientation, inverter/AC losses and detailed electrical panel behavior are NOT
modelled. The rated cap is this prototype's assumption, not a universal physical
limit on module output. One weather series is shared by all PV buses.

```powershell
python -m unittest discover -s .\07_Implementation\tests -p test_pv_model.py -v
```

Tests include hand calculations, threshold continuity, invalid data, both actual
8,784-hour provider files, aggregation/non-mutation and loader/simulator use.
These verify implementation; they do not validate actual PV output measurements.

See [the load-generation README](README_load_generator.md) for the paired demand
file and how to substitute an imported load profile.
