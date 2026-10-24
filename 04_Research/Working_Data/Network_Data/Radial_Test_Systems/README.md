# Downloaded radial distribution test systems

Downloaded from the official MATPOWER repository on **19 Oct 2026**, at the
user's request. These are published reference networks, not invented project
loads and not a new team decision about the final case study.

## What is available

| Original file | Buses | Active lines | Voltage (kV) | Base MVA | Demand (kW / kvar) | Useful role |
|---|---:|---:|---:|---:|---:|---|
| `case10ba.m` | 10 | 9 | 23 | 10 | 12368 / 4186 | Small chain, strongly stressed base voltage |
| `case12da.m` | 12 | 11 | 11 | 1 | 435 / 405 | Small, straightforward chain for debugging |
| `case15da.m` | 15 | 14 | 11 | 1 | 1226.4 / 1251.1785 | Small branched feeder, useful for diagram tests |
| `case22.m` | 22 | 21 | 11 | 1 | 662.311 / 657.4 | Medium branched feeder |
| `case33bw.m` | 33 | 32 | 12.66 | 10 | 3715 / 2300 | Baran–Wu reference, including five normally open ties |
| `case69.m` | 69 | 68 | 12.66 | 10 | 3802.1 / 2694.7 | Larger radial feeder for later checks |

Original files are in `MATPOWER_8.1_Originals/`. None were edited. All six active
networks were checked for connectivity, acyclic topology and N−1 active lines.
The 33-bus file contains **37 total branch records**: 32 closed and five open.
Those open ties remain in the original file; closing them is not part of this
download or our solver check.

The 12-bus case is a practical small starting point; use the 15-bus case when a
branched diagram is more useful. This is an implementation recommendation,
not a replacement of the confirmed study direction.

## Important: downloaded does not mean directly loadable in our UI

These are **MATPOWER MATLAB/Octave `.m` source files**. Our current network
loader accepts supported `.xlsx` schemas, not `.m` files. Do not rename them
to `.xlsx`, select PJM as a substitute, or expect the UI to import them yet.

The next integration step is a separate, documented conversion to our project
Excel schema, or an explicitly implemented MATPOWER adapter. Neither was added
by this find/download request. The existing IEEE33 Excel workbook remains the
already-supported UI input. Existing radial five-bus Python fixtures are
different networks and are not replaced by these downloads.

For a faithful series-impedance/PQ-load conversion:

- Preserve bus IDs, connections, slack voltage, source MVA/kV bases and P/Q.
- All six files declare their **literal** bus demand in kW/kvar and branch R/X
  in ohms. Their MATLAB functions convert these values to MW/Mvar and per-unit
  when executed. Do not apply both conversions to the literal source tables.
- Honor branch status. Do not import the normally open ties as closed lines.
- The only generator in each selected case is at the slack bus. It represents
  the external supply, not solar PV. There are no other voltage-controlled
  generation buses, bus shunts, line charging or non-unity transformer taps in
  these six selected cases. This was checked, not assumed from their names.
- A limited FBS representation is not the full MATPOWER OPF model: source
  generator costs, supply P/Q limits and voltage/branch limits must not be
  silently presented as enforced by our implementation. In particular, generator
  cost is not a battery investment coefficient.
- Frequency is not specified in these case files. Supply the intended study
  frequency explicitly rather than claiming a downloaded value.
- Solar ratings, batteries, hourly profiles and uncertainty settings remain
  separate study inputs. Base loads are not measured multi-month profiles.

The previously supplied IEEE33 workbook uses a 100 MVA base; the downloaded
MATPOWER case uses 10 MVA. Keep originals separate and document conversions;
do not overwrite an earlier source or assume every version is byte-identical.

## Read-only compatibility check

Literal numeric tables were extracted without executing MATLAB code. Checked
single voltage level, one slack supply, PQ-only other buses, zero shunts/line
charging, nominal taps and topology. Transient in-memory `NetworkModel` objects
were passed to the existing `run_fbs` with base demand, no PV/BESS, a flat start
and default FBS settings. A 60 Hz value was used only to satisfy the project's
model interface; it is **not** a source-data frequency. No new importer, converted
file or application behavior was created.

| Case | FBS converged | Minimum voltage (pu) | Active loss (kW) |
|---|---|---:|---:|
| 10 bus | Yes | 0.83750362 | 783.777902 |
| 12 bus | Yes | 0.94335401 | 20.713763 |
| 15 bus | Yes | 0.94451700 | 61.794377 |
| 22 bus | Yes | 0.97287508 | 17.742589 |
| 33 bus | Yes | 0.91309050 | 202.677055 |
| 69 bus | Yes | 0.90918776 | 224.991479 |

These are our solver's integration checks, **not independent numerical
validation** against a separate solver. No voltage controls or shedding were
applied. Except for the 22-bus case, the minima are below the project's 0.95 pu
study limit. Convergence does not establish feasibility or a storage need.

## Source and version

- Official repository: [MATPOWER/matpower](https://github.com/MATPOWER/matpower).
- Release tag: `8.1`, annotated tag object
  `3f8ecfdbc79b07697d6b45f8d868ac1c2d27f788`.
- Resolved immutable commit: `1a828c7af590714499284e36ee9c81273388c594`.
- [Pinned data directory](https://github.com/MATPOWER/matpower/tree/1a828c7af590714499284e36ee9c81273388c594/data).
- `DOWNLOAD_MANIFEST.json` records exact download URLs, byte counts and SHA256
  checksums. Checksums identify the saved copies; they are not a license grant.

Original literature attribution, retained in the downloaded headers:

- **10 bus:** Baghzouz and Ertem (1990), “Shunt capacitor sizing for radial
  distribution feeders with distorted substation voltages,” IEEE Transactions
  on Power Delivery, volume 5, pages 650–657.
- **12 bus:** Das, Nagi and Kothari (1994), “Novel method for solving radial
  distribution networks,” IEE Proceedings C, 141(4), pages 291–298.
- **15 bus:** Das, Kothari and Kalam (1995), “Simple and efficient method for
  load flow solution of radial distribution networks,”
  [DOI](https://doi.org/10.1016/0142-0615(95)00050-0).
- **22 bus:** Raju, Murthy and Ravindra (2012), “Direct search algorithm for
  capacitive compensation in radial distribution systems,”
  [DOI](https://doi.org/10.1016/j.ijepes.2012.03.006).
- **33 bus:** Baran and Wu (1989), “Network reconfiguration in distribution
  systems for loss reduction and load balancing,”
  [DOI](https://doi.org/10.1109/61.25627).
- **69 bus:** Baran and Wu (1989), “Optimal capacitor placement on radial
  distribution systems,” [DOI](https://doi.org/10.1109/61.19265), with the
  additional Das (2008) reference retained in the source header.

These are MATPOWER's attributions; this download did not independently verify
each table against every original paper.

### Licensing caution

The saved upstream `LICENSE` explicitly says **MATPOWER case files are not
covered by its software BSD license**. It states that case data is generally
included with permission or converted from public sources. Do not describe
these datasets as BSD-licensed merely because MATPOWER software is. Preserve
the source headers/attribution and check applicable dataset rights before
republication or redistribution. No ownership or blanket reuse permission is
asserted by adding local research copies.

The official IEEE 13/34/37/123-node feeders were also considered, but their
unbalance, transformer/regulator and capacitor features would need more than
our current balanced, single-voltage model. They were not silently simplified
or included as directly compatible cases.
