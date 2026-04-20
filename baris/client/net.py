from __future__ import annotations

import asyncio
import logging
import queue
import threading
from typing import Any

import websockets

from baris import protocol

log = logging.getLogger("baris.client.net")


class NetClient:
    """Websocket client that runs in a background thread.

    Pygame's main loop is synchronous, so we bridge via two queues:
    - outbound: messages the game loop wants to send
    - inbound: messages received from the server, drained each frame
    """

    def __init__(self, server_url: str) -> None:
        self.server_url = server_url
        self.outbound: queue.Queue[str] = queue.Queue()
        self.inbound: queue.Queue[dict[str, Any]] = queue.Queue()
        self.connected = threading.Event()
        self.closed = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws: object | None = None

    def start(self) -> None:
        self._thread.start()

    def send(self, msg_type: str, **fields: Any) -> None:
        self.outbound.put(protocol.encode(msg_type, **fields))

    def drain_inbound(self) -> list[dict[str, Any]]:
        msgs: list[dict[str, Any]] = []
        while True:
            try:
                msgs.append(self.inbound.get_nowait())
            except queue.Empty:
                break
        return msgs

    def _run(self) -> None:
        try:
            asyncio.run(self._main())
        except Exception as e:
            log.error("Net thread crashed: %s", e)
            self.inbound.put({"type": protocol.ERROR, "message": f"connection failed: {e}"})
        finally:
            self.closed.set()

    async def _main(self) -> None:
        async with websockets.connect(self.server_url) as ws:
            self._ws = ws
            self.connected.set()
            log.info("Connected to %s", self.server_url)
            sender = asyncio.create_task(self._sender(ws))
            receiver = asyncio.create_task(self._receiver(ws))
            done, pending = await asyncio.wait(
                {sender, receiver}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()

    async def _sender(self, ws: object) -> None:
        loop = asyncio.get_running_loop()
        while True:
            msg = await loop.run_in_executor(None, self.outbound.get)
            await ws.send(msg)

    async def _receiver(self, ws: object) -> None:
        async for raw in ws:
            try:
                self.inbound.put(protocol.decode(raw))
            except ValueError:
                log.warning("ignored malformed server message: %r", raw)
