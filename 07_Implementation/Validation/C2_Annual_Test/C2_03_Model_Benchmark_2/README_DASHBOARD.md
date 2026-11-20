# Model benchmark 2 dashboard

1. In Windows Explorer, choose **Extract All** on the ZIP and open the extracted folder.
2. Double-click **START_DASHBOARD.bat** or open **Dashboard.html** directly in a current version of Edge, Chrome or Firefox. The data and chart code are embedded. Internet access and Python are optional.
3. Choose a dataset. The hourly chart starts on July 1–14, 2019. Click a model in the rankings or choose a configuration and click **View configuration**. Click the comparison button to restore the default series.
4. Use **Analysis** for residuals, absolute errors, error distributions or seasonal profiles. Change **Resolution** for daily, weekly or monthly results. **Period integral** gives kWh for power or Wh/m² for irradiance. Seasonal resolution selects hour of day, weekday, ISO week or month.
5. Choose **Custom dates** for another interval, or **Full year** for March 1, 2019 through February 29, 2020. Hover for exact values, click a legend item to toggle visibility, scroll to zoom and drag to pan. **Reset view** restores the standard range. The metric tables always use the entire test year.

## PowerShell alternative

Open PowerShell in the extracted folder that contains Dashboard.html. For example:

```powershell
cd "$env:USERPROFILE\Downloads\C2_03_Model_Benchmark_2"
py -3.14 -m http.server 8000 --bind 127.0.0.1
```

Open http://127.0.0.1:8000/Dashboard.html in the browser. To stop the server, press Ctrl+C in PowerShell. If port 8000 is occupied, use 8001 in both the command and address. If your Python version differs, use `py -3` or `python` in place of `py -3.14`.

## Troubleshooting

For a blank or slow page, wait for the embedded series to decode, open the extracted HTML in the browser directly and enable JavaScript. An up-to-date browser with gzip DecompressionStream support is required. For a missing file, incomplete download or a server 404, confirm that `Get-Item .\Dashboard.html` succeeds in the server folder or extract the complete ZIP again. The dashboard works offline in direct-file mode. The included PDFs and PNGs also open offline.
