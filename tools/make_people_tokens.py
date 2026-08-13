"""Give each person in people.yaml their own MCP token.

Secrets need identity. One shared token cannot tell Wren from Tobias Goreguts, so this
mints a token per person and writes them to `.people-tokens.json` (gitignored).

    python tools\\make_people_tokens.py            # mint any that are missing
    python tools\\make_people_tokens.py --show     # print them, to hand out
    python tools\\make_people_tokens.py --rotate wren

Tokens are only printed when you ask, so they don't end up in scrollback by
accident.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from universe import config as config_mod  # noqa: E402
from universe import people as people_mod  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--show", action="store_true", help="Print the tokens")
    ap.add_argument("--rotate", metavar="KEY",
                    help="Replace one person's token, invalidating the old one")
    ap.add_argument("--rotate-all", action="store_true")
    args = ap.parse_args()

    cfg = config_mod.load()
    registry = people_mod.load(cfg.root)
    if not registry.members:
        print("No people in people.yaml.", file=sys.stderr)
        return 1

    path = cfg.root / people_mod.TOKENS_FILE
    existing: dict[str, str] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    by_key = {key: token for token, key in existing.items()}

    if args.rotate_all:
        by_key = {}
    elif args.rotate:
        by_key.pop(args.rotate.strip().lower(), None)

    minted = []
    for key in registry.members:
        if key not in by_key:
            by_key[key] = secrets.token_urlsafe(32)
            minted.append(key)

    # Drop tokens for people no longer listed.
    stale = [k for k in by_key if k not in registry.members]
    for key in stale:
        by_key.pop(key)

    path.write_text(
        json.dumps({t: k for k, t in by_key.items()}, indent=2), encoding="utf-8"
    )

    print(f"{len(by_key)} token(s) in {path}")
    if minted:
        print(f"  minted: {', '.join(sorted(minted))}")
    if stale:
        print(f"  removed (no longer in people.yaml): {', '.join(sorted(stale))}")

    if args.show:
        print("\nHand these out privately. Each is write access.\n")
        width = max(len(registry.members[k].name) for k in by_key)
        for key in sorted(by_key):
            person = registry.members[key]
            role = "DM" if person.is_dm else person.character or "player"
            print(f"  {person.name:<{width}}  ({role})")
            print(f"      {by_key[key]}\n")
    else:
        print("\nRe-run with --show to print them.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
