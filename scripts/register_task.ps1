# Registers two Windows scheduled tasks (run in PowerShell; admin not required for the current user):
#   GPTI-AutoStart : start the server at logon (keeps scheduler + worker alive while you are logged in)
#   GPTI-RunDue-0700 : at 07:00 every day run run_due.bat (enqueues due P1/P2 presets, processes queue, exits)
# The P1/P2 timing itself is decided by the app in Asia/Ho_Chi_Minh, so a duplicate trigger is harmless (deduplicated).
# NOTE: a powered-off or sleeping computer cannot scan at 07:00. "StartWhenAvailable" runs ONE catch-up when it wakes.
$root = Split-Path -Parent $PSScriptRoot
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 3)
$a1 = New-ScheduledTaskAction -Execute "$root\scripts\start.bat" -WorkingDirectory "$root\backend"
Register-ScheduledTask -TaskName "GPTI-AutoStart" -Action $a1 -Trigger (New-ScheduledTaskTrigger -AtLogOn) -Settings $settings -Force | Out-Null
$a2 = New-ScheduledTaskAction -Execute "$root\scripts\run_due.bat" -WorkingDirectory "$root\backend"
# 07:00 local Windows time. If Windows is not set to UTC+7, change the time below to the local equivalent of 07:00 Vietnam.
Register-ScheduledTask -TaskName "GPTI-RunDue-0700" -Action $a2 -Trigger (New-ScheduledTaskTrigger -Daily -At 7:00am) -Settings $settings -Force | Out-Null
Write-Host "Registered GPTI-AutoStart and GPTI-RunDue-0700. Verify with: Get-ScheduledTask GPTI-* | Get-ScheduledTaskInfo"
