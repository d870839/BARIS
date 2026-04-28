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

import json
import struct
from pathlib import Path

# Search order: glTF binary first (most common in CC0 packs),
# glTF JSON second, OBJ third. Ursina's loader handles all three.
_ASSETS_DIR = Path(__file__).parent / "assets"
_FORMATS = (".glb", ".gltf", ".obj")


_GLB_MAGIC = 0x46546C67   # 'glTF' little-endian
_CHUNK_TYPE_JSON = 0x4E4F534A  # 'JSON'


def glb_first_material_color(path: str | Path) -> tuple[float, float, float] | None:
    """Pop open a .glb file, parse the JSON chunk, and return the
    first material's pbrMetallicRoughness.baseColorFactor as an
    (r, g, b) triple in 0..1.

    Why bother: Panda3D's glTF loader (or its absence) sometimes
    fails to wire up the material colors stored in Kenney's
    .glb files — every model renders pure white because the
    pipeline never sees baseColorFactor. We can't fix the loader
    from outside it, but we CAN read the value ourselves and
    apply it as an Ursina `entity.color` tint, which paints the
    whole mesh in roughly the right colour even with the loader
    misbehaving. Returns None if the file isn't a valid .glb,
    has no materials, or the material has no baseColorFactor
    (in which case the default white tint stays).

    Pure stdlib — struct + json. Safe to call from any thread."""
    p = Path(path)
    if p.suffix.lower() != ".glb":
        return None
    try:
        data = p.read_bytes()
    except OSError:
        return None
    if len(data) < 20:
        return None
    magic, version, _ = struct.unpack("<III", data[:12])
    if magic != _GLB_MAGIC or version != 2:
        return None
    chunk_len, chunk_type = struct.unpack("<II", data[12:20])
    if chunk_type != _CHUNK_TYPE_JSON:
        return None
    try:
        gltf = json.loads(data[20:20 + chunk_len])
    except (ValueError, UnicodeDecodeError):
        return None
    materials = gltf.get("materials") or []
    if not materials:
        return None
    pbr = materials[0].get("pbrMetallicRoughness") or {}
    factor = pbr.get("baseColorFactor")
    if not factor or len(factor) < 3:
        return None
    r, g, b = factor[0], factor[1], factor[2]
    return (float(r), float(g), float(b))


# Per-logical-name fallback aliases. When `try_model('building_rd')`
# is called and rd-renamed file isn't present, we also try every
# alias here in order. This lets us ship a sensible default mapping
# (Kenney's hangar files → BARIS building IDs) without forcing the
# player to rename anything after extracting the pack.
_ALIASES: dict[str, tuple[str, ...]] = {
    "building_rd":      ("hangar_largeA", "hangar_largeB", "hangar_roundA"),
    "building_mc":      ("hangar_roundGlass", "hangar_roundB", "hangar_largeA"),
    "building_astro":   ("hangar_largeB", "hangar_largeA", "hangar_roundB"),
    "building_library": ("hangar_smallA", "hangar_smallB", "hangar_roundA"),
    "building_intel":   ("hangar_smallB", "hangar_smallA", "hangar_roundB"),
    "building_museum":  ("hangar_roundA", "hangar_roundGlass", "hangar_largeB"),
}


def _scan(name: str) -> str | None:
    """Return a model path string Ursina's loader can resolve.

    Ursina's `application.asset_folder` defaults to the
    *script's* directory (so `baris/client3d/` for our 3D
    client). Absolute Windows paths handed to `Entity(model=...)`
    are silently ignored on some Ursina builds — the Entity is
    created but the load returns no geometry, which is why
    asset-pack swaps were mounting as invisible bodies. Return
    a path relative to the client3d folder (i.e. starting with
    `assets/...`) so the loader resolves it the way Ursina's
    own asset paths do."""
    for ext in _FORMATS:
        path = _ASSETS_DIR / f"{name}{ext}"
        if path.exists():
            # Path relative to baris/client3d/ — that's
            # `assets/<name>.<ext>`. Forward slashes so the
            # Ursina/Panda3D path resolver doesn't trip on
            # Windows backslashes.
            return f"assets/{name}{ext}"
    return None


def try_model(logical_name: str) -> str | None:
    """Return a model path string if `logical_name`.<ext> exists
    in the assets folder, OR if any of the registered aliases
    for `logical_name` exists. Returns None if nothing matches.

    Pure path lookup — no engine import — so it's safe to call
    from headless tests."""
    direct = _scan(logical_name)
    if direct is not None:
        return direct
    for alias in _ALIASES.get(logical_name, ()):
        path = _scan(alias)
        if path is not None:
            return path
    return None


def asset_dir() -> Path:
    """Public accessor in case a caller wants to walk the directory
    (e.g. for a future asset-status panel that lists what's
    installed and what's missing)."""
    return _ASSETS_DIR
