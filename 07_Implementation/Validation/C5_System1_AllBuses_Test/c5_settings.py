"""C5 experiment settings: EDIT THIS FILE to change the test horizon.

These are C5-controlled test assumptions; original src_accelerated code is unchanged.
"""

# ---- TIME HORIZON ----
START_DATE = "2019-01-01"  # Choose a month within the loaded 2017-05 to 2020-02 range
HORIZON_MONTHS = 1          # Calendar months (1, 2, 3, ...). Jan 2019 has raw voltage violations.
HORIZON_DAYS = None         # Set e.g. 2 for a quick pilot; overrides HORIZON_MONTHS

# ---- PV ----
PV_BUS = 13
PV_RATING_KW = 490.0
PV_CRITICAL_IRRADIANCE_W_M2 = 120.0

# ---- BESS DISPATCH: choose "scheduled" OR "grid_aware" ----
# The original grid-aware policy only charges on PV surplus. The supplied 490 kW
# solar profile NEVER exceeds aggregate load (checked over the entire overlap).
# To test active battery cycling, scheduled mode charges from the GRID at low-load
# hours and discharges during evening demand. This is not renewable-only dispatch.
DISPATCH_MODE = "scheduled"
CHARGE_HOURS = (0, 1, 2, 3, 4)
DISCHARGE_HOURS = (17, 18, 19, 20)
CHARGE_POWER_FRACTION = 0.7   # fraction of battery rated power
DISCHARGE_POWER_FRACTION = 0.9

# ---- STRICT CONSTRAINTS ----
VOLTAGE_MIN_PU = 0.95
VOLTAGE_MAX_PU = 1.05
RESERVE_FRACTION = 0.0
ENFORCE_LINE_AMPACITY = False  # Original reference does not provide complete ampacity limits.
ALLOW_PV_CURTAILMENT = True
ALLOW_LOAD_SHEDDING = True    # If used, MUST be reported in comparisons.
GRID_IMPORT_LIMIT_KW = None
GRID_EXPORT_LIMIT_KW = None

# ---- BESS SEARCH CATALOG ----
ALLOWED_BUS_IDS = tuple(range(2, 16))  # ALL non-slack buses 2..15, 14 locations
POWER_RATINGS_KW = (50.0, 100.0, 150.0)
ENERGY_CAPACITIES_KWH = (100.0, 200.0, 300.0)
ETA_CHARGE = 0.95
ETA_DISCHARGE = 0.95
SOC_MIN, SOC_INITIAL, SOC_MAX = 0.20, 0.50, 1.00

# ---- ILLUSTRATIVE C4 ECONOMICS (NOT INVESTMENT-GRADE PRICES) ----
COST_PER_KW = 770.0
COST_PER_KWH = 385.0
DISCOUNT_RATE = 0.06
LIFETIME_YEARS = 10
ANNUAL_OM_FRACTION = 0.02
GRID_IMPORT_TARIFF = 0.20
GRID_EXPORT_TARIFF = 0.05
CURTAILMENT_PENALTY = 0.07
SHEDDING_PENALTY = 12.0
ANNUAL_HOURS = 8760.0

# ---- SEARCH ----
RUN_SEEDS = 20           # Use 1 or 2 for smoke tests; use 20 for validation.
POPULATION_SIZE = 12
ITERATIONS = 20
TARGET_GAP_PERCENT = 5.0
REQUIRED_PASSES = 18
# Precompute the 45 deterministic simulation scores once. GA/GWO then search
# the EXACT same lookup table; search runtimes exclude physical simulation.
# Set False for full, slower, end-to-end per-algorithm evaluation timings.
USE_PRECOMPUTED_SCORES = True
