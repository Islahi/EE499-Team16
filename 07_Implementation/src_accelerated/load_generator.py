"""Synthetic demand using Ali/Shaaban/Sindi (2022), Table 1. Not measured load."""
from dataclasses import dataclass
from math import isfinite
from numbers import Real
from random import Random

import pandas as pd

from .network_model import NetworkModel


# Table 1, pages 11-12, https://doi.org/10.3390/su142013209 (CC BY 4.0).
# The paper labels periods 1-24; this prototype maps them to clock hours 00-23.
SINDI_MEAN_PERCENT = (
    65.177, 62.018, 58.758, 57.756, 58.776, 62.223,
    70.783, 76.010, 78.115, 79.969, 81.174, 81.949,
    82.103, 81.037, 80.539, 80.640, 81.114, 81.093,
    81.050, 81.509, 80.661, 77.876, 73.689, 69.979,
)
SINDI_SD_PERCENT = (
    4.698, 4.410, 5.230, 4.220, 4.614, 6.212,
    9.278, 9.321, 8.115, 7.260, 6.852, 6.811,
    7.116, 7.444, 7.616, 7.944, 8.291, 8.775,
    8.558, 7.702, 6.040, 5.348, 5.373, 5.167,
)


@dataclass(frozen=True)
class LoadGenerationConfig:
    seed: int = 42
    mean_percent: tuple[float, ...] = SINDI_MEAN_PERCENT
    sd_percent: tuple[float, ...] = SINDI_SD_PERCENT

    def __post_init__(self):
        if not isinstance(self.seed, int) or isinstance(self.seed, bool) or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        for name in ("mean_percent", "sd_percent"):
            values = tuple(getattr(self, name))
            if len(values) != 24:
                raise ValueError(f"{name} must contain exactly 24 hourly values")
            for value in values:
                if (isinstance(value, bool) or not isinstance(value, Real)
                        or not isfinite(value) or value < 0):
                    raise ValueError(f"{name} must contain finite nonnegative percentages")
            object.__setattr__(self, name, values)


def generate_load_profile(network: NetworkModel, timestamps,
                          config: LoadGenerationConfig | None = None) -> pd.DataFrame:
    """Scale aggregated base P/Q with a shared, seeded hourly normal multiplier."""
    network.validate()
    settings = config if config is not None else LoadGenerationConfig()
    if not isinstance(settings, LoadGenerationConfig):
        raise TypeError("Use LoadGenerationConfig")
    try:
        times = pd.DatetimeIndex(pd.to_datetime(timestamps, errors="raise", format="ISO8601"))
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError("Load timestamps must be valid datetimes") from error
    if len(times) < 2 or times.hasnans or times.tz is not None:
        raise ValueError("Use at least two timezone-naive timestamps in a documented clock")
    if not times.is_unique or not times.is_monotonic_increasing:
        raise ValueError("Load timestamps must be unique and increasing")
    if any(times[i] - times[i - 1] != pd.Timedelta(hours=1) for i in range(1, len(times))):
        raise ValueError("Load timestamps must be continuous and hourly")
    if not network.loads:
        raise ValueError("Synthetic demand requires explicit network base loads")

    base_by_bus = {}
    for load in network.loads:
        if load.p_base_kw == 0 and load.q_base_kvar != 0:
            raise ValueError("Q-only base loads need a separate reactive model before generation")
        p_kw, q_kvar = base_by_bus.get(load.bus_id, (0.0, 0.0))
        base_by_bus[load.bus_id] = (p_kw + load.p_base_kw, q_kvar + load.q_base_kvar)
    if any(not isfinite(p) or not isfinite(q) for p, q in base_by_bus.values()):
        raise ValueError("Aggregated base demand must be finite")

    generator = Random(settings.seed)
    rows = []
    clipped_count = 0
    for timestamp in times:
        hour = timestamp.hour
        sample = generator.gauss(settings.mean_percent[hour], settings.sd_percent[hour])
        if not isfinite(sample):
            raise ValueError("Sampled load percentage is not finite; check mean/SD magnitudes")
        if sample < 0:
            clipped_count += 1
        multiplier = max(0.0, sample) / 100.0
        for bus_id, (p_base, q_base) in sorted(base_by_bus.items()):
            p_kw, q_kvar = p_base * multiplier, q_base * multiplier
            if not isfinite(p_kw) or not isfinite(q_kvar):
                raise ValueError("Generated demand overflow; check base loads and percentages")
            rows.append((timestamp, bus_id, p_kw, q_kvar))

    result = pd.DataFrame(rows, columns=["timestamp", "bus_id", "p_kw", "q_kvar"])
    result.attrs["source"] = "Synthetic; Ali, Shaaban and Sindi (2022), Table 1; DOI 10.3390/su142013209"
    result.attrs["seed"] = settings.seed
    result.attrs["negative_samples_clipped"] = clipped_count
    result.attrs["assumptions"] = "Shared bus multiplier; fixed base P/Q; independent hours; no seasonality"
    return result
