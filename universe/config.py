"""Config loading for the universe toolchain."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    raw: dict[str, Any]
    root: Path = ROOT

    @property
    def content_dir(self) -> Path:
        return self.root / str(self.raw.get("content_dir", "content"))

    @property
    def assets_dir(self) -> Path:
        return self.root / str(self.raw.get("assets_dir", "assets"))

    @property
    def files_dir(self) -> Path:
        """Uploaded attachments. Separate from assets/, which is regenerable.

        Art can be redrawn from the content and the config; a map someone
        scanned cannot. Keeping them apart means `assets/` stays safe to delete
        and stays out of git, while this doesn't.
        """
        return self.root / str(self.raw.get("files_dir", "files"))

    @property
    def art(self) -> dict[str, Any]:
        return self.raw.get("art", {})

    @property
    def draws_here(self) -> bool:
        """Whether this machine can draw, or only ask for drawings.

        The wiki runs on a free host with no GPU. Everything else works there;
        art does not, and never will. So the site queues a request in the repo
        and the machine at home drains it.

        This is a property of the machine, not of the campaign, so it is a
        marker file rather than a config key. config.yaml is tracked and shared:
        setting it there would have travelled to the machine at home on the next
        pull and switched off the graphics card it exists to use.

        Absent means yes, because every machine that runs the tests or the CLI
        can draw, and the server is the one exception.
        """
        return not (self.root / ".no-gpu").exists()

    @property
    def house_style(self) -> str:
        return self.art.get("house_style", "")

    @property
    def negative_prompt(self) -> str:
        return self.art.get("negative_prompt", "")

    @property
    def worldmap(self) -> dict[str, Any]:
        return self.raw.get("worldmap", {})


def load(root: Path | None = None) -> Config:
    root = root or ROOT
    path = root / "config.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}")
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return Config(raw=raw, root=root)
