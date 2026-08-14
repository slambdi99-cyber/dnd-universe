"""Editing the shape of the wiki: kinds, the front page, the name.

Open to everyone signed in, same as the MCP tools. The table shares the world,
so it shares the shape of it, and the safety net is git rather than permissions:
every change here commits first, so a bad idea is undoable rather than
permanent.
"""

from __future__ import annotations

from functools import partial

import html
from pathlib import Path

from starlette.routing import Route

from .. import schema as schema_mod

async def structure_page(request, wiki):
    """Edit the shape of the wiki: kinds, front page, name.

    Open to everyone signed in, same as the MCP tools. The person who runs
    this decided the table shares the shape of the world as well as its
    contents, so there is no DM tier here.
    """
    redirect = wiki.require_login(request)
    if redirect:
        return redirect
    _, user = wiki.viewer_for(request)
    wiki.schema.reload_if_changed()
    message = error = ""

    if request.method == "POST":
        form = await request.form()
        action = str(form.get("action", ""))
        wiki.snapshot(f"{action or 'structure change'} from the site", user or "")

        if action == "add_kind":
            ok, note = schema_mod.add_kind(
                wiki.schema, str(form.get("key", "")), str(form.get("label", "")),
                nav=bool(form.get("in_nav")))
        elif action == "rename_kind":
            ok, note = schema_mod.rename_kind(
                wiki.schema, str(form.get("key", "")),
                str(form.get("rename_to", "")), wiki.library,
                label=str(form.get("label", "")))
        elif action == "update_kind":
            ok, note = schema_mod.update_kind(
                wiki.schema, str(form.get("key", "")),
                label=str(form.get("label", "")) or None,
                nav=bool(form.get("in_nav")))
        elif action == "remove_kind":
            ok, note = schema_mod.remove_kind(
                wiki.schema, str(form.get("key", "")), wiki.library,
                str(form.get("move_pages_to", "")))
        elif action == "set_site":
            ok, note = schema_mod.set_site(
                wiki.schema, str(form.get("name", "")), str(form.get("tagline", "")))
        elif action == "set_home":
            try:
                import yaml

                parsed = yaml.safe_load(str(form.get("home", ""))) or []
                if not isinstance(parsed, list):
                    raise ValueError("expected a list of sections")
                ok, note = schema_mod.set_home(wiki.schema, parsed)
            except (ValueError, TypeError) as exc:
                ok, note = False, f"That didn't parse: {exc}"
            except Exception as exc:  # yaml.YAMLError and friends
                ok, note = False, f"That isn't valid YAML: {exc}"
        elif action == "set_index_tags":
            try:
                import yaml

                parsed = yaml.safe_load(str(form.get("index_tags", ""))) or []
                if not isinstance(parsed, list):
                    raise ValueError("expected a list of tag groups")
                ok, note = schema_mod.set_index_tags(wiki.schema, parsed)
            except (ValueError, TypeError) as exc:
                ok, note = False, f"That didn't parse: {exc}"
            except Exception as exc:  # yaml.YAMLError and friends
                ok, note = False, f"That isn't valid YAML: {exc}"
        else:
            ok, note = False, "Unknown action."

        message, error = (note, "") if ok else ("", note)

    counts = {k: sum(1 for _ in wiki.library.all(k)) for k in wiki.schema.keys}
    return wiki.render("Structure",
                  _structure_page(wiki.schema, counts, message, error),
                  user=user)


