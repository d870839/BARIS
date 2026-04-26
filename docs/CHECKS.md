# Visual checks — UI refactor + fruit characters

Things to verify in the 3D client when you're back at a GPU. Tick
them as you go; flag anything broken in the conversation and I'll
patch.

## Pygame overlay (steps 1-3a)

- [ ] Bottom-left of the 3D window shows a small `BARIS overlay`
      badge. (Smoke test for the pygame-Surface → Panda3D-texture
      pipeline. If missing, the host isn't compositing.)
- [ ] Existing Ursina menus (lobby, R&D, Mission Control, Astro,
      etc.) still render unchanged — only the result panel migrated
      so far.
- [ ] No new performance regression — 3D scene still hits 60 FPS
      after the per-frame overlay upload.

## Result panel (overlay version)

- [ ] After a launch the result panel appears as a full-screen
      overlay with a translucent dark backdrop dimming the 3D
      world behind it.
- [ ] Text is **crisp at any FOV** — no scaling drift, no
      z-fighting against world geometry.
- [ ] Banner colour matches outcome:
  - SUCCESS → green
  - MOON LANDING → yellow / highlight
  - FAILURE → red
  - PARTIAL → yellow with abort label
  - MISSION ABORTED → dim grey
- [ ] Mission timeline reveals one phase row every ~0.55s. Glyphs:
  - PASS  `+` green
  - FAIL  `X` red
  - PARTIAL  `!` yellow
  - SKIP  `-` dim grey
- [ ] Continue button at the bottom is clickable and Space / Enter
      / Escape also advance.
- [ ] Cycling between own + opponent reports works (multiple
      launches in a turn).

## Fruit characters in the Astronaut Center

- [ ] Walk into the Astronaut Center; bobbing fruit-shaped
      characters appear in two rows along the south wall.
- [ ] Each fruit is **tinted with the character's swatch colour**
      (Bombardiro Crocodilo brown-grey, Tralalero Tralala blue,
      etc.).
- [ ] Each fruit has the character's **glyph** painted on the
      front face.
- [ ] Stem + leaf on top, base disc underneath.
- [ ] Bob animation is gentle, not jittery (sine wave, ~2.4s
      period).
- [ ] KIA + retired astronauts are NOT in the fruit roster (they
      stay on the wall portraits).
- [ ] Roster swap works: recruit a new group, walk back in, the
      new astronauts' fruits appear.

## Things known *not* to be in scope yet

- The Ursina `build_result_panel` is still in `panels_action.py`
  as a fallback. Reverting `_open_overlay_result_panel` in
  `app.py` to the old call restores it.
- All other panels (R&D, Mission Control, Astro, Intel, Museum,
  Library, Training, Recruit, Sabotage, Lobby) still render via
  Ursina entities.
- The standalone 2D client still works as a full game; step 4
  retires it once enough panels are on the overlay.
