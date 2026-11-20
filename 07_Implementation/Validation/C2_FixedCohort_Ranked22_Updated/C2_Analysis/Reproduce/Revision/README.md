# Regenerate the figures from saved forecasts

In a clean working directory, unpack the analysis as C2_Analysis/. Copy its Reproduce folder to scripts/. Copy scripts/Revision/dashboard.template.html to scripts/dashboard.template.html. Extract the original 15-bus ZIP into work/ so the report can find load_profile.csv. Run the following commands from the working directory using Python with numpy, pandas, Pillow, matplotlib and ReportLab. The PNG renderer uses the DejaVu Sans regular and bold fonts at their standard Linux paths. Use a Linux environment or adjust those font paths.

    python scripts/Revision/cache_from_csv.py
    python scripts/Revision/prepare.py
    python scripts/Revision/charts.py
    python scripts/Revision/update_dashboard.py
    python scripts/Revision/report_revision.py

The revised plots, PDF, interactive dashboard and baseline comparisons are written to deliver/C2_Analysis. These steps use saved forecasts. The ZIP also contains the final Windows launcher, guide and verified plot inventory. Numerical and workbook scripts in the parent folder document the earlier benchmark evaluation.
