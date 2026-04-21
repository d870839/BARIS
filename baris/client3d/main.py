"""First-pass 3D BARIS client built on Ursina.

This is the V1 slice: the player walks a first-person camera around a
tiny space-program facility with four labeled buildings. Walking near the
Mission Control tile and pressing E opens a UI panel that submits a pass
turn over the existing websocket protocol — proving the server and 3D
front-end can talk to each other before we invest in briefing / launch /
per-building interiors.

Everything game-logic side (state, resolver, protocol, NetClient) is
reused from the 2D client with no changes. Only the view layer is new.
"""
from __future__ import annotations

import argparse
import logging

from ursina import (
    Button,
    Entity,
    Text,
    Ursina,
    camera,
    color,
    destroy,
    mouse,
)
from ursina.prefabs.first_person_controller import FirstPersonController

from baris import protocol
from baris.client.net import NetClient
from baris.state import GameState, Phase

log = logging.getLogger("baris.client3d")


# Building layout — a plus-shape around a central plaza at the origin.
# For V1 only Mission Control is interactive. The other three are placed
# at matching slots so the facility feels like a real place; we'll wire
# their panels up in the next iteration.
# (id, label, (x, z), roof color, interactive)
BUILDINGS: tuple[tuple[str, str, tuple[float, float], object, bool], ...] = (
    ("mc",      "Mission Control",   (0.0,   20.0), color.rgb(240, 200, 90),  True),
    ("rd",      "R&D Complex",       (0.0,  -20.0), color.rgb(110, 200, 120), False),
    ("astro",   "Astronaut Complex", (20.0,   0.0), color.rgb(130, 160, 220), False),
    ("library", "Library",           (-20.0,  0.0), color.rgb(200, 170, 110), False),
)

INTERACT_RANGE = 8.0  # metres; walk within this of a building to trigger [E].


