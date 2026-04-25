"""Museum interior — the Phase L walk-in exhibit hall.

Two big wall displays:
  * North wall: chronological mission history, one line per launch,
    with first-ever claims highlighted gold and catastrophic flights
    in red.
  * East wall: a crude-but-readable prestige-over-time timeline. Each
    PrestigeSnapshot renders as a pair of coloured cubes whose heights
    track each side's running prestige.

Info-display only — the EXIT pedestal is the single interactive."""
from __future__ import annotations

from typing import Any

from ursina import Entity, Text, color, invoke

from baris.state import PRESTIGE_TO_WIN, Side


ROOM_WIDTH = 18.0
ROOM_DEPTH = 14.0
ROOM_HEIGHT = 4.8
BUTTON_RANGE = 2.0

# How many history rows fit on the wall.
HISTORY_ROWS = 18

# How many prestige snapshots the chart shows (newest-first trim).
TIMELINE_SAMPLES = 40

# How many memorial rows fit on the west wall (Phase N).
MEMORIAL_ROWS = 12


class MuseumInterior:
    def __init__(
        self, origin: tuple[float, float, float] = (-100.0, 0.0, 200.0),
    ) -> None:
        self.origin = origin
        self.root = Entity(position=origin)
        self.root.enabled = False

        self.buttons: dict[str, Entity] = {}
        self.history_title: Text | None = None
        self.history_rows: list[Text] = []
        self.timeline_title: Text | None = None
        self.timeline_legend: Text | None = None
        self.timeline_bars: list[tuple[Entity, Entity]] = []
        self.timeline_xlabel: Text | None = None
        # Phase N — Memorial Wall
        self.memorial_title: Text | None = None
        self.memorial_rows: list[Text] = []
        self.memorial_empty: Text | None = None

        self._build_room()
        self._build_history_wall()
        self._build_timeline_wall()
        self._build_memorial_wall()
        self._build_exit()

    def _build_room(self) -> None:
        half_w = ROOM_WIDTH / 2
        half_d = ROOM_DEPTH / 2
        Entity(
            parent=self.root, model="plane",
            scale=(ROOM_WIDTH, 1, ROOM_DEPTH),
            color=color.rgb32(120, 100, 70),
            texture="white_cube", texture_scale=(ROOM_WIDTH, ROOM_DEPTH),
            collider="box",
        )
        Entity(
            parent=self.root, model="cube",
            scale=(ROOM_WIDTH, 0.1, ROOM_DEPTH), y=ROOM_HEIGHT,
            color=color.rgb32(195, 180, 140),
        )
        wall = color.rgb32(235, 220, 185)
        # North + West + East.
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
        # South wall with doorway split.
        door_half = 1.0
        Entity(
            parent=self.root, model="cube", collider="box",
            scale=((ROOM_WIDTH / 2) - door_half, ROOM_HEIGHT, 0.2),
            position=(-ROOM_WIDTH / 4 - door_half / 2, ROOM_HEIGHT / 2, -half_d),
            color=wall,
        )
        Entity(
            parent=self.root, model="cube", collider="box",
            scale=(ROOM_WIDTH / 2 - door_half, ROOM_HEIGHT, 0.2),
            position=(ROOM_WIDTH / 4 + door_half / 2, ROOM_HEIGHT / 2, -half_d),
            color=wall,
        )
        Entity(
            parent=self.root, model="cube",
            scale=(door_half * 2, 0.6, 0.2),
            position=(0, ROOM_HEIGHT - 0.3, -half_d), color=wall,
        )

    def _build_history_wall(self) -> None:
        """North wall: big dark plaque listing every launch resolved."""
        screen_y = ROOM_HEIGHT / 2 + 0.2
        z = ROOM_DEPTH / 2 - 0.12
        Entity(
            parent=self.root, model="cube",
            position=(0, screen_y, z), scale=(14.0, 3.8, 0.1),
            color=color.rgb32(40, 30, 20),
        )
        Entity(
            parent=self.root, model="cube",
            position=(0, screen_y, z - 0.06), scale=(13.6, 3.4, 0.02),
            color=color.rgb32(16, 14, 22),
        )
        self.history_title = Text(
            text="MISSION  HISTORY",
            parent=self.root,
            position=(0, screen_y + 1.55, z - 0.08),
            scale=9, origin=(0, 0),
            color=color.rgb32(240, 210, 140),
        )
        top = screen_y + 1.15
        for i in range(HISTORY_ROWS):
            t = Text(
                text="",
                parent=self.root,
                position=(-6.5, top - i * 0.17, z - 0.08),
                scale=3.6, origin=(-0.5, 0.5),
                color=color.rgb32(220, 215, 200),
            )
            self.history_rows.append(t)

    def _build_timeline_wall(self) -> None:
        """East wall: prestige-over-time bar chart. Two adjacent cubes
        per sample (USA + USSR), whose heights are set in sync_state."""
        wall_x = ROOM_WIDTH / 2 - 0.14
        y_base = 0.25
        z0 = -ROOM_DEPTH / 2 + 2.0
        # Back plate + frame.
        Entity(
            parent=self.root, model="cube",
            position=(wall_x, 1.6, 0), scale=(0.1, 3.0, 8.0),
            color=color.rgb32(35, 35, 55),
        )
        Entity(
            parent=self.root, model="cube",
            position=(wall_x - 0.06, 1.6, 0), scale=(0.02, 2.7, 7.6),
            color=color.rgb32(14, 16, 28),
        )
        self.timeline_title = Text(
            text="PRESTIGE  TIMELINE",
            parent=self.root,
            position=(wall_x - 0.1, 3.0, 0), rotation=(0, -90, 0),
            scale=9, origin=(0, 0),
            color=color.rgb32(240, 210, 140),
        )
        self.timeline_legend = Text(
            text=f"goal: {PRESTIGE_TO_WIN}  —  USA vs USSR",
            parent=self.root,
            position=(wall_x - 0.1, 2.65, 0), rotation=(0, -90, 0),
            scale=4.5, origin=(0, 0),
            color=color.rgb32(220, 220, 235),
        )
        # Pre-allocate TIMELINE_SAMPLES pairs of tiny cubes. Each cube is
        # 0.08 wide (in the room's z-axis) and scales its y-height based
        # on the prestige reading during sync_state.
        span_z = 7.0
        step = span_z / TIMELINE_SAMPLES
        start_z = -span_z / 2 + step / 2
        for i in range(TIMELINE_SAMPLES):
            z_pair = start_z + i * step
            usa_bar = Entity(
                parent=self.root, model="cube",
                position=(wall_x - 0.08, y_base, z_pair - step * 0.22),
                scale=(0.04, 0.01, step * 0.35),
                color=color.rgb32(120, 180, 230),
            )
            ussr_bar = Entity(
                parent=self.root, model="cube",
                position=(wall_x - 0.08, y_base, z_pair + step * 0.22),
                scale=(0.04, 0.01, step * 0.35),
                color=color.rgb32(230, 120, 130),
            )
            self.timeline_bars.append((usa_bar, ussr_bar))
        # X-axis date range readout.
        self.timeline_xlabel = Text(
            text="",
            parent=self.root,
            position=(wall_x - 0.1, 0.1, 0), rotation=(0, -90, 0),
            scale=3.8, origin=(0, 0),
            color=color.rgb32(180, 180, 200),
        )
        _ = z0

    def _build_memorial_wall(self) -> None:
        """West wall: Memorial plaque listing every astronaut KIA on a
        flight, oldest first. A small headline + a granite-style plate
        + up to MEMORIAL_ROWS engraved name lines."""
        wall_x = -ROOM_WIDTH / 2 + 0.14
        Entity(  # back plate
            parent=self.root, model="cube",
            position=(wall_x, 1.7, 0), scale=(0.1, 3.2, 8.0),
            color=color.rgb32(60, 60, 70),
        )
        Entity(  # inset face
            parent=self.root, model="cube",
            position=(wall_x + 0.06, 1.7, 0), scale=(0.02, 2.9, 7.6),
            color=color.rgb32(35, 35, 45),
        )
        self.memorial_title = Text(
            text="IN  MEMORIAM",
            parent=self.root,
            position=(wall_x + 0.1, 3.05, 0), rotation=(0, 90, 0),
            scale=8.5, origin=(0, 0),
            color=color.rgb32(220, 200, 150),
        )
        # Pre-allocate engraved-name rows. Default empty; sync_state
        # fills them in with KIA entries from state.mission_history.
        for i in range(MEMORIAL_ROWS):
            t = Text(
                text="",
                parent=self.root,
                position=(wall_x + 0.1, 2.55 - i * 0.21, 0),
                rotation=(0, 90, 0),
                scale=4.2, origin=(0, 0),
                color=color.rgb32(220, 215, 200),
            )
            self.memorial_rows.append(t)
        # Empty-state placeholder shown when nobody has died yet.
        self.memorial_empty = Text(
            text="(no losses yet — fly safe)",
            parent=self.root,
            position=(wall_x + 0.1, 1.6, 0), rotation=(0, 90, 0),
            scale=4.2, origin=(0, 0),
            color=color.rgb32(160, 155, 145),
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

    def sync_state(self, me: Any, state: Any = None, *_: Any) -> None:
        self._sync_history(state)
        self._sync_timeline(state)
        self._sync_memorial(state)

    def _sync_memorial(self, state: Any) -> None:
        from baris.resolver import memorial_roll
        roll = memorial_roll(state) if state is not None else []
        if not roll:
            for t in self.memorial_rows:
                t.text = ""
            if self.memorial_empty is not None:
                self.memorial_empty.enabled = True
            return
        if self.memorial_empty is not None:
            self.memorial_empty.enabled = False
        # Newest first so freshly-fallen astronauts are visible at the top.
        for i, t in enumerate(self.memorial_rows):
            if i >= len(roll):
                t.text = ""
                continue
            name, mission_name, year, season, side = roll[-(i + 1)]
            t.text = f"{name:<14}  {mission_name[:18]:<18}  {season[:3]} {year}"

    def _sync_history(self, state: Any) -> None:
        history = list(getattr(state, "mission_history", []) or [])
        # Show the newest HISTORY_ROWS so the chart reads like a recent
        # events feed. Pad with empty strings if we have fewer.
        tail = history[-HISTORY_ROWS:]
        for i, t in enumerate(self.history_rows):
            if i >= len(tail):
                t.text = ""
                continue
            e = tail[i]
            stamp = f"{e.season[:3]} {e.year}"
            side = (e.side or "?")[:4]
            name = (e.mission_name or e.mission_id)[:22]
            if e.first_claimed and e.success:
                tag = "FIRST!"
                t.color = color.rgb32(240, 210, 140)
            elif e.success:
                tag = "ok"
                t.color = color.rgb32(180, 220, 180)
            elif e.deaths:
                tag = f"KIA x{len(e.deaths)}"
                t.color = color.rgb32(230, 120, 120)
            else:
                tag = "fail"
                t.color = color.rgb32(220, 180, 120)
            t.text = (
                f"{stamp:<10}{side:<5}{name:<23}"
                f"{e.prestige_delta:>+3}  {tag}"
            )

    def _sync_timeline(self, state: Any) -> None:
        snaps = list(getattr(state, "prestige_timeline", []) or [])
        tail = snaps[-TIMELINE_SAMPLES:]
        max_p = PRESTIGE_TO_WIN
        for s in tail:
            if s.usa_prestige > max_p:
                max_p = s.usa_prestige
            if s.ussr_prestige > max_p:
                max_p = s.ussr_prestige
        max_bar_height = 2.3  # metres
        y_base = 0.25
        for i, (usa_bar, ussr_bar) in enumerate(self.timeline_bars):
            if i >= len(tail):
                usa_bar.scale_y = 0.01
                ussr_bar.scale_y = 0.01
                usa_bar.y = y_base
                ussr_bar.y = y_base
                continue
            s = tail[i]
            usa_h = max(0.02, (s.usa_prestige / max_p) * max_bar_height) if max_p else 0.02
            ussr_h = max(0.02, (s.ussr_prestige / max_p) * max_bar_height) if max_p else 0.02
            usa_bar.scale_y = usa_h
            ussr_bar.scale_y = ussr_h
            usa_bar.y = y_base + usa_h / 2
            ussr_bar.y = y_base + ussr_h / 2
        if self.timeline_xlabel is not None:
            if tail:
                self.timeline_xlabel.text = (
                    f"{tail[0].season[:3]} {tail[0].year}   →   "
                    f"{tail[-1].season[:3]} {tail[-1].year}"
                )
            else:
                self.timeline_xlabel.text = "(timeline empty)"
        _ = Side  # keep import alive for readers

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
