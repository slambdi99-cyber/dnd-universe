# The Buried Star: a guide for the table

Everything we know about the world lives in one place now: every town, NPC,
faction, item and god, cross-linked, with art. It was built from four years of
our Discord, The DM's wiki pages, Tobias Goreguts' session notes and the D&D Beyond sheets.

There are two ways in. You probably want both.

- **The website** for reading. Works on your phone.
- **Your own AI assistant** for asking questions and writing things down.
  Claude, ChatGPT, Cursor, whatever you already use.

---

## 1. The website

**Timothy Tuttle will send you the link**, and the passphrase with it. Neither is
written down here: this guide is in a public repo.

### Signing in

Two steps, once. The site asks for **one passphrase, shared by the whole
table** - it's in the group chat. Then you click your own name.

That's the whole thing. Your name decides whose secrets you're shown, and the
world genuinely looks different for different people, so pick yours honestly.
Nothing stops you clicking someone else's; we're trusting each other here.

You stay signed in for about a month, passphrase included, so you'll type it
roughly never. **Not you?** at the bottom of any page switches name; signing
out asks for the passphrase again, which is what you want on a shared laptop.

The passphrase only answers "is this someone from our table". It doesn't say
who you are - that's still the name you pick, still on trust.

If your name isn't there, click **Someone new**, type your name and your
character's, and you're in.

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

### Adding and changing things

You don't need an assistant for this. Every page has an **Edit** button in the top
right, and **+ New** sits in the nav bar on every page, so writing something
down never means going back to the front page first.

The form has:

- **Name** and **Summary**, a sentence on what the thing is
- **Appearance**, what it physically looks like. This is what the art generator
  draws, so write physique and colour rather than game words. "Green scaled
  turtle-folk with a domed shell" works; "tortle" does nothing.
- **Body**, the actual writing. Markdown works.
- **Tags** and **Links**, both comma separated. Links look like
  `place/brindlewood`.
- **Add a secret**, at the bottom. Type something, tick who's allowed to read
  it, and only those people ever see it.

Edits are attributed, so pages record who changed them.

**One thing to know if you edit a page with secrets on it.** You only ever see
your own version, so the box you're typing in doesn't contain other people's
secret sections. They're kept exactly as they are and put back when you save,
and the form tells you how many are being preserved. You can't accidentally
delete something you can't see.

### Making a picture for a page

Every page has an **Art** button next to Edit. Type what you want to see and it
draws three versions on the machine in The DM's office. Click the one you like and
it becomes the page's picture.

It takes roughly a minute, so leave the tab open. Nothing is attached until you
pick one, so a prompt that comes out badly costs nothing but the wait. The
earlier pictures for that page stay listed underneath, and you can go back to
one at any time.

Describe what you'd see, not what it is. "Weathered stone bridge over a dry
riverbed, dusk, low mist" gets you something; "the bridge" gets you a bridge
from nowhere in particular. Game words mean nothing to it, so say "green scaled
turtle-folk with a domed shell" rather than "tortle".

### Uploading a picture instead

The same Art page takes an upload. If you drew something, commissioned it, or
found the perfect image, that beats anything the GPU will produce. PNG, JPEG,
GIF or WEBP, up to 25MB. It goes straight on the page and joins the gallery, so
you can switch back and forth.

### Files on a page

**Files** next to Edit and Art. Battle maps, handouts, PDFs, a recording of the
session, the printout of someone's homebrew subclass. Anything the table wants
kept with that page rather than lost in Discord.

Images, PDF, ZIP, MP3, OGG and MP4, up to 25MB. Not SVG, which can carry
scripts and would run as part of the site. Removing a file takes it off the
page but doesn't delete it, in case another page uses the same one.

### Changing the shape of the wiki

**Structure** in the nav. This is the one that surprises people: any of us can
add a whole new *kind* of page. If the campaign needs Ships, or Quests, or
Rumours, add it and it appears in the nav, in the new-page form, and in
everyone's assistant. You can rename kinds too, which moves every page and
repoints every link, and rearrange the front page.

There's no DM-only tier here. Everything commits to git before it changes, so
a bad idea is undoable rather than permanent.

### The inbox

**Inbox** in the nav is everything said in our Discord lore channels that no
page accounts for yet. The server checks Discord every half hour on its own, so
this fills up by itself.

Two buttons on each message:

- **Write it up** opens a new page with the message already in the box. Edit it
  into something that reads like a wiki entry and save. The page credits the
  message, and the message leaves the inbox.
- **Not lore** is for jokes, dice rolls and "lol". It just goes away.

Nothing is ever added to the wiki automatically. A machine summarising four
years of our arguments into confident wiki pages would be worse than useless,
so a person decides every time. That person can be any of us.

Your assistant can work the queue too, which is faster: *"check what's new and
write up anything worth keeping."*

### Secrets

Some pages have blocks only certain people can read. If you can read one, it
appears highlighted with a note saying who else can see it. Worth glancing at
before you repeat something at the table.

If you can't, you'll see a page that reads slightly short, and that's all. You
won't be told what you're missing, and neither will your assistant.

Only The DM can hide things from everyone. Any of us can keep something to
ourselves.

---

## 2. Connecting your assistant

This is the good part. It can read the whole world, answer questions about it,
and write new pages properly linked into everything else.

