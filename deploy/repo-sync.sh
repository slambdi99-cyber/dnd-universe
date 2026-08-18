#!/usr/bin/env bash
# Keep the server's copy of the repo and GitHub in step, in both directions.
#
# Two machines write to one repo now. People write pages here, through the
# website. The machine at home writes pictures, and pushes them. Neither knows
# about the other, so something has to meet in the middle every couple of
# minutes, and this is it.
#
#   1. commit anything the website wrote and did not commit itself
#   2. pull, rebasing local commits on top
#   3. push
#   4. restart the wiki, but only if the pull brought new code
#
# Step 4 is the reason this is a script rather than a cron one-liner. Content
# is read from disk per request, so a page that arrives in a pull is live
# immediately. Code is not. Restarting on every pull would drop connections
# several times an hour for nothing.
#
# On conflict it stops and shouts. A rebase that leaves the working copy
# half-merged is not something to paper over at two in the morning: the
# website keeps serving the last good state, and someone sorts it out.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

WATCH='universe/ mcp_server.py cli.py requirements-server.txt deploy/'

# Set when a pull brings new code, cleared once that code is actually running.
# A file rather than a variable because the verdict it waits on usually is not
# ready within the run that pulled.
PENDING="$ROOT/.needs-restart"
GIVE_UP_AFTER=5

say() { echo "[repo-sync] $*"; }

ci_verdict() {
    # "success", "failure", "pending", or "unknown" for one commit.
    #
    # Unauthenticated, which the public repo allows and which keeps a token off
    # this box. Called only while a restart is owed, so it is a handful of
    # requests per deploy rather than one every two minutes.
    local sha="$1" slug py
    slug="$(git config --get remote.origin.url \
            | sed -E 's#^.*github\.com[:/]##; s#\.git$##')"
    [ -n "$slug" ] || { echo unknown; return; }

    py="$ROOT/.venv/bin/python"
    [ -x "$py" ] || py="$(command -v python3 || true)"
    [ -n "$py" ] || { echo unknown; return; }

    # Captured before parsing rather than piped straight in: under `pipefail` a
    # 404 makes the whole pipeline fail after the parser has already printed,
    # so the fallback fires too and the function answers twice.
    local body
    body="$(curl -sf --max-time 20 \
        "https://api.github.com/repos/$slug/commits/$sha/check-runs" 2>/dev/null)" \
        || { echo unknown; return; }
    [ -n "$body" ] || { echo unknown; return; }

    printf '%s' "$body" | "$py" -c '
import json, sys
try:
    runs = json.load(sys.stdin).get("check_runs") or []
except Exception:
    print("unknown"); raise SystemExit
if not runs:
    # No check has reported yet. Not the same as nothing being wrong.
    print("pending"); raise SystemExit
if any(r.get("status") != "completed" for r in runs):
    print("pending"); raise SystemExit
bad = {"failure", "cancelled", "timed_out", "action_required", "stale"}
print("failure" if any(r.get("conclusion") in bad for r in runs) else "success")
' 2>/dev/null || echo unknown
}

if ! git rev-parse --git-dir >/dev/null 2>&1; then
    say "not a git repo, nothing to do"
    exit 0
fi

# An unfinished rebase from a previous run means a person needs to look. Trying
# again on top of it makes the mess bigger, not smaller.
if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    say "a rebase is half-finished. Fix it by hand; not touching it."
    exit 1
fi

# The website commits its own edits so they carry the right author. This is for
# anything that slipped through: a thumbnail folder, an upload, a page written
# by something that forgot.
if [ -n "$(git status --porcelain -- content files people.yaml structure.yaml art-queue 2>/dev/null)" ]; then
    git add -- content files people.yaml structure.yaml art-queue 2>/dev/null
    git -c user.name=wiki.local -c user.email=server@wiki.local \
        commit -q -m "wiki: changes made on the site" \
        -- content files people.yaml structure.yaml art-queue 2>/dev/null \
        && say "committed loose changes"
