"""Public OKX WebSocket feed with sharded subscriptions and reconnect."""

from __future__ import annotations

import asyncio
import inspect
import json
import random
from collections.abc import Awaitable, Callable
from typing import Any


OKX_PUBLIC_WS = "wss://ws.okx.com:8443/ws/v5/public"
EventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


class OKXPublicFeed:
    def __init__(
        self,
        symbols: list[str],
        handler: EventHandler,
        url: str = OKX_PUBLIC_WS,
        reconnect_min: float = 1.0,
        reconnect_max: float = 30.0,
        instruments_per_connection: int = 30,
        connection_start_delay: float = 0.4,
    ):
        if not symbols:
            raise ValueError("At least one OKX instrument ID is required.")
        if reconnect_min <= 0 or reconnect_max < reconnect_min:
            raise ValueError("Invalid reconnect backoff.")
        if instruments_per_connection < 1:
            raise ValueError("instruments_per_connection must be positive.")
        self.symbols = tuple(dict.fromkeys(symbols))
        self.handler = handler
        self.url = url
        self.reconnect_min = reconnect_min
        self.reconnect_max = reconnect_max
        self.instruments_per_connection = instruments_per_connection
        self.connection_start_delay = max(0.0, connection_start_delay)

    @staticmethod
    def _subscriptions(symbols: tuple[str, ...]) -> dict[str, Any]:
        args = []
        for symbol in symbols:
            for channel in ("books5", "trades", "tickers"):
                args.append({"channel": channel, "instId": symbol})
        return {"op": "subscribe", "args": args}

    async def _run_connection(
        self,
        symbols: tuple[str, ...],
        stop_event: asyncio.Event,
        startup_delay: float,
    ) -> None:
        if startup_delay:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=startup_delay)
                return
            except asyncio.TimeoutError:
                pass

        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError(
                "WebSocket dependency is missing; install the project dependencies."
            ) from exc

        delay = self.reconnect_min
        while not stop_event.is_set():
            try:
                async with websockets.connect(
                    self.url,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                    max_size=2**20,
                ) as socket:
                    await socket.send(json.dumps(self._subscriptions(symbols)))
                    delay = self.reconnect_min
                    while not stop_event.is_set():
                        try:
                            raw = await asyncio.wait_for(socket.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue
                        if raw == "ping":
                            await socket.send("pong")
                            continue
                        message = json.loads(raw)
                        if not isinstance(message, dict):
                            continue
                        if message.get("event") in {"subscribe", "unsubscribe", "error"}:
                            if message.get("event") == "error":
                                raise RuntimeError(f"OKX subscription error: {message}")
                            continue
                        result = self.handler(message)
                        if inspect.isawaitable(result):
                            await result
            except asyncio.CancelledError:
                raise
            except Exception:
                if stop_event.is_set():
                    break
                jitter = random.uniform(0.0, delay * 0.2)
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=delay + jitter)
                except asyncio.TimeoutError:
                    pass
                delay = min(self.reconnect_max, delay * 2)

    async def run(self, stop_event: asyncio.Event) -> None:
        """Run sharded public feeds; each connection subscribes to at most 30 instruments."""
        chunks = [
            self.symbols[index:index + self.instruments_per_connection]
            for index in range(0, len(self.symbols), self.instruments_per_connection)
        ]
        tasks = [
            asyncio.create_task(
                self._run_connection(
                    chunk,
                    stop_event,
                    startup_delay=index * self.connection_start_delay,
                )
            )
            for index, chunk in enumerate(chunks)
        ]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
