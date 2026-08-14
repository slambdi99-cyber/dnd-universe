# Keep the running wiki and the repository in step, in both directions.
#
#   powershell -ExecutionPolicy Bypass -File .\update.ps1
#   .\update.ps1 -WhatIf        say what it would do, change nothing
#
# Two seams used to be manual, and both bit us on the first day two people
# worked on this at once:
#
#   the site  ->  git     edits made through the wiki sat uncommitted until
#                         somebody remembered. Nine changed pages were found
#                         that way, mid-merge.
#   git  ->  the site     code pushed by someone else did nothing until the
#                         server was restarted by hand, so the site ran an
#                         hour-old version without anyone noticing.
#
# The order below is the whole point. Committing first is what lets the pull
# succeed: git refuses to merge over uncommitted changes, which is exactly how
# the earlier attempt failed.
#
#   1. commit whatever the table wrote through the site
#   2. pull, and stop dead if it conflicts
#   3. run the tests
#   4. restart the server, but only if code changed and the tests passed
#   5. push
#
# Nothing here resolves a conflict or forces anything. A conflict means two
# people wrote prose about the same place, and that is a conversation, not a
# merge strategy.

param(
    [switch]$WhatIf,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

function Say($text, $colour = "Gray") {
    if (-not $Quiet) { Write-Host $text -ForegroundColor $colour }
}

# Content the table writes, as opposed to code we write. Only these are
# committed automatically; a change to Python is somebody's work in progress
# and gets committed by a person who can write the message.
$contentPaths = @("content", "files", "structure.yaml", "people.yaml")

# --- 1. commit what the site wrote ---------------------------------------

$dirty = git status --porcelain -- $contentPaths
if ($dirty) {
    $changed = ($dirty | Measure-Object).Count
    Say "  $changed content change(s) written through the site" "Cyan"
    if ($WhatIf) {
        Say "  would commit them"
    } else {
        git add -- $contentPaths
        # Authored as the wiki, not as whoever is logged into this machine. A
        # batch like this covers edits by several people and cannot honestly
        # claim any one of them; per-person authorship belongs on the
        # individual snapshot commits the site already makes.
        $summary = "Wiki edits: $changed file(s) changed through the site"
        git -c user.name="The Buried Star wiki" `
            -c user.email="wiki@buried-star.local" `
            commit -q -m $summary -- $contentPaths
        Say "  committed" "Green"
    }
} else {
    Say "  nothing new written through the site"
}

# --- 2. pull ---------------------------------------------------------------

git fetch -q origin
$behind = (git rev-list --count HEAD..origin/main)
$ahead = (git rev-list --count origin/main..HEAD)
Say "  $ahead ahead, $behind behind"

$codeChanged = $false
if ([int]$behind -gt 0) {
    # Did anything that needs a restart actually change?
    $incoming = git diff --name-only HEAD origin/main
    $codeChanged = [bool]($incoming | Where-Object {
        $_ -like "*.py" -or $_ -like "*.ps1" -or $_ -eq "requirements.txt"
    })

    if ($WhatIf) {
        Say "  would merge $behind commit(s); code changed: $codeChanged"
    } else {
        git merge --no-edit origin/main 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host ""
            Write-Host "  MERGE CONFLICT. Nothing else will run." -ForegroundColor Red
            Write-Host "  The site keeps serving what it already had." -ForegroundColor Yellow
            git diff --diff-filter=U --name-only | ForEach-Object {
                Write-Host "    $_" -ForegroundColor Yellow
            }
            Write-Host "  Resolve it, then run this again." -ForegroundColor Yellow
            exit 1
        }
        Say "  merged $behind commit(s)" "Green"
    }
}

# --- 3. test ---------------------------------------------------------------

$python = Join-Path (Split-Path $root -Parent) "dnd-scribe\.venv\Scripts\python.exe"
$testsPassed = $true
if ($codeChanged -and -not $WhatIf) {
    Say "  code changed, running the suite before restarting"
    # Exit codes, not output. Every suite here prints its startup line to
    # stderr, and PowerShell 5.1 turns a native command's stderr into
    # terminating errors when ErrorActionPreference is Stop, so capturing the
    # text aborted this script on a passing test.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    foreach ($t in Get-ChildItem "$root\tests\test_*.py") {
        & $python $t.FullName *> $null
        if ($LASTEXITCODE -ne 0) {
            $testsPassed = $false
            Write-Host "    FAILED: $($t.Name)" -ForegroundColor Red
        }
    }
    $ErrorActionPreference = $previous
    if ($testsPassed) {
        Say "  suite green" "Green"
    } else {
        Write-Host "  Someone's push broke the tests. Not restarting." -ForegroundColor Red
        Write-Host "  The site keeps serving the version that works." -ForegroundColor Yellow
    }
}

# --- 4. restart, only if warranted ----------------------------------------

if ($codeChanged -and $testsPassed -and -not $WhatIf) {
    # Stop whatever is already serving. The pid file is the reliable way, but
    # a server started before that file existed, or one whose window was
    # closed uncleanly, has to be found by what it is running. Missing this
    # would start a second server that cannot bind the port, and the site
    # would keep serving the old code while looking like it had restarted.
    $stopped = $false
    $pidFile = Join-Path $root ".server-pid"
    if (Test-Path $pidFile) {
        $serverPid = (Get-Content $pidFile -Raw).Trim()
        try {
            Stop-Process -Id $serverPid -Force -ErrorAction Stop
            $stopped = $true
            Say "  stopped the old server"
        } catch { }
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    }
    if (-not $stopped) {
        # --http, not merely mcp_server.py. Everyone's assistant runs a copy of
        # the same script over stdio, and there are usually several: killing
        # those would drop live connections to fix a website they are not
        # serving.
        Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
            Where-Object {
                $_.CommandLine -like "*mcp_server.py*" -and $_.CommandLine -like "*--http*"
            } |
            ForEach-Object {
                Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
                $stopped = $true
            }
        if ($stopped) { Say "  stopped the old server, found by what it serves" }
        else { Say "  nothing was serving" }
    }
    Start-Sleep -Seconds 2
    Start-Process powershell -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $root "start.ps1")
    ) -WindowStyle Hidden
    Start-Sleep -Seconds 8
    Say "  restarted on the new code" "Green"
}

# --- 5. push ---------------------------------------------------------------

if (-not $WhatIf) {
    $ahead = (git rev-list --count origin/main..HEAD)
    if ([int]$ahead -gt 0) {
        if ($testsPassed) {
            git push -q origin main
            if ($LASTEXITCODE -eq 0) {
                Say "  pushed $ahead commit(s)" "Green"
            } else {
                Say "  push rejected; someone pushed again. Next run will merge." "Yellow"
            }
        } else {
            Say "  not pushing while the tests are red" "Yellow"
        }
    }
}

Say "  done"
