# Saved-run recovery

From `07_Implementation`, repair the registration of a completed run using the folder containing `session.json`.

```bat
python Tools\Recovery\RECOVER_ARCHIVED_RUN.py "C:\path\to\saved-session"
```

Rebuild the offline HTML from an exported run folder, such as `optimization\run_001`.

```bat
Tools\Recovery\REGENERATE_SAVED_DASHBOARD.bat "C:\path\to\exported-run"
```

The repair utility backs up the session manifest before changing it. The dashboard utility reads the existing exports and can also be started by dragging the run folder onto the batch file.
