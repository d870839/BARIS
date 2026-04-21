"""Launch-pad and rocket entities for the 3D client.

Kept as a tiny, stateless module so the BarisClient in app.py can import
the factory functions without circular refs. The animation itself is
orchestrated by the client (ursina's entity.animate_y handles tweening;
the client decides when to fire it)."""
from __future__ import annotations

from ursina import Entity, color


# Pad is placed north of Mission Control so the player can see it while
# queueing a launch. Coordinates picked to keep the rocket inside the
# ground plane and not collide with any building.
PAD_POSITION: tuple[float, float, float] = (0.0, 0.0, 40.0)
PAD_HEIGHT: float = 0.6
ROCKET_BODY_HEIGHT: float = 4.0
INITIAL_ROCKET_Y: float = PAD_POSITION[1] + PAD_HEIGHT / 2 + ROCKET_BODY_HEIGHT / 2
APEX_Y: float = 55.0
LIFTOFF_DURATION: float = 2.4


def build_launch_pad() -> Entity:
    """Concrete apron + four red-striped scaffold arms — Saturn-V LC-39 vibes."""
    px, py, pz = PAD_POSITION
    pad = Entity(
        model="cube",
        position=(px, py, pz),
        scale=(5, PAD_HEIGHT, 5),
        color=color.rgb(165, 165, 175),
    )
    # Pad edge trim (black-and-yellow caution stripe).
    Entity(
        model="cube",
        position=(px, py + PAD_HEIGHT / 2 + 0.01, pz),
        scale=(5.05, 0.02, 5.05),
        color=color.rgb(40, 40, 45),
    )
    # Scaffold legs.
    for dx, dz in ((-2.2, -2.2), (2.2, -2.2), (-2.2, 2.2), (2.2, 2.2)):
        Entity(
            model="cube",
            position=(px + dx, py + 2.8, pz + dz),
            scale=(0.3, 6.0, 0.3),
            color=color.rgb(210, 210, 215),
        )
        # Red hazard cap at the top of each leg.
        Entity(
            model="cube",
            position=(px + dx, py + 5.6, pz + dz),
            scale=(0.35, 0.3, 0.35),
            color=color.rgb(210, 60, 60),
        )
    # Gantry crossbeams.
    for z in (pz - 2.2, pz + 2.2):
        Entity(
            model="cube",
            position=(px, py + 5.4, z),
            scale=(4.8, 0.2, 0.2),
            color=color.rgb(210, 210, 215),
        )
    for x in (px - 2.2, px + 2.2):
        Entity(
            model="cube",
            position=(x, py + 5.4, pz),
            scale=(0.2, 0.2, 4.8),
            color=color.rgb(210, 210, 215),
        )
    return pad


def build_rocket() -> Entity:
    """Simple rocket silhouette: tall body + red cone tip + four fins."""
    px, py, pz = PAD_POSITION
    body = Entity(
        model="cube",
        position=(px, INITIAL_ROCKET_Y, pz),
        scale=(0.9, ROCKET_BODY_HEIGHT, 0.9),
        color=color.white,
    )
    # Nose cone (narrow cube, tapered via scale)
    Entity(
        parent=body, model="cube",
        scale=(0.7, 0.25, 0.7),
        y=0.62,
        color=color.rgb(210, 70, 70),
    )
    # Small porthole window (slightly forward-facing)
    Entity(
        parent=body, model="sphere",
        scale=(0.28, 0.28, 0.28),
        y=0.2, z=0.48,
        color=color.rgb(70, 130, 220),
    )
    # Side fins (along x-axis)
    for x in (-0.55, 0.55):
        Entity(
            parent=body, model="cube",
            scale=(0.05, 0.45, 0.5),
            position=(x, -0.3, 0),
            color=color.rgb(180, 60, 60),
        )
    # Front/back fins (along z-axis)
    for z in (-0.55, 0.55):
        Entity(
            parent=body, model="cube",
            scale=(0.5, 0.45, 0.05),
            position=(0, -0.3, z),
            color=color.rgb(180, 60, 60),
        )
    return body


def build_exhaust_flame(parent: Entity) -> Entity:
    """Flame plume parented to the rocket body; hidden by default. Toggled
    visible during a liftoff and hidden again when the rocket resets."""
    flame = Entity(
        parent=parent, model="cube",
        scale=(0.6, 0.7, 0.6),
        y=-0.85,
        color=color.rgb(240, 160, 50),
    )
    flame.enabled = False
    return flame


def reset_rocket(rocket: Entity, flame: Entity) -> None:
    """Drop the rocket back onto the pad between turns."""
    rocket.y = INITIAL_ROCKET_Y
    flame.enabled = False
