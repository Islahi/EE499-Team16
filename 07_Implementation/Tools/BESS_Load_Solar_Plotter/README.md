# BESS Distributed Load & NASA POWER Plotter

A standalone Windows/Python GUI that plots **loads already distributed to feeder buses**, not the original GoiEner customer files.

## Quick start (Windows)

1. Unzip the package to a normal folder.
2. Double-click `start_windows.bat` (Python 3.10+ recommended; internet required to install dependencies once).
3. Click **Add ZIP(s)** and choose one or more ZIPs exported by your GoiEner Load Distributor. The GUI finds every feeder folder containing `load_profile.csv` and `bus_assignments_used.csv`.
4. Select the feeder on the left. The program sums hourly loads by the categories assigned to the buses: Residential, Commercial, Manufacturing, and Total.
5. Select **Daily / Weekly / Monthly / Yearly** and use the new **Start** and **End** date spin controls (separate year/month/day fields, with arrow buttons). On each period change, Detail resets to Default and End automatically resets to one inclusive period after Start (see table below). Changing Start continues to move End automatically until you manually edit End. You may override End to show multi-year windows. Press **Use full available range** to select the whole dataset; the previous/next arrows shift the selected window.
6. For solar plots, click **Import NASA CSV(s) for one location**. You may select several individual monthly files for the **same** NASA location; name the group (e.g. Bilbao). Repeat for other locations.
7. Choose **Load**, **NASA**, or **Compare**. The **Residential, Commercial, Manufacturing, Total feeder, Unclassified, GHI, DHI, DNI, and Temperature** checkboxes refresh the plot automatically (after a short debounce). They do **not** require changing the period or clicking Plot. You can export the visible charts as PNG/SVG and **only the displayed columns** as CSV.

From a terminal:

```powershell
python -m pip install -r requirements.txt
python gui.py
```

The GUI does **not** alter the network Excel workbook, voltage setpoints, topology, or simulation input ZIP.

## Plotting design

| Period | Default resolution | Detail options |
| --- | --- | --- |
| Daily | Hourly (24 points per day) | Hourly, Daily, Weekly or Monthly |
| Weekly | Daily (7 points per complete week) | Hourly, Daily, Weekly or Monthly |
| Monthly | **Weekly (one chart only)** | Hourly, Daily, Weekly or Monthly |
| Yearly | Monthly (12 points per complete year) | Hourly, Daily, Weekly or Monthly |

### Default date windows (new in v3)

| Period selection | Inclusive End date calculated from Start |
| --- | --- |
| Daily | Same day (1 day) |
| Weekly | Start + 6 days (7 days) |
| Monthly | Start + 1 calendar month − 1 day |
| Yearly | Start + 1 calendar year − 1 day |

Examples with Start = `2017-06-12`: Daily → `2017-06-12`, Weekly → `2017-06-18`, Monthly → `2017-07-11`, Yearly → `2018-06-11`. These are **rolling windows**, not a forced calendar-month/year boundary. The date spin controls clamp invalid dates, for example February 31 to the last valid day of February.

- Switching **Period** resets End to its standard window, even if End was previously edited manually.
- Changing **Start** while using a standard window recalculates End automatically.
- Editing **End** manually enables a custom range; you may select more than one day/week/month/year and continue viewing it. Changing Period again returns to the standard window.
- **Use full available range** selects the available span and enables the custom-range behavior.
- The chart is refreshed when the date spinboxes are changed using arrows or when edited text is committed by Enter/focus-out. The Detail dropdown now includes **Weekly** and **Monthly** as well as Hourly and Daily. Switching Period resets Detail to Default; load and NASA checkboxes retain their live updates.

- **Hourly load:** kW (average power for each one-hour sample).
- **Daily/weekly/monthly load:** kWh (sum of hourly kW × 1 h), displayed as MWh automatically when values are large.
- **Average power** setting: shows mean kW per day/week/month, rather than energy.
- **Normalized** setting: divides each shown series by its maximum over the selected plot window. This makes profile shapes comparable; the ordinate becomes dimensionless.
- **NASA hourly:** GHI, DHI, DNI in W/m².
- **NASA daily/weekly/monthly:** irradiation in kWh/m², calculated by summing hourly W/m² × 1 h / 1000.
- **Temperature:** optional separate right-side axis in °C.
- **Date ranges:** both endpoints are inclusive, including the last selected day's 23:00 observation. A two-year range works with any period/resolution choice. For example, **Yearly / Default** gives 24 monthly values for two complete years; **Monthly / Default** gives **one weekly-aggregated chart** across *all* selected months.
- **Partial calendar buckets:** weeks begin Monday, and aggregation uses only the selected hours. When a range starts or ends inside a month, the first/last monthly totals can be much smaller because they are incomplete; the plot shows a note. A partial week also contains only the selected dates. Use **Average power** to compare periods of different durations without misinterpreting total energy as a change in typical load.
- **Responsive controls:** changing any load or NASA channel checkbox immediately schedules a redraw; no need to click Plot. The left control panel scrolls on smaller monitors so all options remain accessible.


