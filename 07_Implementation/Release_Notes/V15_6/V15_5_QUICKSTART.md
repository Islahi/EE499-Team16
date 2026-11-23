# V15.5 Quick Start (Windows)

1. Extract the **entire ZIP** into a **new directory**, then run `RUN_APP.bat` (do not overwrite V15.4 while running).
2. Import your original `network.xlsx`, `load_profile.csv`, and `pv_profile.csv` files for the IEEE 33-bus network. Check your selected annual interval includes all 8,760 (or leap-year 8,784) hours.
3. Open **Settings → Operation**, choose **Sindi strict** and set a 24-hour reference look-ahead; set minimum PF to 0.95, daily SOC restoration, and the intended battery and grid limits.
4. In **Settings → Optimization**, enable Advanced Search if the GA controls are collapsed. Under **Allowed buses**, click **Select all** (or select exactly the buses you want to allow). All eligible non-slack buses will now be available to Joint GA: **no ranked weakness shortlist is applied**.
5. Set **GA population**, **generations**, **crossover**, **mutation** and parallel GA worker count. The default GA crossover is 0.80 and mutation is 0.20. More candidates increase exploration **and** representative-screening time.
6. Set **Annual verification fallback budget** to **3** (default) or **1** for the least verification work. The best stress-screened candidate is verified first; later candidates are annual-verified **only if it fails**. No savings or feasibility claim is made for unverified finalists.
7. Under Economics check inverter investment in **USD/kVA**, battery energy in USD/kWh, lifetime, interest, O&M, grid tariff, load-shedding penalty and curtailment penalty. Do not mix the separate legacy cost coefficients with the strict Sindi mode.
8. Run a **48-hour manual single-BESS simulation** before the full-year optimizer. In results, inspect `sindi_daily_audit.csv` and verify `soc_restored=True`, `pf_compliant=True`, plus zero unresolved voltage violations.
9. Run full-year optimization. The numerical result should appear before HTML generation. Review `fleet_units.csv` including `inverter_rating_kva`, `metrics.csv`, `sindi_daily_audit.csv`, `dashboard.html`, and the search/annual-verification metadata.
10. If HTML build fails, use `REGENERATE_SAVED_DASHBOARD.bat` on the saved results folder; numerical results and session registration should remain usable independently.

**Runtime warning:** An annual run still includes at least one 8,760/8,784-hour no-BESS baseline and one full-year accepted candidate. There is no empirically established speedup yet for this release, and Windows GUI testing remains necessary.

Reference: https://github.com/Islahi/EE499-Team16.git
