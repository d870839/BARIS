"""End-to-end smoke test: two clients connect over a real websocket server
and drive a full turn."""

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


@pytest.mark.asyncio
async def test_two_clients_play_one_turn() -> None:
    # reset server room state between tests
    server_mod = importlib.reload(importlib.import_module("baris.server.main"))

    async with websockets.serve(server_mod.client_handler, "127.0.0.1", 0) as srv:
        port = srv.sockets[0].getsockname()[1]
        url = f"ws://127.0.0.1:{port}"

        async with websockets.connect(url) as a, websockets.connect(url) as b:
            await a.send(json.dumps({"type": "join", "username": "Alice"}))
            await _recv_until(a, "joined")

            await b.send(json.dumps({"type": "join", "username": "Bob"}))
            await _recv_until(b, "joined")

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

            # both submit a turn: Alice spends on Light R&D, Bob on Medium.
            # R&D is stochastic; spend enough MB that a total stall is
            # astronomically unlikely (~10 batches each → 0.5^10 flake).
            await a.send(json.dumps({
                "type": "end_turn",
                "rd_rocket": "Light",
                "rd_spend": 30,
                "launch": None,
            }))
            await b.send(json.dumps({
                "type": "end_turn",
                "rd_rocket": "Medium",
                "rd_spend": 30,
                "launch": None,
            }))

            # wait for summer
            for _ in range(6):
                raw = await asyncio.wait_for(a.recv(), timeout=2.0)
                msg = json.loads(raw)
                if msg["type"] == "state" and msg["state"]["season"] == "Summer":
                    players = {p["username"]: p for p in msg["state"]["players"]}
                    # R&D is stochastic now: assert each player advanced only
                    # their chosen rocket, not both.
                    assert players["Alice"]["reliability"]["Light"] > 0
                    assert players["Alice"]["reliability"]["Medium"] == 0
                    assert players["Bob"]["reliability"]["Medium"] > 0
                    assert players["Bob"]["reliability"]["Light"] == 0
                    return
            pytest.fail("season never advanced to Summer")
