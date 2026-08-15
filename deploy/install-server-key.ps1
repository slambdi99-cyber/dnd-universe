# Take a key downloaded from Oracle and put it where ssh expects it.
#
#   powershell -ExecutionPolicy Bypass -File .\deploy\install-server-key.ps1
#   powershell -ExecutionPolicy Bypass -File .\deploy\install-server-key.ps1 -Ip 1.2.3.4
#
# Oracle hands you a private key at the moment you create an instance and never
# again. It lands in Downloads with a name like ssh-key-2026-08-15.key, with
# permissions inherited from the folder, which ssh refuses to use. This finds
# it, moves it, strips the permissions, and checks it actually parses.
#
# Fighting for free capacity means several create attempts and several
# downloaded keys, most of them belonging to instances that were never made.
# So this takes the newest by default and says which one it took.
#
# Give it -Ip and it also writes an ssh config entry, after which the whole
# checklist is `ssh buried-star` and `scp thing buried-star:~/` rather than a
# path and a username every time.

param(
    [string]$Path = "",
    [string]$Ip = "",
    [string]$Name = "oracle-key",
    [string]$Alias = "buried-star",
    [string]$User = "ubuntu"
)

$ErrorActionPreference = "Stop"
$sshDir = Join-Path $env:USERPROFILE ".ssh"

function Fail($message) {
    Write-Host ""
    Write-Host "  $message" -ForegroundColor Red
    Write-Host ""
    exit 1
}

if (-not (Test-Path $sshDir)) {
    New-Item -ItemType Directory -Path $sshDir | Out-Null
}

# --- find the key ---------------------------------------------------------

if ($Path) {
    if (-not (Test-Path $Path)) { Fail "No file at $Path" }
    $key = Get-Item $Path
} else {
    $downloads = Join-Path $env:USERPROFILE "Downloads"
    $found = Get-ChildItem $downloads -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^ssh-key.*\.key$|\.pem$' -and $_.Name -notlike "*.pub" } |
        Sort-Object LastWriteTime -Descending
    if (-not $found) {
        Fail ("Nothing that looks like a downloaded key in $downloads`n" +
              "  Oracle names them ssh-key-YYYY-MM-DD.key, and only offers the`n" +
              "  download once, while the instance is being created.`n" +
              "  If you have it elsewhere, pass -Path to it.")
    }
    $key = $found[0]
    if ($found.Count -gt 1) {
        Write-Host ""
        Write-Host "  $($found.Count) keys in Downloads. Taking the newest:" -ForegroundColor Yellow
        foreach ($f in $found) {
            $mark = "   "
            if ($f.FullName -eq $key.FullName) { $mark = " > " }
            Write-Host "$mark$($f.Name)   $($f.LastWriteTime)"
        }
    }
}

# --- move it into place ---------------------------------------------------

$dest = Join-Path $sshDir $Name

if (Test-Path $dest) {
    # Never quietly replace a key. The one already there may be the only copy
    # of the way into a running server, and Oracle will not hand it out again.
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backup = "$dest.replaced-$stamp"
    icacls $dest /grant "$($env:USERNAME):(F)" | Out-Null
    Move-Item $dest $backup
    if (Test-Path "$dest.pub") { Move-Item "$dest.pub" "$backup.pub" }
    Write-Host "  moved the existing key aside as $(Split-Path $backup -Leaf)" -ForegroundColor Yellow
}

Move-Item $key.FullName $dest

# The public half is optional. Oracle offers it as a separate download that is
# easy to miss, and it can be derived from the private key anyway.
$pubSource = "$($key.FullName).pub"
if (Test-Path $pubSource) {
    Move-Item $pubSource "$dest.pub"
} else {
    & ssh-keygen -y -f $dest | Set-Content "$dest.pub" -Encoding ascii
}

# --- lock it down ---------------------------------------------------------

# ssh refuses a private key that anyone else can read. Downloads inherits
# permissions that trip this, which is the "UNPROTECTED PRIVATE KEY FILE"
# error. Read for you, nothing for anyone else.
icacls $dest /inheritance:r /grant:r "$($env:USERNAME):(R)" | Out-Null

# --- check it ------------------------------------------------------------

$derived = & ssh-keygen -y -f $dest 2>&1
if ($LASTEXITCODE -ne 0) {
    Fail "That file is not a usable private key: $derived"
}
$fingerprint = & ssh-keygen -l -f "$dest.pub"

Write-Host ""
Write-Host "  Installed: $dest" -ForegroundColor Green
Write-Host "  Was:       $($key.Name)"
Write-Host "  $fingerprint"

# --- ssh config -----------------------------------------------------------

if ($Ip) {
    $configPath = Join-Path $sshDir "config"
    $block = @(
        "Host $Alias",
        "    HostName $Ip",
        "    User $User",
        "    IdentityFile ~/.ssh/$Name",
        "    IdentitiesOnly yes"
    )

    $kept = @()
    if (Test-Path $configPath) {
        # Drop any previous block for this alias. The address changes every
        # time an instance is rebuilt, and a stale HostName fails in a way that
        # looks like the key is wrong.
        $inBlock = $false
        foreach ($line in (Get-Content $configPath)) {
            if ($line -match '^\s*Host\s') {
                $inBlock = ($line -match "^\s*Host\s+$([regex]::Escape($Alias))\s*$")
            }
            if (-not $inBlock) { $kept += $line }
        }
    }

    ($kept + @("") + $block) | Set-Content $configPath -Encoding ascii
    icacls $configPath /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null

    Write-Host ""
    Write-Host "  ssh config written. From now on:" -ForegroundColor Green
    Write-Host "    ssh $Alias"
    Write-Host "    scp somefile $Alias`:~/"
} else {
    Write-Host ""
    Write-Host "  Connect with:"
    Write-Host "    ssh -i `$env:USERPROFILE\.ssh\$Name $User@YOUR-IP"
    Write-Host ""
    Write-Host "  Re-run with -Ip YOUR-IP to get `"ssh $Alias`" instead." -ForegroundColor DarkGray
}
Write-Host ""
