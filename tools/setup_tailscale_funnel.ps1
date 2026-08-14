# Put the MCP server on a permanent public URL using Tailscale Funnel.
#
# Why this instead of a Cloudflare named tunnel: Funnel needs no domain and
# costs nothing. You get a stable address like
# https://your-pc.tailXXXX.ts.net that survives restarts, and your players
# don't need Tailscale themselves. Funnel serves the public internet.
#
# One prerequisite, which is yours because it means signing in to an account:
#
#   & 'C:\Program Files\Tailscale\tailscale.exe' up
#
# That opens a browser. Sign in with Google/GitHub/Microsoft or make an
# account. The free personal plan covers this comfortably.
#
# Then:
#   powershell -ExecutionPolicy Bypass -File .\tools\setup_tailscale_funnel.ps1
#
# The ExecutionPolicy flag matters: Windows blocks unsigned local scripts by
# default, so calling this as `.\tools\setup_tailscale_funnel.ps1` fails with
# "running scripts is disabled on this system".
#
# Re-running is safe.

param(
    [int]$Port = 8787
)

$ErrorActionPreference = "Stop"

$ts = "C:\Program Files\Tailscale\tailscale.exe"
if (-not (Test-Path $ts)) {
    $cmd = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($cmd) { $ts = $cmd.Source } else {
        Write-Host "Tailscale is not installed. Run:" -ForegroundColor Red
        Write-Host "  winget install --id tailscale.tailscale"
        exit 1
    }
}

# --- logged in? -----------------------------------------------------------

$status = & $ts status 2>&1 | Out-String
if ($status -match "Logged out" -or $status -match "NeedsLogin") {
    Write-Host "Not signed in to Tailscale." -ForegroundColor Red
    Write-Host ""
    Write-Host "Run this, sign in in the browser, then run this script again:"
    Write-Host ""
    Write-Host "  & '$ts' up" -ForegroundColor Yellow
    exit 1
}

# --- what is this machine called? -----------------------------------------

$dnsName = $null
try {
    $json = & $ts status --json 2>$null | ConvertFrom-Json
    $dnsName = $json.Self.DNSName
} catch { }

if (-not $dnsName) {
    Write-Host "Couldn't read this machine's Tailscale name." -ForegroundColor Red
    Write-Host "Check '& `"$ts`" status' and try again."
    exit 1
}

$dnsName = $dnsName.TrimEnd(".")
Write-Host "This machine: $dnsName" -ForegroundColor Cyan

# --- turn on Funnel -------------------------------------------------------

Write-Host "Enabling Funnel on port $Port..." -ForegroundColor Cyan

# Run it with its output redirected to a file and a hard timeout, rather than
# piping. When Funnel isn't enabled for the tailnet, the CLI prints an approval
# link and then blocks waiting for you to click it, so piping through Out-String
# buffers forever and the script appears to hang with no explanation.
$stdout = [System.IO.Path]::GetTempFileName()
$stderr = [System.IO.Path]::GetTempFileName()
$proc = Start-Process -FilePath $ts -ArgumentList "funnel", "--bg", "$Port" `
    -NoNewWindow -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr

if (-not $proc.WaitForExit(45000)) {
    try { $proc.Kill() } catch { }
    Start-Sleep -Milliseconds 500
}

$out = ((Get-Content $stdout -Raw -ErrorAction SilentlyContinue) + "`n" +
        (Get-Content $stderr -Raw -ErrorAction SilentlyContinue)).Trim()
Remove-Item $stdout, $stderr -ErrorAction SilentlyContinue
if ($out) { Write-Host $out }

if ($out -match "(https://login\.tailscale\.com/f/funnel\S*)") {
    Write-Host ""
    Write-Host "Funnel is not enabled for your tailnet yet." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Open this and approve it:" -ForegroundColor Yellow
    Write-Host "  $($Matches[1])"
    Write-Host ""
    Write-Host "Then run this script again."
    exit 1
}

# Verify by asking Tailscale what it is actually serving, rather than trusting
# an exit code. Start-Process -PassThru does not reliably populate ExitCode
# without a Refresh(), and reporting failure on a Funnel that is up and running
# is worse than not checking at all.
$state = & $ts funnel status 2>&1 | Out-String
if ($state -notmatch [regex]::Escape($dnsName) -or $state -notmatch "127\.0\.0\.1:$Port") {
    Write-Host ""
    Write-Host "Funnel does not appear to be serving port $Port." -ForegroundColor Yellow
    Write-Host "Current state:"
    Write-Host $state.Trim()
    Write-Host ""
    Write-Host "The usual causes:"
    Write-Host "  - HTTPS certificates aren't enabled for the tailnet"
    Write-Host "    (admin console > DNS > HTTPS Certificates > Enable)"
    Write-Host "  - Funnel isn't permitted by your tailnet policy"
    Write-Host "    (admin console > Access Controls, add the funnel node attribute)"
    exit 1
}

# --- report ---------------------------------------------------------------

Write-Host ""
Write-Host "Funnel is live." -ForegroundColor Green
Write-Host ""
Write-Host "Permanent URL:" -ForegroundColor Yellow
Write-Host "  https://$dnsName/mcp"
Write-Host ""
Write-Host "Restart the MCP server so it accepts that hostname:" -ForegroundColor Yellow
Write-Host "  cd C:\Claude\dnd-universe"
Write-Host "  .\.venv\Scripts\python.exe mcp_server.py --http --allowed-host $dnsName"
Write-Host ""
Write-Host "Check what Funnel is serving with:  & '$ts' funnel status" -ForegroundColor DarkGray
Write-Host "Turn it off with:                   & '$ts' funnel --https=443 off" -ForegroundColor DarkGray
