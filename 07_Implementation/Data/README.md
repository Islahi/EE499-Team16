# Versioned study data

This directory contains the compact datasets required to reproduce the current
data-preparation and plotting workflow:

- `GoiEner_Cleaned_Profiles/` contains the three cleaned category profiles, the
  distributor-ready common interval, customer-quality manifest, exclusions,
  and processing report generated from the checksum-verified GoiEner archive.
- `NASA_POWER/` contains five hourly NASA POWER point downloads used as
  representative Spanish irradiance and temperature inputs.

The original GoiEner `imp-pre.tzst` archive is about 755 MiB and is not stored
in Git. Keep it under the ignored
`../Tools/GoiEner_Multiyear_Download_Extractor/goiener_original/` directory or
restore it with that tool's `goiener_tool.py`. The expected checksums and source
record are documented beside the downloader.

The cleaned categories are research inputs, not proof that all customer labels
are ground truth. Read `GoiEner_Cleaned_Profiles/quality_report.json` and the
cleaner README before interpreting residential, commercial, or manufacturing
results.
