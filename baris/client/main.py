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
    Button,
    DIM,
    FG,
    GREEN,
    HIGHLIGHT,
    MUTED,
    PANEL,
    RED,
    draw_text,
    draw_text_centered,
)
from baris.state import (
    ARCHITECTURE_COST_DELTA,
    ARCHITECTURE_FULL_NAMES,
    ARCHITECTURE_SUCCESS_DELTA,
    MISSIONS,
    MISSIONS_BY_ID,
    Architecture,
    Astronaut,
    GameState,
    MissionId,
    Phase,
    Player,
    ProgramTier,
    RD_TARGETS,
    Rocket,
    Side,
    Skill,
    program_name,
    rocket_display_name,
)

log = logging.getLogger("baris.client")

WINDOW_SIZE = (1200, 940)
FPS = 60

ROCKET_KEYS = {pygame.K_q: Rocket.LIGHT, pygame.K_w: Rocket.MEDIUM, pygame.K_e: Rocket.HEAVY}
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
ENDED = "ended"

# Tabs (within GAME scene)
TAB_OVERVIEW   = "overview"
TAB_RD         = "rd"
TAB_ASTRONAUTS = "astronauts"
TAB_MISSIONS   = "missions"
TAB_LOG        = "log"

TAB_KEYS = {
    pygame.K_F1: TAB_OVERVIEW,
    pygame.K_F2: TAB_RD,
    pygame.K_F3: TAB_ASTRONAUTS,
    pygame.K_F4: TAB_MISSIONS,
    pygame.K_F5: TAB_LOG,
}

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
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        self.clock = pygame.time.Clock()

        self.server_url = server_url
        self.username = username
        self.net: NetClient | None = None

        self.state: GameState | None = None
        self.player_id: str | None = None
        self.status = ""
        self.joined_sent = False

        self.rd_rocket: Rocket = Rocket.LIGHT
        self.rd_spend: int = 10
        self.queued_mission: MissionId | None = None

        self.scene: str = MENU
        self.active_tab: str = TAB_OVERVIEW
        self.menu_buttons = self._build_menu_buttons()
        self.lobby_buttons: list[Button] = []
        self.game_buttons: dict[str, Button] = {}
        self.mission_buttons: list[Button] = []
        self.end_buttons: list[Button] = []

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
        self.status = ""
        self.scene = MENU

    def _enter_lobby(self) -> None:
        self.scene = LOBBY
        self.lobby_buttons = self._build_lobby_buttons()

    def _enter_game(self) -> None:
        self.scene = GAME
        self.active_tab = TAB_OVERVIEW
        self.game_buttons = self._build_game_buttons()
        self.mission_buttons = self._build_mission_buttons()

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
            ("tab_overview",   "OVERVIEW",   "F1"),
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
        btns["rocket_light"]  = Button(pygame.Rect(30,  rd_y, 120, 36), "Light",  key_hint="Q")
        btns["rocket_medium"] = Button(pygame.Rect(160, rd_y, 120, 36), "Medium", key_hint="W")
        btns["rocket_heavy"]  = Button(pygame.Rect(290, rd_y, 120, 36), "Heavy",  key_hint="E")
        btns["spend_minus"]   = Button(pygame.Rect(440, rd_y, 36,  36), "-",      key_hint="Left")
        btns["spend_plus"]    = Button(pygame.Rect(486, rd_y, 36,  36), "+",      key_hint="Right")

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
                if self.state.phase == Phase.PLAYING and self.scene != GAME:
                    self._enter_game()
                elif self.state.phase == Phase.ENDED and self.scene != ENDED:
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
            "tab_overview":   TAB_OVERVIEW,
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
                btn.selected = (self.rd_rocket == rocket)
                if btn.handle_event(event):
                    self.rd_rocket = rocket
            self.game_buttons["spend_minus"].enabled = editable
            self.game_buttons["spend_plus"].enabled = editable
            if self.game_buttons["spend_minus"].handle_event(event) and editable:
                self.rd_spend = max(0, self.rd_spend - 5)
            if self.game_buttons["spend_plus"].handle_event(event) and editable:
                self.rd_spend = min(me.budget, self.rd_spend + 5)

        if self.active_tab == TAB_MISSIONS:
            # Mission rows
            for idx, btn in enumerate(self.mission_buttons):
                btn.enabled = editable
                if btn.handle_event(event) and editable and idx < len(MISSIONS):
                    self.queued_mission = MISSIONS[idx].id
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
                self.rd_rocket = ROCKET_KEYS[event.key]
            elif self.active_tab == TAB_RD and event.key == pygame.K_LEFT:
                self.rd_spend = max(0, self.rd_spend - 5)
            elif self.active_tab == TAB_RD and event.key == pygame.K_RIGHT:
                self.rd_spend = min(me.budget, self.rd_spend + 5)
            elif self.active_tab == TAB_MISSIONS and event.key in MISSION_KEYS:
                idx = MISSION_KEYS[event.key]
                if idx < len(MISSIONS):
                    self.queued_mission = MISSIONS[idx].id
            elif event.key == pygame.K_RETURN:
                self._submit_turn(me)
        return True

    def _submit_turn(self, me: Player) -> None:
        self.net.send(
            protocol.END_TURN,
            rd_rocket=self.rd_rocket.value,
            rd_spend=min(self.rd_spend, me.budget),
            launch=self.queued_mission.value if self.queued_mission else None,
        )
        self.queued_mission = None

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
        elif self.scene == ENDED:
            self._render_end()
        draw_text(self.screen, self.status, (30, WINDOW_SIZE[1] - 22), size=14, color=DIM)
        pygame.display.flip()

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
                "spend_minus", "spend_plus",
            ):
                btn.draw(self.screen)
            elif self.active_tab == TAB_MISSIONS and key.startswith("arch_"):
                # Architecture tiles shown only when Tier 3 unlocked.
                if me is not None and me.is_tier_unlocked(ProgramTier.THREE):
                    btn.draw(self.screen)

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
        rd_line = (
            f"R&D:    {rocket_display_name(self.rd_rocket, me.side)}  "
            f"spend {min(self.rd_spend, me.budget)} MB"
        )
        draw_text(self.screen, rd_line, (20, 872), size=16, color=FG)
        if self.queued_mission is not None:
            m = MISSIONS_BY_ID[self.queued_mission]
            from baris.resolver import (
                _crew_bonus,
                effective_base_success,
                effective_launch_cost,
                effective_rocket,
            )
            from baris.state import SAFETY_SWING_PER_POINT
            eff_rocket = effective_rocket(me, m)
            eff_cost = effective_launch_cost(me, m)
            safety_bonus = (me.safety(eff_rocket) - 50) * SAFETY_SWING_PER_POINT
            effective = effective_base_success(me, m) + safety_bonus
            if m.manned:
                crew = self._preview_crew(me, m)
                if crew:
                    effective += _crew_bonus(crew, m)
            draw_text(
                self.screen,
                f"Launch: {m.name}  cost {eff_cost} MB, ~{int(effective * 100)}% success",
                (20, 898), size=16, color=GREEN,
            )
        else:
            draw_text(self.screen, "Launch: (none)", (20, 898), size=16, color=DIM)
        if me.turn_submitted:
            draw_text(self.screen, "Waiting for opponent...", (700, 882),
                      size=18, color=DIM, bold=True)

    def _render_active_tab(self, me: Player | None, opp: Player | None) -> None:
        if self.active_tab == TAB_OVERVIEW:
            self._render_tab_overview(me, opp)
        elif self.active_tab == TAB_RD:
            self._render_tab_rd(me, opp)
        elif self.active_tab == TAB_ASTRONAUTS:
            self._render_tab_astronauts(me, opp)
        elif self.active_tab == TAB_MISSIONS:
            self._render_tab_missions(me, opp)
        elif self.active_tab == TAB_LOG:
            self._render_tab_log()

    # --- overview tab ---------------------------------------------------
    def _render_tab_overview(self, me: Player | None, opp: Player | None) -> None:
        if me:
            self._draw_overview_card("YOU", me, (30, CONTENT_TOP + 20))
        if opp:
            self._draw_overview_card("OPPONENT", opp, (610, CONTENT_TOP + 20))
        # recent log
        assert self.state is not None
        pygame.draw.rect(self.screen, PANEL, (20, 550, 1160, 295), border_radius=6)
        pygame.draw.rect(self.screen, BORDER, (20, 550, 1160, 295), 1, border_radius=6)
        draw_text(self.screen, "RECENT EVENTS", (36, 562), size=16, color=DIM, bold=True)
        y = 590
        for line in self.state.log[-12:]:
            draw_text(self.screen, line, (36, y), size=14, color=FG)
            y += 20

    def _draw_overview_card(self, label: str, player: Player, pos: tuple[int, int]) -> None:
        x, y = pos
        color = side_color(player.side)
        pygame.draw.rect(self.screen, PANEL, (x - 8, y - 6, 570, 420), border_radius=6)
        pygame.draw.rect(self.screen, BORDER, (x - 8, y - 6, 570, 420), 1, border_radius=6)
        draw_text(self.screen, f"{label}: {player.username}", (x, y), size=20, color=color, bold=True)
        side_label = player.side.value if player.side else "?"
        draw_text(self.screen, f"Side:      {side_label}",           (x, y + 32), size=16, color=FG)
        draw_text(self.screen, f"Budget:    {player.budget} MB",     (x, y + 56), size=16, color=FG)
        draw_text(self.screen, f"Prestige:  {player.prestige}",      (x, y + 80), size=16, color=FG)
        active = len(player.active_astronauts())
        kia = len(player.astronauts) - active
        draw_text(
            self.screen,
            f"Roster:    {active} active"
            + (f", {kia} KIA" if kia else ""),
            (x, y + 104), size=16, color=FG,
        )
        unlocked = [program_name(t, player.side)
                    for t in (ProgramTier.ONE, ProgramTier.TWO, ProgramTier.THREE)
                    if player.is_tier_unlocked(t)]
        draw_text(self.screen, f"Programs:  {', '.join(unlocked) or '-'}", (x, y + 128), size=14, color=FG)
        if player.is_tier_unlocked(ProgramTier.THREE):
            if player.architecture:
                try:
                    arch = Architecture(player.architecture)
                    draw_text(
                        self.screen,
                        f"Arch:      {arch.value} ({ARCHITECTURE_FULL_NAMES[arch]})",
                        (x, y + 148), size=14, color=HIGHLIGHT,
                    )
                except ValueError:
                    pass
            elif player.player_id == self.player_id:
                draw_text(self.screen, "Arch:      CHOOSE ONE (Missions tab)",
                          (x, y + 148), size=14, color=RED)
            else:
                draw_text(self.screen, "Arch:      (opponent choosing)",
                          (x, y + 148), size=14, color=DIM)

        # mini R&D bars
        draw_text(self.screen, "R&D:", (x, y + 180), size=14, color=DIM)
        ry = y + 202
        for r in Rocket:
            self._draw_rd_bar(r, player, (x, ry), compact=True)
            ry += 22
        draw_text(self.screen, "Missions completed:", (x, y + 288), size=14, color=DIM)
        successes = player.mission_successes
        completed = sum(successes.values())
        draw_text(self.screen, f"  {completed} total", (x, y + 308), size=14, color=FG)
        # highlight firsts
        firsts: list[str] = []
        assert self.state is not None
        for mid, holder in self.state.first_completed.items():
            if player.side and holder == player.side.value:
                try:
                    firsts.append(MISSIONS_BY_ID[MissionId(mid)].name)
                except (ValueError, KeyError):
                    continue
        firsts_txt = ", ".join(firsts[:3]) if firsts else "none yet"
        if firsts and len(firsts) > 3:
            firsts_txt += ", ..."
        draw_text(self.screen, f"  firsts: {firsts_txt}",
                  (x, y + 328), size=14, color=HIGHLIGHT if firsts else DIM)

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
        # spend controls label (buttons themselves are drawn on top later)
        draw_text(self.screen, "Target rocket:", (30, 496), size=14, color=DIM)
        draw_text(self.screen, f"Spend per turn: {min(self.rd_spend, me.budget)} MB",
                  (560, 528), size=16, color=FG)
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
        target = RD_TARGETS[rocket]
        progress = player.rd_progress(rocket)
        pct = progress / target
        bar_w = 320 if not compact else 220
        size = 16 if not compact else 14
        display = rocket_display_name(rocket, player.side)
        label = f"{display:<10} {progress:3}/{target:3}"
        draw_text(self.screen, label, (x, y), size=size, color=FG)
        bar_x = x + 220 if not compact else x + 200
        bar_y = y + 3 if not compact else y + 3
        bar_h = 16 if not compact else 12
        pygame.draw.rect(self.screen, DIM, (bar_x, bar_y, bar_w, bar_h), 1)
        pygame.draw.rect(
            self.screen, GREEN if pct >= 1.0 else HIGHLIGHT,
            (bar_x + 1, bar_y + 1, int((bar_w - 2) * pct), bar_h - 2),
        )
        safety = player.safety(rocket)
        if player.rocket_built(rocket):
            safety_color = GREEN if safety >= 70 else HIGHLIGHT if safety >= 40 else RED
            draw_text(self.screen, f"saf {safety:3}%",
                      (bar_x + bar_w + 12, y), size=size - 2, color=safety_color)
        else:
            draw_text(self.screen, "saf --",
                      (bar_x + bar_w + 12, y), size=size - 2, color=DIM)

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
        header = f"{'Name':<14}{'Capsule':<10}{'EVA':<8}{'Endure':<9}{'Command':<10}Status"
        draw_text(self.screen, header, (cx, cy + 32), size=14, color=DIM)
        y = cy + 58
        for astro in me.astronauts:
            color = FG if astro.active else RED
            row = (
                f"{astro.name:<14}"
                f"{astro.capsule:<10}{astro.eva:<8}{astro.endurance:<9}{astro.command:<10}"
                f"{'active' if astro.active else 'KIA'}"
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
        )
        key_labels = [str(i + 1) for i in range(9)] + ["0", "-"]
        for idx, m in enumerate(MISSIONS):
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
            crew_ok = not m.manned or len(me.active_astronauts()) >= m.crew_size
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

    def _preview_crew(self, player: Player, mission) -> list[Astronaut]:
        active = player.active_astronauts()
        if len(active) < mission.crew_size:
            return []
        skill_key: Skill = mission.primary_skill or Skill.COMMAND
        ranked = sorted(active, key=lambda a: a.skill(skill_key), reverse=True)
        return ranked[:mission.crew_size]

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
    def run(self) -> None:
        running = True
        while running:
            self.pump_network()
            for event in pygame.event.get():
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
