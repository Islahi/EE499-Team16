# Standalone implementation tools

- `GoiEner_Multiyear_Download_Extractor/` downloads, verifies, and selectively
  extracts the original GoiEner archive.
- `GoiEner_Three_Category_Cleaner/` prepares the three category profiles and
  quality reports.
- `GoiEner_Load_Distributor_Simple/` maps category load shapes to supported
  feeder workbooks without modifying their electrical parameters.
- `BESS_Load_Solar_Plotter/` plots distributed feeder load alongside imported
  NASA POWER data.

Each tool is intentionally independent and keeps its own README, requirements,
launcher, examples, and tests. Generated outputs and original large archives
do not belong in Git.
