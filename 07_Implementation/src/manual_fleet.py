"""Manual installation settings and their legacy single-battery representation."""

from math import isfinite

from .bess import BESSConfig


def manual_rows(values):
    if "manual_bess_rows" in values:
        return [{**row, "power_kw": row.get("power_kw", row.get("power_rating_kw", "")),
                 "energy_kwh": row.get("energy_kwh", row.get("energy_capacity_kwh", ""))}
                for row in values["manual_bess_rows"]]
    return [{
        "enabled": True, "bus_id": values.get("bess_bus"),
        "power_kw": values.get("spin_bess_power_kw", 0),
        "energy_kwh": values.get("spin_bess_energy_kwh", 0),
    }]


def positive(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) and result > 0 else None


def row_number(value):
    """Keep invalid pending input visible, and store valid values as JSON numbers."""
    result = positive(value)
    return result if result is not None else str(value)


def validate_manual_fleet(values, eligible_buses, parameters):
    if not values.get("group_manual_bess"):
        return ()
    low, high = (values[f"spin_opt_duration_{end}_hours"] for end in ("min", "max"))
    if not isfinite(low) or not isfinite(high) or not 0 <= low <= high:
        raise ValueError("Set a valid battery-duration range")
    units, used = [], set()
    for index, row in enumerate(manual_rows(values), 1):
        if not row.get("enabled"):
            continue
        prefix = f"Manual BESS row {index}"
        bus = row.get("bus_id")
        if bus not in eligible_buses:
            raise ValueError(f"{prefix}: choose a non-slack installation bus from the loaded network")
        if bus in used:
            raise ValueError(f"{prefix}: bus {bus} already has an enabled battery")
        power, energy = positive(row.get("power_kw")), positive(row.get("energy_kwh"))
        if power is None or energy is None:
            raise ValueError(f"{prefix}: enter finite positive power (kW) and energy (kWh)")
        duration = energy / power
        if not low <= duration <= high:
            raise ValueError(f"{prefix}: duration {duration:.3g} h is outside the configured {low:g}-{high:g} h range")
        units.append(BESSConfig(bus, energy, power, parameters.soc_min, parameters.soc_max,
                                parameters.soc_initial, parameters.eta_charge, parameters.eta_discharge))
        used.add(bus)
    if not units:
        raise ValueError("Enable at least one manual BESS row or turn off manual BESS")
    return tuple(units)


def manual_context(units):
    details = {"Fleet count": len(units)}
    if units:
        details["Manual BESS Fleet"] = [dict(vars(unit)) for unit in units]
        if len(units) == 1:
            details["Manual BESS"] = details["Manual BESS Fleet"][0]
    return details
