# EE499 BESS Planning Tool user guide

Use the desktop app to run a feeder power flow, simulate hourly operation with or without a battery, forecast demand and PV, and compare BESS sizes and locations on annual cost.

## Start the app on Windows

Open PowerShell in the project root. Install the dependencies once with the same Python you use to start the app.

```powershell
Set-Location .\07_Implementation
python -m pip install -r requirements-accelerated.txt
python -m src_accelerated.ui
```

Once the dependencies are installed, double-click `src_accelerated/app.pyw` or reuse the last command. Check that **FBS – Numba (CPU)** is ready before running a study. The first launch can take longer while Numba prepares the solver.

## Load the 15-bus case

1. Open **Load data**. Select the radial network `.xlsx` workbook and click **Load network** to inspect the buses and the workbook PV ratings. Verify the network format and frequency.
2. In the load tab, browse for the **GoiEner case folder**. It contains `load_profile.csv`, `bus_assignments_used.csv`, and `manifest.json`. You can also choose their parent folder and pick a case from the list. Extract a ZIP to a folder first. Use the workbook used by the distributor, since the app checks the bus IDs and any workbook hash in the manifest.
3. Enter the actual timestamp clock if the folder does not declare it. Use `UTC` or the actual IANA zone, such as `Asia/Riyadh`. The histories must contain continuous hourly timestamps. Prepare a continuous UTC timeline before importing data with repeated or missing daylight saving hours.
4. In **Solar / PV**, check **No PV study** for a load-only trial. For a PV study, verify the installed bus ratings in kW. Check **Use fallback solar source** if the study folder lacks usable PV history and you want to supply a CSV or provider.
5. Click **Prepare study**. The diagram opens with the first 24 hours of available history selected. Use **Base-case FBS** for one static workbook snapshot, or **Run simulation** for the selected hourly profiles.

A ready load example is `Validation/C2_Final_Test_Sector_Aggregation_Testbench/input` with `Validation/C2_Annual_Test/T04_15-Bus_System_1.xlsx`. The example has a zero-PV placeholder. Use the clock documented for your copy of the demand data.

## Choose a solar source

The app uses verified modeled PV history in the selected case when it is available. **Use fallback solar source** starts unchecked, with its source and file controls hidden. Check it to choose a CSV or provider. The selected fallback is used only if PV is installed and the folder lacks usable history.

| Source | What to enter |
| --- | --- |
| NASA POWER or Open-Meteo automatic history | Actual site latitude and longitude. The app requests hourly historical irradiance in UTC and aligns it to the load clock. |
| NASA POWER irradiance CSV | Raw hourly POWER table or processed CSV with `timestamp` and `ghi_wh_m2` or `irradiance_w_m2`. Review coordinates and confirm the file clock. |
| Open-Meteo irradiance CSV | Hourly `time` and `shortwave_radiation (W/m²)`. Supply the site and file clock if absent from the file. |
| Prepared irradiance CSV | `timestamp,irradiance_w_m2`, site, and file clock. |
| Historical modeled PV power CSV | A single common `timestamp,p_kw` series, its positive reference nameplate in kW, site, and file clock. The app scales the reference capacity factor to each installed bus. |
| No PV study | Bypass solar import and PV forecasting. |

For irradiance conversion, the reference nameplate defaults to the sum of installed PV kW. A modeled-power import needs its own reference nameplate. A NASA LST file needs a documented timestamp conversion before use. Review the PV installation table before preparing. Positive workbook ratings take precedence over folder suggestions. If the two differ, review the conflict and edit the table to choose the final installation. Zero-only folder ratings leave workbook ratings and manual edits in place.

## Select the interval or generate a forecast

- Open **Study interval** to choose historical data or a generated forecast. Use **First 24 hours**, **7 days**, **30 days**, **Full calendar year**, **Full source**, or a custom window. The start is included and the end is excluded. Click **Apply interval** to use the new selection.
- Open **Forecast** to choose a training start, training end, and horizon. Keep at least 8,760 consecutive training hours and place the origin one hour after the training end. A short active simulation interval can coexist with several years of training history.
- Demand models fit residential, commercial, and manufacturing sector sums and distribute the forecasts back to their buses. PV uses a separate XGBoost fit on historical modeled electrical power. The future PV prediction uses calendar features and applies the physical night mask.
- Check the active source and dates before running the simulation. Select a forecast window explicitly if the study is currently using history.

## Simulate and optimize BESS

1. **Technical comparison.** Run the selected interval with **Manual BESS** unchecked for the no-storage case. Enable **Manual BESS**, select the bus, and enter kW, kWh, SOC and efficiency settings. Keep the same profile window and limits for a comparable second run.
2. **Annual optimization.** Select **Full calendar year** and click **Apply interval**. The active window must span January 1 at 00:00 to the next January 1 at 00:00. A June-to-June forecast with 8,760 hours can be simulated. To optimize from a forecast, generate enough coverage for a complete January-to-January period, then select that period. Enter and confirm import and export tariffs in USD/kWh, including an explicit zero if export earns nothing. Review BESS costs, ownership assumptions, grid limits, curtailment and unserved-energy penalties.
3. In economic settings choose **Return to initial SOC** or **Price terminal energy difference**. Equal SOC schedules actual charge or discharge near the end and respects the configured limits. If the rule cannot restore SOC under those limits, the candidate is infeasible. Priced energy requires a positive replacement price. It charges an energy deficit at that rate after charging losses and credits surplus at the configured export rate after discharge losses.
4. Select GWO or GA, eligible non-slack buses, and minimum, maximum and step for kW and kWh. Save settings and run optimization. The app compares the best feasible battery candidate with a no-BESS run over the same hours and tariffs and can select no BESS.

A short technical simulation reports energy and electrical performance over its selected hours. Annual optimization needs the whole calendar period and confirmed prices. Use **Equal terminal SOC for technical runs** in Battery & dispatch to require closure on short runs too.

## Review and reopen a study

- Check run completion, FBS convergence, feasibility, voltage limits, load shedding and PV curtailment. A converged result can still have violations or unserved demand.
- Enable **Show run log** to see each completed simulation time step with its source timestamp and FBS status. The log follows the latest entry. The session's `session.log` retains all hourly entries, including entries beyond the display limit. **Base case** reports one static snapshot and its FBS iterations.
- Review the Network and Results views. After a simulation, use the timestamp and network result controls to inspect individual hours. Session folders under `src_accelerated/Results/Sessions` contain input snapshots and numbered run exports.
- Open **Study interval** and browse to a saved session folder containing `session.json`. It opens read-only. Choose **Migrate compatible inputs to a new study ID** to create a fresh study, then configure the interval, tariffs and optimizer again.

| If the app says… | Check… |
| --- | --- |
| No valid GoiEner case | The folder is extracted and contains the three required files, or is their parent folder. |
| PV history is absent or a placeholder | If PV is installed, add a historical source with complete coverage and the correct clock. Otherwise choose No PV study. |
| Annual evaluation is unavailable | Confirm both tariffs and select a full calendar year. |
| Terminal SOC closure failed | Review BESS power, reserve and PCC headroom. For annual studies with an appropriate replacement price, priced terminal accounting is also available. |
