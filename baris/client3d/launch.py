"""Launch-pad and rocket entities for the 3D client.

Three rocket silhouettes (Light / Medium / Heavy) are all built up-front
and stashed by class name. The BarisClient flips which one is `enabled`
based on whatever the player has queued / is researching, so the pad
shows a Saturn-V-sized monster when you're about to fly Heavy and a
stubby Redstone when you're still on Light."""
from __future__ import annotations

from ursina import Entity, color


# Pad A is the active pad — placed north of Mission Control so the
# player can see it while queueing a launch and watch the liftoff
# animation. Pads B and C are decorative siblings flanking it, drawn
# the same way but without their own rocket silhouettes (V1: only
# Pad A's scheduled mission shows a rocket on the apron).
PAD_POSITION: tuple[float, float, float] = (0.0, 0.0, 40.0)
PAD_B_POSITION: tuple[float, float, float] = (-12.0, 0.0, 40.0)
PAD_C_POSITION: tuple[float, float, float] = (12.0, 0.0, 40.0)
PAD_HEIGHT: float = 0.6
APEX_Y: float = 120.0         # how high the liftoff animation rises
LIFTOFF_DURATION: float = 2.4


# Rough proportions inspired by the real rockets:
#   Light  ~  Redstone   (25m tall)
#   Medium ~  Titan II   (33m) / Proton (56m) — pick 2x Light
#   Heavy  ~  Saturn V   (110m) / N1 — ~4.4x Light
# Heights here are game-world metres. The Heavy towers over the gantry
# (leg tops ~y=5.6), which is the intended Saturn-V-looming effect.
ROCKET_CLASSES: dict[str, dict[str, float]] = {
    "Light":  {"body_w": 0.9, "body_h": 4.0,  "stages": 1},
    "Medium": {"body_w": 1.4, "body_h": 9.0,  "stages": 2},
    "Heavy":  {"body_w": 2.6, "body_h": 18.0, "stages": 3},
}


def _initial_y_for(body_h: float) -> float:
    """Body origin is at its centre, so it has to sit half its height above
    the pad top to just rest on the scaffold deck."""
    return PAD_POSITION[1] + PAD_HEIGHT / 2 + body_h / 2


def build_launch_pad(
    position: tuple[float, float, float] = PAD_POSITION,
    pad_label: str = "A",
) -> Entity:
    """Concrete apron + four red-striped scaffold arms — Saturn-V LC-39 vibes.

    Returns the pad-deck Entity. Surfaces a couple of attributes the caller
    uses to recolour for state changes:
      * `_deck_color`: the original deck colour (so we can restore from
        damaged-red back to concrete).
      * `_label`: which pad this is — "A" / "B" / "C".
      * `_status_marker`: a small cube sitting just above the deck,
        recoloured per state (idle/scheduled/damaged).
      * `_pad_label_text`: floating "PAD A" sign the caller can leave alone."""
    px, py, pz = position
    pad = Entity(
        model="cube",
        position=(px, py, pz),
        scale=(5, PAD_HEIGHT, 5),
        color=color.rgb32(165, 165, 175),
    )
    pad._deck_color = pad.color
    pad._label = pad_label
    # Pad edge trim (black-and-yellow caution stripe).
    Entity(
        model="cube",
        position=(px, py + PAD_HEIGHT / 2 + 0.01, pz),
        scale=(5.05, 0.02, 5.05),
        color=color.rgb32(40, 40, 45),
    )
    # Scaffold legs.
    for dx, dz in ((-2.2, -2.2), (2.2, -2.2), (-2.2, 2.2), (2.2, 2.2)):
        Entity(
            model="cube",
            position=(px + dx, py + 2.8, pz + dz),
            scale=(0.3, 6.0, 0.3),
            color=color.rgb32(210, 210, 215),
        )
        # Red hazard cap at the top of each leg.
        Entity(
            model="cube",
            position=(px + dx, py + 5.6, pz + dz),
            scale=(0.35, 0.3, 0.35),
            color=color.rgb32(210, 60, 60),
        )
    # Gantry crossbeams.
    for z in (pz - 2.2, pz + 2.2):
        Entity(
            model="cube",
            position=(px, py + 5.4, z),
            scale=(4.8, 0.2, 0.2),
            color=color.rgb32(210, 210, 215),
        )
    for x in (px - 2.2, px + 2.2):
        Entity(
            model="cube",
            position=(x, py + 5.4, pz),
            scale=(0.2, 0.2, 4.8),
            color=color.rgb32(210, 210, 215),
        )
    # Status marker — small disk on the deck, recolour-driven.
    pad._status_marker = Entity(
        model="cube",
        position=(px, py + PAD_HEIGHT / 2 + 0.05, pz - 1.6),
        scale=(1.6, 0.08, 0.4),
        color=color.rgb32(120, 200, 120),  # default: idle / OK
    )
    # Floating "PAD X" sign that billboards toward the camera.
    from ursina import Text
    pad._pad_label_text = Text(
        text=f"PAD {pad_label}",
        parent=pad,
        y=PAD_HEIGHT / 2 + 6.5,
        scale=4, origin=(0, 0),
        billboard=True,
        color=color.rgb32(40, 40, 50),
    )
    return pad


