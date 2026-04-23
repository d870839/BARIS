"""Astronaut Complex interior — seven wall portraits showing the player's
roster with live skill readouts. Info-display only: the only interactive
element is the EXIT pedestal by the door."""
from __future__ import annotations

from typing import Any

from ursina import Entity, Text, color, invoke

from baris.state import STARTING_ASTRONAUTS


ROOM_WIDTH = 16.0
ROOM_DEPTH = 12.0
ROOM_HEIGHT = 4.5
BUTTON_RANGE = 2.0


class AstroInterior:
    """Walk-in roster display. Layout: a wall of seven astronaut portraits
    along the north and east walls (4 + 3), each a wall TV with name,
    skill bars, and status. Rebuilt once; `sync_state()` updates the
    dynamic text every frame so KIAs / skill bumps show live."""

    def __init__(self, origin: tuple[float, float, float] = (100.0, 0.0, 100.0)) -> None:
        self.origin = origin
        self.root = Entity(position=origin)
        self.root.enabled = False

        self.portraits: list[dict[str, Any]] = []  # list of refs per slot
        self.buttons: dict[str, Entity] = {}
        self._last_roster_len = 0

        self._build_room()
        self._build_portraits()
        self._build_exit()

    def _build_room(self) -> None:
        half_w = ROOM_WIDTH / 2
        half_d = ROOM_DEPTH / 2
        # Floor
        Entity(
            parent=self.root, model="plane",
            scale=(ROOM_WIDTH, 1, ROOM_DEPTH),
            color=color.rgb32(185, 175, 150),
            texture="white_cube", texture_scale=(ROOM_WIDTH, ROOM_DEPTH),
            collider="box",
        )
        # Ceiling
        Entity(
            parent=self.root, model="cube",
            scale=(ROOM_WIDTH, 0.1, ROOM_DEPTH), y=ROOM_HEIGHT,
            color=color.rgb32(210, 210, 215),
        )
        wall = color.rgb32(230, 235, 240)
        # North
        Entity(
            parent=self.root, model="cube", collider="box",
            scale=(ROOM_WIDTH, ROOM_HEIGHT, 0.2),
            position=(0, ROOM_HEIGHT / 2, half_d), color=wall,
        )
        # West
        Entity(
            parent=self.root, model="cube", collider="box",
            scale=(0.2, ROOM_HEIGHT, ROOM_DEPTH),
            position=(-half_w, ROOM_HEIGHT / 2, 0), color=wall,
        )
        # East
        Entity(
            parent=self.root, model="cube", collider="box",
            scale=(0.2, ROOM_HEIGHT, ROOM_DEPTH),
            position=(half_w, ROOM_HEIGHT / 2, 0), color=wall,
        )
        # South with doorway split
        door_half = 1.0
        Entity(
            parent=self.root, model="cube", collider="box",
            scale=((ROOM_WIDTH / 2) - door_half, ROOM_HEIGHT, 0.2),
            position=(-ROOM_WIDTH / 4 - door_half / 2, ROOM_HEIGHT / 2, -half_d),
            color=wall,
        )
        Entity(
            parent=self.root, model="cube", collider="box",
            scale=((ROOM_WIDTH / 2) - door_half, ROOM_HEIGHT, 0.2),
            position=(ROOM_WIDTH / 4 + door_half / 2, ROOM_HEIGHT / 2, -half_d),
            color=wall,
        )
        Entity(
            parent=self.root, model="cube",
            scale=(door_half * 2, 0.6, 0.2),
            position=(0, ROOM_HEIGHT - 0.3, -half_d), color=wall,
        )

    def _build_portraits(self) -> None:
        """Seven portrait frames — 5 along the north wall, 2 along the east wall."""
        layout = [
            # (x, z, facing) — facing is the direction the portrait points into the room.
            (-6.0, ROOM_DEPTH / 2 - 0.1, "north"),
            (-3.0, ROOM_DEPTH / 2 - 0.1, "north"),
            ( 0.0, ROOM_DEPTH / 2 - 0.1, "north"),
            ( 3.0, ROOM_DEPTH / 2 - 0.1, "north"),
            ( 6.0, ROOM_DEPTH / 2 - 0.1, "north"),
            (ROOM_WIDTH / 2 - 0.1, 0,  "east"),
            (ROOM_WIDTH / 2 - 0.1, 3,  "east"),
        ]
        for (x, z, facing) in layout[:STARTING_ASTRONAUTS]:
            is_east = (facing == "east")
            # Frame + dark screen behind the text.
            if is_east:
                frame_scale = (0.1, 2.2, 1.8)
                screen_offset = (-0.06, 0, 0)
                screen_scale = (0.02, 2.0, 1.6)
                text_rot = (0, -90, 0)
                text_x = x - 0.08
            else:
                frame_scale = (1.8, 2.2, 0.1)
                screen_offset = (0, 0, -0.06)
                screen_scale = (1.6, 2.0, 0.02)
                text_rot = (0, 0, 0)
                text_x = x
            y = 2.4
            Entity(
                parent=self.root, model="cube",
                position=(x, y, z),
                scale=frame_scale, color=color.rgb32(40, 45, 55),
            )
            Entity(
                parent=self.root, model="cube",
                position=(x + screen_offset[0], y, z + screen_offset[2]),
                scale=screen_scale, color=color.rgb32(16, 22, 36),
            )
            # Name line (top)
            name_text = Text(
                text="—", parent=self.root,
                position=(text_x, y + 0.7, z), rotation=text_rot,
                scale=7, origin=(0, 0), color=color.rgb32(240, 200, 90),
            )
            # Status line (below name)
            status_text = Text(
                text="", parent=self.root,
                position=(text_x, y + 0.45, z), rotation=text_rot,
                scale=4, origin=(0, 0), color=color.rgb32(140, 150, 170),
            )
            # Five skill rows — one per manual skill category.
            skill_texts: list[Text] = []
            for i, label in enumerate(("Capsule", "LM", "EVA", "Docking", "Endure")):
                skill = Text(
                    text=f"{label:<8} 0", parent=self.root,
                    position=(text_x, y + 0.15 - i * 0.19, z), rotation=text_rot,
                    scale=4.2, origin=(0, 0),
                    color=color.rgb32(220, 225, 235),
                )
                skill_texts.append(skill)
            self.portraits.append({
                "name": name_text,
                "status": status_text,
                "skills": skill_texts,
            })

    def _build_exit(self) -> None:
        z = -ROOM_DEPTH / 2 + 0.8
        Entity(
            parent=self.root, model="cube",
            position=(0, 0.3, z), scale=(1.4, 0.6, 0.6),
            color=color.rgb32(200, 40, 40),
            collider="box",
        )
        cap = Entity(
            parent=self.root, model="cube",
            position=(0, 0.7, z), scale=(1.2, 0.1, 0.5),
            color=color.rgb32(240, 80, 80),
        )
        cap._rest_y = cap.y
        self.buttons["exit"] = cap
        Text(
            text="EXIT [E]", parent=self.root,
            position=(0, 1.4, z), scale=6, origin=(0, 0),
            color=color.rgb32(255, 220, 220),
        )
        # TRAINING CONSOLE — press E to open the advanced-training panel.
        tx = -4.5
        Entity(
            parent=self.root, model="cube",
            position=(tx, 0.45, z), scale=(1.1, 0.9, 1.1),
            color=color.rgb32(60, 95, 130),
            collider="box",
        )
        tcap = Entity(
            parent=self.root, model="cube",
            position=(tx, 1.0, z), scale=(0.7, 0.15, 0.7),
            color=color.rgb32(90, 160, 220),
        )
        tcap._rest_y = tcap.y
        self.buttons["training"] = tcap
        Text(
            text="TRAINING\nCONSOLE", parent=self.root,
            position=(tx, 1.55, z), scale=4.2, origin=(0, 0),
            billboard=True,
            color=color.rgb32(200, 225, 245),
        )
        # RECRUITMENT CONSOLE — press E to open the recruit-group panel.
        rx = 4.5
        Entity(
            parent=self.root, model="cube",
            position=(rx, 0.45, z), scale=(1.1, 0.9, 1.1),
            color=color.rgb32(95, 130, 60),
            collider="box",
        )
        rcap = Entity(
            parent=self.root, model="cube",
            position=(rx, 1.0, z), scale=(0.7, 0.15, 0.7),
            color=color.rgb32(160, 220, 90),
        )
        rcap._rest_y = rcap.y
        self.buttons["recruit"] = rcap
        Text(
            text="RECRUITMENT\nCONSOLE", parent=self.root,
            position=(rx, 1.55, z), scale=4.2, origin=(0, 0),
            billboard=True,
            color=color.rgb32(220, 245, 200),
        )

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------
    @property
    def entry_world_pos(self) -> tuple[float, float, float]:
        ox, _, oz = self.origin
        return (ox, 1.8, oz - ROOM_DEPTH / 2 + 2.0)

    def sync_state(self, me: Any, *_: Any) -> None:
        if me is None:
            return
        roster = me.astronauts
        for i, slot in enumerate(self.portraits):
            if i >= len(roster):
                slot["name"].text = "—"
                slot["status"].text = ""
                for s in slot["skills"]:
                    s.text = ""
                continue
            astro = roster[i]
            slot["name"].text = astro.name
            if astro.status == "kia":
                slot["status"].text = "KIA"
                slot["status"].color = color.rgb32(220, 90, 90)
            elif astro.status == "retired":
                slot["status"].text = f"RETIRED  (mood {astro.mood})"
                slot["status"].color = color.rgb32(160, 130, 110)
            elif astro.flight_ready:
                slot["status"].text = f"READY  mood {astro.mood} / {astro.compatibility}"
                slot["status"].color = color.rgb32(110, 200, 120)
            else:
                slot["status"].text = (
                    f"{astro.busy_reason.upper()[:18]}  mood {astro.mood}"
                )
                slot["status"].color = color.rgb32(240, 200, 90)
            for s, label, val in zip(
                slot["skills"],
                ("Capsule", "LM", "EVA", "Docking", "Endure"),
                (astro.capsule, astro.lm_pilot, astro.eva, astro.docking, astro.endurance),
            ):
                s.text = f"{label:<8} {val:>3}"
                s.color = (
                    color.rgb32(220, 225, 235) if astro.active
                    else color.rgb32(160, 110, 110)
                )

    def nearby_button(self, world_xz: tuple[float, float]) -> str | None:
        if not self.root.enabled:
            return None
        ox, _, oz = self.origin
        px, pz = world_xz
        for bid, cap in self.buttons.items():
            d = ((px - (ox + cap.x)) ** 2 + (pz - (oz + cap.z)) ** 2) ** 0.5
            if d < BUTTON_RANGE:
                return bid
        return None

    def press_feedback(self, button_id: str) -> None:
        cap = self.buttons.get(button_id)
        if cap is None:
            return
        cap.animate_y(cap._rest_y - 0.05, duration=0.08)
        invoke(setattr, cap, "y", cap._rest_y, delay=0.18)

    def show(self) -> None:
        self.root.enabled = True

    def hide(self) -> None:
        self.root.enabled = False
