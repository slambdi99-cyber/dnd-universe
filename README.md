# dnd-universe

The shared world: every place, person, faction and item in your campaign, as
linked files you can query, draw, and hand to any AI assistant.

This is the layer everything else plugs into. `dnd-scribe` feeds sessions in at
one end. The web app and the MCP server (both still to build) read from it at
the other. Foundry VTT gets maps and encounters pushed to it.

## Status

Working now:

- **Entity model and library.** Places, characters, factions, items, events,
  sessions, creatures, lore. Cross-links, backlinks, search, merge-safe writes.
- **World map import.** Turns an Azgaar Fantasy Map Generator export into
  linked entities with generated visual descriptions.
- **Art pipeline.** Local SDXL on your GPU, one consistent house style across
  the whole world, content-addressed so nothing is ever drawn twice.
- **CLI** over all of it.

- **The live wiki.** Per-person views, editing, art, uploads, a Discord inbox
  and a Structure editor, served over a permanent HTTPS address.
- **The MCP server**, so anyone's assistant can read and write the world.

Not built yet: Foundry integration, and the session-to-wiki pipeline.

## The one architectural decision worth arguing about

**Files are the source of truth. A database, when it arrives, is a derived
index you can delete and rebuild.**

Entities are markdown with YAML frontmatter under `content/<kind>/<slug>.md`.
The reasons:

- Several people edit this world at once, and markdown in git merges. A shared
  database needs a migration and a merge strategy for every schema change, and
  someone to own it.
- Language models read and write files natively. That's the whole basis of the
  MCP server: your friends' assistants author lore directly, and a file is far
  less fragile to hand a model than a write API.
- The web app loses nothing. It indexes the files into SQLite or Postgres at
  load and queries the index.

If you'd rather the database be authoritative, say so before the web app is
built. It's a cheap change now and an expensive one after.

## Setup

```powershell
cd C:\Claude\dnd-universe
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For the `art` command you also need PyTorch from the CUDA 12.8 index, which is
what an RTX 50-series card requires:

```powershell
.\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu128
```

Everything except `art` runs without torch, so you can build the world on any
machine and generate the pictures on the one with the GPU.

Check it works:

```powershell
.\.venv\Scripts\python.exe tests\test_universe.py
```

## Building the world map

1. Open https://azgaar.github.io/Fantasy-Map-Generator/ and generate a world,
   or load one you've already made.
2. Edit it until it's yours: rename states, place burgs, write legend notes.
   Anything you write in the map's Notes carries over as page text.
3. **Menu > Save/Load > Export > Save as JSON.** Not the `.map` file, which is
   a custom format this doesn't read.
4. Import it:

```bash
python cli.py import-map path\to\world.json --dry-run
```

Check the counts look like your map, then drop `--dry-run`.

What comes across:

| Azgaar | becomes | linked to |
| --- | --- | --- |
| state | `place` tagged `realm` | its capital |
| province | `place` tagged `province` | its realm |
| burg | `place` tagged `settlement` | realm and province |
| culture | `faction` tagged `culture` | |
| religion | `faction` tagged `religion` | |

Each settlement gets an `appearance` written from what the map already knows:
size from population, plus harbor, citadel, walls, temple, market, and the
local biome. That's what the art pipeline draws, so imported towns are
immediately drawable without anyone typing a description.

**Re-running is safe.** Import merges rather than overwrites, and anything a
human wrote wins. Automated passes fill empty fields and add to lists; they
never replace prose you typed. Re-import after every map edit.

A caveat: Azgaar's JSON shape shifts between versions, and this parser is
tolerant rather than strict, so it skips what it doesn't recognise instead of
failing. Always `--dry-run` a new export first and check the counts.

## Generating art

```bash
python cli.py art saltmere-keep
```

```bash
python cli.py art --all --kind place --dry-run
```

`--dry-run` prints the prompts without touching the GPU, which is the fast way
to tune style before committing to a few hundred images.

Variants control framing. Places take `wide`, `interior`, `aerial`, `map`.
Characters take `portrait`, `full`, `action`:

```bash
python cli.py art the-drowned-lantern --variant interior
```

**Consistency** is the point of the whole design:

- `house_style` in `config.yaml` is prepended to every prompt. It's the single
  lever that makes four hundred images look like one world. Change it and
  delete `assets/` to restyle everything.
- Seeds are derived from the entity slug and variant, so the same character
  regenerates with roughly the same face every time.
- Images are content-addressed by a hash of prompt, seed, model, size and
  steps. Running `art --all` after adding one character generates one image,
  not four hundred. Use `--force` to override.
- Every image gets a JSON sidecar recording exactly what produced it.

**Appearance beats summary.** Prompts use an entity's `appearance` field and
never its `summary`, because a summary says what something means and an image
model needs to know what it looks like. Entities with no appearance are drawn
from the bare name and the CLI warns you.

## The MCP server

`mcp_server.py` exposes the world to Claude, so everyone at the table can read
and write The Buried Star from their own client instead of routing everything
through one person.

Reading: `search_world`, `get_page`, `list_pages`, `world_overview`,
`open_questions`, `whats_new`, `list_files`, `get_structure`.
Writing: `create_page`, `update_page`, `link_pages`, `mark_filed`,
`remove_file`, `move_page`, `add_kind`, `change_kind`, `remove_kind`,
`set_site`, `set_home_sections`.

### Running it just for yourself

```powershell
.\.venv\Scripts\python.exe mcp_server.py
```

Then point a client at it. For Claude Code, in `.claude/settings.json`:

```json
{
  "mcpServers": {
    "buried-star": {
      "command": "C:\\Claude\\dnd-universe\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Claude\\dnd-universe\\mcp_server.py"]
    }
  }
}
```

### Running it for the table

One machine hosts, everyone else connects over the network. Start the tunnel
first, because you need its hostname to start the server:

```powershell
cloudflared tunnel --url http://127.0.0.1:8787
```

It prints a URL like `https://some-words-here.trycloudflare.com`. Then:

