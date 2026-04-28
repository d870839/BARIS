"""Modular rocket assembly from a Kenney-style asset pack.

Kenney's Space Kit ships cylindrical rocket segments — base /
section / top — that the player stacks into a tower at runtime.
We auto-discover whichever parts the user dropped into
baris/client3d/assets/ and assemble per rocket class:

  Light   = base + 1 section + top   (Mercury / R-7 silhouette)
  Medium  = base + 3 sections + top  (Atlas / Proton)
  Heavy   = base + 5 sections + top  (Saturn V / N-1)

Filename convention (case-insensitive substring match), so the
user can drop the Kenney files in unrenamed:

  *base*.glb / *bottom*.glb        → bottom segment (engine cluster)
  *top*.glb / *capsule*.glb /
   *nose*.glb / *cone*.glb         → cap / payload section
  any other *rocket*.glb /
  *fuel*.glb / *section*.glb       → mid-section

Multiple matches per category are sorted by filename so the
choice is stable across runs. If we can't find at least one
base AND one top, assemble_rocket() returns None and the caller
falls back to the procedural cube rocket. Mid-sections are
optional — Light can run base + top only if the pack has no
sections."""
from __future__ import annotations

import logging
from pathlib import Path

from ursina import Entity

from baris.client3d.asset_registry import asset_dir

log = logging.getLogger(__name__)


_SECTIONS_PER_CLASS: dict[str, int] = {
    "Light":  1,
    "Medium": 3,
    "Heavy":  5,
}

# Per-segment uniform scale. Kenney Space Kit rocket parts are
# native ~1m tall; scaling up makes the rocket read as a real
# tower from across the plaza.
_PART_SCALE = 2.0
# Spacing between segment centres after _PART_SCALE is applied —
# slightly less than _PART_SCALE so each segment butts cleanly
# against the next without a visible seam.
_SEGMENT_HEIGHT = 1.95


def discover_rocket_parts(root: Path | None = None) -> dict[str, list[Path]]:
    """Walk the assets directory and group rocket-part files into
    'base' / 'top' / 'section'. Pure file-system lookup — no
    engine import — so headless tests can validate the discovery
    against a tmp directory without spinning up Ursina."""
    parts: dict[str, list[Path]] = {"base": [], "top": [], "section": []}
    base_dir = root if root is not None else asset_dir()
    for ext in (".glb", ".gltf"):
        for p in base_dir.glob(f"*{ext}"):
            name = p.stem.lower()
            # Only files that look like rocket-pack parts. 'craft'
            # is kept because Kenney sometimes prefixes their
            # space-kit items that way.
            if not any(k in name for k in (
                "rocket", "craft", "fuel", "section", "stage",
            )):
                continue
            if "base" in name or "bottom" in name:
                parts["base"].append(p)
            elif any(k in name for k in ("top", "capsule", "nose", "cone")):
                parts["top"].append(p)
            else:
                parts["section"].append(p)
    for k in parts:
        parts[k].sort()
    return parts


def compose_layout(
    rocket_class: str,
    parts: dict[str, list[Path]] | None = None,
) -> list[tuple[Path, float]] | None:
    """Compute the (filename, y_offset) layout for a rocket class
    given the discovered parts. Returns None if the pack doesn't
    have at least one base + one top — caller drops to the
    procedural fallback."""
    parts = parts if parts is not None else discover_rocket_parts()
    if not parts["base"] or not parts["top"]:
        return None
    n_sections = _SECTIONS_PER_CLASS.get(rocket_class, 1)
    if not parts["section"]:
        n_sections = 0
    layout: list[tuple[Path, float]] = [(parts["base"][0], 0.0)]
    for i in range(n_sections):
        # Cycle through the section pool — a Heavy rocket built
        # from a pack with two distinct sections still has
        # visual variety down its tower.
        sec = parts["section"][i % len(parts["section"])]
        layout.append((sec, _SEGMENT_HEIGHT * (i + 1)))
    layout.append((parts["top"][0], _SEGMENT_HEIGHT * (n_sections + 1)))
    return layout


def assemble_rocket(
    rocket_class: str,
    *,
    pad_x: float, pad_z: float, base_y: float,
) -> Entity | None:
    """Stack the configured segments for `rocket_class` starting
    at (pad_x, base_y, pad_z). Returns the root Entity (the base
    segment) with `_rocket_class` + `_rest_y` set so the caller
    can drive its launch animation. Returns None if the pack is
    missing required parts."""
    layout = compose_layout(rocket_class)
    if layout is None:
        return None
    base_path, _ = layout[0]
    log.info(
        "rocket assembly: %s = %d segments from %s",
        rocket_class, len(layout), base_path.name,
    )
    # Kenney parts are origin-at-base on Y, so we place the root
    # at base_y directly. Scaling the root propagates to children
    # automatically. Pass paths to Ursina as `assets/<file>` so
    # its loader resolves them through application.asset_folder
    # — absolute Windows paths get silently dropped on some
    # Ursina builds and the rocket renders as an empty Entity.
    root = Entity(
        model=f"assets/{base_path.name}",
        position=(pad_x, base_y, pad_z),
        scale=_PART_SCALE,
    )
    for path, dy in layout[1:]:
        Entity(
            parent=root,
            model=f"assets/{path.name}",
            position=(0, dy, 0),
        )
    root._rocket_class = rocket_class
    root._rest_y = base_y
    return root
