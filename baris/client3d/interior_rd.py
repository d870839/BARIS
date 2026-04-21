"""R&D Complex interior scene — the first fully 3D, walk-in-and-push-a-button
room. Kept off to one side of the main facility (default origin (100, 0, 0))
so the outdoor scene and interior can both live in the same Ursina world;
the interior is shown/hidden wholesale as the player enters/exits."""
from __future__ import annotations

from typing import Any

from ursina import Entity, Text, color, invoke

from baris.state import MIN_RELIABILITY_TO_LAUNCH, Module, RELIABILITY_CAP, Rocket


# Targets rendered on the wall. Order matches the x-layout left-to-right.
INTERIOR_TARGETS: tuple[tuple[str, str], ...] = (
    (Rocket.LIGHT.value,   "LIGHT"),
    (Rocket.MEDIUM.value,  "MEDIUM"),
    (Rocket.HEAVY.value,   "HEAVY"),
    (Module.DOCKING.value, "DOCKING"),
)

# Size of the room. Centred on origin.
ROOM_WIDTH = 14.0       # x
ROOM_DEPTH = 12.0       # z
ROOM_HEIGHT = 4.5       # y

# TV screen dimensions on the north wall.
TV_SCREEN_W = 2.0
TV_SCREEN_H = 1.2
TV_BAR_MAX_W = 1.8
TV_SPACING = 3.0        # centre-to-centre between adjacent TVs

# Interaction range for physical buttons (metres).
BUTTON_RANGE = 2.0


