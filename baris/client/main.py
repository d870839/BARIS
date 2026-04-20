from __future__ import annotations

import argparse
import logging
from typing import Any

import pygame

from baris import protocol
from baris.client import ui
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

# Scene names
MENU = "menu"
CONNECTING = "connecting"
LOBBY = "lobby"
GAME = "game"
ENDED = "ended"


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

        # turn-input state
        self.rd_rocket: Rocket = Rocket.LIGHT
        self.rd_spend: int = 10
        self.queued_mission: MissionId | None = None

        self.scene: str = MENU
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
        # Drop net and game state; start fresh on next "New Game".
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
        return {
            "rocket_light":  Button(pygame.Rect(30,  470, 100, 30), "Light",  key_hint="Q"),
            "rocket_medium": Button(pygame.Rect(140, 470, 100, 30), "Medium", key_hint="W"),
            "rocket_heavy":  Button(pygame.Rect(250, 470, 100, 30), "Heavy",  key_hint="E"),
            "spend_minus":   Button(pygame.Rect(370, 470, 30,  30), "-",      key_hint="Left"),
            "spend_plus":    Button(pygame.Rect(410, 470, 30,  30), "+",      key_hint="Right"),
            "arch_da":       Button(pygame.Rect(610, 470, 100, 30), "DA",     key_hint="A"),
            "arch_eor":      Button(pygame.Rect(720, 470, 100, 30), "EOR",    key_hint="S"),
            "arch_lsr":      Button(pygame.Rect(830, 470, 100, 30), "LSR",    key_hint="D"),
            "arch_lor":      Button(pygame.Rect(940, 470, 100, 30), "LOR",    key_hint="F"),
            "submit":        Button(pygame.Rect(30,  870, 240, 50), "SUBMIT TURN", key_hint="Enter"),
            "cancel":        Button(pygame.Rect(280, 870, 240, 50), "Cancel launch", key_hint="Esc"),
        }

    def _build_mission_buttons(self) -> list[Button]:
        # One row-shaped button per mission, aligned with the mission list rendering.
        top = 526
        row_h = 20
        row_w = 960
        x = 30
        buttons: list[Button] = []
        for i in range(len(MISSIONS)):
            buttons.append(Button(
                pygame.Rect(x, top + i * row_h, row_w, row_h),
                label="",  # row content is drawn separately
                key_hint=None,
            ))
        return buttons

    def _build_end_buttons(self) -> list[Button]:
        cx = WINDOW_SIZE[0] // 2
        return [Button(pygame.Rect(cx - 150, 700, 300, 55), "RETURN TO MENU")]

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
                # Transition scenes based on phase.
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
    # Input
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
        # keyboard fallback
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

        # Architecture choice (buttons, enabled only when Tier 3 + not yet chosen).
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
            if btn.handle_event(event):
                self.net.send(protocol.CHOOSE_ARCHITECTURE, architecture=arch.value)

        # Rocket R&D target buttons — always enabled during your turn.
        editable = not me.turn_submitted
        rocket_btn_map = {
            "rocket_light":  Rocket.LIGHT,
            "rocket_medium": Rocket.MEDIUM,
            "rocket_heavy":  Rocket.HEAVY,
        }
        for key, rocket in rocket_btn_map.items():
            btn = self.game_buttons[key]
            btn.enabled = editable
            btn.selected = (self.rd_rocket == rocket)
            if btn.handle_event(event):
                self.rd_rocket = rocket

        # R&D spend +/-
        self.game_buttons["spend_minus"].enabled = editable
        self.game_buttons["spend_plus"].enabled = editable
        if self.game_buttons["spend_minus"].handle_event(event) and editable:
            self.rd_spend = max(0, self.rd_spend - 5)
        if self.game_buttons["spend_plus"].handle_event(event) and editable:
            self.rd_spend = min(me.budget, self.rd_spend + 5)

        # Submit / cancel
        self.game_buttons["submit"].enabled = editable
        self.game_buttons["cancel"].enabled = editable and self.queued_mission is not None
        if self.game_buttons["submit"].handle_event(event) and editable:
            self._submit_turn(me)
        if self.game_buttons["cancel"].handle_event(event):
            self.queued_mission = None

        # Mission rows
        for idx, btn in enumerate(self.mission_buttons):
            btn.enabled = editable
            if btn.handle_event(event) and editable and idx < len(MISSIONS):
                self.queued_mission = MISSIONS[idx].id

        # Keyboard fallbacks
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE and self.queued_mission is not None:
                self.queued_mission = None
                return True
            if can_pick_arch and event.key in ARCHITECTURE_KEYS:
                self.net.send(
                    protocol.CHOOSE_ARCHITECTURE,
                    architecture=ARCHITECTURE_KEYS[event.key].value,
                )
                return True
            if not editable:
                return True
            if event.key in ROCKET_KEYS:
                self.rd_rocket = ROCKET_KEYS[event.key]
            elif event.key == pygame.K_LEFT:
                self.rd_spend = max(0, self.rd_spend - 5)
            elif event.key == pygame.K_RIGHT:
                self.rd_spend = min(me.budget, self.rd_spend + 5)
            elif event.key in MISSION_KEYS:
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
    # Render
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
        draw_text(self.screen, self.status, (30, WINDOW_SIZE[1] - 28), size=14, color=DIM)
        pygame.display.flip()

    # --- menu -----------------------------------------------------------
    def _render_menu(self) -> None:
        cx = WINDOW_SIZE[0] // 2
        # dark backdrop stripe at the top for drama
        pygame.draw.rect(self.screen, BG_DEEP, (0, 0, WINDOW_SIZE[0], 320))
        pygame.draw.rect(self.screen, BORDER, (0, 318, WINDOW_SIZE[0], 2))

        draw_text_centered(self.screen, "BARIS", (cx, 140), size=84, color=HIGHLIGHT, bold=True)
        draw_text_centered(self.screen, "Race Into Space", (cx, 210), size=28, color=FG)
        draw_text_centered(
            self.screen,
            "A 2-player online remake — 1957-1977",
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

        draw_text(
            self.screen,
            f"{self.state.season.value} {self.state.year}",
            (30, 20), size=28, color=HIGHLIGHT, bold=True,
        )
        draw_text(
            self.screen,
            "First manned lunar landing OR 40 prestige wins",
            (240, 32), size=14, color=DIM,
        )

        if me:
            self._draw_player_panel("YOU", me, (30, 70))
        if opp:
            self._draw_player_panel("OPPONENT", opp, (610, 70))

        self._render_mission_list((30, 510))

        if me and not me.turn_submitted:
            self._render_turn_controls((30, 760), me)
        elif me and me.turn_submitted:
            draw_text(self.screen, "Waiting for opponent...", (30, 780), size=20, color=DIM)

        self._render_log((610, 760))

        # draw all game buttons on top of panels
        for btn in self.game_buttons.values():
            btn.draw(self.screen)

    def _draw_player_panel(self, label: str, player: Player, pos: tuple[int, int]) -> None:
        x, y = pos
        color = side_color(player.side)
        pygame.draw.rect(self.screen, PANEL, (x - 8, y - 6, 570, 390), border_radius=6)
        pygame.draw.rect(self.screen, BORDER, (x - 8, y - 6, 570, 390), 1, border_radius=6)
        draw_text(self.screen, f"{label}: {player.username}", (x, y), size=18, color=color)
        side_label = player.side.value if player.side else "?"
        draw_text(self.screen, f"Side:      {side_label}", (x, y + 28), size=18, color=FG)
        draw_text(self.screen, f"Budget:    {player.budget} MB", (x, y + 52), size=18, color=FG)
        draw_text(self.screen, f"Prestige:  {player.prestige}", (x, y + 76), size=18, color=FG)
        unlocked_order = [t for t in (ProgramTier.ONE, ProgramTier.TWO, ProgramTier.THREE)
                          if player.is_tier_unlocked(t)]
        programs = ", ".join(program_name(t, player.side) for t in unlocked_order) or "-"
        draw_text(self.screen, f"Programs:  {programs}", (x, y + 100), size=14, color=FG)

        if player.is_tier_unlocked(ProgramTier.THREE):
            if player.architecture:
                try:
                    arch = Architecture(player.architecture)
                    arch_label = f"Lunar arch: {arch.value} ({ARCHITECTURE_FULL_NAMES[arch]})"
                    draw_text(self.screen, arch_label, (x, y + 120), size=14, color=HIGHLIGHT)
                except ValueError:
                    pass
            elif player.player_id == self.player_id:
                draw_text(self.screen, "Lunar arch: CHOOSE ONE (A/S/D/F or buttons)",
                          (x, y + 120), size=14, color=RED)
            else:
                draw_text(self.screen, "Lunar arch: (opponent choosing)",
                          (x, y + 120), size=14, color=DIM)

        draw_text(self.screen, "R&D progress:", (x, y + 148), size=14, color=DIM)
        ry = y + 168
        for r in Rocket:
            self._draw_rd_bar(r, player, (x, ry))
            ry += 22

        draw_text(self.screen, "Astronauts:", (x, y + 246), size=14, color=DIM)
        ay = y + 266
        for astro in player.astronauts:
            self._draw_astronaut_row(astro, (x, ay))
            ay += 18

    def _draw_rd_bar(self, rocket: Rocket, player: Player, pos: tuple[int, int]) -> None:
        x, y = pos
        target = RD_TARGETS[rocket]
        progress = player.rd_progress(rocket)
        pct = progress / target
        bar_w = 220
        display = rocket_display_name(rocket, player.side)
        label = f"{display:<10} {progress:3}/{target:3}"
        draw_text(self.screen, label, (x, y), size=14, color=FG)
        bar_x = x + 200
        pygame.draw.rect(self.screen, DIM, (bar_x, y + 3, bar_w, 12), 1)
        pygame.draw.rect(self.screen, GREEN if pct >= 1.0 else HIGHLIGHT,
                         (bar_x + 1, y + 4, int((bar_w - 2) * pct), 10))
        safety = player.safety(rocket)
        if player.rocket_built(rocket):
            safety_color = GREEN if safety >= 70 else HIGHLIGHT if safety >= 40 else RED
            draw_text(self.screen, f"saf {safety:3}%",
                      (bar_x + bar_w + 10, y), size=14, color=safety_color)
        else:
            draw_text(self.screen, "saf --", (bar_x + bar_w + 10, y), size=14, color=DIM)

    def _draw_astronaut_row(self, astro: Astronaut, pos: tuple[int, int]) -> None:
        x, y = pos
        alive = astro.active
        color = FG if alive else RED
        status = " " if alive else "+"  # "+" marker for KIA
        row = (
            f"{status} {astro.name:<12} "
            f"Cap{astro.capsule:3} Eva{astro.eva:3} End{astro.endurance:3} Cmd{astro.command:3}"
        )
        draw_text(self.screen, row, (x, y), size=14, color=color)

    def _render_mission_list(self, pos: tuple[int, int]) -> None:
        assert self.state is not None
        me = self._me()
        x, y = pos
        draw_text(self.screen, "MISSIONS", (x, y), size=28, color=HIGHLIGHT, bold=True)
        header = (
            f"{'#':<4}{'Program':<10}{'Mission':<22}{'Type':<7}{'Rocket':<10}{'Cost':<6}"
            f"{'Succ%':<7}{'Presti':<8}{'First':<8}Status"
        )
        draw_text(self.screen, header, (x, y + 36), size=14, color=DIM)
        from baris.resolver import (
            effective_base_success,
            effective_launch_cost,
            effective_rocket,
            meets_architecture_prereqs,
        )
        key_labels = [str(i + 1) for i in range(9)] + ["0", "-"]
        for idx, m in enumerate(MISSIONS):
            row_rect = self.mission_buttons[idx].rect if idx < len(self.mission_buttons) else None
            # highlight the row on hover / selection
            if row_rect is not None:
                if self.queued_mission == m.id:
                    pygame.draw.rect(self.screen, (36, 48, 78), row_rect)
                elif self.mission_buttons[idx]._hover and self.mission_buttons[idx].enabled:
                    pygame.draw.rect(self.screen, (24, 32, 56), row_rect)
            eff_rocket = effective_rocket(me, m) if me else m.rocket
            eff_cost = effective_launch_cost(me, m) if me else m.launch_cost
            eff_succ = effective_base_success(me, m) if me else m.base_success
            first_claimed = self.state.first_completed.get(m.id.value)
            first_txt = f"+{m.first_bonus} ({first_claimed})" if first_claimed else f"+{m.first_bonus}"
            status_parts: list[str] = []
            status_color = DIM
            row_color = FG
            if me:
                tier_unlocked = me.is_tier_unlocked(m.tier)
                built = me.rocket_built(eff_rocket)
                affordable = me.budget >= eff_cost
                crew_ok = not m.manned or len(me.active_astronauts()) >= m.crew_size
                arch_ok = meets_architecture_prereqs(me, m)
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
            my_side = me.side if me else None
            rocket_display = rocket_display_name(eff_rocket, my_side)
            prog_display = program_name(m.tier, my_side)
            key_label = key_labels[idx] if idx < len(key_labels) else "?"
            row = (
                f"{key_label:<4}{prog_display:<10}{m.name:<22}{mtype:<7}{rocket_display:<10}"
                f"{eff_cost:<6}{int(eff_succ * 100):<7}{m.prestige_success:<8}"
                f"{first_txt:<8}"
            )
            draw_text(self.screen, row, (x, y + 56 + idx * 20), size=14, color=row_color)
            draw_text(self.screen, status, (x + 870, y + 56 + idx * 20), size=14, color=status_color)

    def _render_turn_controls(self, pos: tuple[int, int], me: Player) -> None:
        x, y = pos
        pygame.draw.rect(self.screen, PANEL, (x - 8, y - 6, 570, 145), border_radius=6)
        pygame.draw.rect(self.screen, BORDER, (x - 8, y - 6, 570, 145), 1, border_radius=6)
        draw_text(self.screen, "YOUR TURN", (x, y), size=22, color=HIGHLIGHT, bold=True)
        spend = min(self.rd_spend, me.budget)
        draw_text(
            self.screen,
            f"R&D target: {rocket_display_name(self.rd_rocket, me.side)}   "
            f"spend: {spend} MB",
            (x, y + 30), size=16, color=FG,
        )
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
            crew_note = ""
            if m.manned:
                crew = self._preview_crew(me, m)
                if crew:
                    effective += _crew_bonus(crew, m)
                    crew_note = f"  crew: {', '.join(a.name for a in crew)}"
                else:
                    crew_note = "  crew: NONE (will abort)"
            draw_text(
                self.screen,
                f"Launching: {m.name}  cost {eff_cost} MB, {int(effective * 100)}%",
                (x, y + 56), size=16, color=GREEN,
            )
            if crew_note:
                draw_text(self.screen, crew_note.strip(), (x, y + 78), size=14, color=FG)
        else:
            draw_text(self.screen, "No launch queued this turn.",
                      (x, y + 56), size=16, color=DIM)

    def _preview_crew(self, player: Player, mission) -> list[Astronaut]:
        active = player.active_astronauts()
        if len(active) < mission.crew_size:
            return []
        skill_key: Skill = mission.primary_skill or Skill.COMMAND
        ranked = sorted(active, key=lambda a: a.skill(skill_key), reverse=True)
        return ranked[:mission.crew_size]

    def _render_log(self, pos: tuple[int, int]) -> None:
        assert self.state is not None
        x, y = pos
        pygame.draw.rect(self.screen, PANEL, (x - 8, y - 6, 570, 145), border_radius=6)
        pygame.draw.rect(self.screen, BORDER, (x - 8, y - 6, 570, 145), 1, border_radius=6)
        draw_text(self.screen, "LOG:", (x, y), size=14, color=DIM)
        ly = y + 20
        for line in self.state.log[-7:]:
            draw_text(self.screen, line, (x, ly), size=14, color=FG)
            ly += 18

    # --- end ------------------------------------------------------------
    def _render_end(self) -> None:
        assert self.state is not None
        cx = WINDOW_SIZE[0] // 2
        title = f"{self.state.winner.value} WINS THE RACE" if self.state.winner else "GAME OVER"
        color = side_color(self.state.winner)
        draw_text_centered(self.screen, "THE SPACE RACE IS DECIDED", (cx, 120),
                           size=28, color=DIM, bold=True)
        draw_text_centered(self.screen, title, (cx, 190), size=48, color=color, bold=True)

        pygame.draw.rect(self.screen, PANEL, (cx - 450, 260, 900, 400), border_radius=8)
        pygame.draw.rect(self.screen, BORDER, (cx - 450, 260, 900, 400), 1, border_radius=8)
        draw_text(self.screen, "Mission log:", (cx - 430, 280), size=16, color=DIM)
        y = 310
        for line in self.state.log[-12:]:
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
