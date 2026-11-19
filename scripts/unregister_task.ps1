Unregister-ScheduledTask -TaskName "GPTI-AutoStart" -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "GPTI-RunDue-0700" -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Removed GPTI scheduled tasks."
