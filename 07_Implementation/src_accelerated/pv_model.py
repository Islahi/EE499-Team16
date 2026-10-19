"""Prepare hourly PV power from irradiance. See README_pv_model.md for limits."""
from dataclasses import dataclass
from math import isfinite
from numbers import Real
from pathlib import Path

import pandas as pd

from .network_model import NetworkModel


def _nonnegative(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")


@dataclass(frozen=True)
class PVModelConfig:
    critical_irradiance_w_m2: float
    standard_irradiance_w_m2: float = 1000.0

    def __post_init__(self):
        _nonnegative(self.critical_irradiance_w_m2, "critical_irradiance_w_m2")
        _nonnegative(self.standard_irradiance_w_m2, "standard_irradiance_w_m2")
        if not 0 < self.critical_irradiance_w_m2 < self.standard_irradiance_w_m2:
            raise ValueError("Irradiance thresholds must satisfy 0 < critical < standard")


def irradiance_to_power(irradiance_w_m2: float, rated_power_kw: float,
                        config: PVModelConfig) -> float:
    """Term 1 piecewise model; saturation starts at standard, not critical, irradiance."""
    if not isinstance(config, PVModelConfig):
        raise TypeError("Use PVModelConfig for the irradiance thresholds")
    _nonnegative(irradiance_w_m2, "irradiance_w_m2")
    _nonnegative(rated_power_kw, "rated_power_kw")
    critical = config.critical_irradiance_w_m2
    standard = config.standard_irradiance_w_m2
    if irradiance_w_m2 < critical:
        factor = (irradiance_w_m2 / standard) * (irradiance_w_m2 / critical)
    elif irradiance_w_m2 < standard:
        factor = irradiance_w_m2 / standard
    else:
        factor = 1.0
    return rated_power_kw * factor


def _hourly_times(values):
    try:
        times = pd.DatetimeIndex(pd.to_datetime(values, errors="raise", format="ISO8601"))
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError("Irradiance timestamps must be valid datetimes") from error
    if len(times) < 2 or times.hasnans or times.tz is not None:
        raise ValueError("Use at least two timestamps in one explicit, timezone-naive source clock")
    if not times.is_unique or not times.is_monotonic_increasing:
        raise ValueError("Irradiance timestamps must be unique and increasing")
    if any(times[i] - times[i - 1] != pd.Timedelta(hours=1) for i in range(1, len(times))):
        raise ValueError("Irradiance timestamps must be continuous and hourly")
    return times


def _validated_irradiance(frame):
    required = {"timestamp", "irradiance_w_m2"}
    if not isinstance(frame, pd.DataFrame) or not required.issubset(frame.columns):
        raise ValueError("Irradiance data needs timestamp and irradiance_w_m2 columns")
    times = _hourly_times(frame["timestamp"])
    try:
        values = pd.to_numeric(frame["irradiance_w_m2"], errors="raise")
    except (ValueError, TypeError) as error:
        raise ValueError("Irradiance values must be numeric") from error
    for value in values:
        _nonnegative(value, "irradiance_w_m2 (missing values and -999 are not allowed)")
    return pd.DataFrame({"timestamp": times, "irradiance_w_m2": values.to_numpy(dtype=float)})


def _read_provider_csv(path, header_prefix):
    # Providers put metadata above the actual CSV table; do not hard-code a row count.
    with Path(path).open(encoding="utf-8-sig", newline="") as source_file:
        for index, line in enumerate(source_file):
            if line.strip().startswith(header_prefix):
                return pd.read_csv(path, skiprows=index, encoding="utf-8-sig")
    raise ValueError(f"Cannot find the expected CSV header: {header_prefix}")


def read_irradiance(path: str | Path, *, source: str) -> pd.DataFrame:
    """Read prepared W/m², Open-Meteo mean W/m², or NASA hourly Wh/m² data."""
    if source == "prepared":
        frame = pd.read_csv(path, encoding="utf-8-sig")
    elif source == "open_meteo":
        table = _read_provider_csv(path, "time,")
        radiation_column = "shortwave_radiation (W/m²)"
        if radiation_column not in table:
            raise ValueError(f"Open-Meteo CSV needs {radiation_column}")
        frame = table.rename(columns={"time": "timestamp", radiation_column: "irradiance_w_m2"})
    elif source == "nasa_power":
        table = _read_provider_csv(path, "YEAR,MO,DY,HR,")
        required = {"YEAR", "MO", "DY", "HR", "ALLSKY_SFC_SW_DWN"}
        if not required.issubset(table.columns):
            raise ValueError("NASA CSV needs YEAR, MO, DY, HR and ALLSKY_SFC_SW_DWN")
        components = {}
        for column, name in (("YEAR", "year"), ("MO", "month"), ("DY", "day"), ("HR", "hour")):
            values = pd.to_numeric(table[column], errors="raise")
            if any(not isfinite(v) or v != int(v) for v in values):
                raise ValueError(f"NASA {column} values must be finite integers")
            if column == "HR" and any(v < 0 or v > 23 for v in values):
                raise ValueError("NASA HR must be between 0 and 23")
            components[name] = values
        times = pd.to_datetime(pd.DataFrame(components), errors="raise")
        # Energy density for a ONE-hour interval / 1 h = mean power density.
        radiation = pd.to_numeric(table["ALLSKY_SFC_SW_DWN"], errors="raise") / 1.0
        frame = pd.DataFrame({"timestamp": times, "irradiance_w_m2": radiation})
    else:
        raise ValueError("source must be prepared, open_meteo or nasa_power")
    result = _validated_irradiance(frame)
    result.attrs["source"] = source
    result.attrs["radiation_basis"] = "GHI resource proxy; no plane-of-array conversion"
    return result


def make_pv_profile(network: NetworkModel, irradiance: pd.DataFrame,
                    config: PVModelConfig) -> pd.DataFrame:
    """Return long-format absolute kW/kvar rows without changing the network."""
    network.validate()
    if not isinstance(config, PVModelConfig):
        raise TypeError("Use PVModelConfig")
    weather = _validated_irradiance(irradiance)
    ratings = {}
    for unit in network.pv_units:
        ratings[unit.bus_id] = ratings.get(unit.bus_id, 0.0) + unit.p_rated_kw
    if not ratings:
        # The unchanged ProfileData reader still needs a timestamped PV table.
        ratings[network.slack_bus_id()] = 0.0
    for rating in ratings.values():
        _nonnegative(rating, "Aggregated PV rating")
    rows = []
    for timestamp, radiation in weather.itertuples(index=False, name=None):
        for bus_id, rating in sorted(ratings.items()):
            power = irradiance_to_power(radiation, rating, config)
            rows.append((timestamp, bus_id, power, 0.0))
    result = pd.DataFrame(rows, columns=["timestamp", "bus_id", "p_kw", "q_kvar"])
    result.attrs["model"] = "Term 1 piecewise PV, corrected saturation at standard irradiance"
    result.attrs["assumptions"] = "Shared irradiance; unity PF; no temperature, tilt or inverter losses"
    return result
