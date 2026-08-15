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

ts_name() {
    tailscale status --json 2>/dev/null \
        | "$PYTHON" -c 'import json,sys; print((json.load(sys.stdin).get("Self",{}).get("DNSName") or "").rstrip("."))' \
        2>/dev/null || true
}

if command -v tailscale >/dev/null 2>&1; then
    # Wait for it, rather than asking once. systemd's After= only orders the
    # start of tailscaled, not the point where it has talked to the coordination
    # server and knows its own name. On a reboot this service wins that race
    # perfectly often, and starting without --allowed-host means every
    # authenticated request through the funnel gets a 421: the site looks fine,
    # nobody's assistant can connect, and nothing in the log says why.
    #
    # Bounded, because a machine that is deliberately off the tailnet should
    # still serve on localhost rather than refuse to start.
    HOSTNAME_TS=""
    for _ in $(seq 1 30); do
        HOSTNAME_TS="$(ts_name)"
        [ -n "$HOSTNAME_TS" ] && break
        sleep 2
    done

    if [ -n "$HOSTNAME_TS" ]; then
        ARGS+=(--allowed-host "$HOSTNAME_TS")
    else
        echo "tailscale never reported a hostname; serving without --allowed-host." >&2
        echo "Requests through the funnel will be rejected with 421 until this" >&2
        echo "service is restarted with tailscale up." >&2
    fi
fi

exec "$PYTHON" "${ARGS[@]}"
