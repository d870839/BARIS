# 3D visual upgrade — paths past primitives

Scoping doc for moving the 3D client past flat-color cubes and
spheres toward something with a Human Fall Flat aesthetic
(soft pastel palette, gentle shadows, low-poly stylised props,
clean silhouettes, no PBR realism). Written from the perspective
of "you have Unreal available locally but a working Python /
Ursina codebase to protect".

The four credible paths, ranked by effort:

## A. Stay in Ursina, push the existing engine harder

**Effort:** 1-2 weeks of evenings.
**Result:** noticeable but bounded improvement; still recognisably
Ursina, still primitives + free asset packs.

What we'd actually do:

1. **Toon / cel shader pass.** Panda3D has a built-in `ToonShader`
   that adds the characteristic ink-line outline + flat-shaded
   surfaces. Activated with a couple of lines on a NodePath.
   Single biggest visual swing for the smallest code change.
2. **Soft shadows.** Panda3D supports shadow casting on directional
   lights via `Shader.load(Shader.SL_GLSL, ...)` or by enabling
   the auto-shader pipeline. We currently disable shadows on the
   sun. Re-enabling + tuning is a few hours.
3. **Atmospheric fog.** Cheap depth cue — `render.set_fog(...)`
   with a soft cyan that matches the sky tints far buildings
   toward the horizon. Already half-built (we set
   `window.color = sky-blue` so the unlit horizon blends in).
4. **Replace primitives with free low-poly assets.**
   - [Quaternius](https://quaternius.com/) — CC0 stylised props
     packs (rockets, vehicles, buildings, vegetation).
   - [Kenney.nl](https://kenney.nl/assets) — same shape, stronger
     game-asset focus.
   - Both ship `.glb` / `.gltf` which Panda3D loads via
     `loader.load_model('assets/foo.glb')`.
   - Keeps the procedural facility silhouette but the buildings
     stop being literal cubes.
5. **Skybox texture** instead of flat clear-colour. Free skyboxes
   on OpenGameArt, six-sided cubemap.
6. **Subtle post-processing.** Panda3D's
   `CommonFilters.set_bloom(...)` adds the soft glow around
   bright surfaces (rocket engine flames, lights at night)
   that's most of the cartoony feel.

What the code investment looks like:
- ~200 lines in `client3d/` to wire the shader + lights + fog +
  filters.
- A few `loader.load_model(...)` swaps in `_build_scene()`.
- Asset folder + license-attribution README.

What you can't do this way:
- Real character rigs / animation. Our fruit characters are
  procedural; skeletal animation is a lot of plumbing in Panda3D.
- Anything close to Lumen / Nanite quality.
- Custom shader fanciness beyond the toon preset (Panda3D's
  shader system is workable but verbose).

**Recommend this path first.** It's the only one that doesn't
risk our existing gameplay code, and the perceived visual jump
from "cube + flat colour" to "cube with cel-shaded outline +
soft shadow + atmospheric fog" is bigger than the work suggests.

## B. Hybrid — keep the Python server, build a new Unreal client

**Effort:** 1-3 months for a competent Unreal dev (you).
**Result:** AAA-quality stylised look. Best long-term option.

The split:

* `baris/server/` stays exactly as it is. Same websocket
  protocol, same `GameState` dataclasses, same resolver tests.
* `baris/client3d/` (Ursina) becomes one of two clients —
  optional fallback for headless / dev / CI.
* New `baris/client_ue/` — an Unreal project that:
  - Opens a websocket to `ws://server:8765`.
  - Speaks the same JSON protocol (already documented in
    `protocol.py` — JOIN, STATE, REQUEST_*, etc.).
  - Renders the world in UE5 with Lumen, Nanite, real
    character rigs, post-processing, sound.

What you'd build inside Unreal:
- A WebSocket subsystem (UE has built-in WebSockets module).
- Blueprint or C++ data structures mirroring our state's shape
  for what the renderer cares about (pads, units, missions in
  flight, etc.).
- A facility scene (your stylised version of the plaza + 6
  buildings), with the rocket on the pad as a Cinematic Camera
  flythrough on launch.
- The cinematic phase reveal as a UE Sequencer animation.

Why this is the right architecture if you commit to Unreal:
- Zero risk to gameplay. Tests stay green. Server stays stable.
- The protocol is the API — both clients can co-exist.
- You can iterate on Unreal visuals while the Ursina client
  keeps working for friends who don't have UE.

Cost reality:
- WebSocket plumbing in UE is a few days.
- Mirroring the state shape is a couple of days.
- Building one stylised scene to AAA quality is the bulk —
  this is "real game-art work", not a few-hours job.
- Post-processing + lighting tuning is iterative for weeks.

## C. Pure Unreal rewrite — game logic in UE C++

**Effort:** 3-6 months.
**Result:** most cohesive Unreal experience but discards our
Python investment.

You'd port:
- Every dataclass in `state.py` to C++ structs / `USTRUCT()`s.
- The resolver to C++ functions.
- The protocol → UE replication system.
- All 292 tests to UE's test framework (or accept losing them).

Pros: native UE multiplayer, no protocol layer, simplest deploy
for a finished game (one binary).

Cons: months before the game is playable again. Every gameplay
iteration after that is in C++ / Blueprint, not Python. You
lose the rapid Python prototyping that's been driving phase
A → P-deep so far.

**Don't recommend** unless you specifically want to learn UE
deeply and don't mind the rewrite cost. The hybrid (Path B)
gets you the same visual quality with much less risk.

## D. Switch to Godot 4

**Effort:** 3-4 weeks.
**Result:** clean stylised look, much friendlier than UE,
open-source, decent tooling.

Why it could fit:
- Built-in cel-shader / toon material via shader graph.
- Smaller learning curve than UE.
- Free / open source / cross-platform.
- Has a Python-ish scripting language (GDScript) plus C# option.
- Can interop with Python over websocket like Path B.

Why probably not over Path B:
- You already have Unreal locally and want to use it.
- UE's cinematic / lighting tooling is better-than-Godot for
  the launch sequences specifically.

Mention only because if Unreal's complexity ever frustrates
you, Godot is the obvious sidegrade.

## My recommendation

1. **This week / next:** Path A. Toon shader + shadows + fog +
   one low-poly building swap. Costs little, ships visible
   improvement, validates the existing engine isn't the
   bottleneck.
2. **If you still want Human Fall Flat-tier polish after that:**
   Path B (hybrid Unreal client). The server / protocol layer
   has been deliberately designed for this — every state-mutating
   action goes through `protocol.py` already, every state field
   is a dataclass with `to_dict / from_dict`, and the websocket
   server is the only entry point. Adding a second client doesn't
   require any plumbing changes.
3. **Skip Path C unless** you're ready to commit to Unreal as
   your primary stack and accept losing the Python dev velocity.

What you could decide today:

- Which path? (A then maybe B, vs. straight to B?)
- If A: how much asset-pack work are you willing to do, vs.
  pure-shader / pure-light tweaks?
- If B: do you want me to start documenting the protocol +
  state shape more formally so a UE-side dev (you) has a
  cleaner contract to build against?
