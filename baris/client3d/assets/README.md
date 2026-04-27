# 3D asset pack — drop-in directory

Files placed here by their logical name (one of the entries below)
are auto-detected by `baris.client3d.asset_registry.try_model()`
and replace the corresponding procedural-primitive in the scene.

The game ships with this folder mostly empty — every logical name
falls back to a primitive cube / sphere / quad until the matching
file is dropped in. Order of preference: `.glb`, `.gltf`, `.obj`.

## Recommended free packs

All CC0, no attribution required for game use (still nice to credit
in your README).

**Order matters here.** Quaternius is the gold standard for stylised
space packs but ships their downloads on Google Drive, which is
blocked by some corporate web filters (Zscaler / Kroger / similar).
Kenney and Poly Pizza both host directly off their own infrastructure,
so try those first if Quaternius links return a "Not allowed to
browse FileHost category" page.

### Direct-CDN sources (work-network friendly)

* **[Kenney — Space Kit](https://kenney.nl/assets/space-kit)** —
  140+ stylised space props (rockets, capsules, lunar landers,
  satellites, modules). Download is a `.zip` straight off
  `kenney.nl`. Closest match to "stylised cartoon" of the lot.
* **[Kenney — City Kit (Suburban)](https://kenney.nl/assets/city-kit-suburban)**
  / **[City Kit (Commercial)](https://kenney.nl/assets/city-kit-commercial)**
  — flat-roof + pitched-roof building shapes for the facility
  buildings. Use the commercial pack for R&D / Mission Control
  (corporate-glass look) and the suburban pack for the
  Astronaut Center / Library (more residential).
* **[Kenney — Nature Kit](https://kenney.nl/assets/nature-kit)** —
  trees, rocks, grass for the horizon ring.
* **[Poly Pizza](https://poly.pizza/)** — Google Poly archive,
  searchable, CC0 + CC-BY filters in the sidebar. Good fallback
  if a specific shape isn't in the Kenney packs.
* **[OpenGameArt 3D models](https://opengameart.org/art-search?keys=&field_art_type_tid%5B0%5D=10)**
  — community-uploaded, mixed quality, all explicitly licensed.

### Drive-hosted sources (try at home, not at work)

* **[Quaternius — Ultimate Space Kit](https://quaternius.com/packs/ultimatespacekit.html)**
  — best stylised space pack out there, but Google Drive download.
* **[Quaternius — Modular Buildings](https://quaternius.com/packs/modularbuildings.html)**
* **[Quaternius — Ultimate Stylized Nature Pack](https://quaternius.com/packs/ultimatestylizednature.html)**

### Kenney → BARIS asset name mapping

When you grab the Kenney Space Kit, look for these specific files
inside its `Models/GLTF format/` folder and rename to our logical
names before dropping into this directory:

| Kenney filename                  | Rename to            |
|----------------------------------|----------------------|
| `craft_speederA.glb`             | `rocket_light.glb`   |
| `craft_miner.glb`                | `rocket_medium.glb`  |
| `rocketA.glb` (or `rocketB.glb`) | `rocket_heavy.glb`   |
| `satelliteA.glb`                 | `building_intel.glb` (placeholder; pick anything that reads like a comms station) |

For buildings the Commercial / Suburban City Kit gives you flat
or pitched-roof shapes — pick six that read distinct, rename to
`building_rd / mc / astro / library / intel / museum`.

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
