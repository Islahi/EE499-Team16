# Change log — v4: Weekly/Monthly detail and simpler Monthly default

- Added **Weekly** and **Monthly** resolutions to the Detail dropdown, alongside Default, Hourly, and Daily.
- Changed **Monthly / Default** to a **single weekly-aggregated plot**, not two daily and weekly plots.
- Updated Default resolution mapping: Daily → Hourly; Weekly → Daily; Monthly → Weekly; Yearly → Monthly.
- Users may explicitly choose Hourly, Daily, Weekly, or Monthly for **any** plot period and any custom date range, including multi-year spans.
- Switching Period now resets Detail to Default so the period's intended default view reliably appears; Start/End calendar controls continue to work as in v3.
- Applies consistently to Load, NASA, and Compare plotting modes. Checkboxes still redraw automatically.
- Added and updated regression tests for plotting intervals, two-panel comparison, dropdown choices and period switching.
- No source data, network files, battery optimization code or PV calculations changed.
