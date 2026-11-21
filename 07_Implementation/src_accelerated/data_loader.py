from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd


class ProfileData:
    def __init__(self, csv_load: Path, csv_pv: Path):
                
        self._from_frames(pd.read_csv(csv_load), pd.read_csv(csv_pv))

    def _from_frames(self, df_load, df_pv):
        import numpy as np
        frames = []
        for label, frame in (("Load", df_load), ("PV", df_pv)):
            if not {"timestamp", "bus_id", "p_kw", "q_kvar"}.issubset(frame.columns):
                raise ValueError(f"{label} CSV is missing required columns")
            frame = frame.copy()
            frame["timestamp"] = pd.to_datetime(frame.timestamp, format="ISO8601", errors="raise")
            if frame.timestamp.isna().any() or frame.timestamp.dt.tz is not None:
                raise ValueError("Use one explicit timezone-naive source clock")
            for name in ("bus_id", "p_kw", "q_kvar"):
                frame[name] = pd.to_numeric(frame[name], errors="raise")
                if not np.isfinite(frame[name]).all():
                    raise ValueError(f"{label} {name} must be finite")
            if (frame.bus_id % 1 != 0).any() or (frame.p_kw < 0).any():
                raise ValueError(f"{label} bus IDs must be integers and active power nonnegative")
            if frame.duplicated(["timestamp", "bus_id"]).any():
                raise ValueError(f"Duplicate {label} timestamp/bus rows")
            frame = frame.sort_values(["timestamp", "bus_id"])
            times = pd.DatetimeIndex(frame.timestamp.unique()).sort_values()
            if len(times) < 1 or (np.diff(times.as_unit("ns").asi8) != 3600_000_000_000).any():
                raise ValueError("Profile timestamps must be continuous and hourly")
            if not frame.groupby("bus_id").size().eq(len(times)).all():
                raise ValueError(f"{label} series must cover every timestamp for every included bus")
            frames.append((frame, times))
        if not frames[0][1].equals(frames[1][1]):
            raise ValueError("Load and PV timestamps do not match")
        self.timestamps = list(frames[0][1])
        for (frame, _), prefix in zip(frames, ("load", "pv")):
            for column, suffix in (("p_kw", "p_kw"), ("q_kvar", "q_kvar")):
                setattr(self, prefix+"_"+suffix, {int(bus): group[column].tolist()
                        for bus, group in frame.groupby("bus_id", sort=True)})
        self.dt_hours = 1.0

    @classmethod
    def from_arrays(cls, timestamps, load_p_kw, load_q_kvar, pv_p_kw, pv_q_kvar):
        obj = cls.__new__(cls)
        obj.timestamps = list(pd.DatetimeIndex(timestamps))
        obj.dt_hours = 1.0
        for name, values in zip(("load_p_kw", "load_q_kvar", "pv_p_kw", "pv_q_kvar"),
                                (load_p_kw, load_q_kvar, pv_p_kw, pv_q_kvar)):
            setattr(obj, name, {int(bus): list(array) for bus, array in values.items()})
        return obj

    def slice(self, start=None, end=None):
        """Inclusive start, exclusive end; never mutate complete raw history."""
        times = pd.DatetimeIndex(self.timestamps)
        if start is not None and pd.Timestamp(start) not in times:
            raise ValueError("Start must match an available hourly observation")
        if end is not None and pd.Timestamp(end) not in times and pd.Timestamp(end) != times[-1]+pd.Timedelta(hours=1):
            raise ValueError("End must match an available hour or the exclusive end of coverage")
        a = 0 if start is None else times.searchsorted(pd.Timestamp(start))
        b = len(times) if end is None else times.searchsorted(pd.Timestamp(end))
        if a >= b:
            raise ValueError("Selected interval contains no observations")
        return self.from_arrays(times[a:b], *[{bus: values[a:b] for bus, values in getattr(self, field).items()}
                for field in ("load_p_kw", "load_q_kvar", "pv_p_kw", "pv_q_kvar")])

class ProfileSlice:
    def __init__(self, profile_data: ProfileData, index: int):

        if index < 0 or index >= len(profile_data.timestamps):
            raise IndexError("Profile index out of range.")

        self.timestamp = profile_data.timestamps[index]

        self.p_load_kw = {
            bus_id: values[index]
            for bus_id, values in profile_data.load_p_kw.items()
        }

        self.q_load_kvar = {
            bus_id: values[index]
            for bus_id, values in profile_data.load_q_kvar.items()
        }

        self.p_pv_kw = {
            bus_id: values[index]
            for bus_id, values in profile_data.pv_p_kw.items()
        }

        self.q_pv_kvar = {
            bus_id: values[index]
            for bus_id, values in profile_data.pv_q_kvar.items()
        }

def profile_at(profile_data: ProfileData, index: int) -> ProfileSlice:
    return ProfileSlice(profile_data, index)
