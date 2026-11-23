# V15.6 quick start

1. Open `07_Implementation` and launch `start_windows.bat`.
2. To restore **the previous successful run** that was incorrectly recorded as failed, open Command Prompt in `07_Implementation` and run:

   ```bat
   python RECOVER_ARCHIVED_RUN.py "C:\Users\ISLAHI\Music\Case Example\BESS_Planning_Tool\Results\Sessions\20261123_030642_ieee_33bus_network_data"
   ```

   Adjust the path if your actual Sessions folder is elsewhere. Use the saved **session root**, containing `session.json`.
3. Rebuild its dashboard separately if needed:

   ```bat
   REGENERATE_SAVED_DASHBOARD.bat "C:\Users\ISLAHI\Music\Case Example\BESS_Planning_Tool\Results\Sessions\20261123_030642_ieee_33bus_network_data\optimization\run_001"
   ```

The recovery script backs up `session.json` automatically and will refuse to promote a genuine simulation failure. No GA or annual re-run is needed for this already verified result.
