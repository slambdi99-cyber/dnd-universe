# How The Buried Star runs

Three machines, one repository, and a rule about which of them is allowed to be
the source of truth. This is the map: where each piece lives, how a change gets
from one place to another, and what to do when that stops working.

If you read one line of this, read the next one. **The GitHub repository is the
database.** Every other copy is a working copy that syncs to it. Anything living
on only one machine is one dead disk away from gone.

The site: **https://buried-star.tailb26c5b.ts.net/wiki**

---

## The pieces

| Where | What it does | What it holds that matters |
|---|---|---|
| **GitHub**, `dnd-universe` | The source of truth. Public. | Everything: pages, art, code, history |
| **GitHub**, `dnd-scribe` | Private. The Discord reader. | The bot, and the raw channel archive |
| **The server**, an Oracle free VM | Serves the website and MCP, reads Discord | Nothing unique, by design |
| **The PC at home** | Draws pictures, records sessions. Development. | Nothing unique, by design |

That last column is the point. Both machines are disposable. The server can be
rebuilt in half an hour from `deploy/CHECKLIST.md`, and the PC is a clone.
Neither is backed up, and neither needs to be, as long as everything reaches
GitHub.

---

## How a change travels

Four things change the world, and they all end in the same place.

**Someone edits a page on the website.** The wiki writes the file and commits it
straight away, crediting whoever was signed in. It is live immediately, because
pages are read from disk on every request. Within two minutes the server pushes
it to GitHub.

**Someone's assistant writes over MCP.** Identical. The MCP server and the
website are the same process writing the same files.

**Someone pushes code from the PC.** The server pulls it within two minutes. If
the change touched `universe/`, `mcp_server.py`, `cli.py` or `deploy/`, the sync
restarts the wiki. Otherwise it does not, because restarting for a typo in a
place description would drop everyone's connection several times an hour.

**A picture gets drawn.** The one asynchronous path, below.

### The sync itself

`deploy/repo-sync.sh`, on a systemd timer, every two minutes plus up to thirty
seconds of jitter. Each run commits anything loose, pulls, pushes, and restarts
the wiki only if code arrived.

It pulls with a **merge, never a rebase**. An interrupted rebase leaves HEAD
detached, and that has already cost this project days of silent failure while
the wiki cheerfully committed pages onto a branch that did not exist. A merge
cannot do that. If it ever does meet a detached HEAD, it parks the loose commits
on a branch, reattaches, and says what it saved.

On a real conflict it stops and shouts rather than guessing which version wins.
The site keeps serving the last good state throughout, so a broken sync is never
a broken site.

---

## Art, the one thing that is not automatic

The server has no graphics card and never will. So art is a request rather than
an action:

1. Someone presses **Art** on the site. The page says it is queued.
2. The request is committed to `art-queue/` and pushed.
3. The PC at home runs `tools\draw_queued.py`. It pulls, draws, pushes back.
4. The pictures appear on the site as candidates, and whoever asked picks one.

Nothing is attached until a person chooses, so a bad prompt costs nothing.

**This only happens when the PC is on.** A scheduled task, "The Buried Star,
draw queued art", drains the queue every thirty minutes while somebody is
logged in. It runs under `pythonw`, so it never opens a window or steals focus.

The cost of having no console is that a failure would be invisible, so it
writes what it would have printed to `.draw-queued.log`. That file is the first
place to look if a picture never turns up. To see the queue itself, at home:

```powershell
python tools\draw_queued.py --list
```

A cold run downloads about 7GB of model weights the first time and takes
several minutes. After that it is roughly a minute per picture.

This is also why `assets/` is committed rather than ignored, which is unusual
for generated files. Now that the machine that draws is not the machine that
serves, the repository is the only route between them.

---

## Discord

`dnd-scribe` reads the campaign's channels and drops anything new into the
wiki's **Inbox**, where a person decides whether it deserves a page. Nothing is
written to the wiki automatically, ever.

It runs on the server, every thirty minutes on the clock, and nothing about it
touches the PC any more. `.discord-token` and `.sync-state.json` live on the
server alongside the private `dnd-scribe` clone.

The server's copy of `dnd-scribe` is read-only by design: its deploy key has no
write access, because a machine that only reads a channel archive has no reason
to be able to rewrite it. The downloaded archive is a cache, not something that
needs to travel back.

---

## Recording a session

