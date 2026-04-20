"""End-to-end smoke test: two clients connect over a real websocket server
and drive a full turn. Skipped on CI environments that block sockets."""

from __future__ import annotations

import asyncio
import importlib
import json

import pytest
import websockets


async def _recv_until(ws, mtype: str, timeout: float = 2.0) -> dict:
    async def _inner():
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == mtype:
                return msg

    return await asyncio.wait_for(_inner(), timeout)


async def _drain(ws, count: int, timeout: float = 2.0) -> list[dict]:
    """Collect up to `count` state messages (most recent wins)."""
    msgs: list[dict] = []

    async def _inner():
        async for raw in ws:
            msgs.append(json.loads(raw))
            if len(msgs) >= count:
                return

    try:
        await asyncio.wait_for(_inner(), timeout)
    except asyncio.TimeoutError:
        pass
    return msgs


@pytest.mark.asyncio
async def test_two_clients_play_one_turn() -> None:
    # reset server room state between tests
    server_mod = importlib.reload(importlib.import_module("baris.server.main"))

    async with websockets.serve(server_mod.client_handler, "127.0.0.1", 0) as srv:
        port = srv.sockets[0].getsockname()[1]
        url = f"ws://127.0.0.1:{port}"

        async with websockets.connect(url) as a, websockets.connect(url) as b:
            await a.send(json.dumps({"type": "join", "username": "Alice"}))
            joined_a = await _recv_until(a, "joined")
            await _drain(a, 1)  # discard the broadcast state for b joining

            await b.send(json.dumps({"type": "join", "username": "Bob"}))
            joined_b = await _recv_until(b, "joined")
            assert joined_a["state"]["phase"] == "lobby"
            assert joined_b["state"]["phase"] == "lobby"

            # both ready up
            await a.send(json.dumps({"type": "ready"}))
            await b.send(json.dumps({"type": "ready"}))

            # collect state broadcasts until we see phase=playing
            state_after_start = None
            for _ in range(6):
                raw = await asyncio.wait_for(a.recv(), timeout=2.0)
                msg = json.loads(raw)
                if msg["type"] == "state" and msg["state"]["phase"] == "playing":
                    state_after_start = msg
                    break
            assert state_after_start is not None, "game never transitioned to playing"

            # both submit a turn
            await a.send(json.dumps({"type": "end_turn", "rd_spend": 10, "launch": False}))
            await b.send(json.dumps({"type": "end_turn", "rd_spend": 20, "launch": False}))

            # wait for summer
            for _ in range(6):
                raw = await asyncio.wait_for(a.recv(), timeout=2.0)
                msg = json.loads(raw)
                if msg["type"] == "state" and msg["state"]["season"] == "Summer":
                    # each player should have rd_progress matching their spend
                    players = {p["username"]: p for p in msg["state"]["players"]}
                    assert players["Alice"]["rd_progress"] == 10
                    assert players["Bob"]["rd_progress"] == 20
                    return
            pytest.fail("season never advanced to Summer")
