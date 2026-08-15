#!/usr/bin/env bash
# Start the wiki. The Linux counterpart of start.ps1, run by systemd rather
# than by a person, so it prints nothing friendly and never waits.
#
# The one thing it has to work out for itself is what Tailscale calls this
# machine. Without it every authenticated request arriving through the funnel
# is rejected with a 421, which looks like a broken tunnel rather than a
# missing flag, and costs an afternoon to find.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
PORT="${PORT:-8787}"

cd "$ROOT"

ARGS=(mcp_server.py --http --host 127.0.0.1 --port "$PORT" --wiki-live)

if command -v tailscale >/dev/null 2>&1; then
    HOSTNAME_TS="$(tailscale status --json 2>/dev/null \
        | "$PYTHON" -c 'import json,sys; print((json.load(sys.stdin).get("Self",{}).get("DNSName") or "").rstrip("."))' \
        2>/dev/null || true)"
    if [ -n "${HOSTNAME_TS:-}" ]; then
        ARGS+=(--allowed-host "$HOSTNAME_TS")
    fi
fi

exec "$PYTHON" "${ARGS[@]}"
