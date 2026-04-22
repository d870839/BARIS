from __future__ import annotations

import argparse
import logging
from typing import Any

import pygame

from baris import protocol
from baris.client.net import NetClient
from baris.client.ui import (
    ACCENT_USA,
    ACCENT_USSR,
    BG,
    BG_DEEP,
    BORDER,
    BORDER_HOVER,
    Button,
    DIM,
    FG,
    GREEN,
    HIGHLIGHT,
    MUTED,
    PANEL,
    PANEL_HOVER,
    RED,
    draw_text,
    draw_text_centered,
)
from baris.state import (
    ARCHITECTURE_COST_DELTA,
    ARCHITECTURE_FULL_NAMES,
    ARCHITECTURE_SUCCESS_DELTA,
    LM_POINTS_REQUIRED,
    MIN_RELIABILITY_TO_LAUNCH,
    MISSIONS,
    MISSIONS_BY_ID,
    Architecture,
    Astronaut,
    GameState,
    LaunchReport,
    MissionId,
    Module,
    ObjectiveId,
    Phase,
    Player,
    ProgramTier,
    RELIABILITY_CAP,
    Rocket,
    Side,
    Skill,
    objectives_for,
    program_name,
    rocket_display_name,
)

log = logging.getLogger("baris.client")

WINDOW_SIZE = (1200, 940)
FPS = 60

ROCKET_KEYS = {pygame.K_q: Rocket.LIGHT, pygame.K_w: Rocket.MEDIUM, pygame.K_e: Rocket.HEAVY}
MODULE_KEYS = {pygame.K_r: Module.DOCKING}
OBJECTIVE_KEYS = {  # held-down toggle keys while on the Missions tab
    pygame.K_v: ObjectiveId.EVA,
    pygame.K_b: ObjectiveId.DOCKING,
    pygame.K_n: ObjectiveId.LONG_DURATION,
    pygame.K_m: ObjectiveId.MOONWALK,
    pygame.K_COMMA: ObjectiveId.SAMPLE_RETURN,
}
MISSION_KEYS = {
    pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2,
    pygame.K_4: 3, pygame.K_5: 4, pygame.K_6: 5,
    pygame.K_7: 6, pygame.K_8: 7, pygame.K_9: 8,
    pygame.K_0: 9, pygame.K_MINUS: 10,
}
ARCHITECTURE_KEYS = {
    pygame.K_a: Architecture.DA,
    pygame.K_s: Architecture.EOR,
    pygame.K_d: Architecture.LSR,
    pygame.K_f: Architecture.LOR,
}

# Scenes
MENU = "menu"
CONNECTING = "connecting"
LOBBY = "lobby"
GAME = "game"
BRIEFING = "briefing"
LAUNCHING = "launching"
ENDED = "ended"

# Launch-sequence timing (ms). Ascend runs for ASCEND_DURATION_MS before
# auto-advancing to the RESULT sub-phase; results wait for user input.
ASCEND_DURATION_MS = 2400

# Tabs (within GAME scene)
TAB_HUB        = "hub"
TAB_RD         = "rd"
TAB_ASTRONAUTS = "astronauts"
TAB_MISSIONS   = "missions"
TAB_LOG        = "log"

TAB_KEYS = {
    pygame.K_F1: TAB_HUB,
    pygame.K_F2: TAB_RD,
    pygame.K_F3: TAB_ASTRONAUTS,
    pygame.K_F4: TAB_MISSIONS,
    pygame.K_F5: TAB_LOG,
}

# Mission Control hub map: clickable buildings laid out in a 2x4 grid.
# Top row = buildings wired to real tabs. Bottom row = flavor-only for now.
# (id, label, subtitle, linked_tab_or_None)
HUB_BUILDINGS: tuple[tuple[str, str, str, str | None], ...] = (
    ("rd",       "R&D Complex",       "Research rockets & modules",   TAB_RD),
    ("astro",    "Astronaut Complex", "Train & select crews",         TAB_ASTRONAUTS),
    ("mc",       "Mission Control",   "Schedule & review launches",   TAB_MISSIONS),
    ("library",  "Library",           "Flight records & event log",   TAB_LOG),
    ("admin",    "Administration",    "HQ / budget / politics",       None),
    ("vab",      "VAB",               "Vehicle Assembly Building",    None),
    ("infirm",   "Infirmary",         "Crew medical bay",             None),
    ("museum",   "Museum",            "Hall of firsts",               None),
)

# Rooftop color per building — picks out which buildings go together and
# gives the map some variety. Dimmer hues implicitly mark flavor-only tiles.
BUILDING_ROOFS: dict[str, tuple[int, int, int]] = {
    "rd":      (110, 200, 120),
    "astro":   (130, 160, 220),
    "mc":      (240, 200, 90),
    "library": (200, 170, 110),
    "admin":   (140, 140, 160),
    "vab":     (170, 140, 110),
    "infirm":  (210, 120, 120),
    "museum":  (170, 140, 180),
}

BUILDING_KEY_HINTS: dict[str | None, str] = {
    TAB_RD:         "F2",
    TAB_ASTRONAUTS: "F3",
    TAB_MISSIONS:   "F4",
    TAB_LOG:        "F5",
}


def _hub_title(side: Side | None) -> str:
    if side == Side.USA:
        return "MISSION CONTROL COMPLEX — HOUSTON, TEXAS"
    if side == Side.USSR:
        return "COSMODROME COMPLEX — BAIKONUR / STAR CITY"
    return "SPACE PROGRAM COMPLEX"

# Area inside HUD where tab-specific content renders.
CONTENT_TOP = 100
CONTENT_BOTTOM = 860


def side_color(side: Side | None) -> tuple[int, int, int]:
    if side == Side.USA:
        return ACCENT_USA
    if side == Side.USSR:
        return ACCENT_USSR
    return DIM


