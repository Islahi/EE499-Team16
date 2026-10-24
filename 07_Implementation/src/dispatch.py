"""Explicit, configurable dispatch requests; physical limits stay in simulation."""
from dataclasses import dataclass
from math import isfinite
from numbers import Real


@dataclass(frozen=True)
class NetLoadTargetPolicy:
    target_kw: float

    def __post_init__(self):
        if (isinstance(self.target_kw, bool) or not isinstance(self.target_kw, Real)
                or not isfinite(self.target_kw) or self.target_kw < 0):
            raise ValueError("Net-load target must be finite and nonnegative (kW)")

    def __call__(self, index, profile, state):
        """Discharge above the target; charge below it, possibly from the grid."""
        net_load_kw = sum(profile.p_load_kw.values()) - sum(profile.p_pv_kw.values())
        return net_load_kw - self.target_kw