```powershell
.\.venv\Scripts\python.exe mcp_server.py --http --allowed-host some-words-here.trycloudflare.com
```

Your players connect to `<that-url>/mcp` with an `Authorization: Bearer <token>`
header, using their own token. Mint them with `tools/make_people_tokens.py`,
or let each person collect their own from the connect page on the wiki.
There is no shared token: it was dropped after a copy turned up pasted into
a Discord channel, and a personal token does everything it did while also
telling the server who is calling.

**`--allowed-host` is not optional behind a tunnel.** The MCP transport has DNS
rebinding protection that rejects any request whose `Host` header it doesn't
recognise. Through a tunnel the Host is the public name, not localhost, so
without this flag every correctly authenticated request comes back `421
Misdirected Request` and the cause is not obvious.

**Quick tunnels are ephemeral.** Stop `cloudflared` and that URL is gone for
good; the next run gets a different one, and you must restart the server with
the new `--allowed-host`. Fine for a one-off, annoying for a group who have to
reconfigure every time.

### A permanent URL, without buying a domain

Tailscale Funnel gives you a stable public address on a `.ts.net` hostname for
free, with no domain required. Your players don't need Tailscale; Funnel serves
the open internet.

**This is now done on the server, not here.** `deploy/CHECKLIST.md` covers it.
What follows is the same thing for a machine serving the wiki itself, which is
development or a fallback.

```powershell
winget install --id tailscale.tailscale
```

```powershell
& 'C:\Program Files\Tailscale\tailscale.exe' up
```

