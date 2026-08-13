"""Generate art for entities on the local GPU.

Wraps SDXL and ties together the three other pieces: `style` builds the prompt,
`assets` decides whether the image already exists, and `entities` records the
result back onto the entity so the wiki knows the picture is there.

The pipeline loads lazily, so importing this module costs nothing and a dry run
never touches CUDA.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import style
from .assets import AssetSpec, AssetStore
from .config import Config
from .entities import Entity, Library


@dataclass
class ArtResult:
    entity: Entity
    spec: AssetSpec
    path: Path
    generated: bool  # False means it was already in the store

    @property
    def asset_id(self) -> str:
        return self.spec.asset_id


class ArtService:
    def __init__(
        self,
        cfg: Config,
        library: Library,
        store: AssetStore,
        *,
        house_style: str | None = None,
    ):
        self.cfg = cfg
        self.library = library
        self.store = store
        # Overrides config.yaml for one run. Exists so you can A/B a style
        # across a few entities without editing config and regenerating
        # everything to compare.
        self.house_style = house_style if house_style is not None else cfg.house_style
        self._pipe = None

    # -- model ---------------------------------------------------------

    @property
    def pipe(self):
        if self._pipe is None:
            import torch
            from diffusers import StableDiffusionXLPipeline

            model = self.cfg.art.get(
                "model", "stabilityai/stable-diffusion-xl-base-1.0"
            )
            print(f"[art] loading {model} (first run downloads ~7GB)...", flush=True)
            self._pipe = StableDiffusionXLPipeline.from_pretrained(
                model,
                torch_dtype=torch.float16,
                variant="fp16",
                use_safetensors=True,
            )
            # Keeps peak VRAM near 4-5GB by paging submodules onto the GPU only
            # while they run. Leaves room for other work on a 12GB card.
            self._pipe.enable_model_cpu_offload()
            # pipe.enable_vae_tiling() is deprecated and goes away in
            # diffusers 0.40; call it on the VAE directly.
            self._pipe.vae.enable_tiling()
            self._pipe.set_progress_bar_config(disable=True)
            print("[art] ready", flush=True)
        return self._pipe

    def unload(self) -> None:
        if self._pipe is None:
            return
        import torch

        del self._pipe
        self._pipe = None
        torch.cuda.empty_cache()

    # -- generation ----------------------------------------------------

    def spec_for(self, entity: Entity, variant: str = "default") -> AssetSpec:
        art = self.cfg.art
        prompt = style.build(
            entity,
            house_style=self.house_style,
            negative=self.cfg.negative_prompt,
            variant=variant,
            max_words=int(art.get("max_prompt_words", 60)),
            library=self.library,
        )
        return AssetSpec(
            kind=entity.kind,
            slug=entity.slug,
            variant=variant,
            prompt=prompt.text,
            negative=prompt.negative,
            seed=prompt.seed,
            model=art.get("model", "stabilityai/stable-diffusion-xl-base-1.0"),
            width=int(art.get("width", 1024)),
            height=int(art.get("height", 1024)),
            steps=int(art.get("steps", 30)),
        )

    def generate(
        self,
        entity: Entity,
        variant: str = "default",
        *,
        force: bool = False,
        dry_run: bool = False,
    ) -> ArtResult:
        spec = self.spec_for(entity, variant)
        path = self.store.path_for(spec)

        if dry_run:
            return ArtResult(entity, spec, path, generated=False)

        if path.exists() and not force:
            self._record(entity, spec)
            return ArtResult(entity, spec, path, generated=False)

        import torch

        generator = torch.Generator(device="cuda").manual_seed(spec.seed)
        result = self.pipe(
            prompt=spec.prompt,
            negative_prompt=spec.negative or None,
            num_inference_steps=spec.steps,
            guidance_scale=float(self.cfg.art.get("guidance_scale", 6.0)),
            width=spec.width,
            height=spec.height,
            generator=generator,
        )

        path.parent.mkdir(parents=True, exist_ok=True)
        result.images[0].save(path)
        self.store.write_sidecar(spec, {"entity_name": entity.name})
        self._record(entity, spec)
        return ArtResult(entity, spec, path, generated=True)

    def _record(self, entity: Entity, spec: AssetSpec) -> None:
        """Point the entity at its art, without disturbing anything else.

        Re-reads from disk before writing. A long `art --all` run holds entities
        in memory for many minutes, and anything that edits content meanwhile
        (a seed script, a person with a text editor) would otherwise be silently
        reverted when this saved its stale copy back.
        """
        if spec.asset_id in entity.art:
            return
        entity.art.append(spec.asset_id)

        current = self.library.load(entity.kind, entity.slug)
        if current is None:
            self.library.save(entity)
            return
        if spec.asset_id not in current.art:
            current.art.append(spec.asset_id)
        self.library.save(current)

    def generate_missing(
        self, kind: str | None = None, variant: str = "default", *, dry_run: bool = False
    ) -> list[ArtResult]:
        """Fill in art for everything that doesn't have it yet."""
        results = []
        for entity in self.library.all(kind):
            spec = self.spec_for(entity, variant)
            if self.store.path_for(spec).exists():
                continue
            results.append(self.generate(entity, variant, dry_run=dry_run))
        return results
