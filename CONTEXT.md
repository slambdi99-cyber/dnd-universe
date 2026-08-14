# Domain language

The words this project uses, and what they mean here. Written down because five
people and their assistants edit this code, and the words were previously
defined only by usage, which is how "nobody" ended up spelled four different
ways with one of them quietly meaning something else.

Use these terms exactly. If a new concept needs a name, add it here in the same
change that introduces it.

## The world

**Entity**: one page. A place, character, faction, item, event, session,
creature, deity or lore note, stored as markdown with YAML frontmatter at
`content/<kind>/<slug>.md`. The files are the source of truth; anything else is
a derived index you can delete and rebuild.

**Kind**: the category an entity belongs to, and the folder it lives in. Not
hardcoded. The list is in `structure.yaml` and anyone can add to it.

**Slug**: an entity's filename without the extension. Unique within a kind.

**Ref**: `kind/slug`, how one entity points at another. The only identifier that
crosses module boundaries.

**Structure**: the shape of the wiki rather than its contents. Which kinds
exist, how the front page is arranged, what the site is called. Editable by
anyone, from the site or through MCP, and committed to git before each change.

## Who is reading

**Person**: someone at the table, listed in `people.yaml` with a `key`, a
display name and a role. Everyone is named by their character. The DM has no
character and is `The DM`.

**Identity**: a string a secret can be addressed to. A person has two, their own
key and their role, which is why `:::secret dm` reaches whoever is currently DM
without naming them.

**Viewer**: who is reading, as far as the code is concerned. Always an
`access.Viewer`, never a bare set of strings. Built one of three ways, and
saying which you mean is the point:

- `Viewer.person(p)` for a signed-in person, or a valid MCP token.
- `Viewer.nobody()` for a signed-out reader, an unrecognised token, or an
  export. No claim to any identity, so nothing addressed to anyone is readable.
- `Viewer.local()` for the process holding the files. Carries `all_access`, a
  flag rather than a set containing everyone's keys, so it cannot be confused
  with a person who happens to be in every audience.

**Audience**: the identities a secret block, or a whole page, is addressed to.
An empty audience means unrestricted, which is surprising and is preserved
deliberately. See `tests/test_visibility_agreement.py`.

## What may be read

**Entitlement**: everything `universe/access.py` decides. Two rules live there,
because they are the same rule wearing two hats:

- **Page visibility.** An entity may name an audience in `visible_to`. Anyone
  outside it is not told the page exists: not in listings, not in search, and a
  404 rather than a 403, so a refusal cannot be used to enumerate.
- **Link stripping.** A page you cannot see must not appear in anyone else's
  Related list either, or its name leaks even though its body does not.

**Secret**: a block inside a page, addressed to an audience.

```
:::secret dm, wren
Only the DM and Wren read this.
:::
```

Parsing and redaction live in `universe/secrets.py`, which `access` calls. Kept
separate on purpose: it is the deepest and best-tested module here, and
absorbing it would make a larger module without fixing anything.

**View**: one viewer's version of the world, computed once per request by
`access.for_viewer(...)`. Holds the refs that viewer may see, so link stripping
stays consistent instead of each surface assembling its own allowed set.

## Coming in and going out

**Surface**: anywhere the world is read. The live website, the MCP server, the
static site export, the Obsidian export. All four ask `access` the same
question, and that is the invariant this codebase most needs to keep.

**Inbox**: Discord messages that no page accounts for yet. A review queue, never
an importer: nothing is written to the wiki without a person deciding.

**Asset**: a generated or uploaded image, content-addressed under `assets/`.
Regenerable, so it is gitignored.

**Attachment**: a file someone uploaded to a page, such as a map, a handout, a
PDF or a recording, under `files/`. Not regenerable, so it is committed.

**Gate**: the one shared passphrase in front of the website. It answers "is this
someone from our table" and nothing else. Who you are is still the name you
pick, which is trust rather than security.