That opens a browser to sign in. Then:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\setup_tailscale_funnel.ps1
```

The `-ExecutionPolicy Bypass` is needed: Windows blocks unsigned local scripts
by default, so running it as `.\tools\setup_tailscale_funnel.ps1` fails with
"running scripts is disabled on this system".

The script reads your machine's Tailscale name, turns on Funnel for port 8787,
and prints the permanent URL plus the exact command to restart the MCP server
with the right `--allowed-host`.

Funnel also needs enabling once for your tailnet. The first run prints an
approval link if so; open it, approve, run the script again.

If your tailnet needs HTTPS certificates or the Funnel node attribute enabled
first, the script says so and gives you the link.

The Cloudflare route is still there if you'd rather use your own domain:
`tools/setup_named_tunnel.ps1 -Hostname wiki.yourdomain.com`, after
`cloudflared tunnel login`.

The server also only runs while the host machine is on. That is the tradeoff of
self-hosting, and your players will notice it.

**The token is not optional.** The server refuses to start in HTTP mode without
one, and that refusal is deliberate: these tools can rewrite your campaign, and
an unauthenticated endpoint behind a public tunnel is an open invitation. Pick a
long random string and share it the way you'd share a password.

Use `--read-only` to serve the world without `create_page`, `update_page` and
`link_pages`. That's the right setting for a link you don't fully control, or
for anyone you'd rather have read the world than edit it.

### What it's good at

The tools are shaped around how a table actually uses a wiki. `get_page`
returns backlinks along with the page, because "what else touches this" is
usually the real question. `open_questions` lists everything deliberately
unfinished, which is the fastest way for someone to find a useful contribution.
`update_page` appends to the body rather than replacing it, so adding what
happened last session can't wipe what was already written.

Page references are forgiving: `get_page` accepts `"Korran Mossborn"`,
`"korran"`, or `"character/korran-mossborn"`.

## Running it

**The wiki runs on a server now, not on this machine.** A free Oracle Cloud VM
serves the site, reads Discord, and pushes what people write; `deploy/` holds
its setup and `deploy/CHECKLIST.md` the parts that need a login. The site stays
up when this computer is off, which was the whole point.

One job stayed here, because it needs the graphics card: drawing. Pressing Art
on the site writes a request into `art-queue/`, and this machine drains it.

```powershell
python tools\draw_queued.py            # draw what has been asked for
python tools\draw_queued.py --list     # just say what is waiting
```

`tools\install_draw_schedule.ps1` does that every 20 minutes while you are
logged in.

To run the wiki here anyway, for development or if the server is gone:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

That finds the Python environment, asks Tailscale for this machine's hostname
so the transport accepts requests through the funnel, and starts the wiki and
MCP server together. Leave the window open.

Note there is **no venv in this folder**. The interpreter lives next door in
`dnd-scribe\.venv`, which is why `.\.venv\Scripts\python.exe` fails from here.
`start.ps1` exists so you never have to remember that.

Tailscale runs as a service and returns on its own after a reboot, so this is
normally the only thing that needs restarting.

## Sharing the wiki as a website

The simplest thing to hand your table: a link. No Obsidian, no git, no Python.

```powershell
.\.venv\Scripts\python.exe tools\export_site.py
```

That writes `site/`: one HTML page per entity, an index, the art, and a
client-side search index. No build step and no JavaScript framework. Then serve
it alongside the MCP server, on the same address and tunnel:

```powershell
.\.venv\Scripts\python.exe mcp_server.py --http --wiki site --allowed-host <your-host>
```

- `https://<your-host>/wiki`, the wiki, behind the shared passphrase
- `https://<your-host>/mcp`, the MCP tools, behind a per-person bearer token

The split is deliberate, and the two doors are not the same strength. The
passphrase answers "is this someone from our table" for something opened from a
shared link. The MCP tokens are per person and can rewrite the campaign, so
they say who is calling as well as whether they may.

That describes `--wiki-live`, which is what runs. `--wiki` serves a static
export instead and is the older, read-only path.

### Putting a passphrase on it

The live wiki has two doors, in that order. The first is one shared passphrase
for the whole table, which answers "is this someone we know". The second is
picking your name, which decides whose secrets get rendered. Only the first is
a security boundary.

```powershell
python tools\set_passphrase.py
```

It prompts twice without echoing, so the passphrase never lands in your shell
history or in a screen share, and writes a scrypt hash to `.wiki-passphrase`.
The passphrase itself is never stored, so nobody can recover it from the repo
or a backup; forgetting it means setting a new one. `--suggest` invents a
memorable one, and `--remove` takes the door off entirely.

Words rather than random characters, because five people have to type it on
phones, and a passphrase they will use beats a stronger one they lose.

The MCP tokens are entirely separate and per person, so changing one never
affects the other.

The older `--wiki-password` flag still exists, but it only guards `--wiki`, the
exported static folder. It does nothing for the live wiki.

Re-run `export_site.py` after changing content; the folder is rewritten each
time.

## Reading the wiki in Obsidian

The `content/` folder is the source of truth, but it isn't pleasant to browse:
links live in frontmatter as `place/copper-vale` and the art isn't referenced
from the markdown at all. Export an Obsidian vault instead:

```powershell
.\.venv\Scripts\python.exe tools\export_obsidian.py
```

Then in Obsidian choose **Open folder as vault** and pick `vault/`. Open
**Start Here**, and press `Ctrl+G` for the graph.

What the export does that the raw files don't:

- Turns every link into a real `[[wikilink]]`, so the graph and backlinks work
- Embeds each page's art at the top
- Adds a *Mentioned by* section, so pages read properly outside Obsidian too
- Aliases each page to its slug, so `[[copper-vale]]` resolves as well as
  `[[Copper Vale]]`
