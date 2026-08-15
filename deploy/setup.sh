#!/usr/bin/env bash
# Set up a fresh Ubuntu ARM machine to serve The Buried Star.
#
#   curl -fsSL https://raw.githubusercontent.com/slambdi99-cyber/dnd-universe/main/deploy/setup.sh | bash
#
# or, if the repo is already cloned:
#
#   ~/dnd-universe/deploy/setup.sh
#
# Safe to run twice. It skips anything already done, so if it dies halfway
# through, fix whatever it complained about and run it again.
#
# What it does NOT do is touch a single secret. The Discord token, the wiki
# passphrase, the per-person MCP tokens and the deploy key all get copied over
# by hand afterwards. deploy/CHECKLIST.md is the list.
#
# When this finishes the site runs, and is reachable from the machine itself.
# Nobody else can see it until Tailscale is set up, which is also in the
# checklist, because it needs a login.

set -euo pipefail

REPO="https://github.com/slambdi99-cyber/dnd-universe.git"
ROOT="$HOME/dnd-universe"
SCRIBE="$HOME/dnd-scribe"

say()  { echo; echo "== $*"; }
skip() { echo "   already done: $*"; }

if [ "$(id -u)" = "0" ]; then
    echo "Run this as the ordinary user, not root. It uses sudo where it needs to."
    exit 1
fi

say "system packages"
# Nothing here is attended, and apt asks about service restarts and config
# files if it thinks a human is watching.
export DEBIAN_FRONTEND=noninteractive
sudo -E apt-get update -qq
# git for the repo, python3-venv because Ubuntu ships python without it.
# No build toolchain and no image headers: Pillow ships manylinux wheels for
# both architectures this runs on, and a 1GB machine compiling it from source
# is a long wait for the same result.
sudo -E apt-get install -y -qq git python3-venv curl ca-certificates >/dev/null

say "swap, if this is a small machine"
# Oracle's free ARM capacity is a lottery, and the fallback everyone ends up on
# is the 1GB AMD micro. 1GB is enough to serve the site and nowhere near enough
# to `pip install` into, or to run a git operation over 50MB of pictures. Both
# die with a bare "Killed" that looks like a bug rather than an out-of-memory.
MEM_KB="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
SWAP_KB="$(awk '/SwapTotal/ {print $2}' /proc/meminfo)"
if [ "${MEM_KB:-0}" -ge 2000000 ]; then
    echo "   plenty of memory, skipping"
elif [ "${SWAP_KB:-0}" -gt 0 ]; then
    skip "swap is already on"
else
    # Keyed on swap being active rather than the file existing. A previous run
    # that died between creating the file and formatting it would otherwise be
    # skipped forever, leaving 2GB of nothing.
    [ -f /swapfile ] || sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile >/dev/null
    sudo swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || \
        echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
    echo "   added 2GB of swap"
fi

say "the repo"
if [ -d "$ROOT/.git" ]; then
    skip "$ROOT"
    git -C "$ROOT" pull --rebase --quiet || true
else
    git clone --quiet "$REPO" "$ROOT"
    echo "   cloned into $ROOT"
fi
cd "$ROOT"

# The curl one-liner fetches this through GitHub's raw CDN, which keeps serving
# a cached copy for a few minutes after a push. That is invisible, and it
# produces the worst kind of bug: a fix that is definitely committed, definitely
# pushed, and definitely not the code that just ran.
#
# The repo is cloned by this point, so the authoritative copy is now on disk. If
# it differs from whatever is executing, hand over to it, once.
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
REPO_COPY="$ROOT/deploy/setup.sh"
if [ "${BURIED_STAR_REEXEC:-}" != "1" ] && [ -f "$REPO_COPY" ] && \
   [ "$SELF" != "$REPO_COPY" ] && ! cmp -s "$SELF" "$REPO_COPY"; then
    echo "   this copy is older than the repo's; continuing with that one"
    export BURIED_STAR_REEXEC=1
    exec bash "$REPO_COPY" "$@"
fi

say "python environment"
# Not necessarily the system python3. On Ubuntu 20.04 that is 3.8, and every
# package below needs 3.10 or newer.
PYTHON="$("$ROOT/deploy/bootstrap-python.sh")"
if [ -x "$ROOT/.venv/bin/python" ]; then
    skip ".venv"
else
    "$PYTHON" -m venv "$ROOT/.venv"
fi
"$ROOT/.venv/bin/pip" install --quiet --upgrade pip
"$ROOT/.venv/bin/pip" install --quiet -r deploy/requirements-server.txt
echo "   installed"

