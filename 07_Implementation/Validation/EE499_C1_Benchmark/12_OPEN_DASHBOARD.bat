@echo off
cd /d "%~dp0"
if exist "results\dashboard.html" (start "" "results\dashboard.html") else (echo No dashboard yet. Run a test first.)
