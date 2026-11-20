# GoiEner — Combined three-category cleaned profiles

This dataset merges the **Pre**, **During**, and **Post** outputs from the uploaded `Cleaned.zip`, derived from the original GoiEner Zenodo record **7362094**. Original input files were not modified.

## Use this file for the load distributor

**`goiener_distributor_ready.csv`** — 43,969 consecutive hourly records, from **2017-05-31 00:00** through **2022-06-06 00:00**, inclusive. Columns are exactly the same as in the original cleaner:

- `timestamp`
- `Residential-GoiEner-Aggregate`
- `Commercial-GoiEner-Aggregate`
- `Industrial-GoiEner-Aggregate`

All three category columns have valid readings at every timestamp. The entries are **average kW per active customer**, not the sum of customers' power demands. Use the existing load distributor to assign the three category shapes to your distribution network buses. This package does **not** make bus assignments or export `load_profile.csv` itself.

## Other files

- **`goiener_three_profiles.csv`** — maximum available union from **2014-11-02 01:00** through **2022-06-08 00:00** (66,600 hourly records). Some category values are blank before the common start and after the common end. Do **not** feed this directly into forecasting or distribution without handling missing categories.
- **`sector_details/{residential,commercial,manufacturing}.csv`** — original per-category hourly sums, per-customer average, active meter counts, and missing-data flags, stitched into a single history each.
- **`source_periods.csv`** — original archive (`Pre`, `During`, or `Post`) selected for each timestamp in the all-history union.
- **`boundary_comparison.csv`** — two duplicated boundary timestamps and the different observations in their adjacent archives.
- **`monthly_category_means.csv`** — monthly average of the three combined category profiles, for diagnostic purposes only.
- **`quality_report.json`** — merge details, selected date ranges, boundary resolution, input settings, and limitations.

## Merge rules

1. Preserve original cleaned category means; **no extra interpolation, normalization, or smoothing**.
2. At the only two duplicated hours, choose **During** over **Pre** at 2020-03-01 00:00 and **Post** over **During** at 2021-05-31 00:00.
3. Retain the original three-column category schema and ascending hourly timestamps.
4. Limit the *distributor-ready* output to the period with **all three sectors available every hour**.
5. Keep the longer union separately with missing categories marked as blank (CSV NaN).

## Interpretation cautions

- The meter populations differ across the original archives. Sudden changes at archive boundaries can reflect **customer-cohort changes**, not only demand behavior. Compare the boundary file and monthly means before drawing conclusions about COVID effects or model accuracy.
- All three uploaded `quality_report.json` files say **`residential_tariff_proxy_enabled: true`**. The category definition therefore includes an unverified `2.x` tariff residential proxy. This was **not** changed or reclassified during merging.
- The original cleaner notes that timestamp zones are not certified and duplicate daylight-saving-time hours were collapsed. Align source-clock timestamps with NASA POWER's UTC timestamps before combining load and PV data.
- For a single **one-year-ahead C2 benchmark**, a possible split is **training 2017-05-31 through 2020-12-31, testing 2021-01-01 through 2021-12-31** (8,760 hours). The COVID regime shift and cohort transitions should be discussed when interpreting results.
- **This package is load data only.** It does not contain NASA POWER PV data or a PV/load fusion dataset.

## Reproduce the merge

Install `pandas` and `numpy` and run the included script, supplying the uploaded `Cleaned.zip`:

```powershell
python -m pip install pandas numpy
python merge_cleaned.py --input Cleaned.zip --output GoiEner_Combined_Rebuilt
```

Run in an empty output folder. The script validates timestamp continuity, duplicated hours, required columns, and agreement between the wide and distributor-ready profiles.

Original project repository: https://github.com/Islahi/EE499-Team16.git
