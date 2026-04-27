"""Astronaut Complex interior — wall portraits showing the player's
roster with live skill readouts, and a pair of seasonal NEWS screens
flanking the exit that stream the current headline. The only
interactive elements are the EXIT, TRAINING, and RECRUITMENT pedestals
by the door."""
from __future__ import annotations

from typing import Any

from ursina import Entity, Text, color, invoke


ROOM_WIDTH = 16.0
ROOM_DEPTH = 12.0
ROOM_HEIGHT = 4.5
BUTTON_RANGE = 2.0


def _wrap_headline(text: str, max_chars: int = 28) -> str:
    """Greedy word-wrap for the NEWS TV bodies. Ursina Text supports \\n;
    we split the headline on spaces so individual words aren't broken."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for w in words:
        if not current:
            current = w
        elif len(current) + 1 + len(w) <= max_chars:
            current = f"{current} {w}"
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return "\n".join(lines)


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
        self.news_texts: list[Text] = []
        self._last_roster_len = 0

        self._build_room()
        self._build_portraits()
        self._build_news_screens()
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
        """Portrait frames along the north, east, and west walls. Sized to
        fit the full roster after Phase J recruitment drops (up to ~22
        astronauts in a fully-recruited, death-free run). Slightly
        narrower frames than V1 so seven fit across the north wall."""
        half_w = ROOM_WIDTH / 2
        half_d = ROOM_DEPTH / 2
        wall_inset = 0.1
        layout: list[tuple[float, float, str]] = []
        # North wall — 7 portraits.
        for x in (-6.0, -4.0, -2.0, 0.0, 2.0, 4.0, 6.0):
            layout.append((x, half_d - wall_inset, "north"))
        # East and west walls — 6 portraits each at matching z rows.
        side_zs = (-4.5, -2.7, -0.9, 0.9, 2.7, 4.5)
        for z in side_zs:
            layout.append((half_w - wall_inset, z, "east"))
        for z in side_zs:
            layout.append((-(half_w - wall_inset), z, "west"))
        for (x, z, facing) in layout:
            is_side = facing in ("east", "west")
            # Frame + dark screen behind the text.
            if facing == "east":
                frame_scale = (0.1, 2.0, 1.5)
                screen_offset = (-0.06, 0, 0)
                screen_scale = (0.02, 1.8, 1.3)
                text_rot = (0, -90, 0)
                text_x = x - 0.08
                text_z = z
            elif facing == "west":
                frame_scale = (0.1, 2.0, 1.5)
                screen_offset = (0.06, 0, 0)
                screen_scale = (0.02, 1.8, 1.3)
                text_rot = (0, 90, 0)
                text_x = x + 0.08
                text_z = z
            else:
                frame_scale = (1.4, 2.0, 0.1)
                screen_offset = (0, 0, -0.06)
                screen_scale = (1.2, 1.8, 0.02)
                text_rot = (0, 0, 0)
                text_x = x
                # North-wall bug fix: previously text_z = z, which
                # left the text sitting INSIDE the frame cube while
                # the screen was offset forward by 0.06 — so on the
                # north wall every portrait read as a blank screen
                # with the text trapped behind. Push the text
                # forward by a hair MORE than the screen so it's
                # visible against the dark backing.
                text_z = z - 0.08
            _ = is_side  # kept for symmetry / future use
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
                position=(text_x, y + 0.7, text_z), rotation=text_rot,
                scale=7, origin=(0, 0), color=color.rgb32(240, 200, 90),
            )
            # Status line (below name)
            status_text = Text(
                text="", parent=self.root,
                position=(text_x, y + 0.45, text_z), rotation=text_rot,
                scale=4, origin=(0, 0), color=color.rgb32(140, 150, 170),
            )
            # Five skill rows — one per manual skill category.
            skill_texts: list[Text] = []
            for i, label in enumerate(("Capsule", "LM", "EVA", "Docking", "Endure")):
                skill = Text(
                    text=f"{label:<8} 0", parent=self.root,
                    position=(text_x, y + 0.15 - i * 0.19, text_z), rotation=text_rot,
                    scale=4.2, origin=(0, 0),
                    color=color.rgb32(220, 225, 235),
                )
                skill_texts.append(skill)
            self.portraits.append({
                "name": name_text,
                "status": status_text,
                "skills": skill_texts,
            })

    def _build_news_screens(self) -> None:
        """Two NEWS TVs on the south wall flanking the doorway. Each
        displays the current season's headline in a wrapped marquee. They
        face north (into the room) so the player reads them on approach."""
        south_z = -ROOM_DEPTH / 2 + 0.15
        y = 2.8
        # Doorway is at x = 0, width ~2; put the screens at x = ±4.
        for x in (-4.5, 4.5):
            Entity(
                parent=self.root, model="cube",
                position=(x, y, south_z),
                scale=(3.2, 1.7, 0.1),
                color=color.rgb32(40, 45, 55),
            )
            Entity(
                parent=self.root, model="cube",
                position=(x, y, south_z + 0.06),
                scale=(3.0, 1.5, 0.02),
                color=color.rgb32(12, 16, 28),
            )
            Text(
                text="NEWS", parent=self.root,
                position=(x, y + 0.55, south_z + 0.07),
                rotation=(0, 180, 0),
                scale=5, origin=(0, 0),
                color=color.rgb32(220, 180, 90),
            )
            body = Text(
                text="(waiting for this season's news…)",
                parent=self.root,
                position=(x, y - 0.05, south_z + 0.07),
                rotation=(0, 180, 0),
                scale=3.6, origin=(0, 0),
                color=color.rgb32(220, 225, 235),
            )
            self.news_texts.append(body)

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

    def sync_state(self, me: Any, state: Any = None, *_: Any) -> None:
        if me is None:
            return
        self._sync_news(state)
        roster = me.astronauts
        for i, slot in enumerate(self.portraits):
            if i >= len(roster):
                slot["name"].text = "—"
                slot["status"].text = ""
                for s in slot["skills"]:
                    s.text = ""
                continue
            astro = roster[i]
            from baris.state import character_portrait
            _glyph, swatch_rgb = character_portrait(astro.name)
            # Panda3D's default font ships glyphs for ASCII only — the
            # brainrot portrait emoji (🐊 🦢 🪵 etc.) trip a per-frame
            # "No definition for character U+xxxxx" warning if used
            # raw. The swatch tint already conveys identity, so the
            # wall portrait drops the glyph and just shows the name
            # in the character's colour. Emoji still render in the
            # 2D portrait wall + the overlay roster panel where
            # pygame's font path supports them.
            slot["name"].text = astro.name
            slot["name"].color = color.rgb32(*swatch_rgb)
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

    def _sync_news(self, state: Any) -> None:
        """Update both NEWS TVs with the current season's headline. Wraps
        long headlines across a handful of lines because the screen is
        narrow in world units relative to Ursina Text scale."""
        from baris.client3d.text_utils import panda_safe
        headline = (
            getattr(state, "current_news", None)
            if state is not None else None
        )
        if not headline:
            headline = "(waiting for this season's news…)"
        # News headlines occasionally carry → / 📅 / non-ASCII;
        # Panda3D's font can't render them. Sanitise before wrapping.
        wrapped = _wrap_headline(panda_safe(headline), max_chars=28)
        for t in self.news_texts:
            t.text = wrapped

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

