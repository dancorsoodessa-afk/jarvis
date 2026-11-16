"""Public whale intelligence adapters for Hyperliquid and CoinLobster.

No exchange credentials are used. Public endpoints are rate-limited and their
availability/refresh cadence is controlled by the providers.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

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

    def __init__(self, timeout: float = 12.0, session: requests.Session | None = None):
        self.timeout = max(3.0, min(30.0, float(timeout)))
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "JARVIS-BOTok/1.0"})

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
        payload = self._get_json(HYPERLIQUID_LEADERBOARD_URL)
        source_rows = _rows(payload)
        ranked: list[WhaleAccount] = []
        for row in source_rows:
            address = str(row.get("ethAddress") or row.get("address") or "").strip()
            if not address:
                continue
            performances = row.get("windowPerformances") or {}
            metrics: Any = performances.get(window, {}) if isinstance(performances, dict) else {}
            if isinstance(metrics, (list, tuple)) and len(metrics) > 1:
                metrics = metrics[1]
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
        return [
            WhaleAccount(
                rank=index + 1, address=item.address, name=item.name,
                pnl_usd=item.pnl_usd, roi=item.roi, volume_usd=item.volume_usd,
                equity_usd=item.equity_usd, window=item.window,
            )
            for index, item in enumerate(ranked[:limit])
        ]

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
                or row.get("account") or ""
            )
            coin = str(row.get("coin") or row.get("symbol") or row.get("token") or "—")
            side = str(row.get("side") or row.get("direction") or "—").upper()
            timestamp = str(
                row.get("timestamp") or row.get("time") or row.get("ts")
                or row.get("created_at") or "—"
            )
            price = _number(row.get("price") or row.get("px"))
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

    def fetch_snapshot(self, account_limit: int = 200) -> dict[str, Any]:
        """Return independent source results so one provider outage is non-fatal."""
        snapshot: dict[str, Any] = {
            "accounts": [], "hyperliquid_trades": [], "exchange_trades": [],
            "errors": [], "source": "Hyperliquid public leaderboard + CoinLobster public API",
        }
        for key, operation in (
            ("accounts", lambda: self.fetch_top_hyperliquid_accounts(account_limit)),
            ("hyperliquid_trades", lambda: self.fetch_hyperliquid_whale_trades(200)),
            ("exchange_trades", lambda: self.fetch_exchange_whale_trades(100)),
        ):
            try:
                snapshot[key] = operation()
            except Exception as exc:
                snapshot["errors"].append(f"{key}: {type(exc).__name__}: {exc}")
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
