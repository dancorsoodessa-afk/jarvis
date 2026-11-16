"""Public whale intelligence adapters for Hyperliquid and CoinLobster.

No exchange credentials are used. Public endpoints are rate-limited and their
availability/refresh cadence is controlled by the providers.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from datetime import datetime, timedelta, timezone
import os
import time

import requests


HYPERLIQUID_LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"
COINLOBSTER_PUBLIC_URL = "https://coinlobster.com/api/public"


def _rows(payload: Any) -> list[dict[str, Any]]:
    """Accept the common list/envelope shapes used by public analytics APIs."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "rows", "items", "results", "trades", "accounts", "leaderboardRows"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _rows(value)
            if nested:
                return nested
    return []


def _number(value: Any) -> Decimal:
    try:
        result = Decimal(str(value if value is not None else "0"))
        return result if result.is_finite() else Decimal("0")
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


@dataclass(frozen=True)
class WhaleAccount:
    rank: int
    address: str
    name: str
    pnl_usd: Decimal
    roi: Decimal
    volume_usd: Decimal
    equity_usd: Decimal
    window: str = "month"


@dataclass(frozen=True)
class WhaleTrade:
    timestamp: str
    address: str
    coin: str
    side: str
    price: Decimal
    size_usd: Decimal
    venue: str
    raw: dict[str, Any]


