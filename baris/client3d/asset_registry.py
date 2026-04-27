"""Tiny registry that lets the 3D scene swap procedural primitives
for downloaded asset-pack models without code edits per swap.

Why this exists: Quaternius / Kenney ship CC0 stylised props as
`.glb` files. Dropping them into this `assets/` folder by their
logical name (e.g. `rocket_light.glb`) is enough — every call
site that uses `try_model('rocket_light')` will start picking up
the real model. If the file's missing, the call returns None and
the caller falls back to the existing `model="cube"` primitive,
so the game still ships before any assets are downloaded.

Usage in the scene builder:

    from baris.client3d.asset_registry import try_model
    Entity(
        model=try_model('rocket_heavy') or 'cube',
        scale=(2, 8, 2),
        ...
    )

Logical names are documented in baris/client3d/assets/README.md.
"""
from __future__ import annotations

from pathlib import Path

# Search order: glTF binary first (most common in CC0 packs),
# glTF JSON second, OBJ third. Ursina's loader handles all three.
_ASSETS_DIR = Path(__file__).parent / "assets"
_FORMATS = (".glb", ".gltf", ".obj")


def try_model(logical_name: str) -> str | None:
    """Return a model path string if `logical_name`.<ext> exists
    in the assets folder for any supported extension, else None.

    Pure path lookup — no engine import — so it's safe to call
    from headless tests."""
    for ext in _FORMATS:
        path = _ASSETS_DIR / f"{logical_name}{ext}"
        if path.exists():
            return str(path)
    return None


def asset_dir() -> Path:
    """Public accessor in case a caller wants to walk the directory
    (e.g. for a future asset-status panel that lists what's
    installed and what's missing)."""
    return _ASSETS_DIR
