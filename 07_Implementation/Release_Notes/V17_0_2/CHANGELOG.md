# BESS Planning Tool changelog

## v17.0.2 (2026-11-26)

- Expanded the Joint GA independent stress-screening pool from 9 to up to 30 fleets.
- Expanded chronological annual verification from 3 to up to 10 ranked finalists.
- Annual verification stops at the first technically feasible fleet that lowers annual total cost versus No-BESS. If none qualify, No-BESS is retained.
- Added finalist-by-finalist logging for verification outcomes and stopping reasons.

## v17.0.1 (2026-11-25)

- Fixed the E004 IEEE 33-bus PV curtailment boundary before FBS verification.
- Tiny OPF violations snap to the physical bound. Larger or non-finite proposals use the existing fallback.
- PV boundary diagnostics record the fleet, representative day, timestamp, bus and power values.

## v17.0.0 (2026-11-24)

- Released the academic dashboard with engineering views, offline comparison and publication exports.
- Added passive GA generation and candidate diagnostics.
