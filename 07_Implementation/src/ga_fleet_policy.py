"""Capacity gate shared by saved controls and direct optimizer calls."""

EXPERIMENTAL_MIN_UNITS = 4


def validate_ga_fleet_limit(max_units, experimental, eligible, dispatch_mode):
    if type(max_units) is not int or max_units < 1:
        raise ValueError("Maximum BESS units must be a positive integer")
    if not experimental:
        if max_units >= EXPERIMENTAL_MIN_UNITS:
            raise ValueError("Standard optimization supports 1–3 units. Enable experimental Joint GA for larger fleets.")
        return max_units
    if max_units < EXPERIMENTAL_MIN_UNITS:
        raise ValueError(f"Experimental Joint GA requires a maximum of at least {EXPERIMENTAL_MIN_UNITS} units")
    if dispatch_mode != "daily_milp_dispatch":
        raise ValueError("Experimental Joint GA requires coupled daily MILP dispatch")
    eligible_count = len(set(eligible))
    if eligible_count < max_units:
        raise ValueError(f"Experimental Joint GA requires {max_units} selected non-slack buses for this maximum. "
                         f"Only {eligible_count} selected.")
    return max_units


def ga_fleet_limit(values, eligible, dispatch_mode):
    experimental = values.get("chk_experimental_multi_bess") is True
    maximum = values.get("spin_bess_units", 3)
    if experimental:
        maximum = values.get("spin_experimental_bess_units", EXPERIMENTAL_MIN_UNITS)
    elif type(maximum) is int and maximum == 0:
        return 0
    return validate_ga_fleet_limit(maximum, experimental, eligible, dispatch_mode)