class RDInterior:
    """Everything visible when the player is inside the R&D Complex.

    Entities are built once and parented to a single root so `.enabled = bool`
    cheaply toggles the whole interior. Dynamic elements (reliability bars,
    percentages, spend display, target-selected glow) live in per-target
    dicts so `sync_state()` can update them on every server state broadcast.
    """

    def __init__(self, origin: tuple[float, float, float] = (100.0, 0.0, 0.0)) -> None:
        self.origin = origin
        self.root = Entity(position=origin)
        self.root.enabled = False  # hidden until the player walks in

        # Dynamic refs, filled in by builders below.
        self.tv_bars: dict[str, Entity] = {}
        self.tv_pct: dict[str, Text] = {}
        self.tv_frames: dict[str, Entity] = {}
        self.buttons: dict[str, Entity] = {}   # id -> pedestal cap entity
        self.spend_display: Text | None = None

        self._build_room()
        self._build_tvs()
        self._build_target_buttons()
        self._build_spend_station()
        self._build_exit()

    # ------------------------------------------------------------------
    # Geometry builders
    # ------------------------------------------------------------------
    def _build_room(self) -> None:
        half_w = ROOM_WIDTH / 2
        half_d = ROOM_DEPTH / 2

        # Floor
        Entity(
            parent=self.root, model="plane",
            scale=(ROOM_WIDTH, 1, ROOM_DEPTH),
            color=color.rgb32(170, 165, 160),
            texture="white_cube", texture_scale=(ROOM_WIDTH, ROOM_DEPTH),
            collider="box",
        )
        # Ceiling (thin slab so no direct light leaks; also makes the room
        # feel enclosed without needing a skybox override).
        Entity(
            parent=self.root, model="cube",
            scale=(ROOM_WIDTH, 0.1, ROOM_DEPTH),
            y=ROOM_HEIGHT,
            color=color.rgb32(200, 200, 205),
        )
        wall_color = color.rgb32(235, 235, 240)
        # North wall (holds the TVs).
        Entity(
            parent=self.root, model="cube", collider="box",
            scale=(ROOM_WIDTH, ROOM_HEIGHT, 0.2),
            position=(0, ROOM_HEIGHT / 2, half_d),
            color=wall_color,
        )
        # West wall (spend station).
        Entity(
            parent=self.root, model="cube", collider="box",
            scale=(0.2, ROOM_HEIGHT, ROOM_DEPTH),
            position=(-half_w, ROOM_HEIGHT / 2, 0),
            color=wall_color,
        )
        # East wall.
        Entity(
            parent=self.root, model="cube", collider="box",
            scale=(0.2, ROOM_HEIGHT, ROOM_DEPTH),
            position=(half_w, ROOM_HEIGHT / 2, 0),
            color=wall_color,
        )
        # South wall, split around a doorway gap (2m wide).
        door_half = 1.0
        Entity(
            parent=self.root, model="cube", collider="box",
            scale=((ROOM_WIDTH / 2) - door_half, ROOM_HEIGHT, 0.2),
            position=((-ROOM_WIDTH / 4 - door_half / 2), ROOM_HEIGHT / 2, -half_d),
            color=wall_color,
        )
        Entity(
            parent=self.root, model="cube", collider="box",
            scale=((ROOM_WIDTH / 2) - door_half, ROOM_HEIGHT, 0.2),
            position=((ROOM_WIDTH / 4 + door_half / 2), ROOM_HEIGHT / 2, -half_d),
            color=wall_color,
        )
        # Trim header above the doorway.
        Entity(
            parent=self.root, model="cube",
            scale=(door_half * 2, 0.6, 0.2),
            position=(0, ROOM_HEIGHT - 0.3, -half_d),
            color=wall_color,
        )

    def _build_tvs(self) -> None:
        """Four wall-mounted displays along the north wall — one per target,
        each with a frame, dark screen, fillable bar, label, and live %."""
        total_span = TV_SPACING * (len(INTERIOR_TARGETS) - 1)
        start_x = -total_span / 2
        z = ROOM_DEPTH / 2 - 0.15   # just in front of the north wall
        y = 2.8                     # eye level

        for i, (tvalue, tlabel) in enumerate(INTERIOR_TARGETS):
            x = start_x + i * TV_SPACING
            frame = Entity(
                parent=self.root, model="cube",
                position=(x, y, z),
                scale=(TV_SCREEN_W + 0.2, TV_SCREEN_H + 0.2, 0.1),
                color=color.rgb32(40, 45, 55),
            )
            self.tv_frames[tvalue] = frame
            # Dark screen, slightly in front of the frame.
            Entity(
                parent=self.root, model="cube",
                position=(x, y, z - 0.06),
                scale=(TV_SCREEN_W, TV_SCREEN_H, 0.02),
                color=color.rgb32(12, 16, 28),
            )
            # Fillable bar anchored at the left edge of the screen.
            bar = Entity(
                parent=self.root, model="cube",
                origin=(-0.5, 0, 0),
                position=(x - TV_BAR_MAX_W / 2, y - 0.2, z - 0.08),
                scale=(0.01, 0.25, 0.02),
                color=color.rgb32(110, 200, 120),
            )
            self.tv_bars[tvalue] = bar
            # Label
            Text(
                text=tlabel, parent=self.root,
                position=(x, y + TV_SCREEN_H / 2 - 0.15, z - 0.1),
                scale=5, origin=(0, 0),
                color=color.rgb32(220, 225, 235),
            )
            # Percentage readout
            pct = Text(
                text="0%", parent=self.root,
                position=(x, y + 0.15, z - 0.1),
                scale=8, origin=(0, 0),
                color=color.rgb32(110, 200, 120),
            )
            self.tv_pct[tvalue] = pct

    def _build_target_buttons(self) -> None:
        """Pedestals on the floor, one beneath each TV. Player walks up
        and presses E to select that R&D target."""
        total_span = TV_SPACING * (len(INTERIOR_TARGETS) - 1)
        start_x = -total_span / 2
        z = ROOM_DEPTH / 2 - 1.4
        for i, (tvalue, tlabel) in enumerate(INTERIOR_TARGETS):
            x = start_x + i * TV_SPACING
            # Pedestal body
            Entity(
                parent=self.root, model="cube",
                position=(x, 0.45, z),
                scale=(0.7, 0.9, 0.7),
                color=color.rgb32(110, 110, 125),
                collider="box",
            )
            # Red / green cap — the "button" that depresses when pressed.
            cap = Entity(
                parent=self.root, model="cube",
                position=(x, 1.0, z),
                scale=(0.45, 0.15, 0.45),
                color=color.rgb32(220, 70, 70),
            )
            cap._rest_y = cap.y
            self.buttons[f"target:{tvalue}"] = cap
            # Label on the pedestal front.
            Text(
                text=f"SELECT\n{tlabel}",
                parent=self.root,
                position=(x, 0.55, z - 0.36),
                scale=4.2, origin=(0, 0),
                color=color.rgb32(20, 25, 35),
            )

    def _build_spend_station(self) -> None:
        """Two big console buttons on the west wall for -5 / +5 MB spend,
        with a wall TV above showing the live queued spend."""
        x = -ROOM_WIDTH / 2 + 0.6
        # Wall TV (mirrors the target TVs but mounted on the west wall so
        # the screen face normal points +x into the room).
        wall_x = -ROOM_WIDTH / 2
        tv_y = 2.8
        # Frame
        Entity(
            parent=self.root, model="cube",
            position=(wall_x + 0.12, tv_y, 0),
            scale=(0.1, TV_SCREEN_H + 0.2, TV_SCREEN_W + 1.0),
            color=color.rgb32(40, 45, 55),
        )
        # Dark screen slightly in front of the frame.
        Entity(
            parent=self.root, model="cube",
            position=(wall_x + 0.19, tv_y, 0),
            scale=(0.02, TV_SCREEN_H, TV_SCREEN_W + 0.8),
            color=color.rgb32(12, 16, 28),
        )
        # "SPEND" header above the big readout, rotated so it faces the room.
        Text(
            text="QUEUED  SPEND",
            parent=self.root,
            position=(wall_x + 0.22, tv_y + TV_SCREEN_H / 2 - 0.15, 0),
            scale=4.5, origin=(0, 0),
            rotation=(0, 90, 0),
            color=color.rgb32(220, 225, 235),
        )
        # Big live readout.
        self.spend_display = Text(
            text="10 MB",
            parent=self.root,
            position=(wall_x + 0.22, tv_y, 0),
            scale=12, origin=(0, 0),
            rotation=(0, 90, 0),
            color=color.rgb32(240, 200, 90),
        )

        # A low console block the buttons sit on.
        Entity(
            parent=self.root, model="cube",
            position=(x, 0.5, 0),
            scale=(0.8, 1.0, 4.0),
            color=color.rgb32(95, 100, 115),
            collider="box",
        )
        for bid, label, dz, cap_color in (
            ("spend_minus", "-5 MB", -1.6, color.rgb32(210, 80, 80)),
            ("spend_plus",  "+5 MB",  1.6, color.rgb32(80, 200, 110)),
        ):
            cap = Entity(
                parent=self.root, model="cube",
                position=(x + 0.05, 1.1, dz),
                scale=(0.5, 0.15, 0.8),
                color=cap_color,
            )
            cap._rest_y = cap.y
            self.buttons[bid] = cap
            Text(
                text=label, parent=self.root,
                position=(x - 0.5, 1.1, dz),
                scale=7, origin=(0, 0),
                rotation=(0, 90, 0),
                color=color.rgb32(240, 245, 250),
            )

    def _build_exit(self) -> None:
        """A glowing 'EXIT' sign + trigger pedestal just inside the doorway."""
        z = -ROOM_DEPTH / 2 + 0.8
        Entity(
            parent=self.root, model="cube",
            position=(0, 0.3, z),
            scale=(1.4, 0.6, 0.6),
            color=color.rgb32(200, 40, 40),
            collider="box",
        )
        cap = Entity(
            parent=self.root, model="cube",
            position=(0, 0.7, z),
            scale=(1.2, 0.1, 0.5),
            color=color.rgb32(240, 80, 80),
        )
        cap._rest_y = cap.y
        self.buttons["exit"] = cap
        Text(
            text="EXIT [E]",
            parent=self.root,
            position=(0, 1.4, z),
            scale=6, origin=(0, 0),
            color=color.rgb32(255, 220, 220),
        )

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------
    @property
    def entry_world_pos(self) -> tuple[float, float, float]:
        """Where to teleport the player when they enter the interior."""
        ox, oy, oz = self.origin
        return (ox, 1.8, oz - ROOM_DEPTH / 2 + 2.0)

    def sync_state(self, me: Any, rd_target: str | None, rd_spend: int) -> None:
        """Pull current values out of the player state and rewrite the
        visible bars / labels / highlights. Called every frame."""
        for tvalue, bar in self.tv_bars.items():
            rel = 0
            if me is not None:
                rel = me.reliability.get(tvalue, 0)
            frac = max(0.0, min(1.0, rel / RELIABILITY_CAP))
            bar.scale_x = max(0.01, TV_BAR_MAX_W * frac)
            # Colour the bar by launch-readiness.
            if rel >= 75:
                bar.color = color.rgb32(110, 200, 120)
            elif rel >= MIN_RELIABILITY_TO_LAUNCH:
                bar.color = color.rgb32(240, 200, 90)
            else:
                bar.color = color.rgb32(220, 90, 90)
            self.tv_pct[tvalue].text = f"{rel}%"
            # Selected-target frame glow.
            selected = rd_target == tvalue
            self.tv_frames[tvalue].color = (
                color.rgb32(240, 200, 90) if selected else color.rgb32(40, 45, 55)
            )
        if self.spend_display is not None:
            self.spend_display.text = f"{rd_spend} MB"

    def nearby_button(self, world_xz: tuple[float, float]) -> str | None:
        """Which physical button is within BUTTON_RANGE of the player, if any."""
        if not self.root.enabled:
            return None
        ox, _, oz = self.origin
        px, pz = world_xz
        closest: str | None = None
        closest_d = BUTTON_RANGE
        for bid, cap in self.buttons.items():
            bx = ox + cap.x
            bz = oz + cap.z
            d = ((px - bx) ** 2 + (pz - bz) ** 2) ** 0.5
            if d < closest_d:
                closest_d = d
                closest = bid
        return closest

    def press_feedback(self, button_id: str) -> None:
        """Briefly depress the button cap for visual feedback on press."""
        cap = self.buttons.get(button_id)
        if cap is None:
            return
        cap.animate_y(cap._rest_y - 0.05, duration=0.08)
        invoke(setattr, cap, "y", cap._rest_y, delay=0.18)

    def show(self) -> None:
        self.root.enabled = True

    def hide(self) -> None:
        self.root.enabled = False
