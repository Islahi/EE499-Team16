# GoiEner Three-Category Multi-Year Data Cleaner

This is a **standalone data preparation program**. It does not edit the BESS Planning Tool, network workbooks, bus voltages, or the old Load Distributor GUI.

## Agreed procedure

1. Identify **residential**, **commercial (trade)** and **manufacturing** customers using `metadata.csv`.
2. Read **all historical hours available** from `imp-pre.tzst` (no arbitrary year or time-step cap).
3. For each customer, create a continuous hourly series between the first and last recorded hour. **Linearly interpolate any internal missing readings**, including gaps longer than 1–2 hours. Do not create customer data before their first or after their last recorded hour.
4. **Sum customers in each sector at each timestamp** and write three independently dated CSV files.
5. Create a combined wide CSV for importing into the existing Load Distributor and provide quality reports. No bus assignment is made here.

The original `imp-pre.tzst` archive is itself **pre-imputed** by the GoiEner publisher. The cleaner preserves those reported readings and interpolates additional missing or invalid hours. Imputation is not real measured demand, and the quality manifest records filling activity.

## Windows usage (GUI)

1. Extract this ZIP.
2. Double-click `start_windows.bat`, or from a terminal in this folder run:
   ```powershell
   python -m pip install -r requirements.txt
   python goiener_cleaner_gui.py
   ```
3. Select the **original files already on your computer**, e.g. `Downloads\GoiEner_Multiyear_Download_Extractor\goiener_original\metadata.csv` and `imp-pre.tzst`.
4. Select a new output directory.
5. Keep **profile value = average** for the Load Distributor. The three sector CSV files still contain **actual summed hourly consumption**.
6. Click **Clean and Aggregate Full Archive**. Extraction streams the large archive, processing one customer at a time; allow sufficient local disk space and memory. Do not extract `imp-pre.tzst` manually first.

### Optional residential proxy

CNAE `97`–`98` means *household employment/production activities*; it does **not** label every normal residential electricity customer. If too few customers are classified as residential, the **unverified 2.x tariff proxy** checkbox can include otherwise unclassified meters with that tariff prefix. **These must be presented as an assumed residential proxy, not verified residential loads.** Commercial includes CNAE `45`–`47` (trade); manufacturing CNAE `10`–`33`.

## Command-line usage

```powershell
python goiener_prepare.py --metadata "C:\path\to\metadata.csv" --archive "C:\path\to\imp-pre.tzst" --output "C:\path\to\GoiEner_cleaned_profiles"
```

Optional switches:

```powershell
python goiener_prepare.py --metadata metadata.csv --archive imp-pre.tzst --output processed --residential-tariff-proxy --wide-value average
```

For raw summed energy rather than per-customer average in the combined wide profile, use `--wide-value sum`. This can produce artificial changes when customer participation varies; the **average is recommended for the subsequent bus scaling**, while raw sums are already exported in the three sector CSVs.

## Generated files

| File | Contents |
|---|---|
| `residential.csv` | Dated residential aggregate (`load_kwh`, `load_kw`, `average_customer_kw`, `active_customers`, gap indicator) |
| `commercial.csv` | Dated commercial aggregate, same schema |
| `manufacturing.csv` | Dated manufacturing aggregate, same schema |
| `goiener_three_profiles.csv` | Full union of original category date ranges, possibly blank at the edges of individual sectors |
| `goiener_distributor_ready.csv` | **Longest uninterrupted common time interval** of all three sectors, no arbitrary year limit. Produced only if overlap is at least 24 hours. This is the file to import into the Load Distributor GUI v3. |
| `customer_quality_manifest.csv` | Customer ID, category, source CNAE, classification basis, interpolated hours, duplicates, invalid values, source-imputed counts |
| `unclassified_or_unused_customers.csv` | Customers excluded from the three-sector output |
| `quality_report.json` | Per-sector sample sizes, date coverage, source files and methodology |

One-hour kWh consumption is numerically equal to mean kW for that hour (i.e., `kWh / 1 hour`).

## Import to the existing Load Distributor GUI v3

1. Open GUI v3's **GoiEner importer** tab.
2. Click **Select existing converted CSV…**.
3. Select **`goiener_distributor_ready.csv`**, **not** `metadata.csv`, `imp-pre.tzst`, or the 3 separate category CSVs.
4. In the network tab load the desired feeder. The customer profile dropdowns should now contain:
   - `Residential-GoiEner-Aggregate`
   - `Commercial-GoiEner-Aggregate`
   - `Industrial-GoiEner-Aggregate`
5. Assign the three categories to the buses (bulk selection supported), then generate CSVs using **goiener** load mode. The distributor scales the chosen load shape to each bus's reference kW and retains the original base reactive-power ratio.

**Important:** GUI v3's time export may ask for a number of hours. That is a separate simulation/export operation. This cleaner never restricts the historical archive to 24 hours or one year. If the three categories do not overlap for at least 24 hours, the program does **not** fabricate matching dates and no distributor-ready file is written.

## Data quality caveats

- All internal customer gaps are interpolated regardless of length, as requested. Long fills can distort real behavior and forecasts. The manifest provides a count of imputed hours per customer.
- Individual customers enter or leave the dataset on different dates. The sector sum can jump as the number of active customers changes. The separate `average_customer_kw` and **wide average mode** address that for feeder profile *shape*, not for absolute national consumption estimation.
- Hourly timestamps from the source are assumed to share a consistent source clock. If they lack timezone offsets, ambiguous daylight-saving repeated hours are averaged and reported; this is not an authoritative timezone reconstruction.
- The period available in `imp-pre.tzst` ends before the COVID-19 phase. To process other GoiEner archive periods, the same script can be run on another compatible `.tzst` separately. It does not claim `imp-pre.tzst` alone contains all years through 2022.
- The cleaned data contains no reactive power, PV production, network topology, or voltage measurements. Those remain part of the network/simulation model.

## Testing status

The cleaner was tested on a **synthetic source-format archive** with all three sectors, an internal 3-hour gap, an invalid demand reading, and an unverified residential proxy case. These are implementation tests, **not** validation against the original 792 MB GoiEner archive, which is not attached in this conversation.

Source: [GoiEner Zenodo dataset](https://zenodo.org/records/7362094).
