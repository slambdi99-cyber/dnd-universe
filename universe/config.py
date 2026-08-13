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