class BarisClient(Entity):
    """Game object that owns the scene and drives the network loop.

    Inheriting from Entity gives us Ursina's free per-frame `update()`
    and `input(key)` hooks — no need to plumb module-level functions.
    """

    def __init__(self, server_url: str, username: str) -> None:
        super().__init__()
        self.server_url = server_url
        self.username = username
        self.net = NetClient(server_url)
        self.net.start()

        self.state: GameState | None = None
        self.player_id: str | None = None
        self.joined_sent = False
        self.ready_sent = False

        self._build_scene()
        self._build_hud()
        self.panel: Entity | None = None

    # ------------------------------------------------------------------
    # Scene setup
    # ------------------------------------------------------------------
    def _build_scene(self) -> None:
        # Ground
        Entity(
            model="plane", scale=(120, 1, 120),
            color=color.rgb(40, 50, 70),
            texture="white_cube", texture_scale=(60, 60),
        )
        # Central plaza (slightly brighter)
        Entity(
            model="plane", scale=(20, 1, 20), y=0.01,
            color=color.rgb(70, 80, 100),
        )

        # Buildings — solid-colored cubes with a distinct roof slab.
        self.buildings: dict[str, Entity] = {}
        for bid, label, (x, z), roof_color, interactive in BUILDINGS:
            body = Entity(
                model="cube",
                position=(x, 3, z),
                scale=(7, 6, 7),
                color=color.rgb(90, 100, 130),
            )
            body._bid = bid
            body._interactive = interactive
            self.buildings[bid] = body
            # Roof tile (distinct color per building)
            Entity(
                parent=body, model="cube",
                scale=(1.05, 0.15, 1.05),
                y=0.5, color=roof_color,
            )
            # Floating sign above each building.
            Text(
                text=label,
                parent=body,
                y=1.2, scale=14,
                origin=(0, 0),
                billboard=True,
                color=color.white,
            )

        # Player (WASD + mouse look)
        self.player = FirstPersonController(
            position=(0, 2, -5),
            speed=8,
        )

    def _build_hud(self) -> None:
        self.status_text = Text(
            text="Connecting…",
            position=(-0.88, 0.47),
            scale=1.1,
            parent=camera.ui,
            color=color.white,
            background=True,
            background_color=color.rgba(0, 0, 0, 120),
        )
        self.prompt_text = Text(
            text="",
            position=(0, -0.32),
            origin=(0, 0),
            scale=1.8,
            parent=camera.ui,
            color=color.yellow,
        )

    # ------------------------------------------------------------------
    # Ursina hooks
    # ------------------------------------------------------------------
    def update(self) -> None:
        self._pump_network()
        self._update_prompt()

    def input(self, key: str) -> None:
        if key == "escape":
            if self.panel is not None:
                self._close_panel()
            return
        if key == "e":
            if self.panel is not None:
                return
            nearby = self._nearby_interactive_building()
            if nearby is not None and nearby._bid == "mc":
                self._open_mission_control_panel()

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------
    def _pump_network(self) -> None:
        if not self.net.connected.is_set():
            return
        if not self.joined_sent:
            self.net.send(protocol.JOIN, username=self.username)
            self.joined_sent = True
            self.status_text.text = "Joining…"
        for msg in self.net.drain_inbound():
            self._handle_message(msg)

    def _handle_message(self, msg: dict) -> None:
        mtype = msg.get("type")
        if mtype == protocol.JOINED:
            self.player_id = msg["player_id"]
            self.state = GameState.from_dict(msg["state"])
            # V1: auto-ready. Lets you jump straight into the 3D scene
            # without a lobby screen. If both sides auto-ready, the game
            # starts immediately.
            if not self.ready_sent:
                self.net.send(protocol.READY)
                self.ready_sent = True
        elif mtype == protocol.STATE:
            self.state = GameState.from_dict(msg["state"])
        elif mtype == protocol.ERROR:
            self.status_text.text = f"Error: {msg.get('message', '?')}"
        self._refresh_status()

    def _refresh_status(self) -> None:
        if self.state is None:
            return
        me = self._me()
        phase = self.state.phase.value
        if me is None:
            self.status_text.text = f"[{phase}] (no player)"
            return
        side = me.side.value if me.side else "?"
        turn = "submitted" if me.turn_submitted else "your turn"
        self.status_text.text = (
            f"[{phase.upper()}]  {self.state.season.value} {self.state.year}  |  "
            f"{me.username} [{side}]  Budget {me.budget} MB  Prestige {me.prestige}  "
            f"({turn})"
        )

    def _me(self):
        if self.state is None or self.player_id is None:
            return None
        return self.state.find_player(self.player_id)

    # ------------------------------------------------------------------
    # Proximity + interaction
    # ------------------------------------------------------------------
    def _nearby_interactive_building(self) -> Entity | None:
        if self.state is None or self.state.phase != Phase.PLAYING:
            return None
        px, _, pz = self.player.position
        closest: Entity | None = None
        closest_d = INTERACT_RANGE
        for ent in self.buildings.values():
            if not ent._interactive:
                continue
            d = ((px - ent.x) ** 2 + (pz - ent.z) ** 2) ** 0.5
            if d < closest_d:
                closest_d = d
                closest = ent
        return closest

    def _update_prompt(self) -> None:
        if self.panel is not None:
            self.prompt_text.text = ""
            return
        me = self._me()
        if me is None or self.state is None:
            self.prompt_text.text = ""
            return
        if self.state.phase != Phase.PLAYING:
            self.prompt_text.text = f"Lobby: waiting for game to start ({self.state.phase.value})"
            return
        if me.turn_submitted:
            self.prompt_text.text = "Turn submitted — waiting for opponent…"
            return
        nearby = self._nearby_interactive_building()
        if nearby is not None and nearby._bid == "mc":
            self.prompt_text.text = "[E] Enter Mission Control"
        else:
            self.prompt_text.text = ""

    # ------------------------------------------------------------------
    # Mission Control panel (V1 only submits a pass turn)
    # ------------------------------------------------------------------
    def _open_mission_control_panel(self) -> None:
        if self.state is None:
            return
        me = self._me()
        if me is None or me.turn_submitted:
            return

        # Release the FPS controller so the panel is clickable.
        self.player.enabled = False
        mouse.locked = False
        mouse.visible = True

        self.panel = Entity(parent=camera.ui)
        Entity(
            parent=self.panel, model="quad",
            color=color.rgb(20, 28, 48),
            scale=(0.6, 0.45),
        )
        Text(
            text="MISSION CONTROL",
            parent=self.panel,
            position=(0, 0.18),
            origin=(0, 0),
            scale=1.8, color=color.yellow,
        )
        body = (
            f"Season:    {self.state.season.value} {self.state.year}\n"
            f"Budget:    {me.budget} MB\n"
            f"Prestige:  {me.prestige}\n"
            f"Programs:  {self._summarize_programs(me)}\n\n"
            f"V1 only supports a 'pass' turn — no R&D, no launch.\n"
            f"Click SUBMIT to end the turn."
        )
        Text(
            text=body, parent=self.panel,
            position=(-0.28, 0.08),
            origin=(-0.5, 0.5),
            scale=1.0, color=color.white,
        )
        submit = Button(
            parent=self.panel, text="Submit Turn",
            position=(0, -0.1), scale=(0.26, 0.07),
            color=color.rgb(34, 44, 70),
            highlight_color=color.rgb(60, 80, 120),
        )
        submit.on_click = self._submit_and_close
        cancel = Button(
            parent=self.panel, text="Cancel [Esc]",
            position=(0, -0.2), scale=(0.2, 0.05),
            color=color.rgb(60, 70, 100),
        )
        cancel.on_click = self._close_panel

    def _summarize_programs(self, me) -> str:
        from baris.state import ProgramTier, program_name
        unlocked = [
            program_name(t, me.side)
            for t in (ProgramTier.ONE, ProgramTier.TWO, ProgramTier.THREE)
            if me.is_tier_unlocked(t)
        ]
        return ", ".join(unlocked) or "—"

    def _submit_and_close(self) -> None:
        self.net.send(protocol.END_TURN, rd_spend=0, launch=None, objectives=[])
        self._close_panel()

    def _close_panel(self) -> None:
        if self.panel is not None:
            destroy(self.panel)
            self.panel = None
        self.player.enabled = True
        mouse.locked = True
        mouse.visible = False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="ws://localhost:8765")
    parser.add_argument("--name", default="Player")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    app = Ursina(title="BARIS 3D — Race Into Space", borderless=False)
    BarisClient(args.server, args.name)
    app.run()


if __name__ == "__main__":
    main()