class WhaleIntelClient:
    """Read-only whale data client. It has no exchange order methods."""

    def __init__(self, timeout: float = 12.0, session: requests.Session | None = None, nansen_api_key: str | None = None):
        self.timeout = max(3.0, min(30.0, float(timeout)))
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "JARVIS-BOTok/1.0"})
        self.nansen_api_key = (nansen_api_key if nansen_api_key is not None else os.getenv("NANSEN_API_KEY", "")).strip()
        self.poll_interval_seconds = 300.0 if self.nansen_api_key else 60.0
        self._leaderboard_cache_at = 0.0
        self._leaderboard_cache: list[WhaleAccount] = []

    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def fetch_top_hyperliquid_accounts(
        self, limit: int = 200, window: str = "month"
    ) -> list[WhaleAccount]:
        """Rank public Hyperliquid leaderboard accounts by PnL.

        Hyperliquid publishes fixed windows: day, week, month and allTime.
        This is a ranking of Hyperliquid accounts, not all crypto whales.
        """
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        if window not in {"day", "week", "month", "allTime"}:
            raise ValueError("unsupported Hyperliquid leaderboard window")
        now = time.monotonic()
        if self._leaderboard_cache and now - self._leaderboard_cache_at < 900:
            return self._leaderboard_cache[:limit]
        payload = self._get_json(HYPERLIQUID_LEADERBOARD_URL)
        source_rows = _rows(payload)
        ranked: list[WhaleAccount] = []
        for row in source_rows:
            address = str(row.get("ethAddress") or row.get("address") or "").strip()
            if not address:
                continue
            performances = row.get("windowPerformances") or {}
            metrics: Any = performances.get(window, {}) if isinstance(performances, dict) else {}
            if isinstance(performances, (list, tuple)):
                metrics = next((entry[1] for entry in performances if isinstance(entry, (list, tuple)) and len(entry) > 1 and entry[0] == window), {})
            if not isinstance(metrics, dict):
                metrics = {}
            ranked.append(WhaleAccount(
                rank=0,
                address=address,
                name=str(row.get("displayName") or row.get("name") or ""),
                pnl_usd=_number(metrics.get("pnl")),
                roi=_number(metrics.get("roi")),
                volume_usd=_number(metrics.get("vlm") or metrics.get("volume")),
                equity_usd=_number(row.get("accountValue") or row.get("equity")),
                window=window,
            ))
        ranked.sort(key=lambda item: item.pnl_usd, reverse=True)
        self._leaderboard_cache = [
            WhaleAccount(
                rank=index + 1, address=item.address, name=item.name,
                pnl_usd=item.pnl_usd, roi=item.roi, volume_usd=item.volume_usd,
                equity_usd=item.equity_usd, window=item.window,
            )
            for index, item in enumerate(ranked)
        ]
        self._leaderboard_cache_at = now
        return self._leaderboard_cache[:limit]

    def fetch_hyperliquid_whale_trades(self, limit: int = 200) -> list[WhaleTrade]:
        """Get wallet-attributed Hyperliquid whale fills from CoinLobster."""
        payload = self._get_json(
            f"{COINLOBSTER_PUBLIC_URL}/hyperliquid/whales",
            params={"limit": max(1, min(200, int(limit)))},
        )
        return self._normalize_trades(_rows(payload), venue="Hyperliquid")

    def fetch_exchange_whale_trades(self, limit: int = 100) -> list[WhaleTrade]:
        """Get the provider's public cross-exchange whale tape."""
        payload = self._get_json(
            f"{COINLOBSTER_PUBLIC_URL}/crypto-whales",
            params={"limit": max(1, min(200, int(limit)))},
        )
        return self._normalize_trades(_rows(payload), venue="multi-exchange")

    @staticmethod
    def _normalize_trades(rows: list[dict[str, Any]], venue: str) -> list[WhaleTrade]:
        result = []
        for row in rows:
            address = str(
                row.get("wallet") or row.get("address") or row.get("user")
                or row.get("account") or row.get("trader_address") or ""
            )
            coin = str(row.get("coin") or row.get("symbol") or row.get("token") or row.get("token_symbol") or "—")
            side = str(row.get("side") or row.get("direction") or "—").upper()
            timestamp = str(
                row.get("timestamp") or row.get("time") or row.get("ts")
                or row.get("created_at") or row.get("block_timestamp") or "—"
            )
            price = _number(row.get("price") or row.get("px") or row.get("price_usd"))
            size = _number(
                row.get("size_usd") or row.get("notional_usd")
                or row.get("usd_value") or row.get("value_usd")
            )
            if size == 0:
                size = _number(row.get("size") or row.get("sz")) * price
            result.append(WhaleTrade(
                timestamp=timestamp, address=address, coin=coin, side=side,
                price=price, size_usd=size,
                venue=str(row.get("venue") or row.get("exchange") or venue),
                raw=dict(row),
            ))
        return result

    def _post_nansen(self, endpoint: str, payload: dict[str, Any]) -> Any:
        if not self.nansen_api_key:
            raise RuntimeError("NANSEN_API_KEY is not configured")
        response = self.session.post(
            f"https://api.nansen.ai{endpoint}",
            json=payload,
            headers={"apikey": self.nansen_api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def fetch_nansen_top_traders(self, limit: int = 200) -> list[WhaleAccount]:
        """Fetch the top Hyperliquid perp traders for the trailing 30-day window."""
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=30)
        payload = self._post_nansen("/api/v1/perp-leaderboard", {
            "date": {"from": start.isoformat(), "to": end.isoformat()},
            "pagination": {"page": 1, "per_page": limit},
            "order_by": [{"field": "total_pnl", "direction": "DESC"}],
        })
        rows = _rows(payload)
        accounts = []
        for row in rows:
            address = str(row.get("trader_address") or row.get("address") or "")
            if not address:
                continue
            accounts.append(WhaleAccount(
                rank=len(accounts) + 1,
                address=address,
                name=str(row.get("trader_address_label") or ""),
                pnl_usd=_number(row.get("total_pnl")),
                roi=_number(row.get("roi")),
                volume_usd=_number(row.get("volume_usd")),
                equity_usd=_number(row.get("account_value")),
                window="30d",
            ))
        return accounts[:limit]

    def fetch_nansen_smart_money_trades(self, limit: int = 200) -> list[WhaleTrade]:
        """Fetch the latest Smart HL Perps Trader fills (seven-day maximum window)."""
        payload = self._post_nansen("/api/v1/smart-money/perp-trades", {
            "lookback_hours": 24,
            "pagination": {"page": 1, "per_page": max(1, min(1000, int(limit)))},
            "order_by": [{"field": "block_timestamp", "direction": "DESC"}],
        })
        return self._normalize_trades(_rows(payload), venue="Nansen Smart Money / Hyperliquid")

    def fetch_snapshot(self, account_limit: int = 200) -> dict[str, Any]:
        """Return independent source results so one provider outage is non-fatal."""
        if self.nansen_api_key:
            snapshot: dict[str, Any] = {
                "accounts": [], "hyperliquid_trades": [], "exchange_trades": [],
                "errors": [], "source": "Nansen Hyperliquid leaderboard + Smart Money trades",
            }
            operations = (
                ("accounts", lambda: self.fetch_nansen_top_traders(account_limit)),
                ("hyperliquid_trades", lambda: self.fetch_nansen_smart_money_trades(200)),
            )
        else:
            snapshot = {
                "accounts": [], "hyperliquid_trades": [], "exchange_trades": [],
                "errors": [], "source": "Hyperliquid public leaderboard + CoinLobster public API",
            }
            operations = (
                ("accounts", lambda: self.fetch_top_hyperliquid_accounts(account_limit)),
                ("hyperliquid_trades", lambda: self.fetch_hyperliquid_whale_trades(200)),
                ("exchange_trades", lambda: self.fetch_exchange_whale_trades(100)),
            )
        for key, operation in operations:
            try:
                snapshot[key] = operation()
            except Exception as exc:
                snapshot["errors"].append(f"{key}: {type(exc).__name__}: {exc}")
        # If the optional paid provider is unavailable or out of credits, retain
        # the no-key public fallback rather than leaving the whole panel empty.
        if self.nansen_api_key and (
            not snapshot["accounts"] or not snapshot["hyperliquid_trades"]
        ):
            fallback = (
                ("accounts", lambda: self.fetch_top_hyperliquid_accounts(account_limit)),
                ("hyperliquid_trades", lambda: self.fetch_hyperliquid_whale_trades(200)),
                ("exchange_trades", lambda: self.fetch_exchange_whale_trades(100)),
            )
            for key, operation in fallback:
                if snapshot.get(key):
                    continue
                try:
                    snapshot[key] = operation()
                except Exception as exc:
                    snapshot["errors"].append(f"public_{key}: {type(exc).__name__}: {exc}")
            snapshot["source"] += " · public fallback where Nansen was unavailable"
        return snapshot

    def fetch_account_state(self, address: str) -> dict[str, Any]:
        """Read current Hyperliquid positions for one public account."""
        if not address.startswith("0x") or len(address) != 42:
            raise ValueError("invalid Hyperliquid account address")
        response = self.session.post(
            HYPERLIQUID_INFO_URL,
            json={"type": "clearinghouseState", "user": address},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def fetch_account_fills(self, address: str) -> list[dict[str, Any]]:
        """Read recent public fills for one account; callers must throttle requests."""
        if not address.startswith("0x") or len(address) != 42:
            raise ValueError("invalid Hyperliquid account address")
        response = self.session.post(
            HYPERLIQUID_INFO_URL,
            json={"type": "userFills", "user": address},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return _rows(response.json())
