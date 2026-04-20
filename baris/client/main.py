from __future__ import annotations

import argparse
import logging
import sys

import pygame

from baris import protocol
from baris.client.net import NetClient
from baris.state import GameState, Phase, Side

log = logging.getLogger("baris.client")

WINDOW_SIZE = (960, 600)
FPS = 60
BG = (10, 14, 28)
FG = (220, 225, 235)
DIM = (120, 130, 150)
ACCENT_USA = (80, 140, 220)
ACCENT_USSR = (220, 90, 90)
HIGHLIGHT = (240, 200, 90)


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

        self.state: GameState | None = None
        self.player_id: str | None = None
        self.status = f"Connecting to {server_url}..."
        self.joined_sent = False
        self.rd_spend = 10
        self.launch_queued = False

    # ------------------------------------------------------------------
    # Network handling
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
                self.state = GameState.from_dict(msg["state"])
                self.status = f"Joined as {self._me().side.value if self._me() and self._me().side else '?'}"
            elif mtype == protocol.STATE:
                self.state = GameState.from_dict(msg["state"])
            elif mtype == protocol.ERROR:
                self.status = f"Error: {msg.get('message', '?')}"

    def _me(self):
        if self.state is None or self.player_id is None:
            return None
        return self.state.find_player(self.player_id)

    def _opponent(self):
        if self.state is None or self.player_id is None:
            return None
        return self.state.other_player(self.player_id)

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN and self.state is not None:
            me = self._me()
            if me is None:
                return True
            if self.state.phase == Phase.LOBBY:
                if event.key == pygame.K_1:
                    self.net.send(protocol.CHOOSE_SIDE, side=Side.USA.value)
                elif event.key == pygame.K_2:
                    self.net.send(protocol.CHOOSE_SIDE, side=Side.USSR.value)
                elif event.key == pygame.K_RETURN:
                    self.net.send(protocol.READY if not me.ready else protocol.UNREADY)
            elif self.state.phase == Phase.PLAYING and not me.turn_submitted:
                if event.key == pygame.K_LEFT:
                    self.rd_spend = max(0, self.rd_spend - 5)
                elif event.key == pygame.K_RIGHT:
                    self.rd_spend = min(me.budget, self.rd_spend + 5)
                elif event.key == pygame.K_l:
                    self.launch_queued = not self.launch_queued
                elif event.key == pygame.K_RETURN:
                    self.net.send(
                        protocol.END_TURN,
                        rd_spend=min(self.rd_spend, me.budget),
                        launch=self.launch_queued,
                    )
                    self.launch_queued = False
        return True

    # ------------------------------------------------------------------
    # Rendering
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
            (30, 70),
            self.font_small,
            DIM,
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
            (30, 30),
            self.font_big,
            HIGHLIGHT,
        )
        if me:
            self._draw_player_panel("YOU", me, (30, 90))
        if opp:
            self._draw_player_panel("OPPONENT", opp, (500, 90))

        if me and not me.turn_submitted:
            self._draw_text("YOUR TURN", (30, 340), self.font_big, HIGHLIGHT)
            self._draw_text(
                f"R&D spend (Left/Right to adjust by 5): {min(self.rd_spend, me.budget)} MB",
                (30, 380),
                self.font,
                FG,
            )
            launch_label = "queued" if self.launch_queued else "not queued"
            ready_to_launch = "yes" if me.rocket_built else "rocket not built yet"
            self._draw_text(
                f"L = toggle sub-orbital launch ({launch_label}, {ready_to_launch})",
                (30, 408),
                self.font,
                FG,
            )
            self._draw_text("Enter = end turn", (30, 436), self.font, FG)
        elif me and me.turn_submitted:
            self._draw_text("Waiting for opponent...", (30, 340), self.font, DIM)

        y = 480
        self._draw_text("Log:", (30, y), self.font_small, DIM)
        for line in self.state.log[-4:]:
            y += 18
            self._draw_text(line, (30, y), self.font_small, FG)

    def _render_end(self) -> None:
        assert self.state is not None
        msg = "GAME OVER"
        if self.state.winner is not None:
            msg = f"{self.state.winner.value} WINS THE RACE"
        self._draw_text(msg, (30, 30), self.font_big, HIGHLIGHT)
        y = 90
        for line in self.state.log[-8:]:
            self._draw_text(line, (30, y), self.font, FG)
            y += 22

    def _draw_player_panel(self, label: str, player, pos: tuple[int, int]) -> None:
        x, y = pos
        color = side_color(player.side)
        self._draw_text(f"{label}: {player.username}", (x, y), self.font, color)
        self._draw_text(
            f"Side:      {player.side.value if player.side else '?'}",
            (x, y + 30),
            self.font,
            FG,
        )
        self._draw_text(f"Budget:    {player.budget} MB", (x, y + 54), self.font, FG)
        self._draw_text(f"Prestige:  {player.prestige}", (x, y + 78), self.font, FG)
        rd_label = "ROCKET BUILT" if player.rocket_built else f"R&D: {player.rd_progress}%"
        self._draw_text(rd_label, (x, y + 102), self.font, FG)
        self._draw_text(
            f"Turn:      {'submitted' if player.turn_submitted else 'pending'}",
            (x, y + 126),
            self.font_small,
            DIM,
        )

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
