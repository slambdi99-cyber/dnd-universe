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
sudo apt-get update -qq
# git for the repo, python3-venv because Ubuntu ships python without it.
# No build toolchain and no image headers: Pillow ships manylinux wheels for
# both architectures this runs on, and a 1GB machine compiling it from source
# is a long wait for the same result.
sudo apt-get install -y -qq git python3-venv curl ca-certificates

say "swap, if this is a small machine"
# Oracle's free ARM capacity is a lottery, and the fallback everyone ends up on
# is the 1GB AMD micro. 1GB is enough to serve the site and nowhere near enough
# to `pip install` into, or to run a git operation over 50MB of pictures. Both
# die with a bare "Killed" that looks like a bug rather than an out-of-memory.
MEM_KB="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
if [ "${MEM_KB:-0}" -lt 2000000 ] && [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap -q /swapfile
    sudo swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || \
        echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
    echo "   added 2GB of swap"
elif [ -f /swapfile ]; then
    skip "swap"
else
    echo "   plenty of memory, skipping"
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
# The site must not offer a button that cannot work. With this false the art
# panel queues a request into the repo instead, and says so.
if grep -q "draws_here:" config.yaml; then
    skip "config.yaml says where art is drawn"
else
    "$ROOT/.venv/bin/python" - <<'PY'
from pathlib import Path

path = Path("config.yaml")
text = path.read_text(encoding="utf-8")
note = (
    "  # No graphics card on this machine. Art requests are written into the\n"
    "  # repo and drawn at home. tools/draw_queued.py is the other half.\n"
    "  draws_here: false\n"
)
if "art:" in text:
    out = []
    for line in text.splitlines(keepends=True):
        out.append(line)
        if line.rstrip() == "art:":
            out.append(note)
    text = "".join(out)
else:
    text = text.rstrip() + "\n\nart:\n" + note
path.write_text(text, encoding="utf-8")
print("   config.yaml: draws_here false")
PY
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
sleep 3
if curl -fsS -o /dev/null "http://127.0.0.1:8787/wiki"; then
    echo "   the wiki is answering on 127.0.0.1:8787"
else
    echo "   it is NOT answering. What went wrong:"
    sudo systemctl status buried-star.service --no-pager -l | tail -20
    exit 1
fi

cat <<EOF

Done, as far as this can go on its own.

The site runs, and this machine can see it. Nobody else can. There is no
passphrase on it, it cannot push anything anyone writes, and it is not reading
Discord. Those all need your hands:

  $ROOT/deploy/CHECKLIST.md

Read that next. Start with:

  $ROOT/deploy/setup-keys.sh

because until the server can push, everything written on the site stays on
this one machine.
EOF