### Automatic load separation

For each hourly bus record (`timestamp,bus_id,p_kw,q_kvar`), the program uses `bus_assignments_used.csv` to determine which type the bus belongs to. It then computes:

- Residential = sum of `p_kw` at residential buses.
- Commercial = sum of `p_kw` at commercial buses.
- Manufacturing = sum of `p_kw` at manufacturing/industrial buses.
- Unclassified = nonzero loads at buses with no recognizable assignment.
- Total = sum of all four categories.

No network classification is inferred from a bus number. No FBS voltage results are calculated. The source ZIP contains **load values only**, so the voltage settings remain unchanged. If a source ZIP contains zero-PV placeholder values, the plotter does **not** treat those as solar observations.

### NASA CSV format

The importer accepts NASA POWER *hourly point* CSVs with columns such as:

```csv
YEAR,MO,DY,HR,ALLSKY_SFC_SW_DWN,ALLSKY_SFC_SW_DIFF,ALLSKY_SFC_SW_DNI,T2M
2018,1,1,0,0,0,0,8
2018,1,1,1,0,0,0,7
```

The importer also skips the usual NASA POWER text preamble above the real header. NASA numeric missing-value sentinels (−999 etc.) are treated as missing, not as negative irradiance. Duplicated timestamps between overlapping monthly downloads are averaged, **not summed**.

**Time zones:** NASA POWER requests may use UTC or Local Solar Time. For `time-standard=UTC`, choose `UTC → Europe/Madrid` when comparing to Spain-local GoiEner timestamps. The alternative **Use CSV timestamps as written** is provided for data already aligned with the distributed load. Spain daylight-saving changes can create a skipped hour or a repeated local hour; the importer averages duplicates. Check the timestamp convention of your cleaned GoiEner files before interpreting correlations—this GUI cannot prove the input timestamp convention.

**Different NASA sites:** import separate site groups rather than merging Madrid and Bilbao values together as if they were one weather station. Your GoiEner consumption covers many Spanish provinces, so irradiance is an *approximate representative-site* observation, not meter-specific rooftop irradiance.

## Multiple networks / performance

You may import multiple distributor ZIPs or a batch ZIP containing many feeders. Select a network from the list to plot it. `load_profile.csv` can contain millions of bus-hour records: the importer processes it in chunks and keeps only the aggregated hourly series in memory. Already-loaded networks are cached during the session.

For a repeatable preprocessing run without opening the GUI:

```powershell
python aggregate_from_zip.py "path\to\GoiEner_Distributed.zip" -o prepared
```

This produces one `*_hourly_aggregated.csv` and an info JSON per feeder. You can then use **Add prepared CSV** for fast reloads.

## Files in this package

- `gui.py` — Tkinter GUI; feeder selection, controls, NASA import, plotting and export.
- `data_engine.py` — streaming load aggregation and NASA POWER CSV reader.
- `plot_engine.py` — daily/weekly/monthly/yearly figures with correct power/energy units.
- `aggregate_from_zip.py` — optional command-line pre-aggregation of all feeders.
- `examples/85_bus_hourly_aggregated.csv` — **real aggregated** output produced from the 85-bus ZIP you uploaded (24,144 hourly timestamps). This example contains **no raw household GoiEner measurements**.
- `examples/*.png` — charts rendered directly from the real uploaded 85-bus data (not synthetic).
- `tests/` — automated tests.

## Run tests

```powershell
python -m pytest -q tests
```

## Limitations

- Requires Python (desktop Tkinter, pandas, NumPy, Matplotlib); this is **not a compiled Windows EXE**.
- Needs `bus_assignments_used.csv` to classify loads; a ZIP with only `load_profile.csv` is insufficient to separate customer types.
- Does not estimate PV power from irradiance. Solar irradiance is displayed as NASA weather data, not BESS network PV generation.
- No extra forecasting, data-quality scoring, interpolation, or BESS optimization code is added here.
- The example contains one 85-bus feeder. The loader supports any number of feeder folders sharing the same source-CSV schema.

## Scientific/data provenance

- Load inputs: pre-distributed GoiEner profiles from the user-provided `GoiEner_Distributed_20261103_155520_131082.zip`; see that ZIP's `manifest.json` for original source, date range, and stated classification assumptions.
- Solar inputs: when selected, come from the **NASA POWER** hourly point API (`https://power.larc.nasa.gov/`). No NASA measurements are bundled here because none were supplied in the current turn.
