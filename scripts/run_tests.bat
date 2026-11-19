@echo off
cd /d "%~dp0\..\backend"
call ..\.venv\Scripts\activate.bat
pip install -q pytest
python -m pytest -q
pause
