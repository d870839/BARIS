"""Information panels for the 3D client: lobby, astronauts, library.

Each builder takes the BarisClient as first arg (so it can call back into
the client for actions like 'pick side' or 'close panel') and a pygame-
style `parent` Ursina Entity (usually camera.ui). Each returns the panel
root Entity; the client destroys that to close the panel."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ursina import Button, Entity, Text, color

from baris.state import (
    MISSIONS_BY_ID,
    MissionId,
    ProgramTier,
    Side,
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
    header = "{:<14}{:>8}{:>6}{:>9}{:>9}   {}".format(
        "Name", "Capsule", "EVA", "Endure", "Command", "Status"
    )
    Text(
        text=header, parent=root,
        position=(-0.4, 0.3), origin=(-0.5, 0.5),
        scale=0.9, color=color.rgb32(160, 170, 195),
    )
    y = 0.25
    for astro in me.astronauts:
        row = "{:<14}{:>8}{:>6}{:>9}{:>9}   {}".format(
            astro.name, astro.capsule, astro.eva, astro.endurance,
            astro.command, "active" if astro.active else "KIA",
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
