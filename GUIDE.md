# Copper Vale: a guide for the table

Everything we know about the world lives in one place now: every town, NPC,
faction, item and god, cross-linked, with art. It was built from four years of
our Discord, The DM's wiki pages, Tobias Goreguts' session notes and the D&D Beyond sheets.

There are two ways in. You probably want both.

- **The website** for reading. Works on your phone.
- **Your own Claude** for asking questions and writing things down.

---

## 1. The website

**https://the-wiki.example/wiki**

### Making an account

Click **Create one** at the bottom of the sign-in page, then:

1. **Pick your name** from the dropdown. Choose your own, honestly. It decides
   whose secrets you're shown, and the world genuinely looks different for
   different people.
2. **Email and password.** Your email is only a sign-in name. Nothing is sent
   to it, ever, and there's no confirmation email to wait for. Password needs
   8 characters or more.

You'll be signed in straight away, and stay signed in for about a month.

If your name isn't in the dropdown, someone already registered as you. Try
signing in, or tell The DM.

### Reading it

Start at the front page: the region and settlements, the current party, and
the people we've lost.

- **Search** is the box in the top right. It searches everything you're allowed
  to see, including full page text. Press Escape to clear it.
- **Related** at the bottom of a page shows what it connects to.
  **Mentioned by** shows what points back at it.
- The nav bar filters by type: Places, Characters, Factions, Items.

Good places to start: **Copper Vale** for how the region is dying, **Hollow
Root Covenant** for what we're up against, or your own character.

### Secrets

Some pages have blocks only certain people can read. If you can read one, it
appears highlighted with a note saying who else can see it. Worth glancing at
before you repeat something at the table.

If you can't, you'll see a page that reads slightly short, and that's all. You
won't be told what you're missing, and neither will your Claude.

Only The DM can hide things from everyone. Any of us can keep something to
ourselves.

---

## 2. Connecting your own Claude

This is the good part. Your Claude can read the whole world, answer questions
about it, and write new pages properly linked into everything else.

**Ask The DM or Timothy Tuttle for your personal token.** It's yours, it's write access,
so treat it like a password. Everyone has a different one, and yours is what
tells the server which secrets you're allowed to see.

### Setting it up

Paste this into Claude, with your token in place of `PASTE_TOKEN`:

```
Please configure an MCP server for me. Details:

  Name:      copper-vale
  Transport: HTTP (streamable HTTP, not SSE, not stdio)
  URL:       https://the-wiki.example/mcp
  Auth:      an Authorization header with the value
             Bearer PASTE_TOKEN

Work out the right way to add it for whichever Claude client you're running
in, and tell me exactly what to do. Depending on the client that's usually:

  - Claude Code: the `claude mcp add` command with an http transport and a
    --header flag
  - Claude Desktop or another config-file client: an entry under "mcpServers"
    with "type": "http", the url, and a "headers" object containing the
    Authorization header
  - A stdio-only client: bridging with `npx mcp-remote <url> --header ...`

If you can edit the config file yourself, do it and tell me what changed. If
it needs a restart or a step I have to do, say so plainly.

Then verify by calling world_overview. It should report about 84 pages and
list five player characters. If it fails, tell me the exact error: 401 means
the token is wrong, and a connection failure probably means the machine
hosting it is switched off.
```

If your client uses a config file, this is the entry:

```json
{
  "mcpServers": {
    "copper-vale": {
      "type": "http",
      "url": "https://the-wiki.example/mcp",
      "headers": { "Authorization": "Bearer PASTE_TOKEN" }
    }
  }
}
```

### Check it worked

Ask your Claude: **"call whoami on copper-vale"**. It should come back with
your name, and how many pages you can see. If it says *guest*, your token
didn't take.

---

## 3. Getting Claude oriented

Paste this once, at the start of a conversation. It saves a lot of
back-and-forth.

