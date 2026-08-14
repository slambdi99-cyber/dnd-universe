# Start The Buried Star wiki and MCP server.
#
#   powershell -ExecutionPolicy Bypass -File .\start.ps1
#
# Leave the window open; closing it stops the site. Tailscale runs as a service
# and comes back on its own after a reboot, so this is usually the only thing
# you need to restart.
#
# Options:
#   -Port 8787            listen somewhere else
#   -ReadOnly             serve without the MCP write tools

param(
    [int]$Port = 8787,
    [switch]$ReadOnly
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# There is no venv in this folder. The interpreter with torch, mcp, starlette
# and everything else lives next door in dnd-scribe, and pointing at the wrong
# one is the single easiest way to get a confusing "not recognized" error.
$python = Join-Path (Split-Path $root -Parent) "dnd-scribe\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Can't find the Python environment at:" -ForegroundColor Red
    Write-Host "  $python"
    Write-Host ""
    Write-Host "Run dnd-scribe\setup.ps1 first."
    exit 1
}

# No shared token any more. Everyone connects with their own, minted by
# tools\make_people_tokens.py and handed out by the connect page. The one that
# used to live here was dropped after a copy turned up pasted into a Discord
# channel, which is what a shared secret does eventually.

# Ask Tailscale what this machine is called, so the transport accepts requests
# arriving through the funnel. Without it every authenticated request 421s.
$ts = "C:\Program Files\Tailscale\tailscale.exe"
$hostname = $null
if (Test-Path $ts) {
    try {
        $status = & $ts status --json 2>$null | ConvertFrom-Json
        if ($status.Self.DNSName) { $hostname = $status.Self.DNSName.TrimEnd(".") }
    } catch { }
}

$args = @("mcp_server.py", "--http", "--host", "127.0.0.1", "--port", "$Port",
          "--wiki-live")
if ($hostname) { $args += @("--allowed-host", $hostname) }
if ($ReadOnly) { $args += "--read-only" }

Write-Host ""
if ($hostname) {
    Write-Host "  Wiki: https://$hostname/wiki" -ForegroundColor Green
    Write-Host "  MCP:  https://$hostname/mcp" -ForegroundColor Green
} else {
    Write-Host "  Tailscale not detected; serving on localhost only." -ForegroundColor Yellow
    Write-Host "  http://127.0.0.1:$Port/wiki"
}
Write-Host ""
Write-Host "  Leave this window open. Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

Set-Location $root
& $python @args