def build_rocket(rocket_class: str = "Light") -> Entity:
    """Rocket silhouette sized by class. Children's scales are relative to
    the body so fins / cone / porthole / paint automatically scale with
    the rocket.

    Detail set (rough Saturn-V / Titan II / Redstone cues):
    - Alternating white body + thin black paint bands (roll patterns).
    - A vertical black stripe on the 'nameplate' face of the first stage.
    - A tapered, stepped nose cone (stacked narrower cubes).
    - A bottom cluster of engine bells (1 for Light, 3 for Medium,
      5 for Heavy).
    - A launch-escape tower on Medium and Heavy.

    The returned entity carries `_rocket_class` and `_rest_y` so the caller
    can reset it after a liftoff animation without juggling globals."""
    specs = ROCKET_CLASSES[rocket_class]
    body_h = specs["body_h"]
    body_w = specs["body_w"]
    px, _, pz = PAD_POSITION
    base_y = _initial_y_for(body_h)

    body = Entity(
        model="cube",
        position=(px, base_y, pz),
        scale=(body_w, body_h, body_w),
        color=color.rgb32(245, 245, 245),
    )
    body._rocket_class = rocket_class
    body._rest_y = base_y

    black = color.rgb32(22, 22, 26)
    silver = color.rgb32(180, 180, 190)

    # ------------------------------------------------------------------
    # Paint pattern — horizontal roll-pattern bands on the body.
    # ------------------------------------------------------------------
    for band_y, band_h in (
        (0.42, 0.02),       # just below the top shoulder
        (0.22, 0.025),      # upper third
        (-0.05, 0.04),      # waistline (thicker band)
        (-0.28, 0.02),      # lower third
    ):
        Entity(
            parent=body, model="cube",
            scale=(1.04, band_h, 1.04),
            y=band_y, color=black,
        )
    # "Nameplate" — a vertical black stripe on the front face.
    Entity(
        parent=body, model="cube",
        scale=(0.14, 0.55, 0.01),
        y=0.05, z=-0.505,
        color=black,
    )
    # Small silver trim square on the nameplate, suggesting roundels.
    Entity(
        parent=body, model="cube",
        scale=(0.09, 0.09, 0.01),
        y=0.25, z=-0.51,
        color=silver,
    )

    # ------------------------------------------------------------------
    # Stepped nose cone — three narrowing cubes stacked above the body.
    # ------------------------------------------------------------------
    cone_tiers = (
        (0.78, 0.06, 0.53),
        (0.58, 0.05, 0.585),
        (0.36, 0.04, 0.628),
    )
    for w, h, y in cone_tiers:
        Entity(
            parent=body, model="cube",
            scale=(w, h, w),
            y=y, color=color.rgb32(235, 230, 225),
        )
    # Red ring where the command module joins the service module.
    Entity(
        parent=body, model="cube",
        scale=(0.82, 0.01, 0.82),
        y=0.503, color=color.rgb32(200, 60, 60),
    )

    # ------------------------------------------------------------------
    # Launch-escape tower (only tall enough to matter on Medium / Heavy).
    # ------------------------------------------------------------------
    if rocket_class in ("Medium", "Heavy"):
        Entity(
            parent=body, model="cube",
            scale=(0.04, 0.08, 0.04),
            y=0.67, color=silver,
        )
        Entity(
            parent=body, model="cube",
            scale=(0.06, 0.03, 0.06),
            y=0.715, color=color.rgb32(200, 60, 60),
        )

    # ------------------------------------------------------------------
    # Stage-separation rings (kept in addition to the paint bands).
    # ------------------------------------------------------------------
    for i in range(1, specs["stages"]):
        Entity(
            parent=body, model="cube",
            scale=(1.05, 0.01, 1.05),
            y=0.5 - i / specs["stages"],
            color=black,
        )

    # ------------------------------------------------------------------
    # Porthole (Command Module window).
    # ------------------------------------------------------------------
    Entity(
        parent=body, model="sphere",
        scale=(0.22 / body_w, 0.22 / body_h, 0.22 / body_w),
        y=0.38, z=0.48,
        color=color.rgb32(70, 130, 220),
    )

    # ------------------------------------------------------------------
    # Fins (stabilisers on the first stage).
    # ------------------------------------------------------------------
    for x in (-0.55, 0.55):
        Entity(
            parent=body, model="cube",
            scale=(0.05, 0.13, 0.6),
            position=(x, -0.4, 0),
            color=color.rgb32(180, 60, 60),
        )
    for z in (-0.55, 0.55):
        Entity(
            parent=body, model="cube",
            scale=(0.6, 0.13, 0.05),
            position=(0, -0.4, z),
            color=color.rgb32(180, 60, 60),
        )

    # ------------------------------------------------------------------
    # Engine bells at the base — count scales with class (1 / 3 / 5),
    # hinting at Redstone single engine up to Saturn V's F-1 cluster.
    # ------------------------------------------------------------------
    bell_positions: tuple[tuple[float, float], ...]
    if rocket_class == "Light":
        bell_positions = ((0.0, 0.0),)
    elif rocket_class == "Medium":
        bell_positions = ((0.0, 0.0), (-0.28, 0.0), (0.28, 0.0))
    else:  # Heavy
        bell_positions = (
            (0.0, 0.0),
            (-0.3, -0.3), (0.3, -0.3),
            (-0.3, 0.3),  (0.3, 0.3),
        )
    bell_col = color.rgb32(55, 55, 65)
    for ex, ez in bell_positions:
        Entity(
            parent=body, model="cube",
            scale=(0.17, 0.06, 0.17),
            position=(ex, -0.53, ez),
            color=bell_col,
        )
        # Nozzle lip (slightly flared darker ring beneath each bell).
        Entity(
            parent=body, model="cube",
            scale=(0.2, 0.015, 0.2),
            position=(ex, -0.565, ez),
            color=color.rgb32(30, 30, 35),
        )

    return body


def build_exhaust_flame(parent: Entity) -> Entity:
    """Flame plume parented to the rocket body; hidden by default. Toggled
    visible during a liftoff and hidden again when the rocket resets."""
    flame = Entity(
        parent=parent, model="cube",
        scale=(0.7, 0.18, 0.7),
        y=-0.58,
        color=color.rgb32(240, 160, 50),
    )
    flame.enabled = False
    return flame


def reset_rocket(rocket: Entity, flame: Entity) -> None:
    """Drop the rocket back onto the pad between turns."""
    rocket.y = rocket._rest_y
    flame.enabled = False
