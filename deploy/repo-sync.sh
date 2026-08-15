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

say() { echo "[repo-sync] $*"; }

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

if [ "$BEFORE" != "$AFTER" ]; then
    for path in $WATCH; do
        if git diff --name-only "$BEFORE" "$AFTER" | grep -q "^${path%/}"; then
            say "code changed, restarting the wiki"
            sudo systemctl restart buried-star.service
            break
        fi
    done
fi
