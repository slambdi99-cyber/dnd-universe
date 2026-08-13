"""Content-addressed store for generated art.

Every image is keyed by a hash of everything that determined it: prompt,
negative prompt, seed, model, and dimensions. Two consequences that matter:

  * Regenerating with identical inputs is a no-op instead of ten minutes of
    GPU time. Re-running the whole world after adding one new character costs
    one image, not four hundred.
  * Every image on disk can be traced back to exactly what produced it, via
    the JSON sidecar written alongside it.

Layout:

    assets/<kind>/<slug>/<variant>-<hash8>.png
    assets/<kind>/<slug>/<variant>-<hash8>.json
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class AssetSpec:
    kind: str
    slug: str
    variant: str
    prompt: str
    negative: str
    seed: int
    model: str
    width: int
    height: int
    steps: int

    def digest(self) -> str:
        payload = json.dumps(
            {
                "prompt": self.prompt,
                "negative": self.negative,
                "seed": self.seed,
                "model": self.model,
                "width": self.width,
                "height": self.height,
                "steps": self.steps,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @property
    def asset_id(self) -> str:
        return f"{self.kind}/{self.slug}/{self.variant}-{self.digest()[:8]}"


class AssetStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def path_for(self, spec: AssetSpec) -> Path:
        return self.root / spec.kind / spec.slug / f"{spec.variant}-{spec.digest()[:8]}.png"

    def has(self, spec: AssetSpec) -> bool:
        return self.path_for(spec).exists()

    def resolve(self, asset_id: str) -> Path:
        kind, slug, name = asset_id.split("/", 2)
        return self.root / kind / slug / f"{name}.png"

    def write_sidecar(self, spec: AssetSpec, extra: dict | None = None) -> Path:
        path = self.path_for(spec).with_suffix(".json")
        payload = asdict(spec)
        payload["asset_id"] = spec.asset_id
        payload["created_at"] = datetime.now(timezone.utc).isoformat()
        if extra:
            payload.update(extra)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def variants_for(self, kind: str, slug: str) -> list[Path]:
        folder = self.root / kind / slug
        if not folder.exists():
            return []
        return sorted(folder.glob("*.png"))