The wiki speaks MCP, which is an open protocol, so this isn't Claude-only:
ChatGPT, Cursor, VS Code, Zed and most others can connect to it too. Use
whatever you already have.

You don't need to ask anyone for anything. Once you're signed in to the
website, click **connect an assistant** in the top right.

That page has your own connection details already filled in, several ways:

- **The three facts any MCP client needs** (URL, transport, auth header), which
  is all you need if your client has a settings box for them.
- **A prompt to paste in**, which gets your assistant to work out its own client
  and set itself up. Easiest, and what most people should use.
- **A one-line command** for Claude Code and the CLIs that copied its syntax.
- **The raw config**, which is the same shape in Claude Desktop, Cursor,
  Windsurf, Cline and Zed.
- **A curl command**, to prove the endpoint is up without any assistant at all.

Each has a Copy button. Pick whichever suits and paste it.

### Check it worked

Ask your assistant: **"call whoami on buried-star"**. It should come back with
your name, and how many pages you can see. If it says *guest*, the header
didn't take: go back to the connect page and try one of the other options.

### One thing to be careful with

What's on that page is effectively your password. It can write to the campaign,
and it decides whose secrets you're shown. Don't paste it into the group chat.
If it does get out, tell The DM and it can be replaced.

---

## 3. Getting your assistant oriented

Paste this once, at the start of a conversation. It saves a lot of
back-and-forth.

```
You have access to a "buried-star" MCP server. It's the shared wiki for our
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
Using buried-star: I'm going to tell you what happened in tonight's session.
Search for each person, place and thing I mention before assuming it's new.
Then update the existing pages and create only what's genuinely missing,
linking everything together. Source it as "session <today's date>". Ask me
about anything ambiguous rather than guessing.
```

Then just talk. It'll ask questions when something's unclear.

### Flesh out your character

```
Using buried-star: get_page for my character, then interview me about them.
Ask one question at a time. When we're done, update the page with what we
established, keeping the appearance field visual and concrete, and link them
to the places and people that matter to them.
```

Character pages currently have descriptions taken from the art you posted
years ago. If yours is wrong, this is how to fix it.

### Write something only some people know

```
Using buried-star: add to my character's page, as a secret only The DM and I can
read: <the thing>.
```

Your assistant passes `secret_audience` and it's invisible to everyone else,
on the website and through theirs.

### Fill a gap

```
Using buried-star: call open_questions and show me what's unfinished. Then
help me write up one of them.
```

### Catch up on Discord

```
Using buried-star: call whats_new. Show me what's worth keeping, write up the
ones I agree with, and mark the rest as filed. Don't invent anything that
isn't in the messages.
```

There are pages that are deliberately just a name: **Sister Lethra**,
**Arrowfell**, the **Underbelly Safehouse**. If you know something about them,
that's the most useful thing you can add.

---

## 5. The tools, if you're curious

Whatever client you use:

| | |
|---|---|
| `whoami` | who the server thinks you are |
| `world_overview` | the shape of everything |
| `search_world` | keyword search |
| `get_page` | one page plus what links to it |
| `list_pages` | browse by type or tag |
| `open_questions` | what's deliberately unfinished |
| `whats_new` | Discord messages no page accounts for yet |
| `get_structure` | what kinds exist and how the front page is built |
| `list_files` | files attached to a page |
| `create_page` | add something new |
| `update_page` | add to something existing |
| `link_pages` | connect two things |
| `mark_filed` | dismiss Discord messages that aren't lore |
| `add_kind`, `change_kind`, `remove_kind` | reshape the world |
| `move_page` | move one page to a different kind |
| `set_site`, `set_home_sections` | rename it, rebuild the front page |
| `remove_file` | take a file off a page |

You don't need to name them. Just ask for what you want.

---

## 6. When something goes wrong

**"My name isn't on the sign-in page."** Click **Someone new** and add
yourself. It takes ten seconds and nobody has to approve it.

**"The inbox is empty but people have been posting."** It checks every half
hour, and it only counts the channels that were imported. Ask Timothy Tuttle.

**"The art button is spinning forever."** One picture at a time, and the queue
is one graphics card. If someone else hit generate first, yours waits. Give it
a couple of minutes before assuming it's stuck.

**It says 401.** The header didn't copy cleanly. Go back to **connect
an assistant** on the website and use the Copy button rather than selecting by
hand.

**It can't connect at all, or the site won't load.** The whole thing runs
on Timothy Tuttle's PC. If it's off, the wiki and the MCP both stop working. It isn't
broken, it's asleep. Timothy Tuttle: `powershell -ExecutionPolicy Bypass -File
.\start.ps1` from `C:\Claude\dnd-universe`.

**It says something that's wrong.** Tell The DM, and check the page's Sources
line: it records where each fact came from. Some of it was reconstructed from
Discord history and a bit of it is guesswork. It's a wiki, not scripture.

---

## 7. A short etiquette

**Write things down after sessions.** Five minutes each is better than The DM
doing all of it.

**Don't overwrite people's prose.** Append. Your assistant knows to, if you don't
push it.

**Don't invent lore to fill a gap.** A page saying "we don't know" is more
useful than one confidently wrong, because the wrong one gets believed later.

**Say where things came from.** "Session 2026-08-20" or "The DM said in Discord"
is enough. Future us will care.

**Secrets are real.** If you can read something in a highlighted block, some of
us can't. Try not to say it out loud at the table.
