# dnd-universe

The shared world: every place, person, faction and item in your campaign, as
linked files you can query, draw, and hand to Claude.

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

Not built yet: the web app, the MCP server, Foundry integration, and the
session-to-wiki pipeline.

## The one architectural decision worth arguing about

**Files are the source of truth. A database, when it arrives, is a derived
index you can delete and rebuild.**

Entities are markdown with YAML frontmatter under `content/<kind>/<slug>.md`.
The reasons:

- Several people edit this world at once, and markdown in git merges. A shared
  database needs a migration and a merge strategy for every schema change, and
  someone to own it.
- Claude reads and writes files natively. That's the whole basis of the MCP
  server plan: your friends' Claude can author lore directly, and a file is far
  less fragile to hand a language model than a write API.
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
and write Copper Vale from their own client instead of routing everything
through one person.

Eight tools: `search_world`, `get_page`, `list_pages`, `world_overview`,
`open_questions`, `create_page`, `update_page`, `link_pages`.

### Running it just for yourself

```powershell
.\.venv\Scripts\python.exe mcp_server.py
```

Then point a client at it. For Claude Code, in `.claude/settings.json`:

```json
{
  "mcpServers": {
    "copper-vale": {
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
$env:UNIVERSE_MCP_TOKEN = (Get-Content .mcp-token -Raw).Trim()
```

```powershell
.\.venv\Scripts\python.exe mcp_server.py --http --allowed-host some-words-here.trycloudflare.com
```

Your players connect to `<that-url>/mcp` with an `Authorization: Bearer <token>`
header.

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

- `https://<your-host>/wiki` — the wiki, **open, no token**
- `https://<your-host>/mcp` — the MCP tools, **token required**

The split is deliberate. The wiki is a read-only rendering meant to be opened
from a shared link. The MCP tools can rewrite the campaign, so they stay behind
the bearer token.

### Putting a password on it

Without `--wiki-password` the wiki is readable by anyone with the link. To lock
it:

```powershell
.\.venv\Scripts\python.exe tools\make_wiki_password.py
```

That writes a five-word passphrase to `.wiki-password` (gitignored). Words
rather than random characters, because five people have to type it on phones,
and a passphrase they'll use beats a stronger one they lose. Then:

```powershell
$env:UNIVERSE_WIKI_PASSWORD = (Get-Content .wiki-password -Raw).Trim()
```

and start the server as above. Browsers prompt once and remember it. The
username is ignored; there's one shared secret.

Pages and images are both covered, and the MCP token is entirely separate, so
changing one never affects the other.

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
| `universe/worldmap/azgaar.py` | Azgaar export to entities. |
| `cli.py` | All commands. |
| `content/` | Your world. This is the real deliverable. |
| `assets/` | Generated art. Regenerable, gitignored. |
