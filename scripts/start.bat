@echo off
REM Starts API + web UI + background worker + P1/P2 scheduler. Open http://127.0.0.1:8765
cd /d "%~dp0\..\backend"
call ..\.venv\Scripts\activate.bat
start "" http://127.0.0.1:8765
python -m app.cli serve
