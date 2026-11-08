# GoiEner Load Distributor — Simple GUI

A standalone, **GoiEner-only** distribution-profile generator for the EE499 BESS Planning Tool. It reads the outputs of the **GoiEner Three-Category Cleaner** and your original network workbooks. It does **not** read raw `imp-pre.tzst` or run optimization/power flow.

## What changed compared with the earlier GUI

- Only **Residential / Commercial / Manufacturing**; no Ausgrid, Angizeh or individual GoiEner customer profile dropdowns.
- **Three tabs:** (1) Profiles, (2) Networks & bus types, (3) Export.
- Reads the existing cleaner's `residential.csv`, `commercial.csv`, and `manufacturing.csv` **directly**. You can also select its `goiener_distributor_ready.csv` or `goiener_three_profiles.csv`.
- No arbitrary 24-hour or 8,760-hour cutoff. Keeps the **longest consecutive span where all three types have valid data**. If data start/end dates differ, the union remains in your cleaner outputs and only the common overlap goes to network distribution.
- Batch-import multiple `.xlsx` and `.csv` networks, including the **Working_RDS** workbook format and the separate five-bus project format.
- Bulk assignments in ranges such as `2-50, 70, 100-136` with a single profile per category. Existing bus assignments can be imported/exported as CSVs.
- Generates **load-only** network profiles, and clearly labels zero-PV placeholders as **not actual PV data**.
- Writes large files incrementally, keeping memory usage low for multi-year, 100+ bus studies.

## Install (Windows)

1. Extract the ZIP, keeping `bundled_project/` beside the Python scripts.
2. Install **Python 3.10+** with Tkinter, then in this extracted folder run:

   ```bat
   python -m pip install -r requirements.txt
   python goiener_distribution_gui.py
   ```

   Or double-click `start_windows.bat`.

   On Linux/macOS:

   ```bash
   python3 -m pip install -r requirements.txt
   python3 goiener_distribution_gui.py
   ```

## Workflow

### 1. Profiles

Select the **folder produced by GoiEner Three-Category Cleaner**, with:

```text
cleaner_output/
  residential.csv
  commercial.csv
  manufacturing.csv
  goiener_distributor_ready.csv  # also accepted directly
  quality_report.json
```

Choose **Average** (recommended) or **Sum**. When loading the three separate sector files, the program reads:

- `average`: `average_customer_kw` in each category file
- `sum`: `load_kw` in each category file

For a prepared wide CSV the value has **already been chosen** by the cleaner: its previous `average`/`sum` setting is used; the GUI selector does not change it.

Click **Load and validate profiles**. The GUI shows the available continuous overlap and the exact timestamps. It does **not** invent/mislabel missing historical years. Internal interpolation belongs to the separate cleaner.

### 2. Networks & bus types

- Click **Add network files** or **Add whole folder**.
- For reference-format workbooks, select the study frequency (50/60 Hz) *before* loading. It is a user-supplied study parameter where not defined by the workbook.
- Supported formats:
  - Excel `Overview`, `Bus Data`, `Branch Data` (any supported radial size, including 33, 69, 118, 136 buses).
  - Excel `Network`, `Buses`, `Lines`, optionally `Loads`, `PV` (e.g., five-bus guide case).
  - CSV with `bus_id,p_base_kw,q_base_kvar,is_slack`, optionally `pv_rated_kw,base_kv,v_set_pu`.
- To label real or scenario bus types, select **one** network and click **Edit selected network's bus types**. Assign residential, commercial, or manufacturing to selected buses or entire bus ranges. Click **Save mapping and close**.
- For multiple networks, you may store mapping files named `<network_filename_without_extension>_assignments.csv` in a folder, each containing `bus_id,category` for every load bus; choose that folder in the Export tab. Save mappings from the editor to help generate these files.
- Optional quick scenarios: **all residential** or **demo round-robin**. These are explicit synthetic assumptions, **not** automatically verified customer classifications.

### 3. Export

- Choose the normalization anchor:
  - **Mean** (default): nominal bus P and Q are interpreted as average-demand references.
  - **Peak**: nominal bus P and Q are interpreted as peak-demand references.
- The algorithm uses *each sector's own* source curve:

  ```text
  multiplier_sector,t = profile_sector,t / (mean or peak of that sector's full selected history)
  P_bus,t = P_base,bus * multiplier_assigned_sector,t
  Q_bus,t = Q_base,bus * multiplier_assigned_sector,t
  ```

  This keeps each load's original Q/P ratio, including Q-only loads. It does not modify the network's base-load entries.
- Select the output folder and click **Export all loaded networks**. All available common hours are exported. Very large feeders and multi-year periods can require hundreds of MB per output, so ensure free disk space.

Sample layout:

```text
GoiEner_Distributed_YYYYMMDD_HHMMSS_microseconds/
  batch_summary.csv
  SCENARIO_CLASSIFICATION.txt
  T23_136-Bus/
    load_profile.csv                   # timestamp,bus_id,p_kw,q_kvar
    pv_profile.csv                     # zeros only; NOT a PV measurement set
    bus_assignments_used.csv           # bus_id,category,profile
    bus_summary.csv
    source_voltage_settings_READ_ONLY.csv
    manifest.json
    IMPORTANT_PV_AND_VOLTAGE.txt
```

Keep your original network workbook when importing `load_profile.csv` into the BESS Planning Tool. The GUI only produces time-series inputs.

## Critical electricity-system notes

1. **The original bus voltages are unchanged.** Nominal `base_kv`, slack `v_set_pu`, line impedance, and topology are read from the original network and never overwritten. Operating voltages at PQ buses must be recomputed by FBS for each new load scenario.
2. **GoiEner does not provide solar PV generation.** `pv_profile.csv` is a **zero-PV compatibility placeholder**, with an explicit warning in `manifest.json`. If any imported network has installed PV units, generation is blocked until you tick the GUI's explicit load-only zero-PV acknowledgement. **Do not** use that output to claim PV curtailment or PV-related BESS economics; add separate PV time series later.
3. **Bus category labels are not inferred.** Network workbooks contain electrical loads, not trusted residential/commercial/manufacturing classifications. Manually document any assignments used in a research paper.
4. **The cleaned residential group may contain unverified customer proxies.** See the cleaner's quality report and CNAE caveats.
5. **Your input raw and cleaned files remain unchanged.** If sector coverage differs, the common period used for distribution is selected and reported; the original category exports still preserve their broader history.
6. This is a data-preparation GUI, not a full feeder model or solver. CSV-only network inputs describe loads, not topology.

## Testing and examples

Run from this folder:

```bash
python -m unittest discover -s tests -v
```

Included are three **unaltered** example network workbooks (5, 33, 136 buses), a generic example CSV, and **synthetic demo profiles only** under `examples/SYNTHETIC_CLEANED_DATA/`. The actual GoiEner archive is **not** bundled and should be processed with the existing cleaner. Tests verify 17,520-hour exports, voltage preservation, conversion, a PV guard, and 136-bus operation. In addition, the bundled network loader was checked against all 22 supplied workbooks in `BESS_Planning_Tool.zip`.

The loader in `bundled_project/` is a compatibility adapter derived from the earlier project loader. It does **not** require a Python installation of the compiled BESS planning executable and does not modify it.
