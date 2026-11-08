# GoiEner multi-year load data: original download and profile selection

**Source:** Carlos Quesada Granja, Cruz Enrique Borges Hernández, Leire Astigarraga & Chris Merveille, *GoiEner smart meters data*, Zenodo (2022), DOI: https://doi.org/10.5281/zenodo.7362094  
**Associated paper:** *An electricity smart meter dataset of Spanish households: insights into consumption patterns*, Scientific Data, https://doi.org/10.1038/s41597-023-02846-0

## What this kit is and is not

This ZIP **does not contain the original GoiEner data**, because the remote download was blocked in the ChatGPT execution environment. It contains a Python downloader and extractor for the public Zenodo files. The published dataset contains hourly metered consumption from Spain, with varying customer date ranges. It is not Saudi Arabian metered data and it does not include co-timed PV measurements for every customer.

## Dataset files to obtain

| Filename | Approx. compressed size | Why it is relevant |
|---|---:|---|
| `metadata.csv` | 5.6 MB | Source for anonymized client IDs, date coverage, CNAE activity codes and tariffs |
| `imp-pre.tzst` | 791.6 MB | Hourly processed pre-COVID consumption series for more than one year, including imputation flags |
| `imp-in.tzst` | 555.9 MB | During COVID period; **not recommended** for a simple stable pre-pandemic forecasting study |
| `imp-post.tzst` | 508.2 MB | Later period; customer date coverage differs |

The pre-2020 archive decompresses to roughly 6.28 GB. **You need several gigabytes of free disk space**, and the downloader supports continuation after interruptions where the host supports HTTP Range. Verify the original dataset licensing on the Zenodo record before redistribution; the record mentions CC-BY-SA while the associated paper describes CC BY 4.0.

## Setup (Windows/Mac/Linux)

```bash
python -m pip install -r requirements.txt
```

Download only the small metadata file first:

```bash
python goiener_tool.py download
```

Fetch both metadata and the large hourly archive (approximately 792 MB compressed):

```bash
python goiener_tool.py download --with-pre
```

If the automated download is blocked, open https://zenodo.org/records/7362094 and **download `metadata.csv` and `imp-pre.tzst` manually**. Place both files in the `goiener_original/` directory next to the script. The downloader verifies original MD5 checksums reported by Zenodo.

## Extract a three-year training/validation/testing interval

```bash
python goiener_tool.py extract --start 2017-01-01 --end 2019-12-31 --max-per-sector 5
```

**This does not guarantee three profiles exist with these exact dates in every category.** The tool checks metadata coverage, streams the Zstandard-compressed TAR archive without extracting every customer, and exports only qualifying customer series. Each selected file has `timestamp,kWh,imputed,p_kw_avg`. For a one-hour meter interval, kWh per hour is numerically average kW. It also writes a data-quality manifest. Default thresholds: >=98% timestamp coverage of the specified window, <=10% imputed hours. Missing timestamps are **not silently filled**.

If a category has no eligible customers, try the two-year interval:

```bash
python goiener_tool.py extract --start 2017-01-01 --end 2018-12-31
```

Use actual chronology in forecasting: for the three-year window, train on 2017, validate on 2018, and test on 2019. Do not randomly shuffle hourly data.

## Customer classification limitations

- **Manufacturing:** CNAE section `C` or 2-digit codes 10–33 (verified economic-activity classification).
- **Commercial retail/trade:** CNAE section `G` or codes 45–47 (only this subset of commercial activities; other services are not included by default).
- **Residential:** The formal CNAE `T` or codes 97–98 refer to *households as employers*, **which should not be assumed to cover all residential electricity accounts**. Accordingly the extractor's residential selection can be empty. This is a significant limitation of using economic-activity codes for residential labels. 
- Optional `--residential-fallback-tariff` includes otherwise-unclassified customers on a 2.X tariff as **residential_unverified_tariff**, clearly labeled as uncertain; tariffs 2.X can also serve small businesses, so do not cite these as confirmed households. Confirm with dataset methodology and customer metadata before interpreting sector assignments.

**Do not claim the data supplies balanced three-sector cohorts until you have verified actual qualifying series.** Many customers have different start/end dates and not all cover the same 2017–2019 window.

## Connecting to the BESS Load Distributor GUI

The extractor makes individual customer time series, not a finished per-bus CSV. To use them for your network, select verified customer profiles, normalize to each bus's documented reference demand, map load categories to buses, preserve network parameters, and then export `timestamp,bus_id,p_kw,q_kvar`. Your BESS GUI may require an additional input adapter for these multi-year profiles; do not assume it can import this layout unchanged.

## Scientific citation

Quesada Granja, C., Borges Hernández, C. E., Astigarraga, L., & Merveille, C. (2022). *GoiEner smart meters data* (Version 1) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.7362094

The above data is not included in this helper package.
