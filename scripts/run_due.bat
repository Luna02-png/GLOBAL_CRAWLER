@echo off
REM Used by Windows Task Scheduler: enqueue due P1/P2 scans (at most one catch-up) and process the queue, then exit.
cd /d "%~dp0\..\backend"
call ..\.venv\Scripts\activate.bat
python -m app.cli run-due >> ..\data\run_due.log 2>&1
