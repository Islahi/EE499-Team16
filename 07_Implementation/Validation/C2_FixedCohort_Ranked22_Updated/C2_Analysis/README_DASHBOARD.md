# Open the C2 forecast dashboard on Windows

**Fastest route:** Extract the ZIP, open its `C2_Analysis` folder and double-click `START_DASHBOARD.bat`. It opens the residential comparison immediately. The HTML file includes its forecast data, plotting code and styles. Opening it offline requires only a current browser.

## A. Open the HTML directly

1. In File Explorer, right-click the ZIP and choose **Extract All**. Choose a short local path such as `C:\EE499` for the full collection.
2. Open the extracted `C2_Analysis\00_Overview` folder. Double-click **C2_Forecast_Explorer.html** or right-click it and select **Open with → Microsoft Edge** or **Google Chrome**.
3. If you downloaded the HTML separately, you can open that file by itself. The first screen shows residential actuals, daily AutoARIMA and the three leading candidates for July 1–14, 2021.

Direct opening is supported. No Python, internet connection or neighboring CSV files are required. Use a browser tab rather than a ZIP or web-download preview pane.

## B. Serve the extracted folder with Python

In PowerShell, change the example path to your actual extracted folder. The folder you select must contain `START_DASHBOARD.bat` and `00_Overview`.

```powershell
Set-Location -LiteralPath 'C:\EE499\C2_Analysis'
Test-Path -LiteralPath '.\00_Overview\C2_Forecast_Explorer.html'
py -3.14 -m http.server 8000 --bind 127.0.0.1
```

`Test-Path` should return **True**. Leave this window open. In the browser address bar enter:

```text
http://127.0.0.1:8000/00_Overview/C2_Forecast_Explorer.html
```

The service root is `http://127.0.0.1:8000/`; the dashboard entry point relative to that root is `00_Overview/C2_Forecast_Explorer.html`. Press **Ctrl+C** in the server window when finished.

If port 8000 is occupied, use another port for both the command and the URL:

```powershell
py -3.14 -m http.server 8081 --bind 127.0.0.1
```

Open `http://127.0.0.1:8081/00_Overview/C2_Forecast_Explorer.html`. If Python 3.14 is unavailable, use `py -3` or a working `python` command in its place. The server uses the Python standard library. Method A and the launcher work without Python.

## C. Use the Windows launcher

Double-click `START_DASHBOARD.bat` in the extracted root, or run `.\START_DASHBOARD.bat` from PowerShell. It locates the dashboard relative to its own file, checks that the HTML exists and opens it in the default browser. It uses direct-file mode. Keep the launcher beside the `00_Overview` folder. If your default HTML application is an editor, open the HTML via **Open with**.

## Explore the forecasts

- **Compare models.** Choose a dataset or bus and click **Actual + ARIMA + top 3**. Choose a configuration and click **View configuration**, or click a row in the rankings table, for an individual comparison. Click a legend entry to hide or restore its trace.
- **Inspect a date.** Standard hourly forecast and error traces show 336 hourly samples, July 1 at 00:00 through July 14 at 23:00. Choose **Custom dates** to set an inclusive date range anywhere in 2021, or **Full year** for the entire trace. Wheel to zoom, drag to pan, and move the pointer to inspect values. **Reset view** restores the standard range.
- **Aggregate.** With **Standard range** selected, daily, weekly and monthly views include the full year. Choose mean power or integrated energy. Sector cohorts use kW/customer and kWh/customer. Other targets use kW and kWh. Edge calendar weeks include only their 2021 hours.
- **Examine errors.** Select signed residual, mean absolute error, error distribution or seasonal profile to view one analysis at a time. Error distributions and seasonal profiles default to the full year. Highest- and lowest-error periods are supplemental views with separately shown dates.
- **Read the comparison.** The annual metric table and the percentage-improvement table use all 8,760 hours regardless of the visible dates. Positive improvement means the displayed model reduced error relative to AutoARIMA__daily. A dash indicates an undefined comparison. The zero-load slack bus has actual and baseline traces only in its main view.

## Troubleshooting

| Symptom | What to check |
|---|---|
| Blank page or no chart | Open the downloaded HTML in a current Edge, Chrome or Firefox tab and allow JavaScript for that page. Wait for the first plot. Use Method B if browser policy blocks direct file access. |
| Data/JavaScript fails to load | The data and plotting code are embedded in the approximately 34 MiB HTML file. Extract or download it again if the file is truncated. There is no external JavaScript bundle to install. |
| Address already in use | Change both the Python port and browser URL to 8081 or another free port. |
| Directory listing, 404 or wrong working directory | Run `Get-Location` and the `Test-Path` command above. The server root should contain `00_Overview`. Use the complete entry-point URL. |
| Launcher reports a missing dashboard | Extract the entire ZIP, then run the launcher from the root of the extracted package. To use a separately downloaded HTML file, use Method A. |
| Slow first load | Copy the HTML to a local disk and open one tab. Initial loading reads the embedded data file. Select a single configuration or a shorter interactive date range for lighter rendering. |
| No internet connection | Both direct and local-server methods use local files. A local server is accessible while its PowerShell window is running. |
