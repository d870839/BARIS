"""Procedural fruit-shaped character models.

Each Italian Brainrot astronaut is rendered as a spherical fruit
in their swatch colour with the glyph painted on the front face.
A short stem-and-leaf sits on top to sell the fruit aesthetic; a
tiny base cylinder gives them something to stand on. No real
appendages — the joke lands harder when they're just floating
fruit-globes.

The body sphere bobs gently on a sine wave so a roomful of them
reads as alive without any keyframed animation.

Build one with:

    from baris.client3d.character_model import FruitCharacter
    char = FruitCharacter(name="Bombardiro Crocodilo", parent=root)
    char.position = (3, 0, 1)
"""
from __future__ import annotations

import math

from ursina import Entity, Text, color, time as ursina_time

from baris.state import character_portrait


# Default body radius — tuned so a row of 6-8 characters fits across
# the astro interior without overlap. Caller can override per-instance.
_BODY_RADIUS = 0.45
_BOB_AMPLITUDE = 0.05      # metres
_BOB_PERIOD_S = 2.4        # seconds for a full bob cycle


class FruitCharacter(Entity):
    """Spherical fruit-bodied astronaut. Driven entirely by the
    character_portrait() table (glyph + RGB swatch) so each meme
    name renders with its canonical colour."""

    def __init__(
        self,
        name: str,
        *,
        parent: Entity | None = None,
        position: tuple[float, float, float] = (0.0, 0.0, 0.0),
        radius: float = _BODY_RADIUS,
        bob: bool = True,
    ) -> None:
        # Root entity is invisible — we just use it as a transform
        # parent for the body / face / stem pieces. The "model=None"
        # entity has no mesh of its own but still hosts the bob
        # animation in update().
        super().__init__(parent=parent, position=position)
        self.name_label = name
        self.bob_enabled = bob
        glyph, swatch = character_portrait(name)
        self._glyph = glyph
        self._swatch = swatch
        self._t0 = self._now()

        body_color = color.rgb32(*swatch)

        # Body: sphere in the character's swatch colour. Slightly
        # raised so it sits at eye-ish level rather than floor level.
        self.body = Entity(
            parent=self, model="sphere",
            scale=radius * 2,   # Ursina's sphere model is unit-radius
            position=(0, radius + 0.1, 0),
            color=body_color,
        )

        # Face decal: a small disc of the contrasting colour on the
        # front of the body, with the glyph centred on it. Z is
        # +radius * 0.95 so it sits proud of the sphere surface
        # without z-fighting.
        face_z = radius * 0.95
        self.face = Entity(
            parent=self.body, model="circle",
            scale=0.55,                   # relative to body scale
            position=(0, 0, face_z / (radius * 2)),
            color=color.rgb32(245, 245, 235),
            double_sided=True,
        )
        # Glyph as a Text entity parented to the face.
        self.face_text = Text(
            text=glyph,
            parent=self.face,
            origin=(0, 0),
            scale=12,                     # Text scale lives in text-units
            position=(0, 0, -0.01),       # in front of the face disc
            color=color.rgb32(40, 40, 60),
        )

        # Stem: tiny brown cylinder on top.
        self.stem = Entity(
            parent=self, model="cylinder",
            scale=(radius * 0.18, radius * 0.25, radius * 0.18),
            position=(0, radius * 2 + 0.1, 0),
            color=color.rgb32(95, 65, 40),
        )
        # Leaf: a flat green ellipse cocked at an angle off the stem.
        self.leaf = Entity(
            parent=self.stem, model="quad",
            scale=(2.6, 1.4, 1.0),
            position=(0.7, 0.1, 0.0),
            rotation=(0, 0, 35),
            color=color.rgb32(110, 170, 80),
            double_sided=True,
        )

        # Base: short brown cylinder so they have something to stand
        # on rather than floating awkwardly above the floor.
        self.base = Entity(
            parent=self, model="cylinder",
            scale=(radius * 0.6, 0.08, radius * 0.6),
            position=(0, 0.04, 0),
            color=color.rgb32(70, 65, 60),
        )

    # ------------------------------------------------------------------
    @property
    def glyph(self) -> str:
        return self._glyph

    @property
    def swatch(self) -> tuple[int, int, int]:
        return self._swatch

    # ------------------------------------------------------------------
    @staticmethod
    def _now() -> float:
        # ursina.time.time exists; fall back to a dt accumulator if
        # the engine isn't running (e.g. unit tests that import this
        # module by accident).
        try:
            return float(ursina_time.time)
        except Exception:
            return 0.0

    def update(self) -> None:
        """Per-frame bob animation. Ursina invokes this on every
        Entity that has it; we don't need to do anything else."""
        if not self.bob_enabled:
            return
        elapsed = self._now() - self._t0
        offset = math.sin(elapsed * (2 * math.pi / _BOB_PERIOD_S))
        self.body.y = (_BODY_RADIUS + 0.1) + _BOB_AMPLITUDE * offset
