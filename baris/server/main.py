from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
from typing import Any

import websockets

from baris import protocol
from baris.resolver import (
    all_turns_in,
    can_start,
    choose_architecture,
    resolve_turn,
    start_game,
    submit_turn,
)
from baris.state import (
    Architecture,
    GameState,
    MissionId,
    Module,
    ObjectiveId,
    Phase,
    Player,
    Rocket,
    Side,
)

log = logging.getLogger("baris.server")


class Room:
    """Single-game room. MVP: one room per server process."""

    def __init__(self, debug: bool = False) -> None:
        self.state = GameState()
        self.connections: dict[str, Any] = {}
        self.debug = debug

    def is_full(self) -> bool:
        return len(self.state.players) >= 2

    def add_player(self, username: str, ws: Any) -> Player:
        player_id = uuid.uuid4().hex[:8]
        # auto-assign first player USA, second USSR; players can swap in lobby.
        used_sides = {p.side for p in self.state.players}
        default_side = Side.USA if Side.USA not in used_sides else Side.USSR
        player = Player(player_id=player_id, username=username, side=default_side)
        self.state.players.append(player)
        self.connections[player_id] = ws
        return player

    def remove_player(self, player_id: str) -> None:
        self.state.players = [p for p in self.state.players if p.player_id != player_id]
        self.connections.pop(player_id, None)
        # if someone drops mid-game, end the game.
        if self.state.phase == Phase.PLAYING:
            self.state.phase = Phase.ENDED
            self.state.log.append("Opponent disconnected — game ended.")

    async def broadcast_state(self) -> None:
        msg = protocol.encode(protocol.STATE, state=self.state.to_dict())
        stale: list[str] = []
        for pid, ws in self.connections.items():
            try:
                await ws.send(msg)
            except websockets.ConnectionClosed:
                stale.append(pid)
        for pid in stale:
            self.remove_player(pid)


room = Room()


async def handle_join(ws: Any, msg: dict[str, Any]) -> Player | None:
    if room.is_full():
        await ws.send(protocol.encode(protocol.ERROR, message="Room is full"))
        return None
    if room.state.phase != Phase.LOBBY:
        await ws.send(protocol.encode(protocol.ERROR, message="Game already in progress"))
        return None
    username = str(msg.get("username", "player")).strip()[:24] or "player"
    player = room.add_player(username, ws)
    await ws.send(
        protocol.encode(
            protocol.JOINED,
            player_id=player.player_id,
            state=room.state.to_dict(),
        )
    )
    await room.broadcast_state()
    log.info("%s joined as %s (%s)", username, player.side and player.side.value, player.player_id)
    return player


async def handle_choose_side(player: Player, msg: dict[str, Any]) -> None:
    if room.state.phase != Phase.LOBBY:
        return
    try:
        side = Side(msg.get("side"))
    except ValueError:
        return
    other = room.state.other_player(player.player_id)
    if other and other.side == side:
        # swap sides
        other.side = player.side
    player.side = side
    # reset ready flags when sides change
    for p in room.state.players:
        p.ready = False


async def handle_ready(player: Player, ready: bool) -> None:
    if room.state.phase != Phase.LOBBY:
        return
    player.ready = ready
    log.info(
        "%s [%s] set ready=%s (%s/%s ready on opposing sides)",
        player.username,
        player.side.value if player.side else "?",
        ready,
        sum(1 for p in room.state.players if p.ready),
        len(room.state.players),
    )
    if can_start(room.state):
        log.info("All players ready — starting game.")
        start_game(room.state, debug=room.debug)


async def handle_end_turn(player: Player, msg: dict[str, Any]) -> None:
    if room.state.phase != Phase.PLAYING or player.turn_submitted:
        return
    rd_spend = int(msg.get("rd_spend", 0))
    rd_rocket: Rocket | None = None
    raw_rocket = msg.get("rd_rocket")
    if raw_rocket:
        try:
            rd_rocket = Rocket(raw_rocket)
        except ValueError:
            rd_rocket = None
    rd_module: Module | None = None
    raw_module = msg.get("rd_module")
    if raw_module:
        try:
            rd_module = Module(raw_module)
        except ValueError:
            rd_module = None
    launch: MissionId | None = None
    raw_launch = msg.get("launch")
    if raw_launch:
        try:
            launch = MissionId(raw_launch)
        except ValueError:
            launch = None
    objectives: list[ObjectiveId] = []
    for raw_obj in msg.get("objectives") or ():
        try:
            objectives.append(ObjectiveId(raw_obj))
        except ValueError:
            continue
    submit_turn(
        player,
        rd_rocket=rd_rocket,
        rd_module=rd_module,
        rd_spend=rd_spend,
        launch=launch,
        objectives=objectives,
    )
    if all_turns_in(room.state):
        resolve_turn(room.state)


async def handle_choose_architecture(player: Player, msg: dict[str, Any]) -> None:
    if room.state.phase != Phase.PLAYING:
        return
    raw = msg.get("architecture")
    try:
        arch = Architecture(raw)
    except ValueError:
        return
    choose_architecture(player, arch)


async def client_handler(ws: Any) -> None:
    player: Player | None = None
    try:
        async for raw in ws:
            try:
                msg = protocol.decode(raw)
            except ValueError as e:
                await ws.send(protocol.encode(protocol.ERROR, message=str(e)))
                continue

            mtype = msg["type"]
            if player is None:
                if mtype != protocol.JOIN:
                    await ws.send(protocol.encode(protocol.ERROR, message="Must join first"))
                    continue
                player = await handle_join(ws, msg)
                if player is None:
                    await ws.close()
                    return
                continue

            if mtype == protocol.CHOOSE_SIDE:
                await handle_choose_side(player, msg)
            elif mtype == protocol.READY:
                await handle_ready(player, True)
            elif mtype == protocol.UNREADY:
                await handle_ready(player, False)
            elif mtype == protocol.END_TURN:
                await handle_end_turn(player, msg)
            elif mtype == protocol.CHOOSE_ARCHITECTURE:
                await handle_choose_architecture(player, msg)
            else:
                await ws.send(protocol.encode(protocol.ERROR, message=f"Unknown type {mtype}"))
                continue

            await room.broadcast_state()
    except websockets.ConnectionClosed:
        pass
    finally:
        if player is not None:
            room.remove_player(player.player_id)
            await room.broadcast_state()


async def serve(host: str, port: int) -> None:
    log.info("BARIS server listening on ws://%s:%d", host, port)
    async with websockets.serve(client_handler, host, port):
        await asyncio.Future()  # run forever


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--debug", action="store_true",
                        help="Preseed both players with fat budget, built rockets, "
                             "and Apollo/Soyuz unlocked when the game starts.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    global room
    room = Room(debug=args.debug)
    if args.debug:
        log.warning("DEBUG MODE: players will be preseeded at game start.")
    asyncio.run(serve(args.host, args.port))


if __name__ == "__main__":
    main()
