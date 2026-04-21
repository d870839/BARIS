"""Launch-pad and rocket entities for the 3D client.

Three rocket silhouettes (Light / Medium / Heavy) are all built up-front
and stashed by class name. The BarisClient flips which one is `enabled`
based on whatever the player has queued / is researching, so the pad
shows a Saturn-V-sized monster when you're about to fly Heavy and a
stubby Redstone when you're still on Light."""
from __future__ import annotations

from ursina import Entity, color


# Pad is placed north of Mission Control so the player can see it while
# queueing a launch. Coordinates picked to keep the rocket inside the
# ground plane and not collide with any building.
PAD_POSITION: tuple[float, float, float] = (0.0, 0.0, 40.0)
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


def build_launch_pad() -> Entity:
    """Concrete apron + four red-striped scaffold arms — Saturn-V LC-39 vibes."""
    px, py, pz = PAD_POSITION
    pad = Entity(
        model="cube",
        position=(px, py, pz),
        scale=(5, PAD_HEIGHT, 5),
        color=color.rgb32(165, 165, 175),
    )
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
    return pad


def build_rocket(rocket_class: str = "Light") -> Entity:
    """Rocket silhouette sized by class. Children's scales are relative to
    the body so fins / cone / porthole automatically get bigger on Heavy.

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
        color=color.white,
    )
    body._rocket_class = rocket_class
    body._rest_y = base_y

    # Nose cone — cube narrowed at the top. Heights are fractions of the
    # parent body height so the cone is proportionally short on a tall rocket.
    cone_rel_h = 0.13
    Entity(
        parent=body, model="cube",
        scale=(0.72, cone_rel_h, 0.72),
        y=0.5 + cone_rel_h / 2,
        color=color.rgb32(210, 70, 70),
    )
    # Faint dark ring under the cone for visual separation.
    Entity(
        parent=body, model="cube",
        scale=(1.04, 0.008, 1.04),
        y=0.5,
        color=color.rgb32(40, 40, 45),
    )
    # Stage-separation rings.
    for i in range(1, specs["stages"]):
        Entity(
            parent=body, model="cube",
            scale=(1.04, 0.008, 1.04),
            y=0.5 - i / specs["stages"],
            color=color.rgb32(40, 40, 45),
        )
    # Porthole window — parented so it rides up with the body.
    Entity(
        parent=body, model="sphere",
        scale=(0.28 / body_w, 0.28 / body_h, 0.28 / body_w),
        y=0.32, z=0.48,
        color=color.rgb32(70, 130, 220),
    )
    # Fins — proportional to body, x-axis pair.
    for x in (-0.55, 0.55):
        Entity(
            parent=body, model="cube",
            scale=(0.05, 0.13, 0.55),
            position=(x, -0.4, 0),
            color=color.rgb32(180, 60, 60),
        )
    # Fins — z-axis pair.
    for z in (-0.55, 0.55):
        Entity(
            parent=body, model="cube",
            scale=(0.55, 0.13, 0.05),
            position=(0, -0.4, z),
            color=color.rgb32(180, 60, 60),
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
