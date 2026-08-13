"""Tests for the shared passphrase.

It is the only real boundary on the site, so what matters is that it fails
closed: a wrong attempt, a missing file, a corrupt file and an empty string all
have to be refused, and the passphrase itself must never be recoverable from
what is stored.

    python tests\\test_gate.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from universe import gate  # noqa: E402

FAIL: list[str] = []
SECRET = "correct-horse-battery-staple"


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


sandbox = Path(tempfile.mkdtemp(prefix="gate-test-"))

print("\n== no passphrase set ==")
check("gate is off", not gate.is_enabled(sandbox))
check("and lets everyone through", gate.check(sandbox, "anything"),
      "a wiki with no passphrase must keep working")

print("\n== setting one ==")
ok, msg = gate.set_passphrase(sandbox, SECRET)
check("accepted", ok, msg)
check("gate is on", gate.is_enabled(sandbox))
check("short ones refused", not gate.set_passphrase(sandbox, "abc")[0])

print("\n== what is on disk ==")
raw = (sandbox / ".wiki-passphrase").read_text(encoding="utf-8")
check("the passphrase is not in it", SECRET not in raw,
      "plaintext would put a readable copy on the DM's machine")
stored = json.loads(raw)
check("it is a scrypt hash", stored["algorithm"] == "scrypt")
check("salted", len(stored["salt"]) == 32)
check("parameters recorded", stored["n"] >= 2 ** 14)

print("\n== checking attempts ==")
check("the right one works", gate.check(sandbox, SECRET))
check("a wrong one does not", not gate.check(sandbox, "wrong"))
check("empty does not", not gate.check(sandbox, ""))
check("None does not", not gate.check(sandbox, None))
check("case matters", not gate.check(sandbox, SECRET.upper()))
check("a prefix does not pass", not gate.check(sandbox, SECRET[:-1]))
check("trailing space does not pass", not gate.check(sandbox, SECRET + " "))

print("\n== a second salt gives a different hash ==")
first = json.loads((sandbox / ".wiki-passphrase").read_text(encoding="utf-8"))["hash"]
gate.set_passphrase(sandbox, SECRET)
second = json.loads((sandbox / ".wiki-passphrase").read_text(encoding="utf-8"))["hash"]
check("same passphrase, different stored hash", first != second,
      "so two tables using the same words do not look identical")
check("both still verify", gate.check(sandbox, SECRET))

print("\n== broken input fails closed ==")
(sandbox / ".wiki-passphrase").write_text("{ not json", encoding="utf-8")
check("corrupt file refuses everyone", not gate.check(sandbox, SECRET),
      "locking the table out beats letting the internet in")
(sandbox / ".wiki-passphrase").write_text('{"salt": "zz", "hash": "qq"}', encoding="utf-8")
check("nonsense hex refuses too", not gate.check(sandbox, SECRET))
check("and it still reports as enabled", gate.is_enabled(sandbox),
      "so the site asks rather than silently opening")

print("\n== removing it ==")
gate.set_passphrase(sandbox, SECRET)
check("clear reports true", gate.clear(sandbox))
check("gate is off again", not gate.is_enabled(sandbox))
check("clearing twice is false", not gate.clear(sandbox))

shutil.rmtree(sandbox, ignore_errors=True)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")