- Disambiguates pages that share a name by appending the kind, because Obsidian
  resolves links by filename and duplicates would silently point at the wrong
  page

**The vault is generated and one-way.** Edits inside it are overwritten on the
next export. Write through `content/`, the CLI, or the MCP server. It only
deletes files it created itself (tracked in `.export-manifest.json`), so
anything you add to the vault by hand survives.

## Structure, and who gets to change it

What kinds of thing exist, how the front page is arranged and what the site is
called all live in `structure.yaml`, editable through the MCP tools or the
Structure page. Adding a kind is a config change, not a code change, and
renaming one migrates every page and repoints every link that pointed at them.

Anyone connected can do it. That was a deliberate decision by the person
running this table: the campaign is shared, so its shape is shared. The safety
net is git, not permissions. Every structural change commits first, so the
worst case is `git revert` rather than an evening lost.

The line that isn't crossed is code. Nothing here writes Python, edits
templates or runs a command; a tool that did would hand a shell to anyone who
ever leaked a token. Feature work goes through the repo instead.

## Uploads

Two kinds, kept apart:

- **Pictures** uploaded on the Art page join the same gallery as the generated
  ones, in `assets/`.
- **Attachments** on the Files page (maps, handouts, PDFs, recordings) live in
  `files/`, which is *not* gitignored: art can be redrawn from the content, a
  scanned map cannot.

What a file is gets decided by its leading bytes, never its name or the
browser's claim. SVG is refused outright since it can carry script and would
run on the wiki's own origin. Stored names are content hashes, so nothing a
person typed reaches the filesystem, and everything but plain images is served
as a download with `X-Content-Type-Options: nosniff`.

## The Discord inbox

`dnd-scribe` pulls the campaign's Discord channels into `lore/` on a schedule.
The wiki reads that archive and shows, at `/wiki/inbox`, everything that no
page accounts for yet.

A message stops being new when a page cites it (`discord:<channel>:<id>` in
`sources`), when someone presses **Not lore**, or when it predates the
watermark set the first time a channel is seen. That last rule is what keeps
four years of backlog from landing in the queue on day one; to review a channel
from the start anyway, set its watermark to `0` in `.inbox.json`.

Nothing is written to the wiki automatically, and that is the point. Discord is
four years of argument, jokes and half-ideas; the wiki is what the table
decided was true. Only a person can tell those apart, so the inbox hands them
the raw messages and a **Write it up** button that opens the new-page form with
the text already in it. Claude can work the same queue through `whats_new` and
`mark_filed`.

Point `lore_dir` in `config.yaml` somewhere else if the two projects aren't
side by side.

## Everyday commands

```bash
python cli.py new character "Kira Ashvale" --appearance "half-elf rogue, silver hair, twin daggers" --link place/saltmere-keep
```

```bash
python cli.py ls place --tag settlement
```

```bash
python cli.py show saltmere-keep
```

```bash
python cli.py check
```

`check` is the one to run before a session. It finds broken links and entities
nothing points at, which is how a shared wiki quietly rots.

## Layout

| Path | What it does |
| --- | --- |
| `universe/entities.py` | The data model, and the merge rules that protect human writing. |
| `universe/style.py` | Entity to image prompt. House style, framing, stable seeds. |
| `universe/assets.py` | Content-addressed art store and provenance sidecars. |
| `universe/art.py` | Local SDXL generation. |
| `universe/webapp.py` | The live wiki: sign-in, editing, art, inbox. |
| `universe/inbox.py` | What's been said in Discord that no page accounts for. |
| `universe/schema.py` | Kinds, front page layout, site name, and editing them. |
| `universe/hierarchy.py` | Which places sit inside which, and who may see the trail. |
| `universe/artqueue.py` | Asking for a picture when the GPU is on another machine. |
| `universe/uploads.py` | Uploaded pictures and attachments, and what's refused. |
| `universe/worldmap/azgaar.py` | Azgaar export to entities. |
| `cli.py` | All commands. |
| `content/` | Your world. This is the real deliverable. |
| `assets/` | Generated art. Regenerable, but committed: the server has no GPU. |
| `art-queue/` | Pictures the site asked for, waiting for the machine at home. |
| `deploy/` | Setting the server up, and keeping it in step with GitHub. |
| `OPERATIONS.md` | Where everything runs, how a change travels, what to do when it stops. |