class Client:
    def __init__(self, server_url: str, username: str) -> None:
        pygame.init()
        pygame.display.set_caption("BARIS — Race Into Space (remake)")
        # Real OS window — resizable. Start at WINDOW_SIZE but fit the
        # display if that's taller than the user's screen (laptops) so the
        # bottom of the canvas isn't clipped on first open.
        info = pygame.display.Info()
        max_w = max(640, int(info.current_w * 0.9))
        max_h = max(480, int(info.current_h * 0.85))
        scale = min(1.0, max_w / WINDOW_SIZE[0], max_h / WINDOW_SIZE[1])
        initial = (int(WINDOW_SIZE[0] * scale), int(WINDOW_SIZE[1] * scale))
        self.window = pygame.display.set_mode(initial, pygame.RESIZABLE)
        # All rendering goes to a fixed-size off-screen canvas; render()
        # blits it scaled into self.window so the UI layout is resolution-
        # independent and mouse coordinates are predictable.
        self.screen = pygame.Surface(WINDOW_SIZE)
        self.clock = pygame.time.Clock()

        self.server_url = server_url
        self.username = username
        self.net: NetClient | None = None

        self.state: GameState | None = None
        self.player_id: str | None = None
        self.status = ""
        self.joined_sent = False

        # R&D target: either a Rocket OR a Module. Stored as enum value string
        # so submission is uniform.
        self.rd_target_rocket: Rocket | None = Rocket.LIGHT
        self.rd_target_module: Module | None = None
        self.rd_spend: int = 10
        self.queued_mission: MissionId | None = None
        self.queued_objectives: set[ObjectiveId] = set()

        self.scene: str = MENU
        self.active_tab: str = TAB_HUB
        self.menu_buttons = self._build_menu_buttons()
        self.lobby_buttons: list[Button] = []
        self.game_buttons: dict[str, Button] = {}
        self.mission_buttons: list[Button] = []
        self.hub_buttons: dict[str, Button] = {}
        self.briefing_buttons: list[Button] = []
        self.launching_buttons: list[Button] = []
        self.end_buttons: list[Button] = []

        # Launch-sequence playback state.
        self.report_queue: list[LaunchReport] = []
        self.report_idx: int = 0
        self.launch_phase: str = "ascend"   # "ascend" | "result"
        self.launch_phase_start_ms: int = 0
        # Identity of the last resolve we've already animated so repeat state
        # broadcasts (e.g. after READY / CHOOSE_SIDE) don't replay the scene.
        self._consumed_launch_sig: tuple | None = None

    # ------------------------------------------------------------------
    # Scene transitions
    # ------------------------------------------------------------------
    def _start_new_game(self) -> None:
        self.status = f"Connecting to {self.server_url}..."
        self.net = NetClient(self.server_url)
        self.net.start()
        self.scene = CONNECTING

    def _return_to_menu(self) -> None:
        self.net = None
        self.state = None
        self.player_id = None
        self.joined_sent = False
        self.queued_mission = None
        self.queued_objectives.clear()
        self.report_queue = []
        self.report_idx = 0
        self._consumed_launch_sig = None
        self.status = ""
        self.scene = MENU

    def _enter_lobby(self) -> None:
        self.scene = LOBBY
        self.lobby_buttons = self._build_lobby_buttons()

    def _enter_game(self) -> None:
        self.scene = GAME
        self.active_tab = TAB_HUB
        self.game_buttons = self._build_game_buttons()
        self.mission_buttons = self._build_mission_buttons()
        self.hub_buttons = self._build_hub_buttons()

    def _enter_briefing(self) -> None:
        self.scene = BRIEFING
        self.briefing_buttons = self._build_briefing_buttons()

    def _enter_launching(self, reports: list[LaunchReport]) -> None:
        """Seed the animation queue (own launch first, opponent's after) and
        jump to the full-screen launch-sequence scene."""
        me = self._me()
        my_side = me.side.value if me and me.side else None
        own = [r for r in reports if my_side and r.side == my_side]
        other = [r for r in reports if not my_side or r.side != my_side]
        self.report_queue = own + other
        if not self.report_queue:
            return
        self.report_idx = 0
        self._enter_current_report()
        self.launching_buttons = self._build_launching_buttons()
        self.scene = LAUNCHING

    def _enter_current_report(self) -> None:
        """Reset phase + timer for the report at self.report_idx.
        Aborted reports skip straight to RESULT (no countdown to show)."""
        report = self.report_queue[self.report_idx]
        self.launch_phase = "result" if report.aborted else "ascend"
        self.launch_phase_start_ms = pygame.time.get_ticks()

    def _advance_launch_sequence(self) -> None:
        """User pressed space / clicked 'continue'. Skip to result if still
        ascending; otherwise advance to the next report or finish."""
        if self.launch_phase == "ascend":
            self.launch_phase = "result"
            self.launch_phase_start_ms = pygame.time.get_ticks()
            return
        self.report_idx += 1
        if self.report_idx >= len(self.report_queue):
            self._finish_launch_sequence()
        else:
            self._enter_current_report()

    def _finish_launch_sequence(self) -> None:
        self.report_queue = []
        self.report_idx = 0
        if self.state and self.state.phase == Phase.ENDED:
            self._enter_ended()
        else:
            self.scene = GAME

    def _enter_ended(self) -> None:
        self.scene = ENDED
        self.end_buttons = self._build_end_buttons()

    # ------------------------------------------------------------------
    # Button builders
    # ------------------------------------------------------------------
    def _build_menu_buttons(self) -> list[Button]:
        cx = WINDOW_SIZE[0] // 2
        return [
            Button(pygame.Rect(cx - 150, 430, 300, 60), "NEW GAME"),
            Button(pygame.Rect(cx - 150, 510, 300, 60), "EXIT"),
        ]

    def _build_lobby_buttons(self) -> list[Button]:
        return [
            Button(pygame.Rect(30, 300, 220, 50), "Pick USA", key_hint="1"),
            Button(pygame.Rect(260, 300, 220, 50), "Pick USSR", key_hint="2"),
            Button(pygame.Rect(30, 370, 450, 50), "Ready", key_hint="Enter"),
        ]

    def _build_game_buttons(self) -> dict[str, Button]:
        btns: dict[str, Button] = {}

        # Tab bar (always visible)
        tab_w, tab_h, gap = 140, 36, 8
        total = 5 * tab_w + 4 * gap
        start_x = (WINDOW_SIZE[0] - total) // 2
        tab_y = 40
        tab_specs = [
            ("tab_hub",        "HUB",        "F1"),
            ("tab_rd",         "R&D",        "F2"),
            ("tab_astronauts", "ASTRONAUTS", "F3"),
            ("tab_missions",   "MISSIONS",   "F4"),
            ("tab_log",        "LOG",        "F5"),
        ]
        for i, (key, label, hint) in enumerate(tab_specs):
            x = start_x + i * (tab_w + gap)
            btns[key] = Button(pygame.Rect(x, tab_y, tab_w, tab_h), label, key_hint=hint)

        # R&D tab controls (only rendered on that tab)
        rd_y = 520
        btns["rocket_light"]  = Button(pygame.Rect(30,  rd_y, 120, 36), "Light",   key_hint="Q")
        btns["rocket_medium"] = Button(pygame.Rect(160, rd_y, 120, 36), "Medium",  key_hint="W")
        btns["rocket_heavy"]  = Button(pygame.Rect(290, rd_y, 120, 36), "Heavy",   key_hint="E")
        btns["module_docking"]= Button(pygame.Rect(420, rd_y, 140, 36), "Docking", key_hint="R")
        btns["spend_minus"]   = Button(pygame.Rect(590, rd_y, 36,  36), "-",       key_hint="Left")
        btns["spend_plus"]    = Button(pygame.Rect(636, rd_y, 36,  36), "+",       key_hint="Right")

        # Missions tab: architecture tiles (shown only when Tier 3 unlocked)
        arch_y = 750
        btns["arch_da"]  = Button(pygame.Rect(30,  arch_y, 170, 44), "DA",  key_hint="A")
        btns["arch_eor"] = Button(pygame.Rect(210, arch_y, 170, 44), "EOR", key_hint="S")
        btns["arch_lsr"] = Button(pygame.Rect(390, arch_y, 170, 44), "LSR", key_hint="D")
        btns["arch_lor"] = Button(pygame.Rect(570, arch_y, 170, 44), "LOR", key_hint="F")

        # Bottom bar
        btns["submit"] = Button(pygame.Rect(940, 875, 240, 50), "SUBMIT TURN", key_hint="Enter")
        btns["cancel"] = Button(pygame.Rect(680, 875, 240, 50), "Cancel launch", key_hint="Esc")
        return btns

    def _build_mission_buttons(self) -> list[Button]:
        # Mission rows live on the MISSIONS tab, starting just below the header.
        top = 160
        row_h = 28
        row_w = 1140
        x = 30
        buttons: list[Button] = []
        for i in range(len(MISSIONS)):
            buttons.append(Button(
                pygame.Rect(x, top + i * row_h, row_w, row_h),
                label="",
                key_hint=None,
            ))
        return buttons

    def _build_hub_buttons(self) -> dict[str, Button]:
        # 2 rows x 4 columns of building tiles inside the HUB content area.
        # Top row (y=140): buildings wired to real tabs.
        # Bottom row (y=420): flavor-only buildings (no tab link yet).
        cols, rows = 4, 2
        margin_x, margin_y = 30, 20
        tile_w = (WINDOW_SIZE[0] - 2 * margin_x - (cols - 1) * margin_y) // cols
        tile_h = 260
        top_y = 140
        buttons: dict[str, Button] = {}
        for i, (bid, label, _subtitle, _linked) in enumerate(HUB_BUILDINGS):
            r, c = divmod(i, cols)
            x = margin_x + c * (tile_w + margin_y)
            y = top_y + r * (tile_h + margin_y)
            buttons[f"hub_{bid}"] = Button(pygame.Rect(x, y, tile_w, tile_h), label)
        return buttons

    def _build_briefing_buttons(self) -> list[Button]:
        cx = WINDOW_SIZE[0] // 2
        return [
            Button(pygame.Rect(cx + 30, 860, 260, 56), "LAUNCH", key_hint="Enter"),
            Button(pygame.Rect(cx - 290, 860, 260, 56), "Abort", key_hint="Esc"),
        ]

    def _build_launching_buttons(self) -> list[Button]:
        cx = WINDOW_SIZE[0] // 2
        return [Button(pygame.Rect(cx - 120, 880, 240, 46), "Continue", key_hint="Space")]

    def _build_end_buttons(self) -> list[Button]:
        cx = WINDOW_SIZE[0] // 2
        return [Button(pygame.Rect(cx - 150, 810, 300, 55), "RETURN TO MENU")]

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------
    def pump_network(self) -> None:
        if self.net is None:
            return
        if self.net.connected.is_set() and not self.joined_sent:
            self.net.send(protocol.JOIN, username=self.username)
            self.joined_sent = True
            self.status = "Joining..."

        for msg in self.net.drain_inbound():
            mtype = msg.get("type")
            if mtype == protocol.JOINED:
                self.player_id = msg["player_id"]
                self.state = GameState.from_dict(msg["state"])
                me = self._me()
                side_label = me.side.value if me and me.side else "?"
                self.status = f"Joined as {side_label}"
                if self.scene != GAME:
                    self._enter_lobby()
            elif mtype == protocol.STATE:
                self.state = GameState.from_dict(msg["state"])
                me = self._me()
                if me is None or me.turn_submitted:
                    self.queued_mission = None
                if self.state.phase == Phase.PLAYING and self.scene not in (
                    GAME, BRIEFING, LAUNCHING,
                ):
                    self._enter_game()
                # Detect a freshly-resolved turn with launches to animate.
                # We guard against re-firing on unrelated state broadcasts by
                # remembering the (year, season, phase) tuple we've already
                # consumed — last_launches is cleared on every resolve, so a
                # repeat with the same sig always has the same content.
                current_sig = (
                    self.state.year, self.state.season.value, self.state.phase.value,
                )
                if (
                    self.state.last_launches
                    and current_sig != self._consumed_launch_sig
                ):
                    self._consumed_launch_sig = current_sig
                    self._enter_launching(self.state.last_launches)
                elif self.state.phase == Phase.ENDED and self.scene not in (
                    ENDED, LAUNCHING,
                ):
                    # Game ended (on prestige) with no launch to animate.
                    self._enter_ended()
            elif mtype == protocol.ERROR:
                self.status = f"Error: {msg.get('message', '?')}"

    def _me(self) -> Player | None:
        if self.state is None or self.player_id is None:
            return None
        return self.state.find_player(self.player_id)

    def _opponent(self) -> Player | None:
        if self.state is None or self.player_id is None:
            return None
        return self.state.other_player(self.player_id)

    # ------------------------------------------------------------------
    # Input dispatch
    # ------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.QUIT:
            return False
        if self.scene == MENU:
            return self._handle_menu_event(event)
        if self.scene == CONNECTING:
            return self._handle_connecting_event(event)
        if self.scene == LOBBY:
            return self._handle_lobby_event(event)
        if self.scene == GAME:
            return self._handle_game_event(event)
        if self.scene == BRIEFING:
            return self._handle_briefing_event(event)
        if self.scene == LAUNCHING:
            return self._handle_launching_event(event)
        if self.scene == ENDED:
            return self._handle_end_event(event)
        return True

    def _handle_menu_event(self, event: pygame.event.Event) -> bool:
        if self.menu_buttons[0].handle_event(event):
            self._start_new_game()
        if self.menu_buttons[1].handle_event(event):
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self._start_new_game()
            elif event.key == pygame.K_ESCAPE:
                return False
        return True

    def _handle_connecting_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._return_to_menu()
        return True

    def _handle_lobby_event(self, event: pygame.event.Event) -> bool:
        me = self._me()
        if me is None:
            return True
        if self.lobby_buttons[0].handle_event(event):
            self.net.send(protocol.CHOOSE_SIDE, side=Side.USA.value)
        if self.lobby_buttons[1].handle_event(event):
            self.net.send(protocol.CHOOSE_SIDE, side=Side.USSR.value)
        if self.lobby_buttons[2].handle_event(event):
            self.net.send(protocol.READY if not me.ready else protocol.UNREADY)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_1:
                self.net.send(protocol.CHOOSE_SIDE, side=Side.USA.value)
            elif event.key == pygame.K_2:
                self.net.send(protocol.CHOOSE_SIDE, side=Side.USSR.value)
            elif event.key == pygame.K_RETURN:
                self.net.send(protocol.READY if not me.ready else protocol.UNREADY)
            elif event.key == pygame.K_ESCAPE:
                self._return_to_menu()
        return True

    def _handle_game_event(self, event: pygame.event.Event) -> bool:
        me = self._me()
        if me is None or self.state is None:
            return True

        # Tab navigation (always available)
        tab_map = {
            "tab_hub":        TAB_HUB,
            "tab_rd":         TAB_RD,
            "tab_astronauts": TAB_ASTRONAUTS,
            "tab_missions":   TAB_MISSIONS,
            "tab_log":        TAB_LOG,
        }
        for key, tab in tab_map.items():
            btn = self.game_buttons[key]
            btn.selected = (self.active_tab == tab)
            if btn.handle_event(event):
                self.active_tab = tab

        if event.type == pygame.KEYDOWN and event.key in TAB_KEYS:
            self.active_tab = TAB_KEYS[event.key]
            return True

        editable = not me.turn_submitted

        # Bottom bar: Submit / Cancel (always accessible)
        self.game_buttons["submit"].enabled = editable
        self.game_buttons["cancel"].enabled = editable and self.queued_mission is not None
        if self.game_buttons["submit"].handle_event(event) and editable:
            self._submit_turn(me)
        if self.game_buttons["cancel"].handle_event(event):
            self.queued_mission = None

        # Hub: clicking a linked building routes to its tab; flavor buildings
        # still register hover (for the tooltip) but don't navigate.
        if self.active_tab == TAB_HUB:
            for bid, _label, _sub, linked in HUB_BUILDINGS:
                btn = self.hub_buttons[f"hub_{bid}"]
                btn.enabled = linked is not None
                if btn.handle_event(event) and linked is not None:
                    self.active_tab = linked

        # Tab-gated controls
        if self.active_tab == TAB_RD:
            rocket_btns = {
                "rocket_light":  Rocket.LIGHT,
                "rocket_medium": Rocket.MEDIUM,
                "rocket_heavy":  Rocket.HEAVY,
            }
            for key, rocket in rocket_btns.items():
                btn = self.game_buttons[key]
                btn.enabled = editable
                btn.selected = (self.rd_target_rocket == rocket)
                if btn.handle_event(event):
                    self.rd_target_rocket = rocket
                    self.rd_target_module = None
            mod_btn = self.game_buttons["module_docking"]
            mod_btn.enabled = editable
            mod_btn.selected = (self.rd_target_module == Module.DOCKING)
            if mod_btn.handle_event(event):
                self.rd_target_module = Module.DOCKING
                self.rd_target_rocket = None
            self.game_buttons["spend_minus"].enabled = editable
            self.game_buttons["spend_plus"].enabled = editable
            if self.game_buttons["spend_minus"].handle_event(event) and editable:
                self.rd_spend = max(0, self.rd_spend - 5)
            if self.game_buttons["spend_plus"].handle_event(event) and editable:
                self.rd_spend = min(me.budget, self.rd_spend + 5)

        if self.active_tab == TAB_MISSIONS:
            # Mission rows — only those mapping to a currently-visible mission.
            from baris.resolver import visible_missions
            visible = visible_missions(me)
            already_scheduled = me.scheduled_launch is not None
            for idx, btn in enumerate(self.mission_buttons):
                if idx < len(visible):
                    btn.enabled = editable and not already_scheduled
                    if btn.handle_event(event) and editable and not already_scheduled:
                        self.queued_mission = visible[idx].id
                else:
                    btn.enabled = False
            # Architecture tiles
            can_pick_arch = me.is_tier_unlocked(ProgramTier.THREE) and me.architecture is None
            arch_btn_map = {
                "arch_da":  Architecture.DA,
                "arch_eor": Architecture.EOR,
                "arch_lsr": Architecture.LSR,
                "arch_lor": Architecture.LOR,
            }
            for key, arch in arch_btn_map.items():
                btn = self.game_buttons[key]
                btn.enabled = can_pick_arch
                btn.selected = (me.architecture == arch.value)
                if btn.handle_event(event):
                    self.net.send(protocol.CHOOSE_ARCHITECTURE, architecture=arch.value)

        # Keyboard fallbacks
        if event.type == pygame.KEYDOWN:
            # Shift+Esc scrubs an already-scheduled launch. Checked before
            # plain Esc so the player doesn't also clear a queued one.
            if (
                event.key == pygame.K_ESCAPE
                and (event.mod & pygame.KMOD_SHIFT)
                and me.scheduled_launch is not None
            ):
                self.net.send(protocol.SCRUB_SCHEDULED)
                return True
            if event.key == pygame.K_ESCAPE and self.queued_mission is not None:
                self.queued_mission = None
                return True
            # Architecture is accessible regardless of tab (one-time action).
            if (
                me.is_tier_unlocked(ProgramTier.THREE)
                and me.architecture is None
                and event.key in ARCHITECTURE_KEYS
            ):
                self.net.send(
                    protocol.CHOOSE_ARCHITECTURE,
                    architecture=ARCHITECTURE_KEYS[event.key].value,
                )
                return True
            if not editable:
                return True
            if self.active_tab == TAB_RD and event.key in ROCKET_KEYS:
                self.rd_target_rocket = ROCKET_KEYS[event.key]
                self.rd_target_module = None
            elif self.active_tab == TAB_RD and event.key in MODULE_KEYS:
                self.rd_target_module = MODULE_KEYS[event.key]
                self.rd_target_rocket = None
            elif self.active_tab == TAB_RD and event.key == pygame.K_LEFT:
                self.rd_spend = max(0, self.rd_spend - 5)
            elif self.active_tab == TAB_RD and event.key == pygame.K_RIGHT:
                self.rd_spend = min(me.budget, self.rd_spend + 5)
            elif self.active_tab == TAB_MISSIONS and event.key in MISSION_KEYS:
                from baris.resolver import visible_missions
                visible = visible_missions(me)
                idx = MISSION_KEYS[event.key]
                if idx < len(visible) and me.scheduled_launch is None:
                    self.queued_mission = visible[idx].id
                    self.queued_objectives.clear()
            elif self.active_tab == TAB_MISSIONS and event.key in OBJECTIVE_KEYS and self.queued_mission:
                obj_id = OBJECTIVE_KEYS[event.key]
                # only toggle if this objective belongs to the queued mission
                available_obj_ids = {o.id for o in objectives_for(self.queued_mission)}
                if obj_id in available_obj_ids:
                    if obj_id in self.queued_objectives:
                        self.queued_objectives.discard(obj_id)
                    else:
                        self.queued_objectives.add(obj_id)
            elif event.key == pygame.K_RETURN:
                self._submit_turn(me)
        return True

    def _submit_turn(self, me: Player) -> None:
        """Open the briefing screen if the player queued a mission; otherwise
        (R&D-only turns) skip straight to sending END_TURN."""
        if self.queued_mission is not None:
            self._enter_briefing()
            return
        self._send_end_turn(me)

    def _send_end_turn(self, me: Player) -> None:
        """Actually wire the turn over the network and clear the queue."""
        payload: dict[str, object] = {
            "rd_spend": min(self.rd_spend, me.budget),
            "launch": self.queued_mission.value if self.queued_mission else None,
            "objectives": [o.value for o in self.queued_objectives],
        }
        if self.rd_target_module is not None:
            payload["rd_module"] = self.rd_target_module.value
        elif self.rd_target_rocket is not None:
            payload["rd_rocket"] = self.rd_target_rocket.value
        self.net.send(protocol.END_TURN, **payload)
        self.queued_mission = None
        self.queued_objectives.clear()

    def _handle_briefing_event(self, event: pygame.event.Event) -> bool:
        me = self._me()
        if me is None:
            return True
        # buttons[0] = LAUNCH, buttons[1] = Abort
        if self.briefing_buttons[0].handle_event(event):
            self._send_end_turn(me)
            self.scene = GAME
            return True
        if self.briefing_buttons[1].handle_event(event):
            self.scene = GAME
            return True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self._send_end_turn(me)
                self.scene = GAME
            elif event.key == pygame.K_ESCAPE:
                self.scene = GAME
        return True

    def _handle_launching_event(self, event: pygame.event.Event) -> bool:
        if self.launching_buttons and self.launching_buttons[0].handle_event(event):
            self._advance_launch_sequence()
            return True
        if event.type == pygame.KEYDOWN and event.key in (
            pygame.K_SPACE, pygame.K_RETURN, pygame.K_ESCAPE,
        ):
            self._advance_launch_sequence()
        return True

    def _handle_end_event(self, event: pygame.event.Event) -> bool:
        if self.end_buttons[0].handle_event(event):
            self._return_to_menu()
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_ESCAPE):
            self._return_to_menu()
        return True

    # ------------------------------------------------------------------
    # Render dispatch
    # ------------------------------------------------------------------
    def render(self) -> None:
        self.screen.fill(BG)
        if self.scene == MENU:
            self._render_menu()
        elif self.scene == CONNECTING:
            self._render_connecting()
        elif self.scene == LOBBY:
            self._render_lobby()
        elif self.scene == GAME:
            self._render_game()
        elif self.scene == BRIEFING:
            self._render_briefing()
        elif self.scene == LAUNCHING:
            self._tick_launching()
            self._render_launching()
        elif self.scene == ENDED:
            self._render_end()
        draw_text(self.screen, self.status, (30, WINDOW_SIZE[1] - 22), size=14, color=DIM)
        # Scale the logical canvas to whatever the real window size is now.
        win_size = self.window.get_size()
        if win_size == WINDOW_SIZE:
            self.window.blit(self.screen, (0, 0))
        else:
            pygame.transform.smoothscale(self.screen, win_size, self.window)
        pygame.display.flip()

    def _tick_launching(self) -> None:
        """Auto-advance from ascend → result once the ascend timer elapses."""
        if not self.report_queue or self.launch_phase != "ascend":
            return
        now = pygame.time.get_ticks()
        if now - self.launch_phase_start_ms >= ASCEND_DURATION_MS:
            self.launch_phase = "result"
            self.launch_phase_start_ms = now

    # --- menu -----------------------------------------------------------
    def _render_menu(self) -> None:
        cx = WINDOW_SIZE[0] // 2
        pygame.draw.rect(self.screen, BG_DEEP, (0, 0, WINDOW_SIZE[0], 320))
        pygame.draw.rect(self.screen, BORDER, (0, 318, WINDOW_SIZE[0], 2))
        draw_text_centered(self.screen, "BARIS", (cx, 140), size=84, color=HIGHLIGHT, bold=True)
        draw_text_centered(self.screen, "Race Into Space", (cx, 210), size=28, color=FG)
        draw_text_centered(
            self.screen, "A 2-player online remake — 1957-1977",
            (cx, 250), size=18, color=DIM,
        )
        draw_text_centered(
            self.screen,
            f"Server: {self.server_url}     Playing as: {self.username}",
            (cx, 380), size=14, color=MUTED,
        )
        for btn in self.menu_buttons:
            btn.draw(self.screen)

    # --- connecting -----------------------------------------------------
    def _render_connecting(self) -> None:
        cx, cy = WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2
        draw_text_centered(self.screen, "Connecting...", (cx, cy - 20), size=32, color=FG, bold=True)
        draw_text_centered(self.screen, self.server_url, (cx, cy + 20), size=16, color=DIM)
        draw_text_centered(self.screen, "Esc to cancel", (cx, cy + 60), size=14, color=MUTED)

    # --- lobby ----------------------------------------------------------
    def _render_lobby(self) -> None:
        assert self.state is not None
        draw_text(self.screen, "LOBBY", (30, 30), size=40, color=HIGHLIGHT, bold=True)
        draw_text(
            self.screen,
            "Choose a side and ready up. Game starts when both players are ready on opposite sides.",
            (30, 80), size=16, color=DIM,
        )
        y = 130
        for p in self.state.players:
            ready_txt = "READY" if p.ready else "not ready"
            label = f"{p.username}  [{p.side.value if p.side else '?'}]  {ready_txt}"
            color = side_color(p.side) if p.player_id != self.player_id else HIGHLIGHT
            draw_text(self.screen, label, (30, y), size=18, color=color)
            y += 30
        if len(self.state.players) < 2:
            draw_text(self.screen, "Waiting for opponent...", (30, y + 20), size=18, color=DIM)

        me = self._me()
        if me is not None:
            self.lobby_buttons[0].selected = me.side == Side.USA
            self.lobby_buttons[1].selected = me.side == Side.USSR
            self.lobby_buttons[2].selected = me.ready
            self.lobby_buttons[2].label = "Unready" if me.ready else "Ready"
        for btn in self.lobby_buttons:
            btn.draw(self.screen)

    # --- game -----------------------------------------------------------
    def _render_game(self) -> None:
        assert self.state is not None
        me = self._me()
        opp = self._opponent()

        self._render_top_hud(me)
        self._render_active_tab(me, opp)
        self._render_bottom_bar(me)

        # draw buttons on top of content
        for key, btn in self.game_buttons.items():
            # Only draw the buttons that belong to the active tab
            # (plus always-visible tab + submit/cancel buttons).
            always = key.startswith("tab_") or key in ("submit", "cancel")
            if always:
                btn.draw(self.screen)
            elif self.active_tab == TAB_RD and key in (
                "rocket_light", "rocket_medium", "rocket_heavy",
                "module_docking", "spend_minus", "spend_plus",
            ):
                btn.draw(self.screen)
            elif self.active_tab == TAB_MISSIONS and key.startswith("arch_"):
                # Architecture tiles shown only when Tier 3 unlocked.
                if me is not None and me.is_tier_unlocked(ProgramTier.THREE):
                    btn.draw(self.screen)

        # Hub building tiles: custom-drawn (not Button.draw) so the render lives
        # entirely inside _render_tab_hub, but we still need hover state from
        # the Button instances — that's updated during event handling.

    def _render_top_hud(self, me: Player | None) -> None:
        assert self.state is not None
        pygame.draw.rect(self.screen, BG_DEEP, (0, 0, WINDOW_SIZE[0], 80))
        pygame.draw.rect(self.screen, BORDER, (0, 80, WINDOW_SIZE[0], 1))
        draw_text(
            self.screen, f"{self.state.season.value} {self.state.year}",
            (20, 6), size=22, color=HIGHLIGHT, bold=True,
        )
        if me is not None:
            x = WINDOW_SIZE[0] - 240
            draw_text(self.screen, f"Budget:   {me.budget} MB",   (x, 4),  size=14, color=FG)
            draw_text(self.screen, f"Prestige: {me.prestige}",    (x, 20), size=14, color=FG)
            turn_color = DIM if me.turn_submitted else HIGHLIGHT
            turn_lbl   = "submitted" if me.turn_submitted else "your turn"
            draw_text(self.screen, f"Turn:     {turn_lbl}",       (x, 36), size=14, color=turn_color)
        # goal reminder (centered below season)
        draw_text(
            self.screen,
            "Goal: first manned lunar landing OR 40 prestige wins",
            (20, 78), size=12, color=MUTED,
        )

    def _render_bottom_bar(self, me: Player | None) -> None:
        pygame.draw.rect(self.screen, BG_DEEP, (0, 860, WINDOW_SIZE[0], 80))
        pygame.draw.rect(self.screen, BORDER, (0, 860, WINDOW_SIZE[0], 1))
        if me is None:
            return
        # Left: turn intent summary
        if self.rd_target_module is not None:
            rd_label = self.rd_target_module.value
        elif self.rd_target_rocket is not None:
            rd_label = rocket_display_name(self.rd_target_rocket, me.side)
        else:
            rd_label = "(none)"
        rd_line = f"R&D:    {rd_label}  spend {min(self.rd_spend, me.budget)} MB"
        draw_text(self.screen, rd_line, (20, 872), size=16, color=FG)
        # A mission already in the VAB takes precedence in the display —
        # the player can't queue another until it resolves or is scrubbed.
        if me.scheduled_launch is not None:
            sl = me.scheduled_launch
            try:
                m_name = MISSIONS_BY_ID[MissionId(sl.mission_id)].name
            except (ValueError, KeyError):
                m_name = sl.mission_id
            draw_text(
                self.screen,
                f"Scheduled: {m_name}  launch due {sl.launch_cost_remaining} MB  [Shift+Esc to scrub]",
                (20, 898), size=16, color=HIGHLIGHT,
            )
        elif self.queued_mission is not None:
            m = MISSIONS_BY_ID[self.queued_mission]
            from baris.resolver import (
                _crew_bonus,
                effective_base_success,
                effective_launch_cost,
                effective_lunar_modifier,
                effective_rocket,
            )
            from baris.state import ASSEMBLY_COST_FRACTION, RELIABILITY_SWING_PER_POINT
            eff_rocket = effective_rocket(me, m)
            eff_cost = effective_launch_cost(me, m)
            assembly_due = int(eff_cost * ASSEMBLY_COST_FRACTION)
            reliability_bonus = (me.rocket_reliability(eff_rocket) - 50) * RELIABILITY_SWING_PER_POINT
            recon_bonus, lm_penalty = effective_lunar_modifier(me, m)
            effective = (
                effective_base_success(me, m) + reliability_bonus
                + recon_bonus - lm_penalty
            )
            if m.manned:
                crew = self._preview_crew(me, m)
                if crew:
                    effective += _crew_bonus(crew, m)
            draw_text(
                self.screen,
                f"Schedule: {m.name}  assembly {assembly_due} MB now + "
                f"{eff_cost - assembly_due} MB on launch,  ~{int(effective * 100)}% success",
                (20, 898), size=16, color=GREEN,
            )
        else:
            draw_text(self.screen, "Launch: (none)", (20, 898), size=16, color=DIM)
        if me.turn_submitted:
            draw_text(self.screen, "Waiting for opponent...", (700, 882),
                      size=18, color=DIM, bold=True)

    def _render_active_tab(self, me: Player | None, opp: Player | None) -> None:
        if self.active_tab == TAB_HUB:
            self._render_tab_hub(me, opp)
        elif self.active_tab == TAB_RD:
            self._render_tab_rd(me, opp)
        elif self.active_tab == TAB_ASTRONAUTS:
            self._render_tab_astronauts(me, opp)
        elif self.active_tab == TAB_MISSIONS:
            self._render_tab_missions(me, opp)
        elif self.active_tab == TAB_LOG:
            self._render_tab_log()

    # --- hub tab (Mission Control map) ----------------------------------
    def _render_tab_hub(self, me: Player | None, opp: Player | None) -> None:
        assert self.state is not None
        title = _hub_title(me.side if me else None)
        draw_text(self.screen, title, (30, CONTENT_TOP + 8), size=22,
                  color=HIGHLIGHT, bold=True)
        draw_text(
            self.screen,
            "Click a building to enter — or use F1-F5 to switch tabs directly.",
            (30, CONTENT_TOP + 38), size=13, color=DIM,
        )

        # Ground: subtle darker slab under all the tiles; faint "road" between rows.
        ground = pygame.Rect(20, 130, WINDOW_SIZE[0] - 40, 560)
        pygame.draw.rect(self.screen, BG_DEEP, ground)
        pygame.draw.rect(self.screen, BORDER, ground, 1)
        pygame.draw.line(self.screen, (40, 50, 70),
                         (40, 410), (WINDOW_SIZE[0] - 40, 410), 3)

        # Building tiles
        for bid, label, subtitle, linked in HUB_BUILDINGS:
            self._draw_building_tile(bid, label, subtitle, linked)

        # Standings: one compact row per player so opponent budget/prestige/
        # architecture stay visible after losing the old overview cards.
        standings = pygame.Rect(20, 700, WINDOW_SIZE[0] - 40, 48)
        pygame.draw.rect(self.screen, PANEL, standings, border_radius=6)
        pygame.draw.rect(self.screen, BORDER, standings, 1, border_radius=6)
        for row_idx, (row_label, player) in enumerate((("YOU", me), ("OPP", opp))):
            if player is None:
                continue
            y = standings.y + 6 + row_idx * 20
            firsts = sum(
                1 for holder in self.state.first_completed.values()
                if player.side and holder == player.side.value
            )
            arch = player.architecture or "—"
            side_lbl = player.side.value if player.side else "?"
            line = (
                f"{row_label}  [{side_lbl}] {player.username:<12}"
                f"Budget {player.budget:>3} MB   "
                f"Prestige {player.prestige:>3}   "
                f"Firsts {firsts}   "
                f"Arch {arch}   "
                f"Recon {player.lunar_recon:>2}%   "
                f"LM {player.lm_points}/{LM_POINTS_REQUIRED}"
            )
            draw_text(self.screen, line, (36, y), size=14, color=side_color(player.side))

        # Recent events strip
        events = pygame.Rect(20, 752, WINDOW_SIZE[0] - 40, 98)
        pygame.draw.rect(self.screen, PANEL, events, border_radius=6)
        pygame.draw.rect(self.screen, BORDER, events, 1, border_radius=6)
        draw_text(self.screen, "RECENT EVENTS",
                  (36, events.y + 6), size=13, color=DIM, bold=True)
        y = events.y + 28
        for line in self.state.log[-3:]:
            draw_text(self.screen, line, (36, y), size=13, color=FG)
            y += 20

    def _draw_building_tile(
        self,
        bid: str,
        label: str,
        subtitle: str,
        linked: str | None,
    ) -> None:
        btn = self.hub_buttons[f"hub_{bid}"]
        rect = btn.rect
        is_flavor = linked is None
        hovering = btn._hover and btn.enabled
        roof_color = BUILDING_ROOFS.get(bid, MUTED)

        # Body
        body_bg = PANEL_HOVER if hovering else PANEL
        if hovering:
            border_color = BORDER_HOVER
        elif is_flavor:
            border_color = MUTED
        else:
            border_color = BORDER
        pygame.draw.rect(self.screen, body_bg, rect, border_radius=6)
        pygame.draw.rect(self.screen, border_color, rect, 2, border_radius=6)

        # Roof stripe
        roof_h = 28
        roof_rect = pygame.Rect(rect.x, rect.y, rect.w, roof_h)
        pygame.draw.rect(self.screen, roof_color, roof_rect,
                         border_top_left_radius=6, border_top_right_radius=6)
        draw_text_centered(
            self.screen, label,
            (rect.centerx, rect.y + roof_h // 2),
            size=16, color=(20, 24, 34), bold=True,
        )

        # Icon
        icon_color = FG if not is_flavor else MUTED
        self._draw_building_icon(bid, (rect.centerx, rect.y + roof_h + 78), icon_color)

        # Subtitle
        draw_text_centered(
            self.screen, subtitle,
            (rect.centerx, rect.bottom - 50),
            size=13, color=DIM if not is_flavor else MUTED,
        )

        # Key hint (linked) / placeholder (flavor)
        hint = BUILDING_KEY_HINTS.get(linked)
        if hint:
            draw_text_centered(
                self.screen, f"[{hint}]",
                (rect.centerx, rect.bottom - 22),
                size=14,
                color=HIGHLIGHT if hovering else DIM,
                bold=True,
            )
        else:
            draw_text_centered(
                self.screen, "(flavor)",
                (rect.centerx, rect.bottom - 22),
                size=12, color=MUTED,
            )

    def _draw_building_icon(
        self,
        bid: str,
        center: tuple[int, int],
        color: tuple[int, int, int],
    ) -> None:
        """Stylized pygame-primitive silhouettes, ~60x50 centered on `center`."""
        cx, cy = center
        s = self.screen
        if bid == "rd":
            # Conical flask: trapezoid body + narrow neck.
            pygame.draw.polygon(s, color, [
                (cx - 22, cy + 20), (cx + 22, cy + 20),
                (cx + 10, cy - 8),  (cx - 10, cy - 8),
            ])
            pygame.draw.rect(s, color, (cx - 6, cy - 24, 12, 16), 2)
            pygame.draw.line(s, BG_DEEP, (cx - 14, cy + 8), (cx + 14, cy + 8), 2)
        elif bid == "astro":
            # Helmet: circle outline with a visor band.
            pygame.draw.circle(s, color, (cx, cy), 22, 2)
            pygame.draw.rect(s, color, (cx - 14, cy - 6, 28, 10), 2)
        elif bid == "mc":
            # Console with three scanlines + base.
            pygame.draw.rect(s, color, (cx - 26, cy - 18, 52, 30), 2)
            for i, w in enumerate((30, 24, 36)):
                pygame.draw.line(s, color,
                    (cx - 22, cy - 10 + i * 6),
                    (cx - 22 + w, cy - 10 + i * 6), 1)
            pygame.draw.rect(s, color, (cx - 6, cy + 12, 12, 6))
        elif bid == "library":
            # Three books of varying heights.
            for i, h in enumerate((28, 22, 32)):
                x = cx - 26 + i * 18
                pygame.draw.rect(s, color, (x, cy + 16 - h, 14, h), 2)
        elif bid == "admin":
            # Government building: pediment + columns + base.
            pygame.draw.polygon(s, color, [
                (cx - 28, cy - 6), (cx + 28, cy - 6), (cx, cy - 22),
            ])
            pygame.draw.rect(s, color, (cx - 28, cy - 4, 56, 4))
            for x in (-20, -10, 0, 10, 20):
                pygame.draw.rect(s, color, (cx + x - 2, cy, 4, 18))
            pygame.draw.rect(s, color, (cx - 28, cy + 18, 56, 4))
        elif bid == "vab":
            # Tall assembly tower with a crane arm.
            pygame.draw.rect(s, color, (cx - 14, cy - 22, 28, 42), 2)
            pygame.draw.line(s, color, (cx, cy - 22), (cx, cy - 32), 2)
            pygame.draw.line(s, color, (cx, cy - 32), (cx + 16, cy - 32), 2)
            pygame.draw.rect(s, color, (cx - 5, cy + 14, 10, 6))
        elif bid == "infirm":
            # Medical cross inside a square.
            pygame.draw.rect(s, color, (cx - 22, cy - 22, 44, 44), 2)
            pygame.draw.rect(s, color, (cx - 4, cy - 14, 8, 28))
            pygame.draw.rect(s, color, (cx - 14, cy - 4, 28, 8))
        elif bid == "museum":
            # Columned facade, slimmer than Admin.
            pygame.draw.polygon(s, color, [
                (cx - 26, cy - 6), (cx + 26, cy - 6), (cx, cy - 20),
            ])
            pygame.draw.rect(s, color, (cx - 26, cy - 4, 52, 4))
            pygame.draw.rect(s, color, (cx - 26, cy + 16, 52, 4))
            for x in (-16, 0, 16):
                pygame.draw.rect(s, color, (cx + x - 3, cy, 6, 16))

    # --- R&D tab --------------------------------------------------------
    def _render_tab_rd(self, me: Player | None, opp: Player | None) -> None:
        if me is None:
            return
        x = 30
        draw_text(self.screen, "RESEARCH & DEVELOPMENT", (x, CONTENT_TOP + 10), size=26,
                  color=HIGHLIGHT, bold=True)
        draw_text(
            self.screen,
            "Pick a rocket class and invest MB to progress. A rocket is built once R&D reaches target.",
            (x, CONTENT_TOP + 50), size=14, color=DIM,
        )
        y = CONTENT_TOP + 90
        for r in Rocket:
            self._draw_rd_bar(r, me, (x, y), compact=False)
            y += 50
        # docking module gets its own bar below the rockets
        self._draw_module_bar(Module.DOCKING, me, (x, y))
        # spend controls label (buttons themselves are drawn on top later)
        draw_text(self.screen, "Target:", (30, 496), size=14, color=DIM)
        draw_text(self.screen, f"Spend per turn: {min(self.rd_spend, me.budget)} MB",
                  (710, 528), size=16, color=FG)
        # Opponent progress snapshot
        if opp is not None:
            pygame.draw.rect(self.screen, PANEL, (600, CONTENT_TOP + 90, 580, 220),
                             border_radius=6)
            pygame.draw.rect(self.screen, BORDER, (600, CONTENT_TOP + 90, 580, 220), 1,
                             border_radius=6)
            draw_text(
                self.screen,
                f"OPPONENT R&D ({opp.username}, {opp.side.value if opp.side else '?'})",
                (616, CONTENT_TOP + 100), size=16, color=side_color(opp.side), bold=True,
            )
            oy = CONTENT_TOP + 130
            for r in Rocket:
                self._draw_rd_bar(r, opp, (616, oy), compact=True)
                oy += 24

    def _draw_rd_bar(self, rocket: Rocket, player: Player, pos: tuple[int, int],
                     compact: bool = False) -> None:
        x, y = pos
        rel = player.rocket_reliability(rocket)
        bar_w = 320 if not compact else 220
        size = 16 if not compact else 14
        display = rocket_display_name(rocket, player.side)
        label = f"{display:<10} {rel:3}%"
        draw_text(self.screen, label, (x, y), size=size, color=FG)
        bar_x = x + 220 if not compact else x + 200
        bar_y = y + 3
        bar_h = 16 if not compact else 12
        # empty bar frame
        pygame.draw.rect(self.screen, DIM, (bar_x, bar_y, bar_w, bar_h), 1)
        # threshold marker (where it becomes launch-ready)
        threshold_x = bar_x + int((bar_w - 2) * (MIN_RELIABILITY_TO_LAUNCH / RELIABILITY_CAP))
        pygame.draw.line(self.screen, MUTED,
                         (threshold_x, bar_y), (threshold_x, bar_y + bar_h))
        # fill bar — color reflects launchable / reliable
        built = player.rocket_built(rocket)
        if not built:
            fill_color = RED
        elif rel >= 75:
            fill_color = GREEN
        else:
            fill_color = HIGHLIGHT
        fill_w = int((bar_w - 2) * (rel / RELIABILITY_CAP))
        pygame.draw.rect(self.screen, fill_color, (bar_x + 1, bar_y + 1, fill_w, bar_h - 2))
        # trailing label: readiness state
        if not built:
            tail = "not ready"
            tail_color = RED
        elif rel >= 75:
            tail = "reliable"
            tail_color = GREEN
        else:
            tail = "launch-ready"
            tail_color = HIGHLIGHT
        draw_text(self.screen, tail, (bar_x + bar_w + 12, y), size=size - 2, color=tail_color)

    def _draw_module_bar(self, module: Module, player: Player,
                         pos: tuple[int, int]) -> None:
        """Module reliability bar — same layout as _draw_rd_bar but keyed by Module."""
        x, y = pos
        rel = player.module_reliability(module)
        bar_w = 320
        size = 16
        label = f"{module.value:<16} {rel:3}%"
        draw_text(self.screen, label, (x, y), size=size, color=FG)
        bar_x = x + 220
        bar_y = y + 3
        bar_h = 16
        pygame.draw.rect(self.screen, DIM, (bar_x, bar_y, bar_w, bar_h), 1)
        threshold_x = bar_x + int((bar_w - 2) * (MIN_RELIABILITY_TO_LAUNCH / RELIABILITY_CAP))
        pygame.draw.line(self.screen, MUTED,
                         (threshold_x, bar_y), (threshold_x, bar_y + bar_h))
        built = player.module_built(module)
        if not built:
            fill_color = RED
        elif rel >= 75:
            fill_color = GREEN
        else:
            fill_color = HIGHLIGHT
        fill_w = int((bar_w - 2) * (rel / RELIABILITY_CAP))
        pygame.draw.rect(self.screen, fill_color, (bar_x + 1, bar_y + 1, fill_w, bar_h - 2))
        tail = "not ready" if not built else ("reliable" if rel >= 75 else "usable")
        tail_color = RED if not built else (GREEN if rel >= 75 else HIGHLIGHT)
        draw_text(self.screen, tail, (bar_x + bar_w + 12, y), size=size - 2, color=tail_color)

    # --- Astronauts tab -------------------------------------------------
    def _render_tab_astronauts(self, me: Player | None, opp: Player | None) -> None:
        if me is None:
            return
        draw_text(self.screen, "ASTRONAUT ROSTER", (30, CONTENT_TOP + 10),
                  size=26, color=HIGHLIGHT, bold=True)
        draw_text(
            self.screen,
            "Skills grow each season. Manned missions auto-select the top-skilled active crew.",
            (30, CONTENT_TOP + 50), size=14, color=DIM,
        )
        # Your roster — big
        card_w = 760
        card_h = 600
        cx, cy = 30, CONTENT_TOP + 90
        pygame.draw.rect(self.screen, PANEL, (cx - 8, cy - 6, card_w + 16, card_h),
                         border_radius=6)
        pygame.draw.rect(self.screen, BORDER, (cx - 8, cy - 6, card_w + 16, card_h), 1,
                         border_radius=6)
        side_label = me.side.value if me.side else "?"
        draw_text(self.screen, f"YOUR ROSTER — {side_label}", (cx, cy), size=18,
                  color=side_color(me.side), bold=True)
        header = (
            f"{'Name':<14}{'Capsule':<9}{'LM':<6}{'EVA':<6}{'Dock':<6}{'Endure':<8}Status"
        )
        draw_text(self.screen, header, (cx, cy + 32), size=14, color=DIM)
        y = cy + 58
        for astro in me.astronauts:
            if not astro.active:
                status = "KIA"
                color = RED
            elif not astro.flight_ready:
                status = astro.busy_reason or "training"
                color = HIGHLIGHT
            else:
                status = "ready"
                color = FG
            row = (
                f"{astro.name:<14}"
                f"{astro.capsule:<9}{astro.lm_pilot:<6}"
                f"{astro.eva:<6}{astro.docking:<6}{astro.endurance:<8}"
                f"{status}"
            )
            draw_text(self.screen, row, (cx, y), size=15, color=color)
            y += 28

        # Opponent roster — compact
        if opp is None:
            return
        ox, oy = 810, CONTENT_TOP + 90
        pygame.draw.rect(self.screen, PANEL, (ox - 8, oy - 6, 376, card_h), border_radius=6)
        pygame.draw.rect(self.screen, BORDER, (ox - 8, oy - 6, 376, card_h), 1, border_radius=6)
        opp_side = opp.side.value if opp.side else "?"
        draw_text(self.screen, f"OPPONENT — {opp_side}", (ox, oy), size=18,
                  color=side_color(opp.side), bold=True)
        active = len(opp.active_astronauts())
        kia = len(opp.astronauts) - active
        draw_text(self.screen, f"Active: {active}", (ox, oy + 36), size=15, color=FG)
        draw_text(self.screen, f"KIA:    {kia}", (ox, oy + 58), size=15,
                  color=RED if kia else DIM)
        draw_text(self.screen, "Known names:", (ox, oy + 90), size=14, color=DIM)
        ry = oy + 112
        for astro in opp.astronauts:
            line = f"{astro.name}{' +' if not astro.active else ''}"
            draw_text(self.screen, line, (ox, ry), size=14,
                      color=FG if astro.active else RED)
            ry += 20

    # --- Missions tab ---------------------------------------------------
    def _render_tab_missions(self, me: Player | None, opp: Player | None) -> None:
        if me is None or self.state is None:
            return
        draw_text(self.screen, "MISSION CONTROL", (30, CONTENT_TOP + 10),
                  size=26, color=HIGHLIGHT, bold=True)
        header = (
            f"{'#':<4}{'Program':<10}{'Mission':<22}{'Type':<7}{'Rocket':<10}{'Cost':<6}"
            f"{'Succ%':<7}{'Presti':<8}{'First':<8}Status"
        )
        draw_text(self.screen, header, (30, CONTENT_TOP + 40), size=14, color=DIM)

        from baris.resolver import (
            effective_base_success,
            effective_launch_cost,
            effective_rocket,
            meets_architecture_prereqs,
            visible_missions,
        )
        visible = visible_missions(me)
        if not visible:
            draw_text(
                self.screen,
                "No missions available yet — start by researching a Light rocket (R&D tab).",
                (30, CONTENT_TOP + 80), size=16, color=DIM,
            )
        key_labels = [str(i + 1) for i in range(9)] + ["0", "-"]
        for idx, m in enumerate(visible):
            row_rect = self.mission_buttons[idx].rect
            # row background based on hover / selection
            if self.queued_mission == m.id:
                pygame.draw.rect(self.screen, (36, 48, 78), row_rect)
            elif self.mission_buttons[idx]._hover and self.mission_buttons[idx].enabled:
                pygame.draw.rect(self.screen, (24, 32, 56), row_rect)
            eff_rocket = effective_rocket(me, m)
            eff_cost = effective_launch_cost(me, m)
            eff_succ = effective_base_success(me, m)
            first_claimed = self.state.first_completed.get(m.id.value)
            first_txt = f"+{m.first_bonus} ({first_claimed})" if first_claimed else f"+{m.first_bonus}"
            tier_unlocked = me.is_tier_unlocked(m.tier)
            built = me.rocket_built(eff_rocket)
            affordable = me.budget >= eff_cost
            crew_ok = not m.manned or len(me.flight_ready_astronauts()) >= m.crew_size
            arch_ok = meets_architecture_prereqs(me, m)
            status_parts: list[str] = []
            status_color = DIM
            row_color = FG
            if not tier_unlocked:
                status_parts.append(f"{program_name(m.tier, me.side)} LOCKED")
                row_color = DIM
            elif m.id == MissionId.MANNED_LUNAR_LANDING and me.architecture is None:
                status_parts.append("choose arch")
            elif not arch_ok:
                status_parts.append("arch prereq")
            elif not built:
                status_parts.append(f"need {eff_rocket.value}")
            elif not affordable:
                status_parts.append("low funds")
            elif not crew_ok:
                status_parts.append(f"need {m.crew_size} astro")
            else:
                status_parts.append("READY")
                status_color = GREEN
            if self.queued_mission == m.id:
                status_parts.append("[QUEUED]")
                status_color = HIGHLIGHT
            status = " ".join(status_parts) or "-"
            mtype = "manned" if m.manned else "unmanned"
            rocket_display = rocket_display_name(eff_rocket, me.side)
            prog_display = program_name(m.tier, me.side)
            key_label = key_labels[idx] if idx < len(key_labels) else "?"
            row = (
                f"{key_label:<4}{prog_display:<10}{m.name:<22}{mtype:<7}{rocket_display:<10}"
                f"{eff_cost:<6}{int(eff_succ * 100):<7}{m.prestige_success:<8}"
                f"{first_txt:<8}"
            )
            row_y = row_rect.y + 6
            draw_text(self.screen, row, (40, row_y), size=14, color=row_color)
            draw_text(self.screen, status, (40 + 870, row_y), size=14, color=status_color)

        # Architecture panel (only meaningful after Tier 3 unlocks)
        panel_y = 720
        pygame.draw.rect(self.screen, PANEL, (20, panel_y - 6, 1160, 126), border_radius=6)
        pygame.draw.rect(self.screen, BORDER, (20, panel_y - 6, 1160, 126), 1, border_radius=6)
        draw_text(self.screen, "LUNAR MISSION ARCHITECTURE",
                  (36, panel_y), size=16, color=HIGHLIGHT, bold=True)
        if not me.is_tier_unlocked(ProgramTier.THREE):
            draw_text(
                self.screen,
                f"Locked until you reach {program_name(ProgramTier.THREE, me.side)}.",
                (36, panel_y + 26), size=14, color=DIM,
            )
        elif me.architecture:
            try:
                arch = Architecture(me.architecture)
                draw_text(
                    self.screen,
                    f"Committed: {arch.value} — {ARCHITECTURE_FULL_NAMES[arch]}  "
                    f"(cost {ARCHITECTURE_COST_DELTA[arch]:+} MB, success {ARCHITECTURE_SUCCESS_DELTA[arch]:+.0%})",
                    (36, panel_y + 26), size=14, color=HIGHLIGHT,
                )
            except ValueError:
                pass
        else:
            draw_text(
                self.screen,
                "Commit one — permanent choice. EOR is the only path that doesn't need a Heavy rocket.",
                (36, panel_y + 26), size=14, color=FG,
            )

        # Objectives strip — only when the queued mission has any.
        if self.queued_mission is not None:
            objs = objectives_for(self.queued_mission)
            if objs:
                self._render_objective_toggles(me, objs, (20, panel_y + 68))

    # --- Log tab --------------------------------------------------------
    def _render_tab_log(self) -> None:
        assert self.state is not None
        draw_text(self.screen, "EVENT LOG", (30, CONTENT_TOP + 10),
                  size=26, color=HIGHLIGHT, bold=True)
        pygame.draw.rect(self.screen, PANEL, (20, CONTENT_TOP + 60, 1160, 730),
                         border_radius=6)
        pygame.draw.rect(self.screen, BORDER, (20, CONTENT_TOP + 60, 1160, 730), 1,
                         border_radius=6)
        y = CONTENT_TOP + 80
        # Show up to ~30 most-recent lines (oldest first within that window).
        for line in self.state.log[-30:]:
            draw_text(self.screen, line, (36, y), size=15, color=FG)
            y += 22

    def _render_objective_toggles(self, me: Player, objs: tuple, pos: tuple[int, int]) -> None:
        x, y = pos
        # Shared hotkey map for the hint labels; flipped order matches OBJECTIVE_KEYS.
        hint_by_obj = {
            ObjectiveId.EVA: "V",
            ObjectiveId.DOCKING: "B",
            ObjectiveId.LONG_DURATION: "N",
            ObjectiveId.MOONWALK: "M",
            ObjectiveId.SAMPLE_RETURN: ",",
        }
        draw_text(self.screen, "OPTIONAL OBJECTIVES (toggle before submit)",
                  (x + 16, y), size=14, color=HIGHLIGHT, bold=True)
        cy = y + 24
        for obj in objs:
            queued = obj.id in self.queued_objectives
            prereq_missing = (
                obj.requires_module is not None
                and not me.module_built(obj.requires_module)
            )
            risk = ""
            if obj.fail_ship_loss_chance > 0:
                risk = f" [risk: {int(obj.fail_ship_loss_chance * 100)}% SHIP LOSS on fail]"
            elif obj.fail_crew_death_chance > 0:
                risk = f" [risk: {int(obj.fail_crew_death_chance * 100)}% crew death on fail]"
            marker = "[X]" if queued else "[ ]"
            if prereq_missing:
                marker = "[!]"
            color = HIGHLIGHT if queued else (RED if prereq_missing else FG)
            hint = hint_by_obj.get(obj.id, "?")
            line = (
                f"{marker} ({hint}) {obj.name}  "
                f"skill {obj.required_skill.value}, +{obj.prestige_bonus} prestige"
                f"{risk}"
            )
            if prereq_missing and obj.requires_module is not None:
                line += f"  — requires {obj.requires_module.value}"
            draw_text(self.screen, line, (x + 16, cy), size=14, color=color)
            cy += 20

    def _preview_crew(self, player: Player, mission) -> list[Astronaut]:
        pool = player.flight_ready_astronauts()
        if len(pool) < mission.crew_size:
            return []
        skill_key: Skill = mission.primary_skill or Skill.CAPSULE
        ranked = sorted(pool, key=lambda a: a.skill(skill_key), reverse=True)
        return ranked[:mission.crew_size]

    # --- briefing scene -------------------------------------------------
    def _render_briefing(self) -> None:
        assert self.state is not None
        me = self._me()
        if me is None or self.queued_mission is None:
            return
        from baris.resolver import (
            _crew_bonus,
            effective_base_success,
            effective_launch_cost,
            effective_rocket,
        )
        from baris.state import RELIABILITY_SWING_PER_POINT, objectives_for

        mission = MISSIONS_BY_ID[self.queued_mission]
        eff_rocket = effective_rocket(me, mission)
        eff_cost = effective_launch_cost(me, mission)
        base_succ = effective_base_success(me, mission)
        reliability = me.rocket_reliability(eff_rocket)
        rel_bonus = (reliability - 50) * RELIABILITY_SWING_PER_POINT
        crew: list[Astronaut] = []
        crew_b = 0.0
        if mission.manned:
            crew = self._preview_crew(me, mission)
            crew_b = _crew_bonus(crew, mission)
        effective = base_succ + crew_b + rel_bonus

        # Ribbon header
        pygame.draw.rect(self.screen, BG_DEEP, (0, 0, WINDOW_SIZE[0], 80))
        pygame.draw.rect(self.screen, BORDER, (0, 80, WINDOW_SIZE[0], 1))
        draw_text(self.screen, "FLIGHT PLAN", (30, 12), size=26, color=HIGHLIGHT, bold=True)
        draw_text(
            self.screen,
            f"{self.state.season.value} {self.state.year}  —  "
            f"{me.username} [{me.side.value if me.side else '?'}]",
            (30, 48), size=16, color=DIM,
        )

        # Main panel
        panel = pygame.Rect(40, 110, WINDOW_SIZE[0] - 80, 730)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=8)
        pygame.draw.rect(self.screen, BORDER, panel, 1, border_radius=8)

        x, y = panel.x + 30, panel.y + 26
        draw_text(self.screen, mission.name.upper(), (x, y), size=34,
                  color=side_color(me.side), bold=True)
        y += 54
        rocket_label = rocket_display_name(eff_rocket, me.side)
        draw_text(
            self.screen,
            f"Rocket:  {eff_rocket.value} class — {rocket_label}  "
            f"(reliability {reliability}%)",
            (x, y), size=18, color=FG,
        )
        y += 30
        draw_text(self.screen, f"Launch cost:  {eff_cost} MB",
                  (x, y), size=18, color=FG)
        y += 34

        if mission.manned:
            crew_line = ", ".join(a.name for a in crew) if crew else "(roster too small)"
            draw_text(self.screen, f"Crew ({mission.crew_size}):  {crew_line}",
                      (x, y), size=18, color=FG)
            if mission.primary_skill and crew:
                avg = sum(a.skill(mission.primary_skill) for a in crew) / len(crew)
                y += 24
                draw_text(
                    self.screen,
                    f"  Avg {mission.primary_skill.value.capitalize()}: {avg:.0f}",
                    (x, y), size=14, color=DIM,
                )
            y += 34

        # Odds breakdown
        draw_text(self.screen, "Odds", (x, y), size=20, color=HIGHLIGHT, bold=True)
        y += 28
        draw_text(self.screen, f"  Base success         {base_succ:+.2f}",
                  (x, y), size=16, color=FG)
        y += 22
        if mission.manned:
            draw_text(self.screen, f"  Crew bonus           {crew_b:+.2f}",
                      (x, y), size=16, color=FG)
            y += 22
        draw_text(self.screen, f"  Reliability bonus    {rel_bonus:+.3f}",
                  (x, y), size=16, color=FG)
        y += 22
        draw_text(self.screen, "  " + "-" * 44, (x, y), size=16, color=DIM)
        y += 22
        draw_text(
            self.screen,
            f"  Effective chance     {effective:.2f}   "
            f"(~{int(max(0, min(1, effective)) * 100)}% success)",
            (x, y), size=18,
            color=GREEN if effective >= 0.6 else HIGHLIGHT if effective >= 0.4 else RED,
            bold=True,
        )
        y += 38

        # Architecture line (only for manned lunar landing)
        if mission.id == MissionId.MANNED_LUNAR_LANDING and me.architecture:
            try:
                arch = Architecture(me.architecture)
                draw_text(
                    self.screen,
                    f"Architecture: {arch.value} ({ARCHITECTURE_FULL_NAMES[arch]})  "
                    f"— success {ARCHITECTURE_SUCCESS_DELTA[arch]:+.0%}, "
                    f"cost {ARCHITECTURE_COST_DELTA[arch]:+} MB",
                    (x, y), size=15, color=HIGHLIGHT,
                )
                y += 30
            except ValueError:
                pass

        # Objectives
        objs = objectives_for(mission.id)
        queued_objs = [o for o in objs if o.id in self.queued_objectives]
        if queued_objs:
            y += 8
            draw_text(self.screen, "Opt-in objectives", (x, y),
                      size=20, color=HIGHLIGHT, bold=True)
            y += 28
            for obj in queued_objs:
                risk = ""
                if obj.fail_ship_loss_chance > 0:
                    risk = f"  (fail: {int(obj.fail_ship_loss_chance*100)}% ship loss)"
                elif obj.fail_crew_death_chance > 0:
                    risk = f"  (fail: {int(obj.fail_crew_death_chance*100)}% crew death)"
                else:
                    risk = "  (fail: no casualties)"
                risk_color = RED if risk.endswith("ship loss)") else (
                    HIGHLIGHT if "crew death" in risk else DIM
                )
                line = f"  - {obj.name:<22} {obj.required_skill.value:<10} base {obj.base_success:.0%}  +{obj.prestige_bonus} prestige"
                draw_text(self.screen, line, (x, y), size=15, color=FG)
                draw_text(self.screen, risk, (x + 700, y), size=15, color=risk_color)
                y += 22
        elif mission.manned and objs:
            y += 8
            draw_text(
                self.screen,
                "(No opt-in objectives queued — nominal flight only.)",
                (x, y), size=14, color=DIM,
            )
            y += 22

        # Footer hint + buttons
        draw_text(
            self.screen,
            "Abort to go back to the hub. LAUNCH commits the turn.",
            (panel.x + 30, panel.bottom - 40), size=14, color=DIM,
        )
        for btn in self.briefing_buttons:
            btn.draw(self.screen)

    # --- launching scene (ascend + result) ------------------------------
    def _render_launching(self) -> None:
        if not self.report_queue:
            return
        report = self.report_queue[self.report_idx]
        me = self._me()
        is_own = bool(me and me.side and report.side == me.side.value)
        # Solid deep background.
        self.screen.fill((4, 6, 14))
        if self.launch_phase == "ascend":
            self._render_launch_ascend(report, is_own)
        else:
            self._render_launch_result(report, is_own)
        # Progress indicator + continue hint
        total = len(self.report_queue)
        pos = self.report_idx + 1
        draw_text(
            self.screen,
            f"Mission {pos} of {total}",
            (24, 12), size=14, color=DIM,
        )
        hint = (
            "Space / Enter to skip"
            if self.launch_phase == "ascend"
            else "Space / Enter for next"
        )
        draw_text_centered(
            self.screen, hint, (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] - 30),
            size=14, color=DIM,
        )
        for btn in self.launching_buttons:
            btn.draw(self.screen)

    def _render_launch_ascend(self, report: LaunchReport, is_own: bool) -> None:
        cx = WINDOW_SIZE[0] // 2
        elapsed = pygame.time.get_ticks() - self.launch_phase_start_ms
        # Header
        who = "YOUR LAUNCH" if is_own else f"OPPONENT ({report.side}) LAUNCH"
        draw_text_centered(
            self.screen, who, (cx, 80),
            size=22, color=HIGHLIGHT if is_own else DIM, bold=True,
        )
        draw_text_centered(
            self.screen, report.mission_name.upper(), (cx, 120),
            size=42, color=FG, bold=True,
        )
        draw_text_centered(
            self.screen, f"Rocket: {report.rocket}  —  {report.username}",
            (cx, 170), size=18, color=DIM,
        )

        # Countdown sequence.
        if elapsed < 600:
            countdown = "T-3"
        elif elapsed < 1200:
            countdown = "T-2"
        elif elapsed < 1800:
            countdown = "T-1"
        else:
            countdown = "LIFTOFF"
        text_color = HIGHLIGHT if countdown != "LIFTOFF" else GREEN
        draw_text_centered(
            self.screen, countdown, (cx, 260),
            size=96, color=text_color, bold=True,
        )

        # Rocket position: sits on the pad through the countdown, rises
        # during the LIFTOFF phase. Pad is chosen so the body + fins clear
        # the Continue button at the bottom of the screen.
        pad_y = 700
        apex_y = 180
        if elapsed < 1800:
            rocket_y = pad_y
            flame_on = False
        else:
            t = (elapsed - 1800) / max(1, ASCEND_DURATION_MS - 1800)
            t = max(0.0, min(1.0, t))
            rocket_y = int(pad_y + (apex_y - pad_y) * t)
            flame_on = True
        self._draw_launch_rocket(cx, rocket_y, flame_on)
        # Ground line
        pygame.draw.line(self.screen, (40, 50, 70),
                         (0, pad_y + 64), (WINDOW_SIZE[0], pad_y + 64), 2)

    def _draw_launch_rocket(self, cx: int, tip_y: int, flame: bool) -> None:
        """Simple rocket silhouette. `tip_y` is the y-coordinate of the nose cone."""
        body_w = 26
        body_h = 90
        # Body (rectangle)
        body = pygame.Rect(cx - body_w // 2, tip_y + 22, body_w, body_h)
        pygame.draw.rect(self.screen, (220, 220, 235), body)
        pygame.draw.rect(self.screen, (120, 130, 150), body, 1)
        # Nose cone
        pygame.draw.polygon(self.screen, (220, 220, 235), [
            (cx, tip_y),
            (cx - body_w // 2, tip_y + 24),
            (cx + body_w // 2, tip_y + 24),
        ])
        # Fins
        pygame.draw.polygon(self.screen, (180, 60, 60), [
            (cx - body_w // 2, body.bottom - 20),
            (cx - body_w // 2 - 14, body.bottom),
            (cx - body_w // 2, body.bottom),
        ])
        pygame.draw.polygon(self.screen, (180, 60, 60), [
            (cx + body_w // 2, body.bottom - 20),
            (cx + body_w // 2 + 14, body.bottom),
            (cx + body_w // 2, body.bottom),
        ])
        # Window
        pygame.draw.circle(self.screen, ACCENT_USA, (cx, tip_y + 40), 5)
        pygame.draw.circle(self.screen, (60, 70, 100), (cx, tip_y + 40), 5, 1)
        if flame:
            now = pygame.time.get_ticks()
            flick = (now // 70) % 2  # two-frame flicker
            for color, h_off in (((240, 200, 90), 10), ((240, 120, 40), 22 + flick * 4)):
                pygame.draw.polygon(self.screen, color, [
                    (cx - body_w // 2 + 2, body.bottom + 1),
                    (cx + body_w // 2 - 2, body.bottom + 1),
                    (cx, body.bottom + h_off + 10),
                ])

    def _render_launch_result(self, report: LaunchReport, is_own: bool) -> None:
        cx = WINDOW_SIZE[0] // 2
        # Header
        who = "YOUR MISSION" if is_own else f"OPPONENT ({report.side})"
        draw_text_centered(self.screen, who, (cx, 70),
                           size=20, color=HIGHLIGHT if is_own else DIM, bold=True)
        draw_text_centered(self.screen, report.mission_name.upper(), (cx, 108),
                           size=32, color=FG, bold=True)
        draw_text_centered(
            self.screen,
            f"{report.username} [{report.side or '?'}]   Rocket: {report.rocket}",
            (cx, 148), size=16, color=DIM,
        )

        # Outcome banner
        if report.aborted:
            banner = "MISSION ABORTED"
            banner_color = DIM
            sub = report.abort_reason or "—"
        elif report.success:
            if report.ended_game:
                banner = "MOON LANDING"
                banner_color = HIGHLIGHT
            else:
                banner = "SUCCESS"
                banner_color = GREEN
            sub = (
                f"Effective {report.effective_success:.2f} — "
                f"FIRST!" if report.first_claimed else
                f"Effective {report.effective_success:.2f}"
            )
        else:
            banner = "FAILURE"
            banner_color = RED
            sub = f"Effective {report.effective_success:.2f} — roll did not clear"

        banner_rect = pygame.Rect(cx - 280, 190, 560, 90)
        pygame.draw.rect(self.screen, PANEL, banner_rect, border_radius=10)
        pygame.draw.rect(self.screen, banner_color, banner_rect, 3, border_radius=10)
        draw_text_centered(self.screen, banner, banner_rect.center,
                           size=56, color=banner_color, bold=True)
        draw_text_centered(self.screen, sub, (cx, banner_rect.bottom + 16),
                           size=16, color=DIM)

        # Detail panel
        panel = pygame.Rect(cx - 340, 310, 680, 500)
        pygame.draw.rect(self.screen, (14, 20, 38), panel, border_radius=8)
        pygame.draw.rect(self.screen, BORDER, panel, 1, border_radius=8)
        x, y = panel.x + 30, panel.y + 26

        if report.aborted:
            draw_text(self.screen, f"Reason: {report.abort_reason}",
                      (x, y), size=18, color=FG)
            return

        draw_text(self.screen, f"Prestige       {report.prestige_delta:+d}",
                  (x, y), size=18, color=FG, bold=True)
        y += 28
        if report.first_claimed:
            draw_text(self.screen, "  FIRST! bonus applied.",
                      (x, y), size=14, color=HIGHLIGHT)
            y += 22
        draw_text(
            self.screen,
            f"Reliability    {report.reliability_before}% → {report.reliability_after}%",
            (x, y), size=16, color=FG,
        )
        y += 26

        if report.crew:
            draw_text(self.screen, f"Crew           {', '.join(report.crew)}",
                      (x, y), size=16, color=FG)
            y += 26
        if report.deaths:
            draw_text(self.screen, f"KIA            {', '.join(report.deaths)}",
                      (x, y), size=16, color=RED, bold=True)
            y += 26
        if report.budget_cut:
            draw_text(self.screen, f"Funding cut    {report.budget_cut} MB",
                      (x, y), size=16, color=RED)
            y += 26

        if report.objectives:
            y += 8
            draw_text(self.screen, "Objectives", (x, y), size=18,
                      color=HIGHLIGHT, bold=True)
            y += 26
            for obj in report.objectives:
                if obj.skipped:
                    line = f"  - {obj.name}: skipped ({obj.skip_reason})"
                    color = DIM
                elif obj.ship_lost:
                    line = (f"  - {obj.name}: CATASTROPHIC FAILURE — "
                            f"KIA {', '.join(obj.deaths) or '?'}")
                    color = RED
                elif obj.success:
                    line = (f"  - {obj.name}: {obj.performer} succeeded "
                            f"({obj.prestige_delta:+d} prestige)")
                    color = GREEN
                elif obj.deaths:
                    line = (f"  - {obj.name}: {', '.join(obj.deaths)} lost "
                            f"({obj.prestige_delta:+d} prestige)")
                    color = RED
                else:
                    line = f"  - {obj.name}: failed (no casualties)"
                    color = DIM
                draw_text(self.screen, line, (x, y), size=14, color=color)
                y += 20

    # --- end ------------------------------------------------------------
    def _render_end(self) -> None:
        assert self.state is not None
        cx = WINDOW_SIZE[0] // 2
        title = f"{self.state.winner.value} WINS THE RACE" if self.state.winner else "GAME OVER"
        color = side_color(self.state.winner)
        draw_text_centered(self.screen, "THE SPACE RACE IS DECIDED", (cx, 120),
                           size=28, color=DIM, bold=True)
        draw_text_centered(self.screen, title, (cx, 190), size=48, color=color, bold=True)

        pygame.draw.rect(self.screen, PANEL, (cx - 450, 260, 900, 500), border_radius=8)
        pygame.draw.rect(self.screen, BORDER, (cx - 450, 260, 900, 500), 1, border_radius=8)
        draw_text(self.screen, "Mission log:", (cx - 430, 280), size=16, color=DIM)
        y = 310
        for line in self.state.log[-16:]:
            draw_text(self.screen, line, (cx - 430, y), size=14, color=FG)
            y += 22
        for btn in self.end_buttons:
            btn.draw(self.screen)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def _translate_mouse_event(self, event: pygame.event.Event) -> pygame.event.Event:
        """Map mouse coordinates from real-window space to logical canvas
        space so buttons (which hit-test in canvas coords) fire correctly
        after the user resizes the window."""
        if event.type not in (
            pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
        ):
            return event
        win_w, win_h = self.window.get_size()
        if (win_w, win_h) == WINDOW_SIZE:
            return event
        cx, cy = WINDOW_SIZE
        sx, sy = event.pos
        tx = int(sx * cx / max(1, win_w))
        ty = int(sy * cy / max(1, win_h))
        fields: dict = {"pos": (tx, ty)}
        if event.type == pygame.MOUSEMOTION:
            fields["rel"] = event.rel
            fields["buttons"] = event.buttons
        else:
            fields["button"] = event.button
        return pygame.event.Event(event.type, fields)

    def run(self) -> None:
        running = True
        while running:
            self.pump_network()
            for event in pygame.event.get():
                event = self._translate_mouse_event(event)
                if not self.handle_event(event):
                    running = False
                    break
            self.render()
            self.clock.tick(FPS)
        pygame.quit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="ws://localhost:8765")
    parser.add_argument("--name", default="Player")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    Client(args.server, args.name).run()


if __name__ == "__main__":
    main()
