"""Explicit site/clock handling and historical common-PV source acquisition."""
from dataclasses import dataclass, asdict
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
import json

import numpy as np
import pandas as pd

from .pv_model import PVModelConfig, irradiance_to_power, read_irradiance


@dataclass(frozen=True)
class SolarSite:
    latitude: float
    longitude: float
    clock: str

    def __post_init__(self):
        if not np.isfinite([self.latitude, self.longitude]).all() or not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise ValueError("Supply finite site latitude [-90,90] and longitude [-180,180]")
        utc_times([pd.Timestamp("2020-01-01")], self.clock)


def utc_times(times, clock):
    if not clock or clock.upper() == "LST":
        raise ValueError("Supply an explicit IANA clock or UTC; NASA LST must be converted using documented source offsets, never relabeled")
    ix = pd.DatetimeIndex(times)
    if ix.tz is not None:
        return ix.tz_convert("UTC")
    try:
        return ix.tz_localize(clock, ambiguous="raise", nonexistent="raise").tz_convert("UTC")
    except Exception as error:
        raise ValueError(f"Clock {clock!r} cannot unambiguously identify these hourly observations: {error}") from error


def convert_clock(times, source_clock, target_clock):
    result = utc_times(times, source_clock).tz_convert(target_clock).tz_localize(None)
    if not result.is_unique or (np.diff(result.as_unit("ns").asi8) != 3600_000_000_000).any():
        raise ValueError("Clock conversion crosses a civil DST discontinuity; prepare a continuous explicit fixed/UTC clock")
    return result


def daylight(times, site):
    """NOAA approximate solar elevation at hourly midpoint; source C2 physical mask."""
    ix = utc_times(times, site.clock)
    d = ix.dayofyear.to_numpy(float)
    hour = ix.hour.to_numpy(float) + ix.minute.to_numpy(float)/60 + .5
    gamma = 2*np.pi/np.where(ix.is_leap_year,366.,365.)*(d-1+(hour-12)/24)
    eqtime = 229.18*(.000075+.001868*np.cos(gamma)-.032077*np.sin(gamma)-.014615*np.cos(2*gamma)-.040849*np.sin(2*gamma))
    decl = (.006918-.399912*np.cos(gamma)+.070257*np.sin(gamma)-.006758*np.cos(2*gamma)
            +.000907*np.sin(2*gamma)-.002697*np.cos(3*gamma)+.00148*np.sin(3*gamma))
    angle = np.radians((hour*60+eqtime+4*site.longitude)%1440/4-180)
    lat = np.radians(site.latitude)
    return np.sin(lat)*np.sin(decl)+np.cos(lat)*np.cos(decl)*np.cos(angle) > 0


