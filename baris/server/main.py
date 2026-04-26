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
    cancel_training,
    choose_architecture,
    execute_sabotage,
    recruit_next_group,
    request_intel,
    request_stand_test,
    resolve_turn,
    scrub_scheduled,
    start_game,
    start_training,
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
    Skill,
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
    raw_crew = msg.get("crew") or []
    crew = [str(c) for c in raw_crew] if isinstance(raw_crew, list) else []
    submit_turn(
        player,
        rd_rocket=rd_rocket,
        rd_module=rd_module,
        rd_spend=rd_spend,
        launch=launch,
        objectives=objectives,
        crew=crew,
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


async def handle_scrub_scheduled(player: Player, msg: dict[str, Any]) -> None:
    """Cancel a scheduled launch and refund a fraction of the assembly
    cost. With pad_id, targets that specific pad; without, scrubs the
    first pad that has a booking. No-op otherwise."""
    if room.state.phase != Phase.PLAYING:
        return
    pad_id = msg.get("pad_id") or None
    if scrub_scheduled(player, pad_id=pad_id):
        log.info("%s scrubbed scheduled launch on pad %s",
                 player.username, pad_id or "(first)")


async def handle_start_training(player: Player, msg: dict[str, Any]) -> None:
    if room.state.phase != Phase.PLAYING:
        return
    astronaut_id = str(msg.get("astronaut_id") or "")
    try:
        skill = Skill(msg.get("skill"))
    except ValueError:
        return
    if start_training(player, astronaut_id, skill):
        log.info("%s started %s training for %s",
                 player.username, skill.value, astronaut_id)


async def handle_cancel_training(player: Player, msg: dict[str, Any]) -> None:
    if room.state.phase != Phase.PLAYING:
        return
    astronaut_id = str(msg.get("astronaut_id") or "")
    if cancel_training(player, astronaut_id):
        log.info("%s cancelled training for %s", player.username, astronaut_id)


async def handle_recruit_group(player: Player, _msg: dict[str, Any]) -> None:
    if room.state.phase != Phase.PLAYING:
        return
    if recruit_next_group(player, room.state):
        log.info(
            "%s recruited group %d", player.username,
            player.next_recruitment_group - 1,
        )


async def handle_request_intel(player: Player, _msg: dict[str, Any]) -> None:
    if room.state.phase != Phase.PLAYING:
        return
    if request_intel(player, room.state):
        log.info("%s requested intelligence report", player.username)


async def handle_execute_sabotage(player: Player, msg: dict[str, Any]) -> None:
    if room.state.phase != Phase.PLAYING:
        return
    card_id = str(msg.get("card_id") or "")
    if execute_sabotage(player, room.state, card_id):
        log.info("%s fired sabotage card %s", player.username, card_id)


async def handle_request_stand_test(player: Player, msg: dict[str, Any]) -> None:
    if room.state.phase != Phase.PLAYING:
        return
    target_id = str(msg.get("target_id") or "")
    if request_stand_test(player, room.state, target_id):
        log.info("%s ran stand test on %s", player.username, target_id)


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
            elif mtype == protocol.SCRUB_SCHEDULED:
                await handle_scrub_scheduled(player, msg)
            elif mtype == protocol.START_TRAINING:
                await handle_start_training(player, msg)
            elif mtype == protocol.CANCEL_TRAINING:
                await handle_cancel_training(player, msg)
            elif mtype == protocol.RECRUIT_GROUP:
                await handle_recruit_group(player, msg)
            elif mtype == protocol.REQUEST_INTEL:
                await handle_request_intel(player, msg)
            elif mtype == protocol.EXECUTE_SABOTAGE:
                await handle_execute_sabotage(player, msg)
            elif mtype == protocol.REQUEST_STAND_TEST:
                await handle_request_stand_test(player, msg)
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
