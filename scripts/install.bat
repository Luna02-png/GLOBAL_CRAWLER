@echo off
REM One-time setup on Windows. Requires Python 3.12+ from python.org (tick "Add python.exe to PATH").
cd /d "%~dp0\.."
if not exist .venv ( py -3 -m venv .venv || python -m venv .venv )
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r backend\requirements.txt || goto :err
if not exist .env copy .env.example .env
cd backend
python -m app.cli init || goto :err
echo.
echo Installed. Start the app with scripts\start.bat
pause
exit /b 0
:err
echo Installation failed - see messages above.
pause
exit /b 1
