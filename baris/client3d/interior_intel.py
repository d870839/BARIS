"""Intelligence Office interior — a small dim room with one big
dashboard wall showing the latest intelligence snapshot on the
opponent, and a REQUEST INTEL pedestal that triggers a new report
(costs INTEL_COST MB). Info-display everywhere else."""
from __future__ import annotations

from typing import Any

from ursina import Entity, Text, color, invoke

from baris.state import INTEL_COST, Module, Rocket, Side, rocket_display_name


ROOM_WIDTH = 14.0
ROOM_DEPTH = 12.0
ROOM_HEIGHT = 4.5
BUTTON_RANGE = 2.0


class IntelInterior:
    def __init__(
        self, origin: tuple[float, float, float] = (300.0, 0.0, -100.0),
    ) -> None:
        self.origin = origin
        self.root = Entity(position=origin)
        self.root.enabled = False

        self.buttons: dict[str, Entity] = {}
        self.dashboard_lines: list[Text] = []
        self.dashboard_title: Text | None = None
        self.status_text: Text | None = None

        self._build_room()
        self._build_dashboard()
        self._build_intel_console()
        self._build_sabotage_console()
        self._build_exit()

    def _build_room(self) -> None:
        half_w = ROOM_WIDTH / 2
        half_d = ROOM_DEPTH / 2
        Entity(
            parent=self.root, model="plane",
            scale=(ROOM_WIDTH, 1, ROOM_DEPTH),
            color=color.rgb32(80, 75, 90),
            texture="white_cube", texture_scale=(ROOM_WIDTH, ROOM_DEPTH),
            collider="box",
        )
        Entity(
            parent=self.root, model="cube",
            scale=(ROOM_WIDTH, 0.1, ROOM_DEPTH), y=ROOM_HEIGHT,
            color=color.rgb32(60, 60, 75),
        )
        wall = color.rgb32(90, 90, 110)
        # North
        Entity(
            parent=self.root, model="cube", collider="box",
            scale=(ROOM_WIDTH, ROOM_HEIGHT, 0.2),
            position=(0, ROOM_HEIGHT / 2, half_d), color=wall,
        )
        # West + East
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
        # South wall with doorway split (same pattern as every other interior).
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

    def _build_dashboard(self) -> None:
        """North wall = a big dark ops board with the latest report."""
        screen_y = ROOM_HEIGHT / 2 + 0.1
        z = ROOM_DEPTH / 2 - 0.12
        Entity(
            parent=self.root, model="cube",
            position=(0, screen_y, z), scale=(10.5, 3.4, 0.1),
            color=color.rgb32(40, 45, 55),
        )
        Entity(
            parent=self.root, model="cube",
            position=(0, screen_y, z - 0.06), scale=(10.1, 3.0, 0.02),
            color=color.rgb32(14, 18, 32),
        )
        self.dashboard_title = Text(
            text="INTELLIGENCE DESK",
            parent=self.root,
            position=(0, screen_y + 1.4, z - 0.08),
            scale=9, origin=(0, 0),
            color=color.rgb32(240, 200, 110),
        )
        # Pre-allocate body lines; sync_state fills them.
        top = screen_y + 0.95
        for i in range(10):
            t = Text(
                text="",
                parent=self.root,
                position=(-4.8, top - i * 0.22, z - 0.08),
                scale=4.2, origin=(-0.5, 0.5),
                color=color.rgb32(220, 225, 235),
            )
            self.dashboard_lines.append(t)

    def _build_intel_console(self) -> None:
        """Blue pedestal near the door — press E to spend INTEL_COST MB
        and request a fresh report."""
        z = -ROOM_DEPTH / 2 + 0.8
        x = -3.5
        Entity(
            parent=self.root, model="cube",
            position=(x, 0.45, z), scale=(1.1, 0.9, 1.1),
            color=color.rgb32(60, 80, 130),
            collider="box",
        )
        cap = Entity(
            parent=self.root, model="cube",
            position=(x, 1.0, z), scale=(0.7, 0.15, 0.7),
            color=color.rgb32(90, 130, 220),
        )
        cap._rest_y = cap.y
        self.buttons["intel"] = cap
        Text(
            text=f"REQUEST INTEL\n({INTEL_COST} MB)",
            parent=self.root,
            position=(x, 1.55, z), scale=4.2, origin=(0, 0),
            billboard=True,
            color=color.rgb32(200, 220, 255),
        )
        # Cost/status readout above the console, updated in sync_state.
        self.status_text = Text(
            text="",
            parent=self.root,
            position=(x, 2.2, z), scale=3.8, origin=(0, 0),
            billboard=True,
            color=color.rgb32(160, 170, 195),
        )

    def _build_sabotage_console(self) -> None:
        """Pedestal opposite the intel console, with a comically-sketchy
        red-purple cap. Press E to open the DIRTY TRICKS panel where
        you actually pick which sabotage card to fire."""
        z = -ROOM_DEPTH / 2 + 0.8
        x = 3.5
        Entity(
            parent=self.root, model="cube",
            position=(x, 0.45, z), scale=(1.1, 0.9, 1.1),
            color=color.rgb32(120, 50, 80),
            collider="box",
        )
        cap = Entity(
            parent=self.root, model="cube",
            position=(x, 1.0, z), scale=(0.7, 0.15, 0.7),
            color=color.rgb32(190, 70, 110),
        )
        cap._rest_y = cap.y
        self.buttons["sabotage"] = cap
        Text(
            text="DIRTY TRICKS",
            parent=self.root,
            position=(x, 1.55, z), scale=4.2, origin=(0, 0),
            billboard=True,
            color=color.rgb32(255, 200, 220),
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
        self._sync_dashboard(me)
        self._sync_status(me, state)

    def _sync_dashboard(self, me: Any) -> None:
        report = getattr(me, "latest_intel", None) if me is not None else None
        if report is None:
            self._write_lines([
                "(No intelligence has been gathered yet.)",
                "",
                f"Press E at the blue console to spend {INTEL_COST} MB",
                "on a snapshot of the opponent's program.",
                "",
                "Reports come back with reliability bands ±15%",
                "and an 80% chance the rumored next mission is",
                "accurate — sources sometimes get it wrong.",
            ])
            return
        opp_side = report.opponent_side or "?"
        opp_enum = None
        for s in (Side.USA, Side.USSR):
            if s.value == opp_side:
                opp_enum = s
        lines = [
            f"Report on {opp_side} — captured "
            f"{report.taken_season} {report.taken_year}",
            "",
        ]
        for rocket in Rocket:
            low, high = report.rocket_estimates.get(rocket.value, (0, 0))
            label = rocket_display_name(rocket, opp_enum)
            lines.append(f"  {label:<16} {low:>3}-{high:>3}%")
        for module in Module:
            low, high = report.rocket_estimates.get(module.value, (0, 0))
            lines.append(f"  {module.value:<16} {low:>3}-{high:>3}%")
        lines.append("")
        lines.append(f"Active crew: {report.active_crew_count}")
        if report.rumored_mission_name:
            lines.append(f"Rumored next: {report.rumored_mission_name}")
        else:
            lines.append("Rumored next: (sources disagree)")
        self._write_lines(lines)

    def _sync_status(self, me: Any, state: Any) -> None:
        if self.status_text is None:
            return
        if me is None or state is None:
            self.status_text.text = ""
            return
        from baris.resolver import intel_available
        ok, reason = intel_available(me, state)
        if ok:
            self.status_text.text = f"Ready — budget {me.budget} MB"
            self.status_text.color = color.rgb32(120, 200, 130)
        else:
            self.status_text.text = f"Unavailable — {reason}"
            self.status_text.color = color.rgb32(220, 180, 90)

    def _write_lines(self, lines: list[str]) -> None:
        for i, t in enumerate(self.dashboard_lines):
            t.text = lines[i] if i < len(lines) else ""

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