fi

BEFORE="$(git rev-parse HEAD)"

if ! git pull --rebase --quiet; then
    say "pull failed. Someone has to look at this."
    git rebase --abort 2>/dev/null || true
    exit 1
fi

AFTER="$(git rev-parse HEAD)"

if [ "$BEFORE" != "$AFTER" ]; then
    CHANGED="$(git diff --name-only "$BEFORE" "$AFTER")"
    say "pulled $(echo "$CHANGED" | wc -l) changed file(s)"
fi

if ! git push --quiet 2>/dev/null; then
    # Nothing to push is not a failure, and neither is losing a race with the
    # machine at home: the next run in two minutes carries it.
    #
    # A push that keeps failing is a different thing. Everything written on the
    # site lives only here until it lands on GitHub, and this is a free VM that
    # nobody backs up. So say how much is stuck, and say it every time, because
    # the usual cause is a deploy key added without write access and that never
    # fixes itself.
    STUCK="$(git log --oneline @{u}..HEAD 2>/dev/null | wc -l)"
    if [ "${STUCK:-0}" -gt 0 ]; then
        say "push failed: $STUCK commit(s) stuck here and nowhere else."
        say "if this repeats, the deploy key probably has no write access."
    fi
fi

# New pictures arrive the same way everything else does: in a pull from the
# machine at home. Shrinking them here, once, means the first person to open
# the front page after new art lands gets thumbnails that already exist rather
# than waiting while thirty of them are built one at a time. Cheap to run when
# nothing changed, so it is not worth guessing whether anything did.
if [ "$BEFORE" != "$AFTER" ]; then
    if [ -x "$ROOT/.venv/bin/python" ]; then
        say "thumbnails: $("$ROOT/.venv/bin/python" tools/warm_thumbs.py 2>&1 | tail -1)"
    fi

    for path in $WATCH; do
        if git diff --name-only "$BEFORE" "$AFTER" | grep -q "^${path%/}"; then
            say "code changed, restart pending"
            echo 0 > "$PENDING"
            break
        fi
    done
fi

# Restarting into whatever just landed was a race the server always lost. A
# push reaches here inside two minutes; the tests that say whether it works
# take about forty seconds and report back to GitHub, not to this machine. So
# the old order was: pull, restart, and find out afterwards. A broken commit
# was already being served by the time the red X appeared.
#
# Now the restart waits for a verdict. The marker file outlives a single run
# because the answer usually is not ready yet, and without it the next run --
# which pulls nothing, so BEFORE equals AFTER -- would forget a restart was
# owed and leave the new code sitting on disk unserved.
#
# A failing verdict holds indefinitely and on purpose: the last good process
# keeps serving, and the fix that follows flips this to success on its own. An
# unreachable API is different, because "GitHub is down" must not mean "this
# server never updates again", so that one gives up after a few tries and
# restarts anyway, loudly.
if [ -f "$PENDING" ]; then
    TRIES="$(cat "$PENDING" 2>/dev/null || echo 0)"
    case "$(ci_verdict "$(git rev-parse HEAD)")" in
        success)
            say "tests passed, restarting the wiki"
            rm -f "$PENDING"
            sudo systemctl restart buried-star.service
            ;;
        failure)
            say "tests FAILED for $(git rev-parse --short HEAD). Not restarting."
            say "the running wiki is the last version that worked. Push a fix."
            ;;
        pending)
            say "tests still running; restart waits for the next check"
            echo $((TRIES + 1)) > "$PENDING"
            ;;
        *)
            if [ "$TRIES" -ge "$GIVE_UP_AFTER" ]; then
                say "no verdict from GitHub after $TRIES tries. Restarting anyway."
                rm -f "$PENDING"
                sudo systemctl restart buried-star.service
            else
                say "could not reach GitHub for a verdict ($((TRIES + 1))/$GIVE_UP_AFTER)"
                echo $((TRIES + 1)) > "$PENDING"
            fi
            ;;
    esac
fi
