# Draw whatever the website asked for, whenever this machine is on.
#
#   powershell -ExecutionPolicy Bypass -File .\tools\install_draw_schedule.ps1
#
#   -Minutes 60     check less often
#   -Remove         delete the task again
#
# The site runs on a server with no graphics card. When someone presses Art
# there, the request is committed to the repo and the page says it is waiting
# for the machine at home. This is the machine at home.
#
# It costs nothing when the queue is empty: a pull, a look at one folder, and
# it exits. When there is something waiting it takes about a minute per
# picture, on the GPU, in the background.

param(
    [int]$Minutes = 20,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$TaskName = "The Buried Star - draw queued art"
$root = Split-Path $PSScriptRoot -Parent
$script = Join-Path $root "tools\draw_queued.py"

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

# pythonw, not python: it has no console, so a picture being drawn in the
# background never steals focus or flashes a window at whoever is using the
# machine. Everything it would have printed goes to .draw-queued.log instead,
# because a scheduled task that fails invisibly is worse than one that is
# merely quiet.
$python = Join-Path (Split-Path $root -Parent) "dnd-scribe\.venv\Scripts\pythonw.exe"
if (-not (Test-Path $python)) {
    Write-Host "Can't find the Python environment at:" -ForegroundColor Red
    Write-Host "  $python"
    Write-Host "Run dnd-scribe\setup.ps1 first."
    exit 1
}

# Drawing needs the card. Without torch this would install a task that fails
# every twenty minutes, silently, which is the whole failure mode the log file
# exists to catch.
#
# Checked with the console interpreter, not pythonw. PowerShell does not wait
# for a GUI-subsystem executable, so $LASTEXITCODE from pythonw is whatever it
# was before, and this test would pass no matter what.
$consolePython = Join-Path (Split-Path $python -Parent) "python.exe"
& $consolePython -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "That environment has no working CUDA torch, so nothing can be" -ForegroundColor Red
    Write-Host "drawn. Scheduling it would just fail quietly every $Minutes minutes."
    exit 1
}

if ($Minutes -lt 10) {
    Write-Host "Ten minutes is the floor. Drawing takes longer than that anyway." -ForegroundColor Yellow
    $Minutes = 10
}

$action = New-ScheduledTaskAction -Execute $python `
    -Argument "`"$script`"" -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(3) `
    -RepetitionInterval (New-TimeSpan -Minutes $Minutes)

# Four pictures at a minute each, plus loading the model on a cold start, is
# comfortably inside an hour. Two runs overlapping would fight for the card and
# both would fail with an out-of-memory error.
$settings = New-ScheduledTaskSettingsSet `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "Draws art requests queued by the website, and pushes the results back." `
    -Force | Out-Null

Write-Host ""
Write-Host "  Scheduled: every $Minutes minutes, while you're logged in." -ForegroundColor Green
Write-Host "  Task name: $TaskName"
Write-Host ""
Write-Host "  See what's waiting: python tools\draw_queued.py --list"
Write-Host "  Draw it now:        Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Remove it:          .\tools\install_draw_schedule.ps1 -Remove"
Write-Host ""