`/join` in Discord starts it, on the PC. The bot records the voice channel in
ten-minute chunks; a worker transcribes each chunk and draws a scene image
from it. Each image posts to the table's chosen Discord channel as it is
drawn, and the whole recording becomes a page under **Sessions** on the wiki,
with the images attached as its art. `/stop` ends it, and the page reaches the
site within a couple of minutes of the last image.

The transcript and audio never leave the PC's private repo; only the scene art
and the page travel. `.bot.log` next to `run.py` says what the bot did, and
each session folder's `worker.log` says what the worker did.

---

## Secrets, and what breaks without each

None of these are in the repository, and none of them should be. They travel by
hand over `scp`, once, and get set to `600` on arrival.

| File | Lives on | Without it |
|---|---|---|
| `.wiki-passphrase` | server | No front door. Anyone with the URL walks in |
| `.people-tokens.json` | server | The wiki refuses to start at all |
| `.session-secret` | server | Everyone is signed out, once |
| `.accounts.json` | server | Everyone makes their account again |
| `.discord-token` | wherever the reader runs | No Discord reading |
| `~/.ssh/dnd-universe` | server | **Cannot push.** Writing piles up on the VM |
| `~/.ssh/dnd-scribe` | server | Cannot read the private repo |

The passphrase is one shared secret for the whole table. It answers "is this
someone we know" and nothing else; who you are is the name you pick after it, on
trust. The MCP tokens are the real credential: one per person, they say who is
calling, and they decide whose secrets get rendered.

---

## When something is wrong

Work down this list. Each step says whether to keep going.

**Is the site up?**

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://buried-star.tailb26c5b.ts.net/wiki
```

`307` is healthy: the passphrase gate redirecting. Anything else means look at
the server.

**Is the wiki running?**

```bash
ssh buried-star 'systemctl status buried-star --no-pager | head -5'
```

If it is restarting in a loop, `journalctl -u buried-star -n 30` says why. The
usual cause is a missing secret. It refuses to serve without personal tokens on
purpose, because an endpoint nobody can authenticate to is a slower way of being
offline.

**Is it in step with GitHub?** This is the one that fails quietly, and the one
that has actually bitten.

```bash
ssh buried-star 'cd ~/dnd-universe && git rev-parse --abbrev-ref HEAD && git rev-list --left-right --count origin/main...HEAD'
```

You want `main`, then `0 0`. A number on the right that keeps growing means it
cannot push, and everything written on the site is piling up on a machine
nothing backs up. The usual cause is a deploy key added without write access.

```bash
ssh buried-star 'journalctl -u buried-star-repo -n 30 --no-pager'
```

**Did the bot say "The application did not respond"?** The transcription bot
on the PC is offline. It runs as a scheduled task, "The Buried Star,
transcription bot", started at logon and restarted on crash; its log is
`.bot.log` next to `run.py` in `dnd-scribe`. Discord keeps slash commands
registered even when the bot is down, which is why the command appears and then
fails.

**Did a picture never arrive?** At home, read `.draw-queued.log` for what the
last drain actually did, and `python tools\draw_queued.py --list` for what is
still waiting. If the log is stale, the PC has been off or the scheduled task
is not running.

---

## Rebuilding from nothing

If the server is lost, or Oracle reclaims it, nothing goes with it. Make a new
VM and follow `deploy/CHECKLIST.md`. About half an hour, most of it waiting, and
the only irreplaceable parts are the secrets above.

Two things to get right, because both have already gone wrong once:

- The image must be **Ubuntu 24.04**. 20.04 ships Python 3.8, and every package
  here needs 3.10 or newer.
- The shape must say **Always Free-eligible**. Only `VM.Standard.A1.Flex` and
  `VM.Standard.E2.1.Micro` are. The console will happily give you something else
  on trial credits and reclaim it a month later.

---

## The rules that keep this working

**One fact in one place.** A place records its parent; what it contains is
worked out by looking. Two records of one fact drift apart, and nothing tells
you when they do.

**Nothing reaches the wiki without a person deciding.** The Discord reader fills
a queue, never the wiki. A machine confidently summarising four years of
arguments into wiki pages would be worse than a thin wiki.

**Git is the undo button, which is why there are no permissions.** Anyone can
rename a kind or reshape the front page. Everything commits before it changes.
That is a reason to be unafraid, not a reason to be casual.

**A page you may not read is indistinguishable from one that does not exist.**
Not in listings, not in search, not in a link, not in a breadcrumb. Half a trail
announces that something is hidden, and a place name is usually the whole
spoiler.

**Fail loudly, keep serving.** A broken sync must never be a broken site. The
wiki serves the last good state and complains in the log.
