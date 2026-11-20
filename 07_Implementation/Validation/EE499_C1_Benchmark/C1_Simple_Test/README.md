# EE499 Team 16 — Simple C1 FBS validation

This kit runs **all 22 Working_RDS workbooks** as nominal/static, no-PV, no-BESS power-flow cases. It uses the **unchanged** `src_accelerated.network_loader.load_network` and `src_accelerated.fbs.run_fbs` imported normally.

## Run on Windows (PowerShell)

1. Extract `C1_Simple_Test.zip` into any folder.
2. Open PowerShell inside the extracted `C1_Simple_Test` folder.
3. Install required packages, if needed:

   ```powershell
   python -m pip install numpy openpyxl
   ```

4. Run **without any arguments**:

   ```powershell
   python .\run_c1.py
   ```

The script creates/replaces these files in `C1_results/`:

- `c1_report.txt` — a paper-versus-program section for **every configuration**, like the summary boxes beneath the paper's tables; **FBS iterations** are included.
- `c1_summary.csv` — all paper-reported values and computed values side by side, errors, iterations, and validation status.
- `c1_bus_voltages.csv` — each bus's computed and published voltage plus absolute error.

The packaged `C1_results/` contains a **sample run** from the bundled source and 22 workbooks; run the script on your computer to generate your own recorded validation evidence.

## What is being compared

Paper: Y. Latreche et al., *Comprehensive Review of Radial Distribution Test Systems*, printed Tables 2–23. For each available case, the supplied `references/` files were transcribed from that paper and contain the printed base, nominal loads, real/reactive power losses, minimum voltage and weakest bus, along with every available published bus voltage.

Program: `src_accelerated` with `backend="python"`, at nominal static P/Q loads, `max_iterations=100`, convergence tolerance `1e-8 pu`, slack angle 0°, and no PV/BESS injections. Frequency 60 Hz is an explicit study setting, not attributed to the source paper.

- **Iterations** are measured from `PowerFlowResult.iterations` and **are not reported by the publication**.
- Paper prints `S_base = 100` without an explicit unit in its case summaries; the FBS model's `100000 kVA` base is printed as `100 MVA` to make the numerical bases comparable. The original printed value is retained in the CSV as `paper_sbase_printed`.
- Voltages are compared bus by bus with the C1 **0.01 pu maximum error** criterion. The 1% real-loss discrepancy flag is only the protocol's *provisional engineering review target*.
- A reference case with different workbook impedances is marked **REVIEW**, not an unqualified pass, even if its voltage errors are small. This applies to the additional IEEE 33-bus workbook (one branch), and the 69-bus case (systematic printed-impedance mismatch). Neither case is silently rescaled.
- The two `T18` feeder files have different slack buses, so the *paper's combined* 70-bus loads and losses are **not compared to each feeder individually**. A computed `T18_COMBINED` summary row adds their loads/losses; the displayed combined iteration count is the **maximum individual feeder iteration count**, not iterations from a separate combined FBS run.
- The Guide 5-bus feeder has no published counterpart in the supplied paper and is marked `NO PAPER REFERENCE`.

The extracted network files and the four original imported Python modules are included only to make the test runnable immediately. To use the active [EE499 Team 16 repository](https://github.com/Islahi/EE499-Team16.git) instead, replace the bundled `src_accelerated` folder with the current source package and leave `run_c1.py`, `Working_RDS`, and `references` together.