def _structure_page(schema, counts: dict[str, int], message: str,
                    error: str) -> str:
    import yaml

    note = f'<div class="notice">{html.escape(message)}</div>' if message else ""
    err = f'<div class="error">{html.escape(error)}</div>' if error else ""

    rows = []
    for kind in schema.kinds:
        n = counts.get(kind.key, 0)
        others = "".join(
            f'<option value="{html.escape(k.key)}">{html.escape(k.label)}</option>'
            for k in schema.kinds if k.key != kind.key
        )
        removal = (
            f'<form method="post" class="inline">'
            f'<input type="hidden" name="action" value="remove_kind">'
            f'<input type="hidden" name="key" value="{html.escape(kind.key)}">'
            + (f'<select name="move_pages_to"><option value="">move '
               f'{n} page(s) to...</option>{others}</select>' if n else "")
            + f'<button type="submit">Remove</button></form>'
        )
        rows.append(f"""
<div class="kindrow">
  <form method="post" class="inline">
    <input type="hidden" name="action" value="update_kind">
    <input type="hidden" name="key" value="{html.escape(kind.key)}">
    <code>{html.escape(kind.key)}</code>
    <input name="label" value="{html.escape(kind.label)}" size="14">
    <label class="cb"><input type="checkbox" name="in_nav"
      {"checked" if kind.nav else ""}> in nav</label>
    <button type="submit">Save</button>
  </form>
  <form method="post" class="inline">
    <input type="hidden" name="action" value="rename_kind">
    <input type="hidden" name="key" value="{html.escape(kind.key)}">
    <input name="rename_to" placeholder="rename to" size="12">
    <button type="submit">Rename</button>
  </form>
  {removal}
  <span class="hint">{n} page{"s" if n != 1 else ""}</span>
</div>""")

    home_yaml = yaml.safe_dump([s.as_dict() for s in schema.home],
                               sort_keys=False, allow_unicode=True)
    index_tags_yaml = yaml.safe_dump([t.as_dict() for t in schema.index_tags],
                                     sort_keys=False, allow_unicode=True)

    return f"""
<h1>Structure</h1>
<p class="summary">What kinds of thing this world is made of, and how the front
page is arranged. Anyone can change this.</p>
{note}{err}
<div class="notice">Every change here commits to git first, so anything that
goes wrong can be undone. Renaming a kind moves its pages and repoints every
link to them.</div>

<h2>Kinds</h2>
{"".join(rows)}

<h3>Add a kind</h3>
<form method="post" class="inline">
  <input type="hidden" name="action" value="add_kind">
  <input name="key" placeholder="ship" size="10" required>
  <input name="label" placeholder="Ships" size="12">
  <label class="cb"><input type="checkbox" name="in_nav" checked> in nav</label>
  <button type="submit">Add</button>
</form>
<p class="hint">The key is lowercase and singular; it becomes the folder and the
URL. The label is what people see.</p>

<h2>The front page</h2>
<p class="hint">One block of cards per section, in this order. A section needs a
<code>kind</code>; <code>tag</code>, <code>any_tag</code> and <code>data</code>
narrow it. Empty sections are skipped.</p>
<form method="post" class="auth wide">
  <input type="hidden" name="action" value="set_home">
  <textarea name="home" rows="14">{html.escape(home_yaml)}</textarea>
  <button type="submit">Save the front page</button>
</form>

<h2>Index pages</h2>
<p class="hint">First-class tags split a kind's index page into sections. Each
entry needs <code>title</code>, <code>kind</code> and <code>tag</code>. Pages
without any configured tag still appear under an automatic Other section.</p>
<form method="post" class="auth wide">
  <input type="hidden" name="action" value="set_index_tags">
  <textarea name="index_tags" rows="16">{html.escape(index_tags_yaml)}</textarea>
  <button type="submit">Save index page groups</button>
</form>

<h2>Name</h2>
<form method="post" class="auth wide">
  <input type="hidden" name="action" value="set_site">
  <label for="sn">Title</label>
  <input id="sn" name="name" value="{html.escape(schema.name)}">
  <label for="tl">Tagline <span class="hint">the line under it</span></label>
  <input id="tl" name="tagline" value="{html.escape(schema.tagline)}">
  <button type="submit">Save</button>
</form>
"""


def routes(wiki) -> list[Route]:
    return [
        Route("/wiki/structure", partial(structure_page, wiki=wiki),
              methods=["GET", "POST"]),
    ]
