"""BarisClient — the Ursina Entity that owns the 3D scene, drives the
network loop, and dispatches panel-open / launch-animation events.

Keeps no game logic of its own; everything flows through the existing
NetClient + server + GameState pipeline."""
from __future__ import annotations

import logging
from typing import Any

from ursina import (
    AmbientLight,
    DirectionalLight,
    Entity,
    Sky,
    Text,
    camera,
    color,
    curve,
    destroy,
    invoke,
    mouse,
)
from ursina.prefabs.first_person_controller import FirstPersonController

from baris import protocol
from baris.client.net import NetClient
from baris.client3d import launch as launch_scene
from baris.client3d import panels_action, panels_info
from baris.state import (
    Architecture,
    GameState,
    LaunchReport,
    MISSIONS_BY_ID,
    MissionId,
    Module,
    ObjectiveId,
    Phase,
    Rocket,
    Side,
    objectives_for,
)

log = logging.getLogger("baris.client3d")


# (id, label, (x, z), roof color, interactive)
# NASA-era roof accents: saturated Space-Race palette against white bodies.
BUILDINGS: tuple[tuple[str, str, tuple[float, float], Any, bool], ...] = (
    ("mc",      "Mission Control",   (0.0,   20.0), color.rgb(240, 130,  50), True),   # NASA orange
    ("rd",      "R&D Complex",       (0.0,  -20.0), color.rgb( 60, 150,  90), True),   # lab green
    ("astro",   "Astronaut Complex", (20.0,   0.0), color.rgb( 40, 100, 200), True),   # sky blue
    ("library", "Library",           (-20.0,  0.0), color.rgb(200, 170, 110), True),   # archive tan
)

INTERACT_RANGE = 8.0


