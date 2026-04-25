"""Mission Control interior — a walk-in ops floor.

V2 layout (Phase L+):
  * North wall — giant briefing TV summarising the queued mission +
    which pad will receive it.
  * West wall — PAD STATUS dashboard (A / B / C, each with state
    + scheduled-mission name + repair countdown when damaged).
  * Centre — single MISSION SELECT console: press E to open the
    full mc panel for picking missions, toggling objectives, and
    committing an architecture. The panel handles every prereq
    constraint (only objectives belonging to the queued mission are
    selectable, architecture only appears at Tier 3, etc.).
  * South wall — SCRUB pedestal beside the EXIT.

The previous floor of mission/objective/architecture pedestals lived
here through phases A-K. It worked but was visually noisy — too many
pedestals competing for attention, and constraints (e.g. moonwalk
only on lunar landings) were communicated by dim red caps in a sea
of pedestals. The panel-driven menu is denser and the constraints
become invisible-by-default rather than disabled-and-visible."""
from __future__ import annotations

from typing import Any

from ursina import Entity, Text, color, invoke

from baris.resolver import (
    crew_compatibility_bonus,
    effective_base_success,
    effective_launch_cost,
    effective_lunar_modifier,
    effective_rocket,
)
from baris.state import (
    MISSIONS_BY_ID,
    MissionId,
    RELIABILITY_SWING_PER_POINT,
    rocket_display_name,
)


ROOM_WIDTH = 26.0
ROOM_DEPTH = 18.0
ROOM_HEIGHT = 5.0
BUTTON_RANGE = 2.0


