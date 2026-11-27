# E004 IEEE 33-bus PV30 boundary fix

## Failure and numerical evidence

The archived run failed inside strict FBS validation while checking a candidate returned by the hourly joint OPF during GA generation 12. Generation 11 logged 2,459 completed unique evaluations. The failed worker's exception contained no fleet, timestamp, bus or proposed curtailment values. All 1,449,393 archived PV rows were finite, nonnegative and within the configured ratings. The configured ratings included 409.2, 491.1, 327.4 and 654.8 kW.

A targeted two-bus run with the real HiGHS solver and the real FBS code reproduced the failure. A fractional 10.375 kW inverter had 3.125 kW available at the operating point. HiGHS returned a successful LP proposal of 3.12500005 kW curtailed, giving -5.000000014021566e-8 kW after subtraction. The previous code passed that value into FBS, which raised the reported exception. Under the fix, the same HiGHS solution produced exactly 0.0 kW of remaining PV and passed nonlinear FBS verification.

## Source modifications

- joint_opf.py checks the proposed curtailment against [0, available PV] before FBS verification. It snaps only out-of-bound excursions within 1e-7 kW to the affected boundary. This absolute tolerance matches the HiGHS primal feasibility default in the bundled SciPy. In-range values pass through at their original precision. Material and non-finite proposals reach the existing OPF corrective fallback.
- multi_bess.py and fleet_ga_optimizer.py pass the hour and representative-day identity for diagnostics. These are logging fields.
- app_log.py appends a separate JSONL file per process under Results/Diagnostics next to the source sessions. Each event includes the fleet with bus/P/E, representative-day start/cluster/index, operating timestamp, PV bus, available PV at the LP anchor, proposed curtailment, raw residual and the clamp/fallback decision.
- test_opf_pv_boundary.py adds focused checks of the physical bounds, FBS strictness, logging and failure routing. release_checks.py adds a PV boundary exercise to the existing portable-build smoke check.

FBS, the day-ahead MILP, optimization and economics retain their existing algorithms and settings. PV ratings retain their numeric values.

## Windows use

Extract the entire ZIP and launch BESS_Planning_Tool.exe with its companion _internal directory beside it. The portable executable was built with the existing PyInstaller specification. In a portable install, recurrence logs appear in _internal/src/Results/Diagnostics/opf_pv_boundary_<pid>.jsonl.

### Build command

Run from the EE499-Team16 repository root with the existing project Python environment.

```powershell
$env:EE499_BUNDLER = (Resolve-Path .venv-exe/Lib/site-packages).Path
python -c "import os,sys; sys.path.append(os.environ['EE499_BUNDLER']); from PyInstaller.__main__ import run; run()" --noconfirm --distpath dist/ee499-e004-windows-x64 --workpath dist/ee499-academic-work/pyinstaller 07_Implementation/Packaging/BESS_Planning_Tool.spec
```

The previous portable build and experiment folders remain available independently of this release.


## Verification

- The relocated Windows executable passed its native startup smoke check. The packaged OPF code was extracted, matched against the updated source and exercised for both boundary outcomes.
- Automatic review blocked the broader native smoke test because of unexpected external telemetry. The completed native startup test opens no browser page.
- E001 No-PV snapshots matched before and after over two 48-hour windows, each checked with zero and three batteries.
- A bounded replay of 72 other fleets across six high-PV days from E004 did not reproduce the excursion. The archived failure lacks the exact worker values.
- Nine focused PV tests and 55 existing OPF, dispatch, and controller checks passed. Automatic review stopped the broader suite and longer exploratory replay after detecting unexpected external telemetry.

Executable SHA-256: 513c010feb1dc2a9efee9d6709d39d8ae9a17b1b255c7abf53fbb6fed316b2d8