def fetch_irradiance(provider, times, site, cache_dir, opener=urlopen):
    """Fetch explicit UTC hourly radiation in yearly chunks; persist source bytes.

    Provider contracts: power.larc.nasa.gov/docs/services/api/temporal/hourly/
    and open-meteo.com/en/docs/historical-weather-api. Network failures block.
    """
    utc = utc_times(times, site.clock)
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    parts, sources = [], []
    for year in sorted(set(utc.year)):
        selected = utc[utc.year == year]
        start, end = selected[0], selected[-1]
        params = dict(latitude=site.latitude, longitude=site.longitude)
        if provider == "nasa_power":
            params.update(parameters="ALLSKY_SFC_SW_DWN", community="RE", start=start.strftime("%Y%m%d"),
                          end=end.strftime("%Y%m%d"), format="JSON", **{"time-standard":"UTC"})
            endpoint = "https://power.larc.nasa.gov/api/temporal/hourly/point"
        elif provider == "open_meteo":
            params.update(start_date=start.strftime("%Y-%m-%d"), end_date=end.strftime("%Y-%m-%d"),
                          hourly="shortwave_radiation", timezone="UTC")
            endpoint = "https://archive-api.open-meteo.com/v1/archive"
        else:
            raise ValueError("Automatic solar provider must be nasa_power or open_meteo")
        url = endpoint+"?"+urlencode(params)
        path = cache/(sha256(url.encode()).hexdigest()+".json")
        if path.exists():
            raw = path.read_bytes()
        else:
            try:
                with opener(url, timeout=60) as response:
                    raw = response.read()
                json.loads(raw)
            except Exception as error:
                raise ValueError(f"{provider} historical retrieval failed (check coverage, connection/rate limit): {error}") from error
            path.write_bytes(raw)
        doc = json.loads(raw)
        if provider == "nasa_power":
            if doc.get("header",{}).get("time_standard","UTC").upper() != "UTC":
                raise ValueError("NASA response is not the explicitly requested UTC clock")
            unit = doc.get("parameters", {}).get("ALLSKY_SFC_SW_DWN", {}).get("units", "")
            if unit not in ("Wh/m^2", "Wh/m2", "W/m^2", "W/m2"):
                raise ValueError(f"Unexpected NASA hourly radiation units: {unit}")
            values = doc["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]
            dates = pd.to_datetime(list(values), format="%Y%m%d%H", utc=True)
            radiation = list(values.values())  # hourly Wh/m² / 1 h -> W/m²
        else:
            if doc.get("hourly_units", {}).get("shortwave_radiation") != "W/m²":
                raise ValueError("Unexpected Open-Meteo shortwave units")
            dates = pd.to_datetime(doc["hourly"]["time"], utc=True)
            radiation = doc["hourly"]["shortwave_radiation"]
        parts.append(pd.Series(radiation, index=dates, dtype=float))
        sources.append({"url":url, "snapshot":str(path), "sha256":sha256(raw).hexdigest()})
    series = pd.concat(parts).reindex(utc)
    if not np.isfinite(series).all() or (series < 0).any():
        raise ValueError("Solar provider has missing, invalid or incomplete hourly coverage")
    return pd.DataFrame({"timestamp":pd.DatetimeIndex(times), "irradiance_w_m2":series.to_numpy()}), sources


@dataclass
class PVReference:
    timestamps: object
    p_kw: object
    capacity_kw: float
    site: SolarSite
    provenance: dict

    def __post_init__(self):
        p = np.asarray(self.p_kw, dtype=float)
        if not np.isfinite(self.capacity_kw) or self.capacity_kw <= 0:
            raise ValueError("PV reference nameplate must be known positive kW")
        ix = pd.DatetimeIndex(self.timestamps)
        if len(ix) != len(p) or not ix.is_unique or not ix.is_monotonic_increasing or (np.diff(ix.as_unit("ns").asi8) != 3600_000_000_000).any():
            raise ValueError("PV reference requires complete unique hourly coverage")
        if not np.isfinite(p).all() or (p < 0).any() or (p > self.capacity_kw+1e-6).any() or not p.any():
            raise ValueError("PV training reference is a placeholder, invalid or exceeds nameplate")
        utc_times(ix, self.site.clock)


def reference_from_file(path, kind, capacity, site, source_clock, conversion):
    if kind == "power":
        frame = pd.read_csv(path)
        if not {"timestamp", "p_kw"}.issubset(frame) or "bus_id" in frame and frame.bus_id.nunique() != 1:
            raise ValueError("Import one common modeled-PV reference with timestamp,p_kw and documented nameplate")
        for column in ("reference_capacity_kw","capacity_kw","site_lat","site_lon","source_clock","timezone"):
            if column in frame and (frame[column].isna().any() or frame[column].nunique()!=1):
                raise ValueError(f"Common PV source metadata {column} must be consistent on every row")
        for column in ("reference_capacity_kw","capacity_kw"):
            if column in frame and not np.isclose(float(frame[column].iloc[0]),capacity):
                raise ValueError("Manual reference nameplate conflicts with the file's declared capacity")
        p = pd.to_numeric(frame.p_kw, errors="raise").to_numpy()
    else:
        frame = read_irradiance(path, source=kind)
        p = np.array([irradiance_to_power(v, capacity, conversion) for v in frame.irradiance_w_m2])
    dates = convert_clock(pd.to_datetime(frame.timestamp), source_clock, site.clock)
    return PVReference(dates, p, capacity, site, {"path":str(path), "sha256":sha256(Path(path).read_bytes()).hexdigest(),
        "target":"modeled electrical kW", "source_clock":source_clock, "site":asdict(site),
        "conversion":asdict(conversion) if kind != "power" else "already modeled kW; no conversion"})