class MCInterior:
    def __init__(self, origin: tuple[float, float, float] = (200.0, 0.0, 0.0)) -> None:
        self.origin = origin
        self.root = Entity(position=origin)
        self.root.enabled = False

        self.buttons: dict[str, Entity] = {}

        # Briefing TV refs
        self.briefing_title: Text | None = None
        self.briefing_rocket: Text | None = None
        self.briefing_cost: Text | None = None
        self.briefing_pad: Text | None = None
        self.briefing_base: Text | None = None
        self.briefing_crew: Text | None = None
        self.briefing_rel: Text | None = None
        self.briefing_effective: Text | None = None
        self.briefing_status: Text | None = None

        # Pad dashboard refs
        self._pad_status_rows: list[dict[str, Any]] = []

        self._build_room()
        self._build_briefing_tv()
        self._build_pad_dashboard()
        self._build_mission_console()
        self._build_scrub_station()
        self._build_exit()

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------
    def _build_room(self) -> None:
        half_w = ROOM_WIDTH / 2
        half_d = ROOM_DEPTH / 2
        Entity(
            parent=self.root, model="plane",
            scale=(ROOM_WIDTH, 1, ROOM_DEPTH),
            color=color.rgb32(165, 170, 180),
            texture="white_cube", texture_scale=(ROOM_WIDTH, ROOM_DEPTH),
            collider="box",
        )
        Entity(
            parent=self.root, model="cube",
            scale=(ROOM_WIDTH, 0.1, ROOM_DEPTH), y=ROOM_HEIGHT,
            color=color.rgb32(205, 205, 210),
        )
        wall = color.rgb32(235, 235, 240)
        # North
        Entity(
            parent=self.root, model="cube", collider="box",
            scale=(ROOM_WIDTH, ROOM_HEIGHT, 0.2),
            position=(0, ROOM_HEIGHT / 2, half_d), color=wall,
        )
        # West / East
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
        # South wall with doorway split
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

    def _build_briefing_tv(self) -> None:
        """Giant status board on the north wall — header, mission name,
        and a 2-column stat grid with rocket / cost / pad / base /
        crew / reliability / effective % / status."""
        z = ROOM_DEPTH / 2 - 0.12
        y = 3.2
        Entity(
            parent=self.root, model="cube",
            position=(0, y, z), scale=(12.0, 3.2, 0.1),
            color=color.rgb32(40, 45, 55),
        )
        Entity(
            parent=self.root, model="cube",
            position=(0, y, z - 0.06), scale=(11.6, 2.8, 0.02),
            color=color.rgb32(16, 22, 36),
        )
        Text(
            text="QUEUED MISSION",
            parent=self.root,
            position=(0, y + 1.15, z - 0.08),
            scale=7, origin=(0, 0),
            color=color.rgb32(240, 200, 90),
        )
        self.briefing_title = Text(
            text="(none)",
            parent=self.root,
            position=(0, y + 0.6, z - 0.08),
            scale=12, origin=(0, 0),
            color=color.rgb32(230, 230, 235),
        )
        left_x = -4.6
        for i, attr in enumerate((
            "briefing_rocket", "briefing_cost", "briefing_pad", "briefing_base",
        )):
            t = Text(
                text="",
                parent=self.root,
                position=(left_x, y + 0.1 - i * 0.33, z - 0.08),
                scale=5, origin=(-0.5, 0.5),
                color=color.rgb32(220, 225, 235),
            )
            setattr(self, attr, t)
        right_x = 0.6
        for i, attr in enumerate((
            "briefing_crew", "briefing_rel", "briefing_effective", "briefing_status",
        )):
            t = Text(
                text="",
                parent=self.root,
                position=(right_x, y + 0.1 - i * 0.33, z - 0.08),
                scale=5, origin=(-0.5, 0.5),
                color=color.rgb32(220, 225, 235),
            )
            setattr(self, attr, t)

    def _build_pad_dashboard(self) -> None:
        """West wall: live readout of all three launch pads. Each row
        gets its own dark plate with a coloured status lamp on the left
        and three text lines (label / state / scheduled mission)."""
        wall_x = -ROOM_WIDTH / 2 + 0.14
        # Backdrop plate.
        Entity(
            parent=self.root, model="cube",
            position=(wall_x, 2.4, 0), scale=(0.1, 4.0, 9.0),
            color=color.rgb32(40, 45, 55),
        )
        Entity(
            parent=self.root, model="cube",
            position=(wall_x + 0.06, 2.4, 0), scale=(0.02, 3.6, 8.6),
            color=color.rgb32(16, 22, 36),
        )
        Text(
            text="LAUNCH PADS",
            parent=self.root,
            position=(wall_x + 0.1, 4.0, 0), rotation=(0, 90, 0),
            scale=7, origin=(0, 0),
            color=color.rgb32(240, 200, 110),
        )
        # Three rows for A / B / C, evenly spaced down the wall.
        for i, pad_label in enumerate(("A", "B", "C")):
            row_y = 3.0 - i * 1.05
            lamp = Entity(
                parent=self.root, model="cube",
                position=(wall_x + 0.1, row_y, -3.0),
                rotation=(0, 90, 0),
                scale=(0.5, 0.5, 0.05),
                color=color.rgb32(110, 200, 120),  # default green / idle
            )
            label = Text(
                text=f"PAD {pad_label}",
                parent=self.root,
                position=(wall_x + 0.1, row_y + 0.25, -2.0),
                rotation=(0, 90, 0),
                scale=6, origin=(-0.5, 0.5),
                color=color.rgb32(240, 240, 245),
            )
            state_line = Text(
                text="",
                parent=self.root,
                position=(wall_x + 0.1, row_y - 0.05, -2.0),
                rotation=(0, 90, 0),
                scale=4, origin=(-0.5, 0.5),
                color=color.rgb32(180, 190, 210),
            )
            mission_line = Text(
                text="",
                parent=self.root,
                position=(wall_x + 0.1, row_y - 0.32, -2.0),
                rotation=(0, 90, 0),
                scale=4, origin=(-0.5, 0.5),
                color=color.rgb32(220, 225, 235),
            )
            self._pad_status_rows.append({
                "lamp": lamp,
                "label": label,
                "state": state_line,
                "mission": mission_line,
            })

    def _build_mission_console(self) -> None:
        """Single tall console in the centre of the floor. Press E to
        open the full mission-control panel — pick a mission, toggle
        objectives, commit an architecture."""
        x = 0.0
        z = -1.0
        Entity(
            parent=self.root, model="cube",
            position=(x, 0.7, z), scale=(2.0, 1.4, 1.4),
            color=color.rgb32(60, 70, 95),
            collider="box",
        )
        cap = Entity(
            parent=self.root, model="cube",
            position=(x, 1.5, z), scale=(1.5, 0.18, 1.0),
            color=color.rgb32(110, 170, 220),
        )
        cap._rest_y = cap.y
        self.buttons["mc_panel"] = cap
        Text(
            text="MISSION SELECT",
            parent=self.root,
            position=(x, 2.4, z), scale=7, origin=(0, 0),
            billboard=True,
            color=color.rgb32(220, 235, 250),
        )
        Text(
            text="press E to open the menu",
            parent=self.root,
            position=(x, 2.0, z), scale=4.5, origin=(0, 0),
            billboard=True,
            color=color.rgb32(160, 175, 195),
        )

    def _build_scrub_station(self) -> None:
        """Dedicated SCRUB pedestal east of the doorway; cap goes hot
        red when something's actually scheduled, dim red otherwise."""
        x = 4.0
        z = -ROOM_DEPTH / 2 + 0.9
        Entity(
            parent=self.root, model="cube",
            position=(x, 0.45, z), scale=(0.9, 0.9, 0.9),
            color=color.rgb32(90, 55, 55),
            collider="box",
        )
        cap = Entity(
            parent=self.root, model="cube",
            position=(x, 1.0, z), scale=(0.55, 0.15, 0.55),
            color=color.rgb32(90, 55, 55),
        )
        cap._rest_y = cap.y
        self.buttons["scrub"] = cap
        self._scrub_cap = cap
        Text(
            text="SCRUB\nSCHEDULED",
            parent=self.root,
            position=(x, 1.55, z),
            scale=4.2, origin=(0, 0),
            billboard=True,
            color=color.rgb32(240, 200, 200),
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

    def sync_state(self, me: Any, state: Any, client: Any = None) -> None:
        if me is None or state is None:
            return
        scheduled = getattr(me, "scheduled_launch", None)
        scheduled_id = scheduled.mission_id if scheduled is not None else None

        # Scrub pedestal cap recolour.
        scrub_cap = getattr(self, "_scrub_cap", None)
        if scrub_cap is not None:
            scrub_cap.color = (
                color.rgb32(220, 70, 70) if scheduled is not None
                else color.rgb32(80, 55, 55)
            )

        self._sync_briefing(me, state, client, scheduled_id)
        self._sync_pad_dashboard(me)

    def _sync_briefing(
        self, me: Any, state: Any, client: Any, scheduled_id: str | None,
    ) -> None:
        # Prefer the scheduled mission (next to fly) over whatever the
        # player's previewing in the open MC panel.
        display_mid: str | None = None
        if scheduled_id is not None:
            display_mid = scheduled_id
        elif client and client.queued_mission is not None:
            display_mid = client.queued_mission.value
        m = None
        if display_mid is not None:
            try:
                m = MISSIONS_BY_ID[MissionId(display_mid)]
            except (ValueError, KeyError):
                m = None
        if m is None:
            self.briefing_title.text = "(no mission queued)"
            for t in (
                self.briefing_rocket, self.briefing_cost, self.briefing_pad,
                self.briefing_base, self.briefing_crew, self.briefing_rel,
                self.briefing_effective, self.briefing_status,
            ):
                if t is not None:
                    t.text = ""
            return

        eff_rocket = effective_rocket(me, m)
        eff_cost = effective_launch_cost(me, m)
        base_s = effective_base_success(me, m)
        rel_bonus = (
            (me.rocket_reliability(eff_rocket) - 50) * RELIABILITY_SWING_PER_POINT
        )
        crew_b = 0.0
        compat_b = 0.0
        if m.manned:
            preview = _preview_crew_selection(me.active_astronauts(), m)
            if preview:
                crew_b = _crew_bonus_from(preview, m)
                compat_b = crew_compatibility_bonus(preview)
        recon_bonus, lm_penalty = effective_lunar_modifier(me, m)
        eff = base_s + crew_b + compat_b + rel_bonus + recon_bonus - lm_penalty

        prefix = "SCHEDULED: " if scheduled_id is not None else ""
        self.briefing_title.text = prefix + m.name.upper()
        self.briefing_rocket.text = (
            f"Rocket:  {rocket_display_name(eff_rocket, me.side)}"
        )
        self.briefing_cost.text = f"Cost:    {eff_cost} MB"
        # Pad assignment line — if a mission is already scheduled it tells
        # you which pad's holding it; otherwise it previews where the
        # currently-queued mission would land.
        if scheduled_id is not None:
            holding_pad = next(
                (p for p in me.pads
                 if p.scheduled_launch is not None
                 and p.scheduled_launch.mission_id == scheduled_id),
                None,
            )
            pad_id = holding_pad.pad_id if holding_pad else "?"
            self.briefing_pad.text = f"Pad:     {pad_id} (assembled)"
            self.briefing_pad.color = color.rgb32(240, 200, 90)
        else:
            next_pad = me.available_pad()
            if next_pad is not None:
                self.briefing_pad.text = f"Pad:     {next_pad.pad_id} (next free)"
                self.briefing_pad.color = color.rgb32(220, 225, 235)
            else:
                self.briefing_pad.text = "Pad:     ALL BUSY — won't fly"
                self.briefing_pad.color = color.rgb32(220, 90, 90)
        if recon_bonus > 0 or lm_penalty > 0:
            self.briefing_base.text = (
                f"Base:    {base_s:+.2f}   Recon {recon_bonus:+.3f}"
            )
            self.briefing_crew.text = (
                f"Crew:    {crew_b:+.2f}   LM {-lm_penalty:+.3f}"
            )
        else:
            self.briefing_base.text = f"Base:    {base_s:+.2f}"
            self.briefing_crew.text = (
                f"Crew:    {crew_b:+.2f}" if m.manned else "Crew:    —"
            )
        if compat_b:
            self.briefing_crew.text += f"   Cmpt {compat_b:+.3f}"
        self.briefing_rel.text = f"Rel'ty:  {rel_bonus:+.3f}"
        self.briefing_effective.text = (
            f"EFF  {eff:.2f}  (~{int(max(0, min(1, eff)) * 100)}%)"
        )
        if m.manned:
            self.briefing_effective.color = (
                color.rgb32(110, 200, 120) if eff >= 0.6
                else color.rgb32(240, 200, 90) if eff >= 0.4
                else color.rgb32(220, 90, 90)
            )
        else:
            self.briefing_effective.color = color.rgb32(110, 200, 120)
        from baris.resolver import missing_modules
        missing_mods = missing_modules(me, m)
        if missing_mods:
            self.briefing_status.text = (
                "NEED: " + " + ".join(mod.value for mod in missing_mods)
            )
            self.briefing_status.color = color.rgb32(220, 90, 90)
        elif m.id.value not in state.first_completed:
            self.briefing_status.text = "FIRST!"
            self.briefing_status.color = color.rgb32(240, 200, 90)
        else:
            self.briefing_status.text = ""

    def _sync_pad_dashboard(self, me: Any) -> None:
        """Walk the player's three pads in order and recolour the lamp
        and update the two text lines for each one."""
        for i, row in enumerate(self._pad_status_rows):
            if i >= len(me.pads):
                row["state"].text = ""
                row["mission"].text = ""
                row["lamp"].color = color.rgb32(80, 80, 100)
                continue
            pad = me.pads[i]
            if pad.damaged:
                row["lamp"].color = color.rgb32(220, 80, 80)
                row["state"].text = (
                    f"REPAIR — {pad.repair_turns_remaining} season"
                    f"{'s' if pad.repair_turns_remaining != 1 else ''} left"
                )
                row["state"].color = color.rgb32(220, 130, 130)
                row["mission"].text = ""
            elif pad.scheduled_launch is not None:
                row["lamp"].color = color.rgb32(240, 200, 90)
                row["state"].text = "ASSEMBLED — flies next turn"
                row["state"].color = color.rgb32(240, 200, 90)
                try:
                    name = MISSIONS_BY_ID[MissionId(
                        pad.scheduled_launch.mission_id
                    )].name
                except (ValueError, KeyError):
                    name = pad.scheduled_launch.mission_id
                row["mission"].text = name
                row["mission"].color = color.rgb32(220, 225, 235)
            else:
                row["lamp"].color = color.rgb32(110, 200, 120)
                row["state"].text = "IDLE — ready to receive"
                row["state"].color = color.rgb32(160, 200, 170)
                row["mission"].text = ""

    def nearby_button(self, world_xz: tuple[float, float]) -> str | None:
        if not self.root.enabled:
            return None
        ox, _, oz = self.origin
        px, pz = world_xz
        closest: str | None = None
        closest_d = BUTTON_RANGE
        for bid, cap in self.buttons.items():
            d = ((px - (ox + cap.x)) ** 2 + (pz - (oz + cap.z)) ** 2) ** 0.5
            if d < closest_d:
                closest_d = d
                closest = bid
        return closest

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


def _preview_crew_selection(active: list, mission) -> list:
    """Pick the top-skilled crew the resolver would select for this mission."""
    if not mission.manned or mission.primary_skill is None:
        return []
    if len(active) < mission.crew_size:
        return []
    ranked = sorted(active, key=lambda a: a.skill(mission.primary_skill), reverse=True)
    return ranked[:mission.crew_size]


def _crew_bonus_from(crew: list, mission) -> float:
    from baris.state import CREW_MAX_BONUS
    if not crew or mission.primary_skill is None:
        return 0.0
    avg = sum(a.skill(mission.primary_skill) for a in crew) / len(crew)
    return (avg / 100.0) * CREW_MAX_BONUS
