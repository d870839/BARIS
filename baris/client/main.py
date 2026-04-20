from __future__ import annotations

import argparse
import logging

import pygame

from baris import protocol
from baris.client.net import NetClient
from baris.state import (
    ARCHITECTURE_COST_DELTA,
    ARCHITECTURE_FULL_NAMES,
    ARCHITECTURE_SUCCESS_DELTA,
    MISSIONS,
    MISSIONS_BY_ID,
    Architecture,
    Astronaut,
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
BG = (10, 14, 28)
PANEL = (20, 28, 48)
FG = (220, 225, 235)
DIM = (120, 130, 150)
ACCENT_USA = (80, 140, 220)
ACCENT_USSR = (220, 90, 90)
HIGHLIGHT = (240, 200, 90)
GREEN = (110, 200, 120)
RED = (220, 90, 90)

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
        self.font = pygame.font.SysFont("consolas", 18)
        self.font_big = pygame.font.SysFont("consolas", 28, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 14)

        self.username = username
        self.net = NetClient(server_url)
        self.net.start()

        from baris.state import GameState
        self.GameState = GameState
        self.state: GameState | None = None
        self.player_id: str | None = None
        self.status = f"Connecting to {server_url}..."
        self.joined_sent = False

        # turn-input state
        self.rd_rocket: Rocket = Rocket.LIGHT
        self.rd_spend: int = 10
        self.queued_mission: MissionId | None = None

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------
    def pump_network(self) -> None:
        if self.net.connected.is_set() and not self.joined_sent:
            self.net.send(protocol.JOIN, username=self.username)
            self.joined_sent = True
            self.status = "Joining..."

        for msg in self.net.drain_inbound():
            mtype = msg.get("type")
            if mtype == protocol.JOINED:
                self.player_id = msg["player_id"]
                self.state = self.GameState.from_dict(msg["state"])
                me = self._me()
                side_label = me.side.value if me and me.side else "?"
                self.status = f"Joined as {side_label}"
            elif mtype == protocol.STATE:
                self.state = self.GameState.from_dict(msg["state"])
                me = self._me()
                if me is None or me.turn_submitted:
                    self.queued_mission = None
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
        if event.type != pygame.KEYDOWN or self.state is None:
            return True
        me = self._me()
        if me is None:
            return True

        if self.state.phase == Phase.LOBBY:
            self._handle_lobby_key(event, me)
        elif self.state.phase == Phase.PLAYING:
            # Architecture choice is a one-time, non-turn action — allow it
            # even while waiting for the opponent to submit their turn.
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
            if not me.turn_submitted:
                self._handle_turn_key(event, me)
        return True

    def _handle_lobby_key(self, event: pygame.event.Event, me: Player) -> None:
        if event.key == pygame.K_1:
            self.net.send(protocol.CHOOSE_SIDE, side=Side.USA.value)
        elif event.key == pygame.K_2:
            self.net.send(protocol.CHOOSE_SIDE, side=Side.USSR.value)
        elif event.key == pygame.K_RETURN:
            self.net.send(protocol.READY if not me.ready else protocol.UNREADY)

    def _handle_turn_key(self, event: pygame.event.Event, me: Player) -> None:
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
        elif event.key == pygame.K_ESCAPE:
            self.queued_mission = None
        elif event.key == pygame.K_RETURN:
            self.net.send(
                protocol.END_TURN,
                rd_rocket=self.rd_rocket.value,
                rd_spend=min(self.rd_spend, me.budget),
                launch=self.queued_mission.value if self.queued_mission else None,
            )
            self.queued_mission = None

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def render(self) -> None:
        self.screen.fill(BG)
        if self.state is None:
            self._draw_text(self.status, (30, 30), self.font, DIM)
        elif self.state.phase == Phase.LOBBY:
            self._render_lobby()
        elif self.state.phase == Phase.PLAYING:
            self._render_game()
        elif self.state.phase == Phase.ENDED:
            self._render_end()
        self._draw_text(self.status, (30, WINDOW_SIZE[1] - 28), self.font_small, DIM)
        pygame.display.flip()

    def _render_lobby(self) -> None:
        assert self.state is not None
        self._draw_text("LOBBY", (30, 30), self.font_big, HIGHLIGHT)
        self._draw_text(
            "1 = pick USA   2 = pick USSR   Enter = ready/unready",
            (30, 70), self.font_small, DIM,
        )
        y = 110
        for p in self.state.players:
            label = f"{p.username}  [{p.side.value if p.side else '?'}]  {'READY' if p.ready else 'not ready'}"
            color = side_color(p.side) if p.player_id != self.player_id else HIGHLIGHT
            self._draw_text(label, (30, y), self.font, color)
            y += 30
        if len(self.state.players) < 2:
            self._draw_text("Waiting for opponent...", (30, y + 20), self.font, DIM)

    def _render_game(self) -> None:
        assert self.state is not None
        me = self._me()
        opp = self._opponent()

        self._draw_text(
            f"{self.state.season.value} {self.state.year}",
            (30, 20), self.font_big, HIGHLIGHT,
        )
        self._draw_text(
            "(first manned lunar landing OR 40 prestige wins)",
            (240, 32), self.font_small, DIM,
        )

        if me:
            self._draw_player_panel("YOU", me, (30, 70))
        if opp:
            self._draw_player_panel("OPPONENT", opp, (610, 70))

        self._render_mission_list((30, 470))

        turn_y = 760
        if me and not me.turn_submitted:
            self._render_turn_controls((30, turn_y), me)
        elif me and me.turn_submitted:
            self._draw_text("Waiting for opponent...", (30, turn_y), self.font, DIM)

        self._render_log((610, turn_y))

    def _render_end(self) -> None:
        assert self.state is not None
        msg = "GAME OVER"
        if self.state.winner is not None:
            msg = f"{self.state.winner.value} WINS THE RACE"
        self._draw_text(msg, (30, 30), self.font_big, HIGHLIGHT)
        y = 90
        for line in self.state.log[-10:]:
            self._draw_text(line, (30, y), self.font, FG)
            y += 22

    def _draw_player_panel(self, label: str, player: Player, pos: tuple[int, int]) -> None:
        x, y = pos
        color = side_color(player.side)
        pygame.draw.rect(self.screen, PANEL, (x - 8, y - 6, 570, 390), border_radius=6)
        self._draw_text(f"{label}: {player.username}", (x, y), self.font, color)
        side_label = player.side.value if player.side else "?"
        self._draw_text(f"Side:      {side_label}", (x, y + 28), self.font, FG)
        self._draw_text(f"Budget:    {player.budget} MB", (x, y + 52), self.font, FG)
        self._draw_text(f"Prestige:  {player.prestige}", (x, y + 76), self.font, FG)
        unlocked_order = [t for t in (ProgramTier.ONE, ProgramTier.TWO, ProgramTier.THREE)
                          if player.is_tier_unlocked(t)]
        programs = ", ".join(program_name(t, player.side) for t in unlocked_order) or "-"
        self._draw_text(f"Programs:  {programs}", (x, y + 100), self.font_small, FG)

        # Architecture display — only meaningful once Tier 3 unlocks.
        if player.is_tier_unlocked(ProgramTier.THREE):
            if player.architecture:
                try:
                    arch = Architecture(player.architecture)
                    label = f"Lunar arch: {arch.value} ({ARCHITECTURE_FULL_NAMES[arch]})"
                    self._draw_text(label, (x, y + 120), self.font_small, HIGHLIGHT)
                except ValueError:
                    pass
            elif player.player_id == self.player_id:
                self._draw_text(
                    "Lunar arch: A=DA S=EOR D=LSR F=LOR",
                    (x, y + 120), self.font_small, RED,
                )
            else:
                self._draw_text("Lunar arch: (opponent choosing)", (x, y + 120), self.font_small, DIM)

        self._draw_text("R&D progress:", (x, y + 128), self.font_small, DIM)
        ry = y + 148
        for r in Rocket:
            self._draw_rd_bar(r, player, (x, ry))
            ry += 22

        self._draw_text("Astronauts:", (x, y + 222), self.font_small, DIM)
        ay = y + 242
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
        self._draw_text(label, (x, y), self.font_small, FG)
        bar_x = x + 200
        pygame.draw.rect(self.screen, DIM, (bar_x, y + 3, bar_w, 12), 1)
        pygame.draw.rect(self.screen, GREEN if pct >= 1.0 else HIGHLIGHT,
                         (bar_x + 1, y + 4, int((bar_w - 2) * pct), 10))
        safety = player.safety(rocket)
        if player.rocket_built(rocket):
            safety_color = GREEN if safety >= 70 else HIGHLIGHT if safety >= 40 else RED
            self._draw_text(
                f"saf {safety:3}%",
                (bar_x + bar_w + 10, y),
                self.font_small,
                safety_color,
            )
        else:
            self._draw_text("saf --", (bar_x + bar_w + 10, y), self.font_small, DIM)

    def _draw_astronaut_row(self, astro: Astronaut, pos: tuple[int, int]) -> None:
        x, y = pos
        alive = astro.active
        color = FG if alive else RED
        status = " " if alive else "+"  # "+" marker for KIA
        row = (
            f"{status} {astro.name:<12} "
            f"Cap{astro.capsule:3} Eva{astro.eva:3} End{astro.endurance:3} Cmd{astro.command:3}"
        )
        self._draw_text(row, (x, y), self.font_small, color)

    def _render_mission_list(self, pos: tuple[int, int]) -> None:
        assert self.state is not None
        me = self._me()
        x, y = pos
        self._draw_text("MISSIONS", (x, y), self.font_big, HIGHLIGHT)
        header = (
            f"{'#':<4}{'Program':<10}{'Mission':<22}{'Type':<7}{'Rocket':<10}{'Cost':<6}"
            f"{'Succ%':<7}{'Presti':<8}{'First':<8}Status"
        )
        self._draw_text(header, (x, y + 36), self.font_small, DIM)
        ly = y + 56
        key_labels = [str(i + 1) for i in range(9)] + ["0", "-"]
        from baris.resolver import (
            effective_base_success,
            effective_launch_cost,
            effective_rocket,
            meets_architecture_prereqs,
        )
        for idx, m in enumerate(MISSIONS):
            first_claimed = self.state.first_completed.get(m.id.value)
            first_txt = f"+{m.first_bonus} ({first_claimed})" if first_claimed else f"+{m.first_bonus}"
            # Architecture-aware stats (only differ for manned lunar landing).
            eff_rocket = effective_rocket(me, m) if me else m.rocket
            eff_cost = effective_launch_cost(me, m) if me else m.launch_cost
            eff_succ = effective_base_success(me, m) if me else m.base_success
            status_parts: list[str] = []
            status_color = DIM
            if me:
                tier_unlocked = me.is_tier_unlocked(m.tier)
                built = me.rocket_built(eff_rocket)
                affordable = me.budget >= eff_cost
                crew_ok = True
                if m.manned:
                    active = me.active_astronauts()
                    crew_ok = len(active) >= m.crew_size
                arch_ok = meets_architecture_prereqs(me, m)
                if not tier_unlocked:
                    status_parts.append(f"{program_name(m.tier, me.side)} LOCKED")
                    status_color = DIM
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
            row_color = FG if me and me.is_tier_unlocked(m.tier) else DIM
            self._draw_text(row, (x, ly), self.font_small, row_color)
            self._draw_text(status, (x + 870, ly), self.font_small, status_color)
            ly += 20

    def _render_turn_controls(self, pos: tuple[int, int], me: Player) -> None:
        x, y = pos
        pygame.draw.rect(self.screen, PANEL, (x - 8, y - 6, 570, 165), border_radius=6)
        self._draw_text("YOUR TURN", (x, y), self.font_big, HIGHLIGHT)
        self._draw_text(
            "Q/W/E: R&D target    ←/→: adjust spend",
            (x, y + 34), self.font_small, DIM,
        )
        self._draw_text(
            "1-9,0,-: queue mission   Esc: cancel   Enter: submit",
            (x, y + 52), self.font_small, DIM,
        )
        spend = min(self.rd_spend, me.budget)
        self._draw_text(
            f"R&D target: {self.rd_rocket.value}   spend: {spend} MB",
            (x, y + 78), self.font, FG,
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
            self._draw_text(
                f"Launching: {m.name}  cost {eff_cost} MB, {int(effective * 100)}%",
                (x, y + 104), self.font, GREEN,
            )
            if crew_note:
                self._draw_text(crew_note, (x, y + 126), self.font_small, FG)
        else:
            self._draw_text("No launch queued this turn.", (x, y + 104), self.font, DIM)

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
        pygame.draw.rect(self.screen, PANEL, (x - 8, y - 6, 570, 165), border_radius=6)
        self._draw_text("LOG:", (x, y), self.font_small, DIM)
        ly = y + 20
        for line in self.state.log[-7:]:
            self._draw_text(line, (x, ly), self.font_small, FG)
            ly += 18

    def _draw_text(self, text: str, pos: tuple[int, int], font, color) -> None:
        surf = font.render(text, True, color)
        self.screen.blit(surf, pos)

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
