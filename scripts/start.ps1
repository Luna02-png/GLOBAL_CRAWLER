# PowerShell alternative to start.bat
$root = Split-Path -Parent $PSScriptRoot
Set-Location "$root\backend"
& "$root\.venv\Scripts\Activate.ps1"
Start-Process "http://127.0.0.1:8765"
python -m app.cli serve
