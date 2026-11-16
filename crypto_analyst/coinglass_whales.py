"""CoinGlass Hyperliquid whale-position snapshot adapter.

This is a read-only market-data client. It cannot place orders or sign wallets.
"""
from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import requests


COINGLASS_WHALE_POSITIONS_URL = (
    "https://open-api-v4.coinglass.com/api/hyperliquid/whale-position"
)


@dataclass(frozen=True)
class WhaleAccountSnapshot:
    address: str
    position_count: int
    gross_position_usd: float
    unrealized_pnl_usd: float
    symbols: tuple[str, ...]
    updated_at_ms: int


class CoinGlassWhaleClient:
    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str = COINGLASS_WHALE_POSITIONS_URL,
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ):
        self.api_key = (api_key or os.getenv("COINGLASS_API_KEY", "")).strip()
        self.endpoint = endpoint
        self.timeout = timeout
        self.session = session or requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def fetch_positions(self) -> list[dict[str, Any]]:
        if not self.configured:
            raise RuntimeError("COINGLASS_API_KEY is not configured.")
        response = self.session.get(
            self.endpoint,
            headers={"CG-API-KEY": self.api_key, "Accept": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if str(payload.get("code")) != "0":
            raise RuntimeError(f"CoinGlass API error: {payload.get('msg') or payload.get('code')}")
        data = payload.get("data") or []
        if not isinstance(data, list):
            raise RuntimeError("CoinGlass whale-position response has an invalid data field.")
        return [row for row in data if isinstance(row, dict)]

    def top_wallets(self, limit: int = 200) -> list[WhaleAccountSnapshot]:
        if limit < 1:
            raise ValueError("limit must be positive")
        grouped: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"notional": 0.0, "pnl": 0.0, "symbols": set(), "updated": 0, "count": 0}
        )
        for row in self.fetch_positions():
            address = str(row.get("user") or "").strip()
            if not address:
                continue
            item = grouped[address]
            item["notional"] += abs(_number(row.get("position_value_usd")))
            item["pnl"] += _number(row.get("unrealized_pnl"))
            symbol = str(row.get("symbol") or "").strip()
            if symbol:
                item["symbols"].add(symbol)
            item["updated"] = max(item["updated"], int(_number(row.get("update_time"))))
            item["count"] += 1
        wallets = [
            WhaleAccountSnapshot(
                address=address,
                position_count=item["count"],
                gross_position_usd=item["notional"],
                unrealized_pnl_usd=item["pnl"],
                symbols=tuple(sorted(item["symbols"])),
                updated_at_ms=item["updated"],
            )
            for address, item in grouped.items()
        ]
        wallets.sort(key=lambda wallet: wallet.gross_position_usd, reverse=True)
        return wallets[:limit]


def _number(value: Any) -> float:
    try:
        result = float(value or 0)
        return result if result == result and abs(result) != float("inf") else 0.0
    except (TypeError, ValueError):
        return 0.0