```
You have access to a "copper-vale" MCP server. It's the shared wiki for our
D&D campaign, The Buried Star, run by The DM. Treat it as the group's collective
memory: it's real, it's shared, and other people rely on what's in it.

The world in one paragraph: Copper Vale is a dying region. Mining at Copper
Ridge tore open sulfide seams and blasting in the Dire Foothills fractured the
watershed, so the groundwater drains into the mines instead of the plains. One
river is left, the Last Run, and Valeshire sits on it. Beneath the bogs, a
secretive society called the Hollow Root Covenant worships an artifact called
the Buried Star and curses the land to keep itself safe. Nearly every thread in
the campaign is downstream of one decision about water.

The party is Tobias Goreguts (half-orc barbarian), Timothy Tuttle (tortle
druid), Korran Mossborn (goliath monk), Wren (elf fighter), and Aelan Viremont
(human illusionist).

Start by calling world_overview so you know what exists before you say
anything about it.

How I want you to work:

- ALWAYS search_world before create_page. Most things already have a page,
  often under a name I didn't guess. Duplicates are how this wiki degrades.
- Prefer update_page over create_page, and append to a body rather than
  replacing it. Someone else wrote what's already there.
- Never invent lore. If the wiki doesn't cover something, say so rather than
  filling the gap plausibly. A page that admits a gap beats a confident wrong
  one.
- Set `source` on anything you add, like "session 2026-08-20" or "The DM, in
  Discord". Every page tracks where its facts came from.
- Link generously with link_pages. Cross-links are most of the value here.
- `summary` is one sentence on what something means. `appearance` is what it
  physically looks like, because that feeds an image generator. Don't put
  "a beloved innkeeper" in appearance.
- Write appearances as physique and colour, never game jargon. An image model
  has never heard of a tortle and will ignore the word. "Green scaled
  turtle-folk with a domed shell" works.
- Sound like a person. No bullet-pointed corporate summary of a tavern.

If you want somewhere useful to start, call open_questions.
```

---

## 4. Things to actually do with it

### Ask it something

The fastest way to trust it is to ask something you already know:

> How did the party lose their memories?

It should come back with Maera Broadkettle, the Misenchanted Lavender Mead, her
recipe notes, and the Enchanters' Guild letter.

Others worth trying:

> Who killed Lucian, and what do we know about them?
> What's the connection between the Underbelly Mercantile and Rumbleshot Quarry?
> Everything we know about the Buried Star.
> Who have we met in Brindlewood?

### Write up a session

```
Using copper-vale: I'm going to tell you what happened in tonight's session.
Search for each person, place and thing I mention before assuming it's new.
Then update the existing pages and create only what's genuinely missing,
linking everything together. Source it as "session <today's date>". Ask me
about anything ambiguous rather than guessing.
```

Then just talk. It'll ask questions when something's unclear.

### Flesh out your character

```
Using copper-vale: get_page for my character, then interview me about them.
Ask one question at a time. When we're done, update the page with what we
established, keeping the appearance field visual and concrete, and link them
to the places and people that matter to them.
```

Character pages currently have descriptions taken from the art you posted
years ago. If yours is wrong, this is how to fix it.

### Write something only some people know

```
Using copper-vale: add to my character's page, as a secret only The DM and I can
read: <the thing>.
```

Your Claude passes `secret_audience` and it's invisible to everyone else, on
the website and through their Claude.

### Fill a gap

```
Using copper-vale: call open_questions and show me what's unfinished. Then
help me write up one of them.
```

There are pages that are deliberately just a name: **Sister Lethra**,
**Arrowfell**, the **Underbelly Safehouse**. If you know something about them,
that's the most useful thing you can add.

---

## 5. The tools, if you're curious

Your Claude has eight:

| | |
|---|---|
| `whoami` | who the server thinks you are |
| `world_overview` | the shape of everything |
| `search_world` | keyword search |
| `get_page` | one page plus what links to it |
| `list_pages` | browse by type or tag |
| `open_questions` | what's deliberately unfinished |
| `create_page` | add something new |
| `update_page` | add to something existing |
| `link_pages` | connect two things |

You don't need to name them. Just ask for what you want.

---

## 6. When something goes wrong

**"I can't sign in."** Passwords are case-sensitive, emails aren't. If you're
sure, ask The DM to reset it.

**"My name isn't in the dropdown."** Someone registered as you already. Try
signing in instead.

**Claude says 401.** Your token is wrong or has a stray space. Ask for it
again.

**Claude can't connect at all.** The whole thing runs on Timothy Tuttle's PC. If it's
off, the wiki and Claude both stop working. It isn't broken, it's asleep.

**Claude says something that's wrong.** Tell The DM, and check the page's Sources
line: it records where each fact came from. Some of it was reconstructed from
Discord history and a bit of it is guesswork. It's a wiki, not scripture.

---

## 7. A short etiquette

**Write things down after sessions.** Five minutes each is better than The DM
doing all of it.

**Don't overwrite people's prose.** Append. Your Claude knows to, if you don't
push it.

**Don't invent lore to fill a gap.** A page saying "we don't know" is more
useful than one confidently wrong, because the wrong one gets believed later.

**Say where things came from.** "Session 2026-08-20" or "The DM said in Discord"
is enough. Future us will care.

**Secrets are real.** If you can read something in a highlighted block, some of
us can't. Try not to say it out loud at the table.
