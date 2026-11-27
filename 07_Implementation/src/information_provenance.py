"""Compact provenance for both viewers, with untouched records on demand."""
from collections.abc import Mapping
from html import escape
import json
from pathlib import PureWindowsPath
import re

_SHA = re.compile(r"[0-9a-fA-F]{64}")


def display_detail(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2, default=str)


def compact_value(value, scalar):
    if isinstance(value, Mapping):
        return f"{len(value)} recorded fields"
    if isinstance(value, (list, tuple)):
        if len(value) <= 4 and all(not isinstance(item, (Mapping, list, tuple)) for item in value):
            preview = ", ".join(scalar(item) for item in value)
            if len(preview) <= 96:
                return preview
        return f"{len(value)} recorded items"
    if isinstance(value, str):
        if _SHA.fullmatch(value):
            return value[:12] + "…"
        if value.startswith(("{", "[", "(")) and len(value) > 32:
            return "Archived structured text"
        if len(value) > 96:
            return value[:93] + "…"
    return scalar(value)


def value_html(value, scalar, *, dashboard):
    preview = compact_value(value, scalar)
    full = display_detail(value) if isinstance(value, (Mapping, list, tuple, str)) else preview
    if full == preview or isinstance(value, (list, tuple)) and not preview.endswith("recorded items"):
        return escape(preview)
    if dashboard:
        return (f"<details class='value-detail'><summary>{escape(preview)}</summary>"
                f"<pre>{escape(full)}</pre></details>")
    return escape(preview) + " <span>(full details available)</span>"


def provenance_records(metadata, snapshot):
    context = metadata.get("context") or {}
    snapshot = snapshot or {}
    return {key: value for key, value in {
        "Source files": context.get("Source files"),
        "PV source provenance": context.get("PV source provenance"),
        "PV reference": snapshot.get("pv_reference"),
        "Selected workbook SHA-256": context.get("Network SHA256"),
        "Distributor workbook SHA-256": context.get("Distributor network SHA256"),
        "Recorded parameters": context,
        "Optimization metadata": metadata.get("optimizer"),
        "Input snapshot": snapshot,
    }.items() if value is not None}


def source_name(value):
    if not isinstance(value, str) or value.startswith(("{", "[", "(")):
        return value
    if "\\" in value or "/" in value and not value.startswith(("https:", "http:")):
        return PureWindowsPath(value).name or value
    return value


def pv_details(context, source, snapshot):
    solar = source.get("solar")
    reference = snapshot.get("pv_reference") or {}
    if not isinstance(reference, Mapping):
        reference = {}
    raw = next((item for item in (solar, context.get("PV source provenance"), reference.get("provenance"))
                if isinstance(item, Mapping)), None)
    if raw is None:
        if isinstance(solar, str) and solar.lstrip().startswith(("{", "[", "(")):
            return "Archived PV provenance", [], {"PV source (archived text)": solar}
        return source_name(solar or context.get("PV source")), [], {}
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), Mapping) else {}
    site = raw.get("site") or reference.get("site") or {}
    site = site if isinstance(site, Mapping) else {}
    conversion = raw.get("conversion") or {}
    model = raw.get("model") or (conversion if isinstance(conversion, str) else conversion.get("model"))
    conversion = conversion if isinstance(conversion, Mapping) else {}
    identity = raw.get("provider") or meta.get("provider") or raw.get("source") or "PV reference"
    provider_code = str(identity).lower().replace("_", " ")
    provider = "NASA POWER" if "nasa" in provider_code else "Open-Meteo" if "meteo" in provider_code else identity
    target = raw.get("target") or raw.get("data_type") or meta.get("data_type")
    if not target and model and any(x in str(model).lower() for x in ("ghi", "irradiance", "piecewise")):
        target = "Modeled generation from irradiance"
    clock = raw.get("source_clock") or meta.get("source_clock") or site.get("clock")
    hashes = raw.get("hashes") or raw.get("profile_hashes_sha256")
    integrity = {}
    def collect(value, label):
        if isinstance(value, Mapping):
            for key, item in value.items():
                collect(item, str(key))
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item, label)
        elif isinstance(value, str) and _SHA.fullmatch(value):
            integrity.setdefault(value, label)
    collect(hashes, "Recorded file")
    collect(raw.get("sources"), "Provider snapshot")
    collect(raw.get("sha256"), source_name(raw.get("path")) or "Reference")
    verification = raw.get("verification_status", meta.get("verification_status", raw.get("verified")))
    rows = [
        ("Provider", provider), ("Source parameter", raw.get("parameter") or meta.get("parameter")),
        ("Data type", target), ("Source clock", clock),
        ("Site", site.get("name") or raw.get("site_name") or meta.get("site_name")),
        ("Latitude (°)", site.get("latitude", site.get("lat"))), ("Longitude (°)", site.get("longitude", site.get("lon"))),
        ("Coverage start", raw.get("start") or meta.get("start")),
        ("Coverage end", raw.get("end") or meta.get("end")),
        ("Reference capacity (kW)", raw.get("capacity_kw", reference.get("capacity_kw"))),
        ("Conversion model", model),
        ("Critical irradiance (W/m²)", raw.get("critical_irradiance_w_m2", conversion.get("critical_irradiance_w_m2"))),
        ("Standard irradiance (W/m²)", raw.get("standard_irradiance_w_m2", conversion.get("standard_irradiance_w_m2"))),
        ("Source units", raw.get("units") or meta.get("units")), ("Verification status", verification),
    ]
    if integrity:
        preview = next(iter(integrity))[:12]
        rows.extend([("Source file checksums", len(integrity)), ("First SHA-256 prefix", preview + "…")])
    label = str(provider)
    if target and "model" in str(target).lower():
        label += " · modeled PV"
    return label, [(name, value) for name, value in rows if value is not None and value != ""], raw

