# 3D asset pack — drop-in directory

Files placed here by their logical name (one of the entries below)
are auto-detected by `baris.client3d.asset_registry.try_model()`
and replace the corresponding procedural-primitive in the scene.

The game ships with this folder mostly empty — every logical name
falls back to a primitive cube / sphere / quad until the matching
file is dropped in. Order of preference: `.glb`, `.gltf`, `.obj`.

## Recommended free packs

All CC0, no attribution required for game use (still nice to credit
in your README):

* **[Quaternius — Ultimate Space Kit](https://quaternius.com/packs/ultimatespacekit.html)**
  — rockets, satellites, capsules, lunar landers. The single most
  useful pack for this game.
* **[Quaternius — Modular Buildings](https://quaternius.com/packs/modularbuildings.html)**
  — facility / control-tower / hangar shapes for the plaza buildings.
* **[Quaternius — Ultimate Stylized Nature Pack](https://quaternius.com/packs/ultimatestylizednature.html)**
  — trees, rocks, grass tufts for the horizon hills.
* **[Kenney — Space Kit](https://kenney.nl/assets/space-kit)**
  — alternative rocket / capsule shapes if you want a chunkier feel.

## Logical names the scene currently looks for

(Implemented call sites mark a swap with `try_model()`. Ones still
on primitives are flagged TODO — wire them in as you go.)

### Rockets (one per Rocket class)
* `rocket_light` — Mercury / R-7 size sub-orbital booster
* `rocket_medium` — Atlas / Proton manned-orbital
* `rocket_heavy` — Saturn V / N-1 lunar booster

### Pad
* `pad_deck` — flat circular concrete deck the rocket sits on
* `pad_tower` — service tower / gantry beside the rocket

### Buildings (one per facility)
* `building_rd` — R&D Complex
* `building_mc` — Mission Control
* `building_astro` — Astronaut Center
* `building_library` — Library / archive
* `building_intel` — Intelligence Office
* `building_museum` — Museum

### Plaza props
* `flagpole` — ceremonial flagpoles flanking the SUBMIT TURN pedestal
* `lamp_post` — perimeter plaza lamps

### Horizon dressing
* `tree_pine` — distant pine silhouettes
* `hill_smooth` — rolling-hill mesh for the apron horizon

## How to add an asset

1. Download the pack zip.
2. Find the model you want (each Quaternius pack has a `glTF/`
   folder inside).
3. Copy the `.glb` (or `.gltf` + textures) into this directory.
4. Rename to one of the logical names above.
5. Restart the 3D client. The model picks up automatically; no
   code change required.

If a model loads at the wrong scale or orientation, the scene
builder's existing `scale=(...)` + `rotation=(...)` parameters
cover it — most asset packs export at 1m = 1 Ursina unit so they
should be roughly right out of the box.

## License + attribution

Quaternius packs are CC0 / public domain — no attribution
strictly required. Kenney's packs are also CC0. If you ship a
public build, listing the packs in the project's README is
courteous; the assets themselves don't need a per-file licence
file.
