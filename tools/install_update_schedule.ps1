# Keep the wiki and the repository in step on a schedule.
#
#   powershell -ExecutionPolicy Bypass -File .\tools\install_update_schedule.ps1
#
#   -Minutes 15     check more often
#   -Remove         delete the task again
#
# Runs update.ps1 every 15 minutes while you are logged in, in a hidden
# window. That job commits what the table wrote through the site, pulls what
# anyone else pushed, runs the tests, restarts the server only when code
# actually changed and the tests passed, and pushes.
#
# The safety property worth knowing: a push that breaks the tests does not
# reach the running site. It keeps serving the last version that worked, and
# the failure is reported rather than deployed.

param(
    [int]$Minutes = 15,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$TaskName = "The Buried Star - sync wiki and repo"
$root = Split-Path $PSScriptRoot -Parent
$script = Join-Path $root "update.ps1"

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed '$TaskName'." -ForegroundColor Green
    } else {
        Write-Host "No task called '$TaskName' to remove."
    }
    exit 0
}

if (-not (Test-Path $script)) {
    Write-Host "Can't find $script" -ForegroundColor Red
    exit 1
}

if ($Minutes -lt 5) {
    Write-Host "Five minutes is the floor; a git fetch every minute is noise." -ForegroundColor Yellow
    $Minutes = 5
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`" -Quiet" `
    -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Minutes $Minutes)

# The test run can take a couple of minutes on a cold cache, and two of these
# overlapping would fight over the same working tree.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "Commits site edits, pulls collaborators' work, tests it, restarts the wiki when code changes, and pushes." `
    -Force | Out-Null

Write-Host ""
Write-Host "  Scheduled: every $Minutes minutes, while you're logged in." -ForegroundColor Green
Write-Host "  Task name: $TaskName"
Write-Host ""
Write-Host "  Run it now:     Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "  See what it did: .\update.ps1 -WhatIf"
Write-Host "  Remove it:      .\tools\install_update_schedule.ps1 -Remove"
Write-Host ""
Write-Host "  A push that fails the tests will not reach the running site." -ForegroundColor DarkGray
Write-Host ""