say "art is drawn elsewhere"
# The site must not offer a button that cannot work. With this marker present
# the art panel queues a request into the repo instead, and says so.
#
# A file rather than a config key, because config.yaml is tracked: writing it
# there would travel to the machine at home on the next pull and switch off the
# graphics card the whole arrangement depends on.
if [ -f "$ROOT/.no-gpu" ]; then
    skip "marked as having no graphics card"
else
    cat > "$ROOT/.no-gpu" <<'EOF'
No graphics card on this machine. The art panel queues requests into
art-queue/ instead of drawing them, and tools/draw_queued.py drains that
queue on the machine at home.

Delete this file only on a machine that can actually draw.
EOF
    echo "   marked: art requests get queued, not drawn"
fi

say "tailscale"
if command -v tailscale >/dev/null 2>&1; then
    skip "installed"
else
    curl -fsSL https://tailscale.com/install.sh | sh
    echo "   installed, not logged in yet (see CHECKLIST.md)"
fi

say "the scripts are runnable"
chmod +x "$ROOT"/deploy/*.sh

say "letting the repo sync restart the wiki"
# repo-sync runs as the ordinary user and needs to restart a system service
# when a pull brings new code. One command, no password, nothing else.
SUDOERS=/etc/sudoers.d/buried-star
if sudo test -f "$SUDOERS"; then
    skip "sudoers rule"
else
    echo "$USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart buried-star.service" \
        | sudo tee "$SUDOERS" >/dev/null
    sudo chmod 440 "$SUDOERS"
fi

say "services"
for unit in buried-star.service buried-star-repo.service buried-star-repo.timer; do
    sudo cp "$ROOT/deploy/$unit" /etc/systemd/system/
done

# The Discord reader only makes sense once the private repo it lives in is
# cloned. Installing its timer before that would put a red failed unit on the
# dashboard every half hour for no reason.
if [ -d "$SCRIBE/scribe" ]; then
    sudo cp "$ROOT/deploy/buried-star-discord.service" /etc/systemd/system/
    sudo cp "$ROOT/deploy/buried-star-discord.timer" /etc/systemd/system/
    DISCORD=yes
else
    DISCORD=no
fi

sudo systemctl daemon-reload
sudo systemctl enable --now buried-star.service
sudo systemctl enable --now buried-star-repo.timer
if [ "$DISCORD" = yes ]; then
    sudo systemctl enable --now buried-star-discord.timer
fi

say "did it come up"
# The service restarts every few seconds while a secret is missing, so a single
# early probe reports a failure that is really a race. Give it a fair chance.
UP=no
for _ in $(seq 1 15); do
    if curl -fsS -o /dev/null "http://127.0.0.1:8787/wiki"; then UP=yes; break; fi
    sleep 2
done
if [ "$UP" = yes ]; then
    echo "   the wiki is answering on 127.0.0.1:8787"
else
    echo "   it is NOT answering. What went wrong:"
    sudo systemctl status buried-star.service --no-pager -l | tail -20
    exit 1
fi

say "what is still missing"
# Checked rather than assumed. This used to print the same list of unfinished
# business every time, including on a fully working server, which teaches you
# to stop reading it.
TODO=0
note() { echo "   [ ] $*"; TODO=$((TODO + 1)); }
done_() { echo "   [x] $*"; }

if [ -f "$ROOT/.people-tokens.json" ]; then done_ "personal tokens"
else note "personal tokens: copy .people-tokens.json across, or nothing can connect"; fi

if [ -f "$ROOT/.wiki-passphrase" ]; then done_ "passphrase"
else note "passphrase: copy .wiki-passphrase across, or the site has no front door"; fi

if git -C "$ROOT" push --dry-run --quiet >/dev/null 2>&1; then done_ "can push to GitHub"
else note "cannot push: run deploy/setup-keys.sh and tick write access on dnd-universe"; fi

if tailscale status --json 2>/dev/null | grep -q '"Online": *true'; then done_ "on the tailnet"
else note "not on the tailnet: sudo tailscale up"; fi

if tailscale funnel status 2>/dev/null | grep -q "http://127.0.0.1:8787"; then
    done_ "reachable from the internet"
else
    note "not published: sudo tailscale funnel --bg 8787"
fi

if [ "$DISCORD" = yes ]; then done_ "reading Discord"
else note "not reading Discord: clone dnd-scribe, then run this again"; fi

echo
if [ "$TODO" -eq 0 ]; then
    echo "Nothing outstanding. The site is up."
    tailscale funnel status 2>/dev/null | grep -o "https://[^ ]*" | head -1 | sed 's/^/  /'
else
    echo "$TODO thing(s) left, each needing a login or a secret."
    echo "  $ROOT/deploy/CHECKLIST.md"
fi
