"""Mission Control interior — a walk-in ops floor. Layout:

- Central console: 3×4 grid of pedestals, one per MissionId. Disabled
  (dim red cap) when the mission isn't currently visible to the player;
  green with [X] prefix when queued.
- North wall: giant briefing TV summarising the queued mission.
- West wall: objective toggle pedestals (up to 5, only those belonging
  to the queued mission are enabled).
- East wall: architecture selector pedestals (LOR/DA/EOR/LSR), only
  enabled once Tier 3 unlocks and no architecture has been committed.
- South wall: doorway + EXIT pedestal.

Each press routes through BarisClient's existing mc_* methods, which
already guard against me.turn_submitted, so interactions lock during
waiting-on-opponent."""
from __future__ import annotations

from typing import Any

from ursina import Entity, Text, color, invoke

from baris.resolver import (
    effective_base_success,
    effective_lunar_modifier,
    effective_launch_cost,
    effective_rocket,
    visible_missions,
)
from baris.state import (
    ARCHITECTURE_FULL_NAMES,
    Architecture,
    MISSIONS,
    MISSIONS_BY_ID,
    MissionId,
    ObjectiveId,
    ProgramTier,
    RELIABILITY_SWING_PER_POINT,
    objectives_for,
    rocket_display_name,
)


ROOM_WIDTH = 22.0
ROOM_DEPTH = 18.0
ROOM_HEIGHT = 5.0
BUTTON_RANGE = 2.0

# Mission grid
MISSION_ROWS = 3
MISSION_COLS = 4
ROW_Z_OFFSET = 2.4
COL_X_OFFSET = 3.0

# All possible objectives in a fixed x-order on the west wall.
ALL_OBJECTIVES: tuple[ObjectiveId, ...] = (
    ObjectiveId.EVA,
    ObjectiveId.DOCKING,
    ObjectiveId.LONG_DURATION,
    ObjectiveId.MOONWALK,
    ObjectiveId.SAMPLE_RETURN,
)


def _tier_for(m) -> int:
    return int(m.tier.value)


