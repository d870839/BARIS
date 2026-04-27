"""Library interior — a walk-in archive. One wall is a scrolling event
log from state.log; the opposite wall is the 'Hall of Firsts' showing
which missions each side has claimed. Info-display only: the only
interactive element is the EXIT pedestal."""
from __future__ import annotations

from typing import Any

from ursina import Entity, Text, color, invoke

from baris.state import MISSIONS_BY_ID, MissionId


ROOM_WIDTH = 16.0
ROOM_DEPTH = 14.0
ROOM_HEIGHT = 4.5
BUTTON_RANGE = 2.0

# How many lines fit on the log wall.
LOG_LINES = 18


class LibraryInterior:
    def __init__(self, origin: tuple[float, float, float] = (200.0, 0.0, 100.0)) -> None:
        self.origin = origin
        self.root = Entity(position=origin)
        self.root.enabled = False

        self.log_texts: list[Text] = []
        self.firsts_title: Text | None = None
        self.firsts_you: Text | None = None
        self.firsts_opp: Text | None = None
        self.buttons: dict[str, Entity] = {}

        self._build_room()
        self._build_log_wall()
        self._build_firsts_wall()
        self._build_exit()

    def _build_room(self) -> None:
        half_w = ROOM_WIDTH / 2
        half_d = ROOM_DEPTH / 2
        Entity(
            parent=self.root, model="plane",
            scale=(ROOM_WIDTH, 1, ROOM_DEPTH),
            color=color.rgb32(165, 145, 120),
            texture="white_cube", texture_scale=(ROOM_WIDTH, ROOM_DEPTH),
            collider="box",
        )
        Entity(
            parent=self.root, model="cube",
            scale=(ROOM_WIDTH, 0.1, ROOM_DEPTH), y=ROOM_HEIGHT,
            color=color.rgb32(200, 195, 185),
        )
        wall = color.rgb32(220, 210, 185)
        Entity(
            parent=self.root, model="cube", collider="box",
            scale=(ROOM_WIDTH, ROOM_HEIGHT, 0.2),
            position=(0, ROOM_HEIGHT / 2, half_d), color=wall,
        )
        Entity(
            parent=self.root, model="cube", collider="box",
            scale=(0.2, ROOM_HEIGHT, ROOM_DEPTH),
            position=(-half_w, ROOM_HEIGHT / 2, 0), color=wall,
        )
        Entity(
            parent=self.root, model="cube", collider="box",
            scale=(0.2, ROOM_HEIGHT, ROOM_DEPTH),
            position=(half_w, ROOM_HEIGHT / 2, 0), color=wall,
        )
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

    def _build_log_wall(self) -> None:
        """North wall becomes a big dark screen listing recent events."""
        screen_y = ROOM_HEIGHT / 2 + 0.1
        z = ROOM_DEPTH / 2 - 0.12
        # Frame
        Entity(
            parent=self.root, model="cube",
            position=(0, screen_y, z), scale=(12.0, 3.4, 0.1),
            color=color.rgb32(40, 30, 20),
        )
        # Dark screen
        Entity(
            parent=self.root, model="cube",
            position=(0, screen_y, z - 0.06), scale=(11.6, 3.0, 0.02),
            color=color.rgb32(18, 16, 22),
        )
        # Header
        Text(
            text="FLIGHT RECORDS",
            parent=self.root,
            position=(0, screen_y + 1.4, z - 0.08),
            scale=9, origin=(0, 0),
            color=color.rgb32(240, 210, 140),
        )
        # Pre-allocate log line Text widgets; contents updated by sync_state.
        top = screen_y + 1.0
        for i in range(LOG_LINES):
            t = Text(
                text="",
                parent=self.root,
                position=(-5.5, top - i * 0.14, z - 0.08),
                scale=4, origin=(-0.5, 0.5),
                color=color.rgb32(220, 215, 200),
            )
            self.log_texts.append(t)

    def _build_firsts_wall(self) -> None:
        """East wall: 'Hall of Firsts' — missions each side has claimed."""
        wall_x = ROOM_WIDTH / 2 - 0.12
        y = 2.6
        Entity(
            parent=self.root, model="cube",
            position=(wall_x, y, 0), scale=(0.1, 3.0, 8.0),
            color=color.rgb32(40, 30, 20),
        )
        Entity(
            parent=self.root, model="cube",
            position=(wall_x - 0.06, y, 0), scale=(0.02, 2.6, 7.6),
            color=color.rgb32(24, 20, 28),
        )
        self.firsts_title = Text(
            text="HALL  OF  FIRSTS",
            parent=self.root,
            position=(wall_x - 0.1, y + 1.0, 0), rotation=(0, -90, 0),
            scale=9, origin=(0, 0),
            color=color.rgb32(240, 210, 140),
        )
        self.firsts_you = Text(
            text="YOU — none yet",
            parent=self.root,
            position=(wall_x - 0.1, y + 0.3, 0), rotation=(0, -90, 0),
            scale=5, origin=(0, 0),
            color=color.rgb32(120, 180, 220),
        )
        self.firsts_opp = Text(
            text="OPP — none yet",
            parent=self.root,
            position=(wall_x - 0.1, y - 0.6, 0), rotation=(0, -90, 0),
            scale=5, origin=(0, 0),
            color=color.rgb32(220, 120, 120),
        )

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

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------
    @property
    def entry_world_pos(self) -> tuple[float, float, float]:
        ox, _, oz = self.origin
        return (ox, 1.8, oz - ROOM_DEPTH / 2 + 2.0)

    def sync_state(self, me: Any, state: Any) -> None:
        # Log lines
        from baris.client3d.text_utils import panda_safe
        lines = list(state.log[-LOG_LINES:]) if state is not None else []
        for i, t in enumerate(self.log_texts):
            if i < len(lines):
                # Resolver log strings carry → arrows + 📅 emoji that
                # Panda3D's default font can't render. Swap them for
                # ASCII before they reach the Text widget so the
                # screen actually reads cleanly + the log doesn't
                # spam font warnings every frame.
                t.text = panda_safe(lines[i])[:70]
            else:
                t.text = ""
        # Firsts lists
        if state is None or me is None:
            return
        mine: list[str] = []
        opps: list[str] = []
        my_side = me.side.value if me.side else None
        for mid, holder in state.first_completed.items():
            try:
                name = MISSIONS_BY_ID[MissionId(mid)].name
            except (ValueError, KeyError):
                continue
            if my_side and holder == my_side:
                mine.append(name)
            else:
                opps.append(name)
        self.firsts_you.text = (
            f"YOU  —  {', '.join(mine)}" if mine else "YOU  —  none yet"
        )
        self.firsts_opp.text = (
            f"OPP  —  {', '.join(opps)}" if opps else "OPP  —  none yet"
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
