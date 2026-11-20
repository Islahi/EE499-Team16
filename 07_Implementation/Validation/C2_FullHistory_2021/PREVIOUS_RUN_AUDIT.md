# Previous C2 benchmarking timing audit

Source: previously uploaded `C2_model_benchmark_results.zip` (November 15–16, 2026).

- First success completion UTC: 2026-11-15 18:03:54.
- Last success completion UTC: 2026-11-16 00:37:01.
- Time between those records: **6 h 33 min 7 s**. This is a lower bound on complete process start-to-finish because setup preceded the first completed run and reporting may have followed the last.
- Sum of successful model fit + predict times: **6.30 hours**.
- Sum of saved per-job elapsed timings (including failures): **6.55 hours**.
- Total planned job statuses = 441: 245 OK, 175 SKIPPED_UNSUPPORTED, 21 FAILED.
- Seven `AutoARIMA monthly_30d` cases failed on memory; seven `AutoETS monthly_30d` cases and seven `HoltWinters monthly_30d` cases had `Parameters out of range` errors.

This file does not claim the previous computer's CPU, RAM, or power level; new experiment runtimes may differ.