class MCInterior:
    def __init__(self, origin: tuple[float, float, float] = (200.0, 0.0, 0.0)) -> None:
        self.origin = origin
        self.root = Entity(position=origin)
        self.root.enabled = False

        # Dynamic refs
        self.buttons: dict[str, Entity] = {}
        self._mission_caps: dict[str, Entity] = {}      # mission_id.value -> cap
        self._mission_labels: dict[str, Text] = {}      # mission_id.value -> label
        self._arch_caps: dict[str, Entity] = {}         # Architecture.value -> cap
        self._objective_caps: dict[str, Entity] = {}    # ObjectiveId.value -> cap
        self._objective_labels: dict[str, Text] = {}

        # Briefing TV text refs
        self.briefing_title: Text | None = None
        self.briefing_rocket: Text | None = None
        self.briefing_cost: Text | None = None
        self.briefing_base: Text | None = None
        self.briefing_crew: Text | None = None
        self.briefing_rel: Text | None = None
        self.briefing_effective: Text | None = None
        self.briefing_status: Text | None = None

        self._build_room()
        self._build_mission_grid()
        self._build_briefing_tv()
        self._build_objective_wall()
        self._build_arch_wall()
        self._build_exit()
        self._build_scrub_station()

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
        # Central console slab — pedestals sit on top of it.
        Entity(
            parent=self.root, model="cube",
            position=(0, 0.3, 0),
            scale=(12.0, 0.6, 8.0),
            color=color.rgb32(70, 75, 90),
            collider="box",
        )

    def _build_mission_grid(self) -> None:
        """3 rows × 4 cols of pedestals, assigned in MISSIONS order (Tier 1
        row, Tier 2 row, Tier 3 row). 12 slots, 11 missions, one empty."""
        missions = list(MISSIONS)
        # Group by tier so each tier lands on its own row.
        rows = [
            [m for m in missions if _tier_for(m) == 1],
            [m for m in missions if _tier_for(m) == 2],
            [m for m in missions if _tier_for(m) == 3],
        ]
        for r, row_missions in enumerate(rows):
            for c, m in enumerate(row_missions[:MISSION_COLS]):
                x = (c - (MISSION_COLS - 1) / 2) * COL_X_OFFSET
                z = (r - (MISSION_ROWS - 1) / 2) * ROW_Z_OFFSET
                # Pedestal base (on top of the console slab at y≈0.6).
                Entity(
                    parent=self.root, model="cube",
                    position=(x, 0.95, z),
                    scale=(0.9, 0.7, 0.9),
                    color=color.rgb32(110, 115, 130),
                    collider="box",
                )
                cap = Entity(
                    parent=self.root, model="cube",
                    position=(x, 1.35, z),
                    scale=(0.55, 0.16, 0.55),
                    color=color.rgb32(70, 75, 95),
                )
                cap._rest_y = cap.y
                bid = f"mission:{m.id.value}"
                self.buttons[bid] = cap
                self._mission_caps[m.id.value] = cap
                # Two-line label above the pedestal.
                lbl = Text(
                    text=m.name[:20],
                    parent=self.root,
                    position=(x, 1.55, z),
                    scale=4.5, origin=(0, 0),
                    billboard=True,
                    color=color.rgb32(220, 225, 235),
                )
                self._mission_labels[m.id.value] = lbl

    def _build_briefing_tv(self) -> None:
        """Giant status board on the north wall."""
        z = ROOM_DEPTH / 2 - 0.12
        y = 3.2
        # Frame + screen
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
        # Header
        Text(
            text="QUEUED MISSION",
            parent=self.root,
            position=(0, y + 1.15, z - 0.08),
            scale=7, origin=(0, 0),
            color=color.rgb32(240, 200, 90),
        )
        # Mission name (big)
        self.briefing_title = Text(
            text="(none)",
            parent=self.root,
            position=(0, y + 0.6, z - 0.08),
            scale=12, origin=(0, 0),
            color=color.rgb32(230, 230, 235),
        )
        # Stats grid: two columns of four rows each
        left_x = -4.6
        for i, attr in enumerate(("briefing_rocket", "briefing_cost",
                                  "briefing_base",   "briefing_crew")):
            t = Text(
                text="",
                parent=self.root,
                position=(left_x, y + 0.1 - i * 0.33, z - 0.08),
                scale=5, origin=(-0.5, 0.5),
                color=color.rgb32(220, 225, 235),
            )
            setattr(self, attr, t)
        right_x = 0.6
        for i, attr in enumerate(("briefing_rel", "briefing_effective",
                                  "briefing_status")):
            t = Text(
                text="",
                parent=self.root,
                position=(right_x, y + 0.1 - i * 0.33, z - 0.08),
                scale=5, origin=(-0.5, 0.5),
                color=color.rgb32(220, 225, 235),
            )
            setattr(self, attr, t)

    def _build_objective_wall(self) -> None:
        """West wall: five objective-toggle pedestals in a vertical column."""
        x = -ROOM_WIDTH / 2 + 0.6
        # Backdrop plinth
        Entity(
            parent=self.root, model="cube",
            position=(x, 0.5, 0), scale=(0.8, 1.0, 8.5),
            color=color.rgb32(85, 90, 105),
            collider="box",
        )
        Text(
            text="OBJECTIVES",
            parent=self.root,
            position=(x - 0.1, 2.8, 0), rotation=(0, 90, 0),
            scale=7, origin=(0, 0),
            color=color.rgb32(240, 200, 90),
        )
        spacing = 1.6
        start_z = -((len(ALL_OBJECTIVES) - 1) / 2) * spacing
        for i, obj_id in enumerate(ALL_OBJECTIVES):
            z = start_z + i * spacing
            cap = Entity(
                parent=self.root, model="cube",
                position=(x + 0.05, 1.1, z), scale=(0.5, 0.15, 0.9),
                color=color.rgb32(70, 75, 95),
            )
            cap._rest_y = cap.y
            bid = f"objective:{obj_id.value}"
            self.buttons[bid] = cap
            self._objective_caps[obj_id.value] = cap
            lbl = Text(
                text=obj_id.value.replace("_", " ").title(),
                parent=self.root,
                position=(x - 0.45, 1.1, z), rotation=(0, 90, 0),
                scale=4, origin=(0, 0),
                color=color.rgb32(220, 225, 235),
            )
            self._objective_labels[obj_id.value] = lbl

    def _build_arch_wall(self) -> None:
        """East wall: architecture selector."""
        x = ROOM_WIDTH / 2 - 0.6
        Entity(
            parent=self.root, model="cube",
            position=(x, 0.5, 0), scale=(0.8, 1.0, 7.0),
            color=color.rgb32(85, 90, 105),
            collider="box",
        )
        Text(
            text="ARCHITECTURE",
            parent=self.root,
            position=(x + 0.1, 2.8, 0), rotation=(0, -90, 0),
            scale=7, origin=(0, 0),
            color=color.rgb32(240, 200, 90),
        )
        specs = (Architecture.LOR, Architecture.DA, Architecture.EOR, Architecture.LSR)
        spacing = 1.6
        start_z = -((len(specs) - 1) / 2) * spacing
        for i, arch in enumerate(specs):
            z = start_z + i * spacing
            cap = Entity(
                parent=self.root, model="cube",
                position=(x - 0.05, 1.1, z), scale=(0.5, 0.15, 0.9),
                color=color.rgb32(70, 75, 95),
            )
            cap._rest_y = cap.y
            bid = f"arch:{arch.value}"
            self.buttons[bid] = cap
            self._arch_caps[arch.value] = cap
            Text(
                text=f"{arch.value}\n{ARCHITECTURE_FULL_NAMES[arch]}",
                parent=self.root,
                position=(x + 0.45, 1.1, z), rotation=(0, -90, 0),
                scale=3.5, origin=(0, 0),
                color=color.rgb32(220, 225, 235),
            )

    def _build_scrub_station(self) -> None:
        """A dedicated SCRUB pedestal just south of the console slab so
        the player can void a scheduled launch without having to swing
        over to the panel."""
        x = 4.0
        z = -3.6
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
            position=(x, 1.5, z),
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
        queued = client.queued_mission.value if (client and client.queued_mission) else None

        # Scrub pedestal cap: hot red when something's scheduled, dim red otherwise.
        scrub_cap = getattr(self, "_scrub_cap", None)
        if scrub_cap is not None:
            scrub_cap.color = (
                color.rgb32(220, 70, 70) if scheduled is not None
                else color.rgb32(80, 55, 55)
            )

        # Mission pedestals: if something is on the manifest, light only
        # that cap (amber for "scheduled, not green-queued"); every other
        # cap goes dim red since nothing else can be queued.
        visible_ids = {m.id.value for m in visible_missions(me)}
        for mid, cap in self._mission_caps.items():
            if scheduled_id is not None:
                if mid == scheduled_id:
                    cap.color = color.rgb32(240, 170, 60)
                else:
                    cap.color = color.rgb32(55, 40, 45)
                continue
            if mid == queued:
                cap.color = color.rgb32(70, 170, 90)
            elif mid in visible_ids:
                cap.color = color.rgb32(70, 75, 95)
            else:
                cap.color = color.rgb32(70, 40, 40)  # unavailable

        # Briefing TV — prefer the scheduled mission (next to fly) over
        # whatever the player may have been previewing with pending clicks.
        display_mid: str | None = None
        if scheduled_id is not None:
            display_mid = scheduled_id
        elif client and client.queued_mission is not None:
            display_mid = client.queued_mission.value
        if display_mid is not None:
            try:
                m = MISSIONS_BY_ID[MissionId(display_mid)]
            except (ValueError, KeyError):
                m = None
        else:
            m = None
        if m is not None:
            eff_rocket = effective_rocket(me, m)
            eff_cost = effective_launch_cost(me, m)
            base_s = effective_base_success(me, m)
            rel_bonus = (
                (me.rocket_reliability(eff_rocket) - 50) * RELIABILITY_SWING_PER_POINT
            )
            crew_b = 0.0
            if m.manned:
                crew_b = _crew_bonus_preview(me.active_astronauts(), m)
            recon_bonus, lm_penalty = effective_lunar_modifier(me, m)
            eff = base_s + crew_b + rel_bonus + recon_bonus - lm_penalty
            prefix = "SCHEDULED: " if scheduled_id is not None else ""
            self.briefing_title.text = prefix + m.name.upper()
            self.briefing_rocket.text = f"Rocket:  {rocket_display_name(eff_rocket, me.side)}"
            self.briefing_cost.text = f"Cost:    {eff_cost} MB"
            if recon_bonus > 0 or lm_penalty > 0:
                # Stash the base modifier line into the 'base' row for
                # the lunar landing so recon + LM penalty are visible.
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
            self.briefing_rel.text = f"Rel'ty:  {rel_bonus:+.3f}"
            self.briefing_effective.text = (
                f"EFFECTIVE  {eff:.2f}  (~{int(max(0, min(1, eff)) * 100)}%)"
            )
            if m.manned:
                self.briefing_effective.color = (
                    color.rgb32(110, 200, 120) if eff >= 0.6
                    else color.rgb32(240, 200, 90) if eff >= 0.4
                    else color.rgb32(220, 90, 90)
                )
            else:
                self.briefing_effective.color = color.rgb32(110, 200, 120)
            self.briefing_status.text = (
                "FIRST!" if m.id.value not in state.first_completed else ""
            )
        else:
            self.briefing_title.text = "(no mission queued)"
            for t in (
                self.briefing_rocket, self.briefing_cost, self.briefing_base,
                self.briefing_crew, self.briefing_rel, self.briefing_effective,
                self.briefing_status,
            ):
                if t is not None:
                    t.text = ""

        # Objective pedestals: enable those applicable to the queued
        # mission; disable (dim) the rest.
        allowed: set[str] = set()
        queued_objs: set[str] = set()
        if client is not None and client.queued_mission is not None:
            allowed = {o.id.value for o in objectives_for(client.queued_mission)}
            queued_objs = {o.value for o in client.queued_objectives}
        for oid, cap in self._objective_caps.items():
            if oid not in allowed:
                cap.color = color.rgb32(70, 40, 40)
            elif oid in queued_objs:
                cap.color = color.rgb32(70, 170, 90)
            else:
                cap.color = color.rgb32(70, 95, 75)
            lbl = self._objective_labels.get(oid)
            if lbl is not None:
                lbl.color = (
                    color.rgb32(220, 225, 235) if oid in allowed
                    else color.rgb32(140, 100, 100)
                )

        # Architecture pedestals.
        can_pick = me.is_tier_unlocked(ProgramTier.THREE) and me.architecture is None
        committed = me.architecture
        for arch_val, cap in self._arch_caps.items():
            if committed == arch_val:
                cap.color = color.rgb32(240, 200, 90)
            elif can_pick:
                cap.color = color.rgb32(70, 95, 75)
            else:
                cap.color = color.rgb32(60, 60, 70)

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


def _crew_bonus_preview(active: list, mission) -> float:
    """Mirror of resolver._crew_bonus using previewable data. Kept local so
    the interior can show the briefing without importing the private name."""
    from baris.state import CREW_MAX_BONUS, Skill
    if not mission.manned or mission.primary_skill is None:
        return 0.0
    if len(active) < mission.crew_size:
        return 0.0
    skill: Skill = mission.primary_skill
    ranked = sorted(active, key=lambda a: a.skill(skill), reverse=True)
    crew = ranked[:mission.crew_size]
    avg = sum(a.skill(skill) for a in crew) / len(crew)
    return (avg / 100.0) * CREW_MAX_BONUS
