# Source and implementation traceability

**Historical source:** `C1_Simple_Test/src_accelerated/fbs.py`, `network_model.py`, `network_loader.py`, and `run_c1.py` were copied without source changes from `C1_Simple_Test_with_Plots.zip`. Original calculated results remain in `C1_Simple_Test/C1_results/`, not `results/`.

**Current GitHub inspected:** `Islahi/EE499-Team16`, main tree `aaf17445f1a9c97f25f45188dd8053c65c177fb8` (as retrieved on 20 Nov 2026). Main `07_Implementation/src_accelerated/fbs.py` blob SHA `33bf7e0c633b4fffbbb543ab0fa536fb8bb17145`, `network_model.py` SHA `601c9b252a355dc4970092c925792da984e6eb63`, `network_loader.py` SHA `7b763a09b75ac2204139e9108d2f2deca5331de3`. Verified `git hash-object` on each bundled archived source file: all three Git object SHA-1 IDs **exactly match the GitHub main branch blobs** listed above. Thus, the historical FBS, model, and loader source content matches the inspected current main-branch files.

**Historical execution path:** `run_c1.py` loads all 22 workbooks through `load_network(...,workbook_format='auto',frequency_hz=60)`, forms nominal static load operating points from the network `loads`, and calls `run_fbs(...FBSConfig(max_iterations=100,voltage_tolerance_pu=1e-8,backend='python'))`. It compares results against paper and creates archived CSV/PNG. This package preserves this path as `fbs_python` and adds independent solver adapters.

**Implementation caveats:** SciPy AC solver is a separately coded damped Newton–Raphson with analytical rectangular Jacobian, using SciPy linear algebra. The optional OpenDSS and MATPOWER integrations are implemented but **cannot be certified without installing their dependencies and checking canonical equivalence on the user's machine**. GPU/GridCal/VeraGrid not implemented. Existing report flags from C1 remain as archive evidence and are not rewritten. The optional XLSX reporting requires `artifact_tool`; the CSV/PDF/dashboard generators do not.

**Original archive:** `C1_results.7z` contains original CSVs, report and figures, overlapping the bundled `C1_Simple_Test/C1_results` folder. It is retained for provenance.
