"""Information panels for the 3D client: lobby, astronauts, library.

Each builder takes the BarisClient as first arg (so it can call back into
the client for actions like 'pick side' or 'close panel') and a pygame-
style `parent` Ursina Entity (usually camera.ui). Each returns the panel
root Entity; the client destroys that to close the panel."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ursina import Button, Entity, Text, color

from baris.state import (
    ADVANCED_TRAINING_COST,
    ADVANCED_TRAINING_SKILL_GAIN,
    ADVANCED_TRAINING_TURNS,
    MISSIONS_BY_ID,
    MissionId,
    ProgramTier,
    Side,
    Skill,
    program_name,
)

if TYPE_CHECKING:  # avoid circular import at runtime
    from baris.client3d.app import BarisClient


def _panel_shell(
    parent: Entity,
    title: str,
    width: float = 0.9,
    height: float = 0.8,
    title_color: tuple[int, int, int] = (240, 200, 90),
) -> tuple[Entity, float, float]:
    """Single dark background quad + title. No separate border quad —
    two overlapping quads at the same z z-fight and the panel flickers
    colors between frames. If we want a frame later, draw four thin
    strips around the edges instead of an outer-larger full quad.

    Returns (root, width, height) so the caller can place children
    relative to the panel size."""
    root = Entity(parent=parent)
    Entity(
        parent=root, model="quad",
        scale=(width, height),
        color=color.rgb32(18, 26, 44),
    )
    Text(
        text=title, parent=root,
        position=(0, height / 2 - 0.05),
        origin=(0, 0),
        scale=1.8, color=color.rgb32(*title_color),
    )
    return root, width, height


def _close_button(client: "BarisClient", parent: Entity, y: float) -> Button:
    btn = Button(
        parent=parent, text="Close [Esc]",
        position=(0, y), scale=(0.22, 0.05),
        color=color.rgb32(60, 70, 100),
    )
    btn.on_click = lambda: client.close_current_panel()
    return btn


# ----------------------------------------------------------------------
# Lobby
# ----------------------------------------------------------------------
def build_lobby_panel(client: "BarisClient", parent: Entity) -> Entity:
    """Shown while state.phase == LOBBY. Pick side, ready up.
    Not closable until both players ready and the server starts the game.
    """
    root, w, h = _panel_shell(parent, "BARIS — LOBBY", width=0.7, height=0.6)

    # Per-player status lines
    state = client.state
    me = client.me()
    y = 0.15
    if state is not None:
        for p in state.players:
            side = p.side.value if p.side else "?"
            ready = "READY" if p.ready else "not ready"
            tag = "  (you)" if me is not None and p.player_id == me.player_id else ""
            tint = color.rgb32(80, 140, 220) if p.side == Side.USA else (
                color.rgb32(220, 90, 90) if p.side == Side.USSR else color.rgb32(180, 180, 180)
            )
            Text(
                text=f"{p.username} [{side}]  —  {ready}{tag}",
                parent=root, position=(-0.3, y),
                origin=(-0.5, 0.5), scale=1.05,
                color=tint,
            )
            y -= 0.05
        if len(state.players) < 2:
            Text(
                text="Waiting for opponent to join…",
                parent=root, position=(0, y),
                origin=(0, 0), scale=1.0,
                color=color.rgb32(180, 180, 180),
            )

    # Side buttons — brighten the one that matches the player's current
    # side so the pick is obvious after the state broadcast lands.
    my_side = me.side if me is not None else None
    usa_selected = my_side == Side.USA
    ussr_selected = my_side == Side.USSR
    usa_btn = Button(
        parent=root,
        text=("[X] USA [1]" if usa_selected else "    USA [1]"),
        position=(-0.17, -0.05), scale=(0.22, 0.055),
        color=(color.rgb32(80, 140, 220) if usa_selected
               else color.rgb32(35, 50, 90)),
        highlight_color=color.rgb32(110, 170, 240),
    )
    usa_btn.on_click = lambda: client.lobby_pick_side("USA")
    ussr_btn = Button(
        parent=root,
        text=("[X] USSR [2]" if ussr_selected else "    USSR [2]"),
        position=(0.17, -0.05), scale=(0.22, 0.055),
        color=(color.rgb32(220, 90, 90) if ussr_selected
               else color.rgb32(90, 35, 35)),
        highlight_color=color.rgb32(240, 120, 120),
    )
    ussr_btn.on_click = lambda: client.lobby_pick_side("USSR")

    # Ready toggle
    ready_label = "Unready" if (me is not None and me.ready) else "Ready Up"
    ready_btn = Button(
        parent=root, text=f"{ready_label} [Enter]",
        position=(0, -0.15), scale=(0.3, 0.06),
        color=color.rgb32(50, 100, 60),
        highlight_color=color.rgb32(80, 150, 90),
    )
    ready_btn.on_click = lambda: client.lobby_toggle_ready()

    Text(
        text="The game starts the moment both players are READY on opposite sides.",
        parent=root, position=(0, -0.24),
        origin=(0, 0), scale=0.9,
        color=color.rgb32(140, 150, 170),
    )
    return root


# ----------------------------------------------------------------------
# Astronaut Complex
# ----------------------------------------------------------------------
def build_astro_panel(client: "BarisClient", parent: Entity) -> Entity:
    me = client.me()
    if me is None:
        root, _, _ = _panel_shell(parent, "ASTRONAUT COMPLEX")
        _close_button(client, root, -0.37)
        return root
    side = me.side.value if me.side else "?"
    root, w, h = _panel_shell(parent, f"ASTRONAUT COMPLEX  —  {side}")

    # Header row
    header = "{:<14}{:>8}{:>5}{:>5}{:>6}{:>8}   {}".format(
        "Name", "Capsule", "LM", "EVA", "Dock", "Endure", "Status"
    )
    Text(
        text=header, parent=root,
        position=(-0.4, 0.3), origin=(-0.5, 0.5),
        scale=0.9, color=color.rgb32(160, 170, 195),
    )
    y = 0.25
    for astro in me.astronauts:
        row = "{:<14}{:>8}{:>5}{:>5}{:>6}{:>8}   {}".format(
            astro.name, astro.capsule, astro.lm_pilot, astro.eva,
            astro.docking, astro.endurance,
            "active" if astro.active else "KIA",
        )
        Text(
            text=row, parent=root,
            position=(-0.4, y), origin=(-0.5, 0.5),
            scale=0.9,
            color=color.rgb32(220, 225, 235) if astro.active else color.rgb32(220, 90, 90),
        )
        y -= 0.04

    Text(
        text="Top-skilled active astronauts are auto-selected for manned missions.",
        parent=root, position=(0, -0.3),
        origin=(0, 0), scale=0.9,
        color=color.rgb32(140, 150, 170),
    )
    _close_button(client, root, -0.37)
    return root


# ----------------------------------------------------------------------
# Library (event log)
# ----------------------------------------------------------------------
def build_library_panel(client: "BarisClient", parent: Entity) -> Entity:
    root, w, h = _panel_shell(parent, "LIBRARY  —  FLIGHT RECORDS")
    if client.state is None:
        _close_button(client, root, -0.37)
        return root

    lines = list(client.state.log[-20:])
    y = 0.3
    if not lines:
        Text(
            text="(No events yet.)",
            parent=root, position=(0, 0),
            origin=(0, 0), scale=1.0,
            color=color.rgb32(180, 180, 180),
        )
    else:
        for line in lines:
            Text(
                text=line, parent=root,
                position=(-0.42, y), origin=(-0.5, 0.5),
                scale=0.85, color=color.rgb32(220, 225, 235),
            )
            y -= 0.033

    # Also summarise "firsts" for each player.
    firsts_y = -0.28
    for p in client.state.players:
        mine: list[str] = []
        for mid, holder in client.state.first_completed.items():
            if p.side and holder == p.side.value:
                try:
                    mine.append(MISSIONS_BY_ID[MissionId(mid)].name)
                except (ValueError, KeyError):
                    continue
        label = f"{p.username} [{p.side.value if p.side else '?'}]  firsts: "
        label += ", ".join(mine) if mine else "none yet"
        Text(
            text=label, parent=root,
            position=(-0.42, firsts_y), origin=(-0.5, 0.5),
            scale=0.9,
            color=color.rgb32(240, 200, 90) if mine else color.rgb32(140, 150, 170),
        )
        firsts_y -= 0.035

    _close_button(client, root, -0.37)
    return root


# ----------------------------------------------------------------------
# Helper: a "programs unlocked" summary, shared by several panels.
# ----------------------------------------------------------------------
def format_programs(me) -> str:
    unlocked = [
        program_name(t, me.side)
        for t in (ProgramTier.ONE, ProgramTier.TWO, ProgramTier.THREE)
        if me.is_tier_unlocked(t)
    ]
    return ", ".join(unlocked) or "—"


# ----------------------------------------------------------------------
# Advanced Training panel (opened from the Astronaut Complex console)
# ----------------------------------------------------------------------
def build_training_panel(client: "BarisClient", parent: Entity) -> Entity:
    me = client.me()
    root, w, h = _panel_shell(
        parent, "ADVANCED TRAINING",
        width=1.0, height=0.85, title_color=(130, 160, 220),
    )
    if me is None:
        _close_button(client, root, -0.4)
        return root

    Text(
        text=(
            f"Cost: {ADVANCED_TRAINING_COST} MB per astronaut.  "
            f"Takes {ADVANCED_TRAINING_TURNS} seasons.  "
            f"Completion: +{ADVANCED_TRAINING_SKILL_GAIN} in the chosen skill.  "
            f"Budget: {me.budget} MB."
        ),
        parent=root, position=(0, 0.36),
        origin=(0, 0), z=-0.01,
        scale=0.95, color=color.rgb32(220, 225, 235),
    )
    # Table header
    header = (
        f"{'Name':<12}{'CA':>4}{'LM':>4}{'EVA':>4}{'DO':>4}{'EN':>4}   Status"
    )
    Text(
        text=header, parent=root,
        position=(-0.45, 0.28),
        origin=(-0.5, 0.5), z=-0.01,
        scale=0.9, color=color.rgb32(160, 170, 195),
    )

    # For each astronaut: one info row + a row of train/cancel buttons.
    row_y = 0.23
    for astro in me.astronauts:
        skills_text = (
            f"{astro.name[:12]:<12}"
            f"{astro.capsule:>4}{astro.lm_pilot:>4}"
            f"{astro.eva:>4}{astro.docking:>4}{astro.endurance:>4}"
        )
        if not astro.active:
            status = "KIA"
            status_color = (220, 90, 90)
        elif astro.flight_ready:
            status = "ready"
            status_color = (110, 200, 120)
        else:
            status = astro.busy_reason
            status_color = (240, 200, 90)
        Text(
            text=skills_text, parent=root,
            position=(-0.45, row_y),
            origin=(-0.5, 0.5), z=-0.01,
            scale=0.88, color=color.rgb32(220, 225, 235),
        )
        Text(
            text=status, parent=root,
            position=(0.02, row_y),
            origin=(-0.5, 0.5), z=-0.01,
            scale=0.88, color=color.rgb32(*status_color),
        )
        # Action buttons: one per skill, or a CANCEL if already training.
        if astro.active:
            if astro.advanced_training_remaining > 0:
                btn = Button(
                    parent=root, text="CANCEL",
                    position=(0.38, row_y), scale=(0.13, 0.045),
                    color=color.rgb32(170, 60, 60),
                    highlight_color=color.rgb32(220, 90, 90),
                )
                btn.on_click = (lambda aid=astro.id:
                                client.astro_cancel_training(aid))
            elif astro.flight_ready:
                skill_specs = [
                    (Skill.CAPSULE, "CA"),
                    (Skill.LM_PILOT, "LM"),
                    (Skill.EVA, "EV"),
                    (Skill.DOCKING, "DO"),
                    (Skill.ENDURANCE, "EN"),
                ]
                start_x = 0.18
                for i, (skill, label) in enumerate(skill_specs):
                    btn = Button(
                        parent=root,
                        text=label,
                        position=(start_x + i * 0.065, row_y),
                        scale=(0.055, 0.04),
                        color=color.rgb32(45, 65, 95),
                        highlight_color=color.rgb32(80, 120, 180),
                    )
                    btn.on_click = (
                        lambda aid=astro.id, s=skill:
                            client.astro_start_training(aid, s)
                    )
        row_y -= 0.052

    _close_button(client, root, -0.4)
    return root
