"""Wiki accounts: email, password, and who you are in the world.

Two ways to register, chosen at the server:

  * **Open** (the default). The roster from `people.yaml` is shown and each
    person picks themselves. Right for a table of friends who all know each
    other; it trusts anyone holding the link to be honest.
  * **Invite-gated** (`--require-invite`). A one-time code bound to one person
    decides who the account is, and nothing the registrant types can change it.
    Right if the link might reach someone you wouldn't vouch for.

The email address is an identifier and nothing more. Nothing is sent to it and
it is never verified, because there's no mail server here. Say so if anyone
asks why they got no confirmation message.

Stored in `.accounts.json` (gitignored):

    {
      "users":   {"wren@example.com": {"key": "wren", "salt": "...", "hash": "..."}},
      "invites": {"CODE": {"key": "wren", "used_by": null}}
    }

Passwords are hashed with scrypt and a per-user salt. The plaintext is never
written anywhere.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

ACCOUNTS_FILE = ".accounts.json"

# scrypt parameters. n=2**15 costs ~50ms per attempt here, which is invisible
# to a person signing in and expensive for anyone guessing.
#
# maxmem must be set explicitly: these parameters need 128 * n * r = 32MiB, and
# OpenSSL's default ceiling is exactly 32MiB, so the call fails with "memory
# limit exceeded" without headroom.
_N, _R, _P, _DKLEN = 2**15, 8, 1, 32
_MAXMEM = 96 * 1024 * 1024

# Deliberately permissive. Real addresses are stranger than most patterns
# allow, and this is an identifier rather than a delivery route, so the only
# job here is to reject obvious typos.
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8


@dataclass
class Account:
    email: str
    key: str  # which person in people.yaml this is


def normalise(email: str) -> str:
    """Addresses are case-insensitive in practice; store one canonical form."""
    return email.strip().lower()


class Accounts:
    def __init__(self, path: Path):
        self.path = path
        self._data: dict = {"users": {}, "invites": {}}
        self._mtime: float | None = None
        self._read()

    def _read(self) -> None:
        if not self.path.exists():
            self._mtime = None
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            self._data["users"] = loaded.get("users", {})
            self._data["invites"] = loaded.get("invites", {})
            self._mtime = self.path.stat().st_mtime
        except (json.JSONDecodeError, OSError):
            pass

    def _refresh(self) -> None:
        """Re-read if the file changed underneath us.

        The server holds this object for its whole lifetime, so without this a
        DM removing an account by hand would have no effect until a restart,
        and the roster would keep claiming a name nobody holds.
        """
        try:
            current = self.path.stat().st_mtime if self.path.exists() else None
        except OSError:
            return
        if current != self._mtime:
            self._read()

    def save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        try:
            self._mtime = self.path.stat().st_mtime
        except OSError:
            self._mtime = None

    # -- passwords -----------------------------------------------------

    @staticmethod
    def _hash(password: str, salt: bytes) -> str:
        return hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P,
            dklen=_DKLEN, maxmem=_MAXMEM,
        ).hex()

    # -- invites -------------------------------------------------------

    def mint_invite(self, key: str) -> str:
        code = secrets.token_urlsafe(9)
        self._data["invites"][code] = {"key": key.lower(), "used_by": None}
        return code

    def open_invites(self) -> dict[str, str]:
        self._refresh()
        return {
            code: info["key"]
            for code, info in self._data["invites"].items()
            if not info.get("used_by")
        }

    def invite_key(self, code: str) -> str | None:
        """The person key an unused code grants, compared in constant time."""
        self._refresh()
        found = None
        for candidate, info in self._data["invites"].items():
            if hmac.compare_digest(code, candidate) and not info.get("used_by"):
                found = info["key"]
        return found

    # -- registration and sign-in --------------------------------------

    @property
    def claimed_keys(self) -> set[str]:
        self._refresh()
        return {record["key"] for record in self._data["users"].values()}

    def register(
        self,
        email: str,
        password: str,
        *,
        code: str = "",
        key: str = "",
        known_keys: set[str] | None = None,
    ) -> tuple[Account | None, str]:
        """Create an account.

        Two ways in. With `code`, a one-time invite decides who the account is.
        With `key`, the person picks themselves from the roster: open
        registration, which trusts whoever has the link to be honest about
        which of your friends they are.
        """
        email = normalise(email)
        if not EMAIL.match(email):
            return None, "That doesn't look like an email address."
        if len(password) < MIN_PASSWORD:
            return None, f"Password must be at least {MIN_PASSWORD} characters."
        if email in self._data["users"]:
            return None, "There's already an account with that email. Sign in instead."

        if code:
            resolved = self.invite_key(code.strip())
            if resolved is None:
                return None, "That invite code isn't valid, or has already been used."
        else:
            resolved = (key or "").strip().lower()
            if not resolved or (known_keys is not None and resolved not in known_keys):
                return None, "Pick who you are from the list."
            # Catches a mis-click immediately rather than leaving two accounts
            # claiming to be the same person.
            if resolved in self.claimed_keys:
                return None, (
                    "Someone has already registered as that person. If it's you, "
                    "sign in instead. If you picked the wrong name, ask your DM."
                )

        salt = secrets.token_bytes(16)
        self._data["users"][email] = {
            "key": resolved,
            "salt": salt.hex(),
            "hash": self._hash(password, salt),
        }
        if code:
            self._data["invites"][code.strip()]["used_by"] = email
        self.save()
        return Account(email=email, key=resolved), ""

    def authenticate(self, email: str, password: str) -> Account | None:
        self._refresh()
        record = self._data["users"].get(normalise(email))
        if record is None:
            # Hash anyway, so an unknown address takes as long as a wrong
            # password and can't be identified by timing.
            self._hash(password, b"\x00" * 16)
            return None
        salt = bytes.fromhex(record["salt"])
        if not hmac.compare_digest(self._hash(password, salt), record["hash"]):
            return None
        return Account(email=normalise(email), key=record["key"])

    def set_password(self, email: str, password: str) -> bool:
        record = self._data["users"].get(normalise(email))
        if record is None:
            return False
        salt = secrets.token_bytes(16)
        record["salt"] = salt.hex()
        record["hash"] = self._hash(password, salt)
        self.save()
        return True

    @property
    def emails(self) -> list[str]:
        self._refresh()
        return sorted(self._data["users"])

    def key_for(self, email: str) -> str | None:
        self._refresh()
        record = self._data["users"].get(normalise(email))
        return record["key"] if record else None


def load(root: Path) -> Accounts:
    return Accounts(root / ACCOUNTS_FILE)
