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

## Astronaut roster (overlay panel — replaces fruit characters in the room)

- [ ] Press **`R`** anywhere in the 3D world (no other panel open) →
      a scrollable card panel appears with one row per astronaut:
      portrait swatch in their colour, glyph emoji, name, status,
      skill bars, bio one-liner.
- [ ] Mouse cursor is visible while the panel is open; player
      camera is parked.
- [ ] Mouse wheel scrolls; arrow keys / PageUp / PageDown / Home
      / End also scroll.
- [ ] Scrollbar on the right reflects position when the roster
      overflows the visible area.
- [ ] Status text matches the astronaut state — `Ready`, `KIA`,
      `Retired`, `Hospital`, `Training`, `Resting`.
- [ ] **`Escape`** or clicking the **X** button closes; mouse
      re-locks to the player camera.
- [ ] No bobbing fruit characters in the Astronaut Center room —
      the wall portraits stay, but the floor is clear.

## Things known *not* to be in scope yet

- The Ursina `build_result_panel` is still in `panels_action.py`
  as a fallback. Reverting `_open_overlay_result_panel` in
  `app.py` to the old call restores it.
- All other panels (R&D, Mission Control, Astro, Intel, Museum,
  Library, Training, Recruit, Sabotage, Lobby) still render via
  Ursina entities.
- The standalone 2D client still works as a full game; step 4
  retires it once enough panels are on the overlay.