class BarisClient(Entity):
    def __init__(self, server_url: str, username: str) -> None:
        super().__init__()
        self.server_url = server_url
        self.username = username
        self.net = NetClient(server_url)
        self.net.start()

        self.state: GameState | None = None
        self.player_id: str | None = None
        self.joined_sent = False

        # Pending-turn selections mirrored from the 2D client semantics.
        self.rd_target: str | None = None     # Rocket.value or Module.value
        self.rd_spend: int = 10
        self.queued_mission: MissionId | None = None
        self.queued_objectives: set[ObjectiveId] = set()

        # Launch-sequence playback state.
        self.report_queue: list[LaunchReport] = []
        self.report_idx: int = 0
        self.launch_phase: str = "idle"   # idle | ascend | result
        self._consumed_launch_sig: tuple | None = None

        # Panel tracking.
        self.panel: Entity | None = None
        self.panel_id: str | None = None
        # True once the lobby panel has auto-opened for this game.
        self._lobby_opened = False

        self._build_scene()
        self._build_hud()

    # ------------------------------------------------------------------
    # Scene
    # ------------------------------------------------------------------
    def _build_scene(self) -> None:
        # Sky + basic lighting so the cubes read as 3D instead of flat
        # silhouettes. Sun is high + slightly from the south for a Florida
        # launch-complex feel; ambient keeps shadows from going full-black.
        Sky(color=color.rgb(130, 180, 225))
        AmbientLight(color=color.rgba(150, 150, 160, 255))
        sun = DirectionalLight(shadows=False)
        sun.look_at((0.3, -0.9, 0.4))

        # Ground — concrete apron, with a collider so the FPC doesn't fall
        # through. `texture_scale` tiles the built-in white_cube texture so
        # the eye can pick up movement across the apron.
        Entity(
            model="plane", scale=(160, 1, 160),
            color=color.rgb(180, 180, 190),
            texture="white_cube", texture_scale=(80, 80),
            collider="box",
        )
        # Central plaza — slightly warmer concrete with a ring of paving.
        Entity(
            model="plane", scale=(26, 1, 26), y=0.02,
            color=color.rgb(210, 205, 195),
            texture="white_cube", texture_scale=(13, 13),
        )
        # Painted taxi lines from the plaza out to each building (thin
        # low-lying rectangles so they read as striping without a texture).
        for (x, z) in ((0, 14), (0, -14), (14, 0), (-14, 0)):
            Entity(
                model="cube",
                position=(x * 0.5, 0.03, z * 0.5),
                scale=(1.0 if z == 0 else 0.5, 0.02, 1.0 if x == 0 else 0.5),
                color=color.rgb(240, 225, 120),
            )

        self.buildings: dict[str, Entity] = {}
        for bid, label, (x, z), roof, interactive in BUILDINGS:
            # White NASA-facility body.
            body = Entity(
                model="cube", position=(x, 3, z),
                scale=(7, 6, 7), color=color.rgb(245, 245, 248),
            )
            body._bid = bid
            body._interactive = interactive
            self.buildings[bid] = body
            # Roof slab — saturated accent so each building is identifiable
            # at a glance from across the complex.
            Entity(
                parent=body, model="cube",
                scale=(1.05, 0.18, 1.05),
                y=0.5, color=roof,
            )
            # Trim strip between roof and body (a faint shadow line).
            Entity(
                parent=body, model="cube",
                scale=(1.02, 0.03, 1.02),
                y=0.4, color=color.rgb(180, 185, 200),
            )
            # Tiny ground-level doorway stripe on the player-facing side.
            Entity(
                parent=body, model="cube",
                scale=(0.25, 0.4, 0.01),
                y=-0.35, z=-0.505,
                color=color.rgb(60, 70, 90),
            )
            # Floating sign: smaller so the building is the focal point.
            Text(
                text=label, parent=body,
                y=1.05, scale=4,
                origin=(0, 0), billboard=True,
                color=color.rgb(30, 35, 45),
                background=True,
                background_color=color.rgba(255, 255, 255, 200),
            )
        # Launch pad + rocket
        self.pad = launch_scene.build_launch_pad()
        self.rocket = launch_scene.build_rocket()
        self.flame = launch_scene.build_exhaust_flame(self.rocket)

        self.player = FirstPersonController(position=(0, 2, -5), speed=8)

    def _build_hud(self) -> None:
        self.status_text = Text(
            text="Connecting…",
            position=(-0.88, 0.47), scale=1.05,
            parent=camera.ui, color=color.white,
            background=True,
            background_color=color.rgba(0, 0, 0, 130),
        )
        self.prompt_text = Text(
            text="", position=(0, -0.32),
            origin=(0, 0), scale=1.8,
            parent=camera.ui, color=color.yellow,
        )

    # ------------------------------------------------------------------
    # Ursina hooks
    # ------------------------------------------------------------------
    def update(self) -> None:
        self._pump_network()
        self._update_prompt()

    def input(self, key: str) -> None:
        if self.panel_id == "result" and key in ("space", "enter", "escape"):
            self.advance_result_panel()
            return
        if self.launch_phase == "ascend" and key in ("space", "enter"):
            self._skip_ascend()
            return
        if key == "escape":
            if self.panel_id not in (None, "lobby"):
                self.close_current_panel()
            return
        if key == "1" and self.panel_id == "lobby":
            self.lobby_pick_side("USA")
            return
        if key == "2" and self.panel_id == "lobby":
            self.lobby_pick_side("USSR")
            return
        if key == "enter" and self.panel_id == "lobby":
            self.lobby_toggle_ready()
            return
        if key == "enter" and self.panel_id == "mc":
            self.mc_submit_turn()
            return
        if key == "e" and self.panel is None:
            nearby = self._nearby_interactive_building()
            if nearby is not None:
                self._open_panel(nearby._bid)

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
        elif mtype == protocol.STATE:
            self.state = GameState.from_dict(msg["state"])
            self._maybe_auto_open_lobby()
            self._maybe_start_launch_sequence()
            self._maybe_close_lobby_on_start()
        elif mtype == protocol.ERROR:
            self.status_text.text = f"Error: {msg.get('message', '?')}"
        self._refresh_status()

    def _refresh_status(self) -> None:
        if self.state is None:
            return
        me = self.me()
        phase = self.state.phase.value
        if me is None:
            self.status_text.text = f"[{phase}] (no player)"
            return
        side = me.side.value if me.side else "?"
        turn = "submitted" if me.turn_submitted else "your turn"
        self.status_text.text = (
            f"[{phase.upper()}]  {self.state.season.value} {self.state.year}  |  "
            f"{me.username} [{side}]  Budget {me.budget} MB  "
            f"Prestige {me.prestige}  ({turn})"
        )

    def me(self):
        if self.state is None or self.player_id is None:
            return None
        return self.state.find_player(self.player_id)

    # ------------------------------------------------------------------
    # Proximity / prompts
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
        if self.panel is not None or self.launch_phase != "idle":
            self.prompt_text.text = ""
            return
        me = self.me()
        if me is None or self.state is None:
            return
        if self.state.phase == Phase.LOBBY:
            self.prompt_text.text = "Lobby open — pick a side and ready up"
            return
        if me.turn_submitted:
            self.prompt_text.text = "Turn submitted — waiting for opponent…"
            return
        nearby = self._nearby_interactive_building()
        if nearby is not None:
            labels = {b[0]: b[1] for b in BUILDINGS}
            self.prompt_text.text = f"[E] Enter {labels[nearby._bid]}"
        else:
            self.prompt_text.text = ""

    # ------------------------------------------------------------------
    # Panel management
    # ------------------------------------------------------------------
    def _open_panel(self, panel_id: str, *, report: LaunchReport | None = None) -> None:
        self._close_panel_silent()
        self.panel_id = panel_id
        if panel_id == "lobby":
            self.panel = panels_info.build_lobby_panel(self, camera.ui)
        elif panel_id == "mc":
            self.panel = panels_action.build_mc_panel(self, camera.ui)
        elif panel_id == "rd":
            self.panel = panels_action.build_rd_panel(self, camera.ui)
        elif panel_id == "astro":
            self.panel = panels_info.build_astro_panel(self, camera.ui)
        elif panel_id == "library":
            self.panel = panels_info.build_library_panel(self, camera.ui)
        elif panel_id == "result" and report is not None:
            self.panel = panels_action.build_result_panel(self, camera.ui, report)
        self._enter_ui_mode()

    def close_current_panel(self) -> None:
        """Public: callable from panel buttons. Lobby panel can't be closed
        manually — the server must transition the phase first."""
        if self.panel_id == "lobby":
            return
        self._close_panel_silent()
        self._exit_ui_mode()

    def _close_panel_silent(self) -> None:
        if self.panel is not None:
            destroy(self.panel)
        self.panel = None
        self.panel_id = None

    def _enter_ui_mode(self) -> None:
        self.player.enabled = False
        mouse.locked = False
        mouse.visible = True

    def _exit_ui_mode(self) -> None:
        self.player.enabled = True
        mouse.locked = True
        mouse.visible = False

    def _refresh_current_panel(self) -> None:
        """Some actions (side pick, ready toggle, target change, queue change)
        update state the panel displays. Cheapest correct thing is to rebuild."""
        if self.panel_id is None:
            return
        current = self.panel_id
        self._close_panel_silent()
        self._open_panel(current)

    # ------------------------------------------------------------------
    # Lobby actions
    # ------------------------------------------------------------------
    def _maybe_auto_open_lobby(self) -> None:
        if (
            self.state is not None
            and self.state.phase == Phase.LOBBY
            and self.panel_id is None
        ):
            self._open_panel("lobby")
            self._lobby_opened = True

    def _maybe_close_lobby_on_start(self) -> None:
        if (
            self.state is not None
            and self.state.phase == Phase.PLAYING
            and self.panel_id == "lobby"
        ):
            self._close_panel_silent()
            self._exit_ui_mode()

    def lobby_pick_side(self, side: str) -> None:
        self.net.send(protocol.CHOOSE_SIDE, side=side)
        # refresh to show highlight; real state will arrive shortly
        self._refresh_current_panel()

    def lobby_toggle_ready(self) -> None:
        me = self.me()
        ready = bool(me and me.ready)
        self.net.send(protocol.UNREADY if ready else protocol.READY)
        self._refresh_current_panel()

    # ------------------------------------------------------------------
    # R&D actions
    # ------------------------------------------------------------------
    def rd_set_target(self, value: str) -> None:
        self.rd_target = value
        self._refresh_current_panel()

    def rd_change_spend(self, delta: int) -> None:
        me = self.me()
        ceiling = me.budget if me is not None else 999
        self.rd_spend = max(0, min(ceiling, self.rd_spend + delta))
        self._refresh_current_panel()

    # ------------------------------------------------------------------
    # Mission Control actions
    # ------------------------------------------------------------------
    def mc_select_mission(self, mission_id: MissionId) -> None:
        if self.queued_mission == mission_id:
            self.queued_mission = None
            self.queued_objectives.clear()
        else:
            self.queued_mission = mission_id
            # Drop any objectives that don't apply to the new mission.
            allowed = {o.id for o in objectives_for(mission_id)}
            self.queued_objectives = {o for o in self.queued_objectives if o in allowed}
        self._refresh_current_panel()

    def mc_toggle_objective(self, obj_id: ObjectiveId) -> None:
        if obj_id in self.queued_objectives:
            self.queued_objectives.discard(obj_id)
        else:
            self.queued_objectives.add(obj_id)
        self._refresh_current_panel()

    def mc_choose_architecture(self, arch: Architecture) -> None:
        self.net.send(protocol.CHOOSE_ARCHITECTURE, architecture=arch.value)
        self._refresh_current_panel()

    def mc_submit_turn(self) -> None:
        me = self.me()
        if me is None or me.turn_submitted:
            return
        payload: dict[str, Any] = {
            "rd_spend": min(self.rd_spend, me.budget),
            "launch": self.queued_mission.value if self.queued_mission else None,
            "objectives": [o.value for o in self.queued_objectives],
        }
        # rd_target may be a Rocket.value or Module.value.
        if self.rd_target in (m.value for m in Module):
            payload["rd_module"] = self.rd_target
        elif self.rd_target in (r.value for r in Rocket):
            payload["rd_rocket"] = self.rd_target
        self.net.send(protocol.END_TURN, **payload)
        self.queued_mission = None
        self.queued_objectives.clear()
        self._close_panel_silent()
        self._exit_ui_mode()

    # ------------------------------------------------------------------
    # Launch sequence
    # ------------------------------------------------------------------
    def _maybe_start_launch_sequence(self) -> None:
        if self.state is None or not self.state.last_launches:
            return
        sig = (self.state.year, self.state.season.value, self.state.phase.value)
        if sig == self._consumed_launch_sig:
            return
        self._consumed_launch_sig = sig
        # Order own launch first so the animation hits for the local player.
        me = self.me()
        my_side = me.side.value if me and me.side else None
        own = [r for r in self.state.last_launches if my_side and r.side == my_side]
        other = [r for r in self.state.last_launches if not my_side or r.side != my_side]
        self.report_queue = own + other
        if not self.report_queue:
            return
        self.report_idx = 0
        self._start_next_report()

    def _start_next_report(self) -> None:
        if self.report_idx >= len(self.report_queue):
            self._finish_launch_sequence()
            return
        report = self.report_queue[self.report_idx]
        me = self.me()
        is_own = bool(me and me.side and report.side == me.side.value)
        # Own non-aborted launches get the ascend animation; everything else
        # jumps straight to the result panel.
        if is_own and not report.aborted:
            self._close_panel_silent()
            self._enter_ui_mode()
            self.launch_phase = "ascend"
            self.flame.enabled = True
            self.rocket.animate_y(
                launch_scene.APEX_Y,
                duration=launch_scene.LIFTOFF_DURATION,
                curve=curve.linear,
            )
            invoke(self._show_result_after_ascend, delay=launch_scene.LIFTOFF_DURATION)
        else:
            self._show_result_panel(report)

    def _show_result_after_ascend(self) -> None:
        if self.launch_phase != "ascend":
            return
        if self.report_idx >= len(self.report_queue):
            return
        self.flame.enabled = False
        self._show_result_panel(self.report_queue[self.report_idx])

    def _show_result_panel(self, report: LaunchReport) -> None:
        self.launch_phase = "result"
        self._open_panel("result", report=report)

    def advance_result_panel(self) -> None:
        if self.launch_phase != "result":
            return
        self.report_idx += 1
        self._close_panel_silent()
        if self.report_idx < len(self.report_queue):
            self.launch_phase = "idle"
            self._start_next_report()
        else:
            self._finish_launch_sequence()

    def _skip_ascend(self) -> None:
        self.rocket.y = launch_scene.APEX_Y
        self.flame.enabled = False
        if self.report_idx < len(self.report_queue):
            self._show_result_panel(self.report_queue[self.report_idx])

    def _finish_launch_sequence(self) -> None:
        self.report_queue = []
        self.report_idx = 0
        self.launch_phase = "idle"
        launch_scene.reset_rocket(self.rocket, self.flame)
        self._exit_ui_mode()
