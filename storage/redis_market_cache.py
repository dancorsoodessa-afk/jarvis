"""Redis cache and append-only event streams for OKX market data."""

from __future__ import annotations

import json
from typing import Any

from crypto_analyst.models import OrderBookSnapshot


class RedisMarketCache:
    def __init__(self, url: str, client: Any | None = None,
                 book_ttl_seconds: int = 10, stream_maxlen: int = 100_000):
        if not url and client is None:
            raise ValueError("Redis URL is required.")
        if book_ttl_seconds < 1 or stream_maxlen < 1:
            raise ValueError("Redis TTL and stream length must be positive.")
        self.url = url
        self.client = client
        self.book_ttl_seconds = book_ttl_seconds
        self.stream_maxlen = stream_maxlen

    async def connect(self) -> None:
        if self.client is None:
            try:
                from redis.asyncio import Redis
            except ImportError as exc:
                raise RuntimeError("Install redis to enable Redis market caching.") from exc
            self.client = Redis.from_url(self.url, decode_responses=True)
        await self.client.ping()

    async def cache_orderbook(self, book: OrderBookSnapshot) -> None:
        if self.client is None:
            raise RuntimeError("RedisMarketCache is not connected.")
        payload = {
            "symbol": book.symbol,
            "timestamp_ms": book.timestamp_ms,
            "received_at_ms": book.received_at_ms,
            "bids": [[str(level.price), str(level.amount)] for level in book.bids],
            "asks": [[str(level.price), str(level.amount)] for level in book.asks],
        }
        await self.client.set(
            f"jarvis:crypto:book:{book.symbol}",
            json.dumps(payload, separators=(",", ":")),
            ex=self.book_ttl_seconds,
        )

    async def append_event(self, message: dict[str, Any], received_at_ms: int) -> None:
        if self.client is None:
            raise RuntimeError("RedisMarketCache is not connected.")
        arg = message.get("arg") or {}
        await self.client.xadd(
            "jarvis:crypto:market-events",
            {
                "received_at_ms": str(received_at_ms),
                "channel": str(arg.get("channel") or "unknown"),
                "symbol": str(arg.get("instId") or "global"),
                "payload": json.dumps(message, separators=(",", ":")),
            },
            maxlen=self.stream_maxlen,
            approximate=True,
        )

    async def read_events(self, start: str = "-", end: str = "+",
                          count: int = 10_000) -> list[dict[str, Any]]:
        if self.client is None:
            raise RuntimeError("RedisMarketCache is not connected.")
        if count < 1:
            raise ValueError("count must be positive.")
        rows = await self.client.xrange(
            "jarvis:crypto:market-events", min=start, max=end, count=count
        )
        result = []
        for _stream_id, fields in rows:
            try:
                result.append({
                    "received_at_ms": int(fields["received_at_ms"]),
                    "message": json.loads(fields["payload"]),
                })
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return result

    async def close(self) -> None:
        if self.client is not None:
            close = getattr(self.client, "aclose", None) or getattr(self.client, "close", None)
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result
            self.client = None
