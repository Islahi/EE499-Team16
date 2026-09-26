# Jeddah Weather and PV Data

This folder contains the supplied research summary and the two complete 2024 hourly datasets identified in that summary. The location is Jeddah, Saudi Arabia, near 21.4858° N, 39.1925° E.

## Files

- `Jeddah_Weather_PV_Data_for_BESS_Research.pdf` — supplied summary of Jeddah climate, solar-resource values, BESS implications and data sources.
- `NASA_POWER_Jeddah_2024_Hourly.csv` — NASA POWER hourly renewable-energy data in Local Solar Time.
- `OpenMeteo_Jeddah_2024_Hourly.csv` — Open-Meteo historical archive data in Asia/Riyadh local time.

Both CSV files cover 1 January through 31 December 2024. Because 2024 is a leap year, each file contains **8,784 hourly records**, not 8,760.

## NASA POWER data

Downloaded from the official NASA POWER Hourly API on 26 September 2026:

`https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,ALLSKY_SFC_SW_DWN,ALLSKY_SFC_SW_DNI,ALLSKY_SFC_SW_DIFF,RH2M,WS2M&community=RE&longitude=39.1925&latitude=21.4858&start=20240101&end=20241231&format=CSV&time-standard=LST`

Included variables:

- `T2M`: air temperature at 2 m (°C)
- `ALLSKY_SFC_SW_DWN`: all-sky downward shortwave irradiation (Wh/m² per hour)
- `ALLSKY_SFC_SW_DNI`: direct normal irradiation (Wh/m² per hour)
- `ALLSKY_SFC_SW_DIFF`: diffuse irradiation (Wh/m² per hour)
- `RH2M`: relative humidity at 2 m (%)
- `WS2M`: wind speed at 2 m (m/s)

NASA POWER uses `-999` for unavailable values. Validation found no `-999` values in this download.

## Open-Meteo data

Downloaded from the official Open-Meteo Historical Archive API on 26 September 2026:

`https://archive-api.open-meteo.com/v1/archive?latitude=21.4858&longitude=39.1925&start_date=2024-01-01&end_date=2024-12-31&hourly=temperature_2m,relative_humidity_2m,shortwave_radiation,direct_normal_irradiance,diffuse_radiation,wind_speed_10m&timezone=Asia%2FRiyadh&wind_speed_unit=ms&format=csv`

Included variables:

- temperature at 2 m (°C)
- relative humidity at 2 m (%)
- shortwave radiation, direct normal irradiance and diffuse radiation (W/m², preceding-hour mean)
- wind speed at 10 m (m/s)

Validation found no blank values in the hourly columns.

## Modeling cautions

- The two sources are independent reanalysis/satellite products and should not be mixed row-by-row without documenting the choice.
- NASA wind is measured/modelled at 2 m, while Open-Meteo wind is at 10 m.
- NASA hourly radiation is reported as energy per area for the hour (Wh/m²); Open-Meteo radiation is an hourly mean power density (W/m²). They are numerically comparable for one-hour intervals but are not the same physical quantity.
- NASA Local Solar Time and Asia/Riyadh civil time are both UTC+3 for these files, but the definitions should remain explicit in code and reports.
- Use one dataset as the primary simulation input and the other for sensitivity or plausibility checks rather than averaging them without justification.

Provider documentation and licensing terms remain authoritative. Cite NASA POWER or Open-Meteo, as applicable, in reports and code derived from these files.
